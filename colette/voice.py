"""Bot vocal Colette (Pipecat 1.15) : micro/HP du laptop ⇄ Gladia FR ⇄ OpenRouter ⇄ Cartesia FR.

Pipeline :
    micro → MicGate → Gladia (solaria-1, fr) → VoiceGate → agrégateur user → OpenRouter
          → Cartesia (fr) → haut-parleurs → StateTap → agrégateur assistant

- MicGate : envoie du silence à la place du micro quand la bulle est fermée, et pendant que
  Colette parle (anti-écho : LocalAudioTransport n'a pas d'AEC). `COLETTE_BARGE_IN=1` (casque)
  laisse le micro ouvert pendant que Colette parle.
- VoiceGate : route chaque transcription finale AVANT le LLM (colette/intents.py) :
  carte OUI/NON affichée → oui / non (sinon « Dites simplement oui ou non. ») ;
  démarche en cours → stop / pause / reprise, par le même chemin que les boutons de la bulle ;
  question H en attente (`ask_user`) → la réponse résout la question (bruit et « euh » ignorés,
  une relance). Une commande reconnue n'atteint jamais le LLM.
- Confirmation garantie par le code : H s'arrête au récapitulatif (ligne `CONFIRMATION: …`),
  Colette pose la question, et seul un « oui » (voix ou bouton) déclenche `runner.follow_up()`.
- StateTap : statut parle/écoute et sous-titres (mots Cartesia) poussés dans la bulle.
- Tool async `run_demarche(objectif)` : lance le DemarcheRunner (vrai H ou faux), narre les étapes
  directement en TTSSpeakFrame (pas via le LLM : Holo met 3–6 s par action), puis rend le résultat
  au LLM qui résume.
- Si l'agent H échoue (exception ou session `failed`/`timed_out`) : guide manuel pas à pas
  (colette/guide.py) — la bulle entoure le bouton à cliquer, une petite fenêtre et la voix
  expliquent l'étape ; la personne clique elle-même, Colette passe à la suite toute seule.

Tout l'audio reste côté Python : Chrome bloque toute connexion de free.fr vers localhost.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Optional

from loguru import logger

from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    FunctionCallResultProperties,
    BotStoppedSpeakingFrame,
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    LLMMessagesAppendFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
    TTSTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.gladia.config import LanguageConfig
from pipecat.services.gladia.stt import GladiaSTTService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openrouter.llm import OpenRouterLLMService
from pipecat.transcriptions.language import Language
from pipecat.turns.user_mute import AlwaysUserMuteStrategy
from pipecat.workers.runner import WorkerRunner

from colette.audio_local import LocalAudioTransport, LocalAudioTransportParams
from colette.guide import ManualGuide
from colette.h_agent import Step, split_confirmation
from colette.intents import is_noise, parse_intent
from colette.narration import Narrator
from colette.prompts import CONFIRMED_FOLLOW_UP, GREETING, H_GOAL_TEMPLATE, SYSTEM_PROMPT
from colette.state import StateServer

DEFAULT_LLM_MODEL = "google/gemini-2.5-flash"
NARRATE_MIN_GAP_S = 5.0  # au plus une phrase de narration toutes les 5 s
ECHO_TAIL_S = 0.4  # micro encore coupé juste après que Colette s'est tue
ASK_TIMEOUT_S = 180.0
CONFIRM_TIMEOUT_S = 120.0  # sans réponse → on ne valide pas
REMIND_GAP_S = 4.0  # « Dites simplement oui ou non. » au plus toutes les 4 s

_URL_RE = re.compile(r"https?://\S+")


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "oui")


class MicGate(FrameProcessor):
    """Remplace l'audio micro par du silence quand Colette ne doit pas écouter."""

    def __init__(self, voice: "ColetteVoice") -> None:
        super().__init__(name="MicGate")
        self.voice = voice

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame) and not self.voice.mic_open():
            frame = InputAudioRawFrame(
                audio=bytes(len(frame.audio)), sample_rate=frame.sample_rate, num_channels=frame.num_channels
            )
        await self.push_frame(frame, direction)


class VoiceGate(FrameProcessor):
    """Après le STT : commandes vocales et réponses aux questions H, avant le LLM."""

    def __init__(self, voice: "ColetteVoice") -> None:
        super().__init__(name="VoiceGate")
        self.voice = voice
        self._pending: Optional[asyncio.Future[str]] = None
        self._question = ""
        self._relanced = False
        self._last_remind = 0.0
        self._tasks: set[asyncio.Task] = set()

    @property
    def pending(self) -> bool:
        return self._pending is not None and not self._pending.done()

    def expect_answer(self, question: str = "") -> asyncio.Future[str]:
        self.cancel_pending()
        self._question = question
        self._relanced = False
        self._pending = asyncio.get_running_loop().create_future()
        return self._pending

    def resolve(self, text: str) -> bool:
        fut, self._pending = self._pending, None
        if fut is not None and not fut.done():
            fut.set_result(text)
            return True
        return False

    def cancel_pending(self) -> None:
        fut, self._pending = self._pending, None
        if fut is not None and not fut.done():
            fut.cancel()

    def _capturing(self) -> bool:
        """Vrai quand la voix ne doit pas ouvrir de tour de parole pour le LLM."""
        return self.pending or self.voice.state.confirm_pending

    def _dispatch(self, msg: dict) -> None:
        """Même chemin que les boutons de la bulle (StateServer.handle_message → callbacks)."""
        task = asyncio.create_task(self.voice.state.handle_message({**msg, "source": "voix"}))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _say_later(self, text: str) -> None:
        task = asyncio.create_task(self.voice.say(text))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def context(self) -> str:
        if self.voice.state.confirm_pending:
            return "confirm"
        if self.voice.guiding:
            return "guide"
        if self.voice.working:
            return "paused" if self.voice.paused else "working"
        return "idle"

    def route(self, text: str) -> bool:
        """Traite une transcription finale. Renvoie True si elle ne doit PAS aller au LLM."""
        ctx = self.context()
        intent = parse_intent(text, ctx)
        if ctx == "confirm":
            if intent in ("yes", "no"):
                logger.info("🎯 Intention « {} » → carte de confirmation", intent)
                self._dispatch({"type": "confirm", "value": intent == "yes"})
            elif intent == "stop":
                logger.info("🎯 Intention « stop »")
                self._dispatch({"type": "stop"})
            elif is_noise(text):
                logger.info("🔇 Ignoré (bruit) : {!r}", text)
            elif time.monotonic() - self._last_remind > REMIND_GAP_S:
                self._last_remind = time.monotonic()
                logger.info("🎯 Pas de oui/non clair → rappel")
                self._say_later("Dites simplement oui ou non.")
            return True
        if ctx == "guide" and intent in ("stop", "next"):
            logger.info("🎯 Intention « {} » (guide)", intent)
            if intent == "stop":
                self._dispatch({"type": "stop"})
            else:
                self.voice.guide.next()
            return True
        if intent in ("stop", "pause", "resume") and self.voice.working:
            logger.info("🎯 Intention « {} »", intent)
            self._dispatch({"type": intent})
            return True
        if is_noise(text):  # bruit, « euh », « Merci. » fantôme sur l'écho : jamais au LLM
            if self.pending:
                logger.info("🔇 Ignoré (bruit) pendant la question H : {!r}", text)
                if not self._relanced:
                    self._relanced = True
                    self._say_later(f"Je n'ai pas bien entendu. {self._question}".strip())
            else:
                logger.info("🔇 Ignoré (bruit) : {!r}", text)
            return True
        if self.pending:
            logger.info("↳ réponse à la question de l'agent H")
            self.resolve(text)
            return True
        return False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, TranscriptionFrame):
                text = (frame.text or "").strip()
                if text:
                    logger.info("🗣️  Utilisateur : {}", text)
                    self.voice.on_user_final(text)
                    if self.route(text):
                        return
                elif self._capturing():
                    return
            elif isinstance(frame, InterimTranscriptionFrame) and self._capturing():
                return
            elif isinstance(frame, InputAudioRawFrame) and self._capturing():
                # Pas de VAD côté agrégateur pendant une question H ou la carte OUI/NON :
                # la réponse ne doit pas ouvrir un tour de parole pour le LLM.
                frame = InputAudioRawFrame(
                    audio=bytes(len(frame.audio)), sample_rate=frame.sample_rate, num_channels=frame.num_channels
                )
        await self.push_frame(frame, direction)


class StateTap(FrameProcessor):
    """Après la sortie audio : statut parle/écoute + sous-titres dans la bulle."""

    def __init__(self, voice: "ColetteVoice") -> None:
        super().__init__(name="StateTap")
        self.voice = voice
        self._words: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, BotStartedSpeakingFrame):
                self._words = []
                self.voice.on_bot_started()
            elif isinstance(frame, BotStoppedSpeakingFrame):
                self.voice.on_bot_stopped()
            elif isinstance(frame, TTSTextFrame):
                word = (frame.text or "").strip()
                if word:
                    self._words.append(word)
                    self.voice.state.set_subtitle(" ".join(self._words))
        await self.push_frame(frame, direction)


class ColetteVoice:
    """Assemble le pipeline et relie voix ⇄ bulle (StateServer) ⇄ agent H (runner)."""

    def __init__(self, state: StateServer, runner, *, script: Optional[list[str]] = None,
                 auto_open: bool = False, overlay=None,
                 start_url: str = "https://mobile.free.fr/account/") -> None:
        self.start_url = start_url  # page de départ de l'agent H (vrai site ou maquette locale)
        self.state = state
        self.runner = runner
        self.script = list(script or [])
        self.auto_open = auto_open
        self.barge_in = _env_flag("COLETTE_BARGE_IN")

        self.bot_speaking = False
        self.last_bot_stop = 0.0
        self.working = False
        self.paused = False
        self._stopped = False
        self.greeted = False
        self._last_user_final_at: Optional[float] = None
        self._last_narration = 0.0
        self._step_seq = 0  # narration « dernier gagnant »
        self._narrated_seq = 0
        self._latest_step: Optional[tuple[int, Step, float]] = None
        self._narr_task: Optional[asyncio.Task] = None
        self._demarche_task: Optional[asyncio.Task] = None
        self._started = asyncio.Event()
        self._bot_started_evt = asyncio.Event()

        self.worker: Optional[PipelineWorker] = None
        self.gate = VoiceGate(self)
        self.narrator = Narrator()
        # Guide manuel pas à pas si l'agent H échoue (a besoin de l'overlay CDP pour lire la page).
        self.guide: Optional[ManualGuide] = ManualGuide(state, overlay, say=self.say) if overlay else None
        state.on_client_message(self.on_client_message)

    @property
    def guiding(self) -> bool:
        return self.guide is not None and self.guide.active

    # ---- état partagé entre processeurs ------------------------------------
    def mic_open(self) -> bool:
        if not self.state.state.open:
            return False
        if self.barge_in:
            return True
        if self.bot_speaking:
            return False
        return time.monotonic() - self.last_bot_stop > ECHO_TAIL_S

    def on_user_final(self, text: str) -> None:
        self._last_user_final_at = time.monotonic()
        self.state.set_subtitle(f"« {text} »")

    def on_bot_started(self) -> None:
        self.bot_speaking = True
        self._bot_started_evt.set()
        if self._last_user_final_at is not None:
            logger.info("⏱️  Latence fin de phrase → voix : {:.2f} s", time.monotonic() - self._last_user_final_at)
            self._last_user_final_at = None
        if not self.working and self.state.state.status not in ("paused", "awaiting_confirm"):
            self.state.set_status("speaking")

    def on_bot_stopped(self) -> None:
        self.bot_speaking = False
        self.last_bot_stop = time.monotonic()
        if not self.working and self.state.state.status == "speaking":
            self.state.set_status("listening")

    # ---- construction du pipeline ------------------------------------------
    def build(self) -> PipelineWorker:
        transport = LocalAudioTransport(LocalAudioTransportParams(audio_in_enabled=True, audio_out_enabled=True))

        stt = GladiaSTTService(
            api_key=os.environ["GLADIA_API_KEY"],
            region="eu-west",
            settings=GladiaSTTService.Settings(
                model="solaria-1",
                language_config=LanguageConfig(languages=["fr"], code_switching=False),
            ),
        )
        llm = OpenRouterLLMService(
            api_key=os.environ["OPENROUTER_API_KEY"],
            settings=OpenRouterLLMService.Settings(
                model=os.getenv("OPENROUTER_MODEL") or DEFAULT_LLM_MODEL,
                system_instruction=SYSTEM_PROMPT,
            ),
        )
        tts = CartesiaTTSService(
            api_key=os.environ["CARTESIA_API_KEY"],
            settings=CartesiaTTSService.Settings(voice=os.environ["CARTESIA_VOICE_ID"], language=Language.FR),
        )

        run_demarche = FunctionSchema(
            name="run_demarche",
            description=(
                "Lance l'agent qui fait la démarche sur le site Free dans le navigateur de la personne. "
                "À appeler UNE SEULE FOIS, quand la personne a confirmé ce qu'elle veut. Ne jamais "
                "rappeler tant que le résultat n'est pas revenu. La confirmation avant de valider "
                "est gérée par l'outil lui-même."
            ),
            properties={
                "objectif": {
                    "type": "string",
                    "description": "Objectif précis et complet en français, ex. « Changer le forfait Free Mobile pour un forfait moins cher ».",
                }
            },
            required=["objectif"],
        )
        llm.register_function("run_demarche", self._run_demarche, cancel_on_interruption=False, timeout_secs=900)

        context = LLMContext(tools=ToolsSchema(standard_tools=[run_demarche]))
        aggregators = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(
                vad_analyzer=SileroVADAnalyzer(),
                user_mute_strategies=[] if self.barge_in else [AlwaysUserMuteStrategy()],
            ),
        )

        pipeline = Pipeline([
            transport.input(),
            MicGate(self),
            stt,
            self.gate,
            aggregators.user(),
            llm,
            tts,
            transport.output(),
            StateTap(self),
            aggregators.assistant(),
        ])
        self.worker = PipelineWorker(
            pipeline,
            params=PipelineParams(enable_metrics=True),
            idle_timeout_secs=None,
        )

        @self.worker.event_handler("on_pipeline_started")
        async def _on_started(worker, frame):
            logger.info("Pipeline voix démarré (barge-in={})", self.barge_in)
            self._started.set()

        return self.worker

    async def run(self) -> None:
        worker = self.build()
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        tasks = [asyncio.create_task(self._after_start())]
        try:
            await runner.run()
        finally:
            for t in tasks:
                t.cancel()

    async def stop(self) -> None:
        if self.worker is not None:
            await self.worker.cancel()

    async def _after_start(self) -> None:
        await self._started.wait()
        if self.auto_open:
            await asyncio.sleep(1.0)
            self.state.set_open(True)
            await self.greet()
        if self.script:
            await self._play_script()

    # ---- parole ------------------------------------------------------------
    async def say(self, text: str, *, to_context: bool = False) -> None:
        if self.worker is not None:
            await self.worker.queue_frame(TTSSpeakFrame(text, append_to_context=to_context))

    async def greet(self) -> None:
        if self.greeted:
            return
        self.greeted = True
        logger.info("Accueil : {}", GREETING)
        self.state.set_subtitle(GREETING)
        await self.say(GREETING, to_context=True)

    # ---- messages de la bulle (et commandes vocales, même chemin) ------------
    async def on_client_message(self, msg: dict) -> None:
        t = msg.get("type")
        running = self._demarche_task is not None and not self._demarche_task.done()
        if t == "open":
            if self._started.is_set():
                await self.greet()
        elif t in ("pause", "resume") and self.guiding:
            return  # guide manuel : la personne a déjà la main
        elif t == "stop":
            self.gate.cancel_pending()
            if self.guide is not None:
                self.guide.stop()
            if running and not self._stopped:
                self._stopped = True
                self.paused = False
                await self.say("D'accord, j'arrête tout.")
                try:
                    await self.runner.cancel()
                except Exception as e:
                    logger.warning("Annulation H : {}", e)
        elif t == "pause":
            if running and not self.paused and not self._stopped:
                self.paused = True
                await self.say("D'accord, je vous laisse la main. Dites « continuez » quand vous voulez.")
                try:
                    await self.runner.pause()
                except Exception as e:
                    logger.warning("Pause H : {}", e)
        elif t == "resume":
            if running and self.paused and not self._stopped:
                self.paused = False
                await self.say("Je reprends.")
                try:
                    await self.runner.resume()
                except Exception as e:
                    logger.warning("Reprise H : {}", e)
                if self.state.state.status == "paused":
                    self.state.set_status("working")

    # ---- tool run_demarche -------------------------------------------------
    async def _run_demarche(self, params: FunctionCallParams) -> None:
        objectif = (params.arguments.get("objectif") or "").strip()
        logger.info("🛠️  run_demarche({!r})", objectif)
        if self._demarche_task and not self._demarche_task.done():
            logger.warning("🛠️  run_demarche refusé : une démarche est déjà en cours")
            await params.result_callback(
                {"statut": "refusé", "raison": "Une démarche est déjà en cours, n'appelle plus l'outil. "
                 "Dis seulement à la personne, en une phrase, que tu t'en occupes déjà."},
            )
            return
        self._demarche_task = asyncio.current_task()
        self.working = True
        self.paused = False
        self._stopped = False
        self.state.update(steps=[], status="working", open=True)
        self.state.add_step("Comprendre votre demande")
        result: dict
        speak = True  # le LLM résume-t-il ? (non : on a déjà tout dit nous-mêmes)
        h_error: Optional[str] = None  # l'agent H a échoué → guide manuel pas à pas
        try:
            goal = H_GOAL_TEMPLATE.format(objectif=objectif or "changer de forfait Free Mobile",
                                          start_url=self.start_url)
            answer = await self.runner.run(goal, on_step=self._on_step, ask_user=self._ask_user)
            self._check_h()
            body, action = split_confirmation(answer)
            logger.info("🛠️  Phase 1 terminée ; confirmation demandée : {!r}", action)
            if self._stopped:
                result, speak = {"statut": "arrêtée par la personne"}, False
            elif action is None:
                self.state.finish_steps()
                result = {"statut": "terminé", "resultat": body or "(l'agent n'a rien répondu)"}
            elif await self._confirm(action):
                self.state.add_step("Valider, avec votre accord")
                answer2 = await self.runner.follow_up(CONFIRMED_FOLLOW_UP)
                self._check_h()
                if self._stopped:
                    result, speak = {"statut": "arrêtée par la personne pendant la validation"}, False
                else:
                    self.state.finish_steps()
                    result = {"statut": "validé avec l'accord oral de la personne",
                              "resultat": answer2 or "(l'agent n'a rien répondu)"}
            elif self._stopped:
                result, speak = {"statut": "arrêtée par la personne"}, False
            else:
                result, speak = {"statut": "non validé : la personne a dit non, rien n'a été changé",
                                 "resultat": body}, False
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if self._stopped:
                result, speak = {"statut": "arrêtée par la personne"}, False
            else:
                logger.exception("Démarche en échec")
                h_error = str(e) or type(e).__name__
                result = {"statut": "échec", "erreur": h_error}
        finally:
            self.working = False
            self.paused = False
            self.gate.cancel_pending()
            self.state.resolve_confirm(False)
            try:
                await self.runner.close()  # H lâche le navigateur avant que la personne clique
            except Exception as e:
                logger.warning("Fermeture de la session H : {}", e)
            self.state.set_status("done")
        if h_error and self.guide is not None and not self._stopped:
            result, speak = await self._guide_fallback(objectif, h_error)
        result["suite"] = ("Cette démarche est terminée. Si la personne demande une nouvelle démarche, "
                           "reformule puis rappelle run_demarche normalement.")
        logger.info("🛠️  run_demarche → {}", result)
        await params.result_callback(result, properties=FunctionCallResultProperties(run_llm=speak))

    def _check_h(self) -> None:
        """Session H finie en échec (sans exception) → on la traite comme une erreur."""
        status = getattr(self.runner, "status", None)
        if not self._stopped and status in ("failed", "timed_out"):
            raise RuntimeError(f"L'agent H s'est arrêté en échec (status={status})")

    async def _guide_fallback(self, objectif: str, h_error: str) -> tuple[dict, bool]:
        """L'agent H a échoué : Colette montre à la personne où cliquer, étape par étape."""
        done = [s["label"] for s in self.state.state.steps if s.get("state") == "done"]
        context = (f"L'agent automatique s'est arrêté sur une erreur ({h_error[:200]}). "
                   f"Il avait déjà fait : {'; '.join(done[-8:]) or 'rien'}. "
                   "La page affichée est celle où il s'est arrêté.")
        logger.info("🧭 Agent H en échec → guide manuel pas à pas")
        try:
            out = await self.guide.run(objectif or "changer de forfait Free Mobile", context)
        except Exception as e:
            logger.exception("Guide manuel en échec")
            return {"statut": "échec", "erreur": h_error, "erreur_guide": str(e)}, True
        finally:
            self.state.set_status("done")
        if out["outcome"] == "done":
            return {"statut": "terminé grâce au guide pas à pas : la personne a cliqué elle-même",
                    "resultat": out["summary"], "etapes": out["steps"]}, False
        if out["outcome"] == "stopped":
            return {"statut": "guide pas à pas arrêté par la personne", "etapes": out["steps"]}, False
        return {"statut": "échec, même avec le guide pas à pas", "resultat": out["summary"]}, False

    async def _confirm(self, action: str) -> bool:
        """Carte OUI/NON + question orale. Seul un oui explicite (voix ou bouton) renvoie True."""
        card = action[0].upper() + action[1:] + " ?"
        question = f"Je m'apprête à {action}. Je valide ? Dites oui ou non."
        logger.info("✋ Confirmation demandée : {}", action)
        fut = self.state.ask_confirm(card)
        await self.say(question)
        try:
            ok = bool(await asyncio.wait_for(fut, CONFIRM_TIMEOUT_S))
        except asyncio.TimeoutError:
            logger.info("✋ Pas de réponse à la confirmation → on ne valide pas")
            self.state.resolve_confirm(False)
            ok = False
        logger.info("✋ Réponse : {}", "OUI" if ok else "NON")
        if self._stopped:
            return False
        await self.say("Merci, je valide." if ok else "D'accord, je ne valide rien. Rien n'a été changé.")
        return ok

    def _on_step(self, step: Step) -> None:
        """Rend la main tout de suite : la narration tourne à côté (« dernier gagnant »)."""
        if step.kind != "step":
            logger.debug("[{}] {}", step.kind, step.text)
            return
        logger.info("👣 [H] {}", step.text)
        self._step_seq += 1
        self._latest_step = (self._step_seq, step, time.monotonic())
        if self._narr_task is None or self._narr_task.done():
            self._narr_task = asyncio.create_task(self._narrate_latest())

    def _can_narrate(self) -> bool:
        return (
            self.working and not self.paused and not self._stopped
            and not self.bot_speaking and not self.gate.pending and not self.state.confirm_pending
            and time.monotonic() - self._last_narration >= NARRATE_MIN_GAP_S
        )

    async def _narrate_latest(self) -> None:
        """Un seul appel au narrateur à la fois ; seule la dernière étape reçue peut être dite."""
        try:
            while self._latest_step and self._latest_step[0] > self._narrated_seq:
                seq, step, received = self._latest_step
                self._narrated_seq = seq
                text = await self.narrator.simplify(step)
                if not text:
                    continue  # action technique, ou phrase déjà dite
                text = _URL_RE.sub("la page", text).strip()
                self.state.add_step(text[:80])
                age = time.monotonic() - received
                if seq != self._step_seq:
                    logger.info("💬 (jetée : étape dépassée) {}", text)
                elif self._can_narrate():
                    self._last_narration = time.monotonic()
                    logger.info("💬 {} (dite {:.1f} s après l'étape)", text, age)
                    await self.say(text.rstrip(".") + ".")
                else:
                    logger.info("💬 (affichée, pas dite) {}", text)
        except Exception:
            logger.exception("Narration en échec")

    async def _ask_user(self, question: str) -> str:
        logger.info("❓ Agent H : {}", question)
        fut = self.gate.expect_answer(question)
        self.state.set_status("listening")
        self.state.set_subtitle(question)
        await self.say(question)
        try:
            answer = await asyncio.wait_for(fut, ASK_TIMEOUT_S)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            answer = "(pas de réponse)"
        if self.working and self.state.state.status == "listening":
            self.state.set_status("paused" if self.paused else "working")
        logger.info("↳ réponse transmise à H : {}", answer)
        return answer

    # ---- mode script (tests sans micro) -------------------------------------
    async def _wait_quiet(self, seconds: float = 2.0) -> None:
        while self.bot_speaking or time.monotonic() - self.last_bot_stop < seconds:
            await asyncio.sleep(0.2)

    async def _play_script(self) -> None:
        """Lignes jouées comme si la personne parlait (même routage que le micro).

        « texte »   : dit quand Colette se tait (part au LLM, sauf commande reconnue).
        « ?texte »  : attend une question H ou la carte OUI/NON, puis répond.
        « !texte »  : commande dite tout de suite (stop, attendez, continuez…), même si Colette parle.
        « @5 »      : attend 5 secondes.
        """
        try:  # laisser passer l'accueil
            await asyncio.wait_for(self._bot_started_evt.wait(), 15)
        except asyncio.TimeoutError:
            logger.warning("Accueil non entendu (TTS ?)")
        for line in self.script:
            if line.startswith("@"):
                await asyncio.sleep(float(line[1:] or 1))
                continue
            if line.startswith("!"):
                line = line[1:].strip()
                logger.info("📜 (commande) {}", line)
                self.on_user_final(line)
                if not self.gate.route(line):
                    logger.warning("📜 « {} » non reconnue comme commande", line)
                continue
            if line.startswith("?"):
                line = line[1:].strip()
                while not (self.gate.pending or self.state.confirm_pending):
                    await asyncio.sleep(0.2)
                await asyncio.sleep(1.5)  # laisser Colette commencer à poser la question
                await self._wait_quiet()
                logger.info("📜 (réponse) {}", line)
                self.on_user_final(line)
                self.gate.route(line)
                continue
            await self._wait_quiet()
            logger.info("📜 {}", line)
            self.on_user_final(line)
            if self.gate.route(line):
                continue
            self._bot_started_evt.clear()
            await self.worker.queue_frame(
                LLMMessagesAppendFrame(messages=[{"role": "user", "content": line}], run_llm=True)
            )
            try:
                await asyncio.wait_for(self._bot_started_evt.wait(), 30)
            except asyncio.TimeoutError:
                logger.warning("Pas de réponse vocale à « {} »", line)
