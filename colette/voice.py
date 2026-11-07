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
from colette.h_agent import VALIDATE_STEP, Step, split_confirmation
from colette.intents import is_noise, parse_intent
from colette.narration import Narrator
from colette.prompts import CONFIRMED_FOLLOW_UP, GREETING, H_GOAL_TEMPLATE, SYSTEM_PROMPT
from colette.skills_loader import list_shortcuts
from colette.state import StateServer

DEFAULT_LLM_MODEL = "google/gemini-2.5-flash"
NARRATE_MIN_GAP_S = 5.0  # au plus une phrase de narration toutes les 5 s
ECHO_TAIL_S = 0.4  # micro encore coupé juste après que Colette s'est tue
ASK_TIMEOUT_S = 180.0
CONFIRM_TIMEOUT_S = 120.0  # sans réponse → on ne valide pas
REMIND_GAP_S = 4.0  # « Dites simplement oui ou non. » au plus toutes les 4 s
ADVISOR_TEXT = ("Vous pouvez appeler le service client Free Mobile au trois, deux, quatre, quatre, "
                "depuis votre téléphone Free. Je reste là si vous avez besoin de moi.")

_URL_RE = re.compile(r"https?://\S+")


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text[:2] != text[:2].upper() else text


def _confirm_card(action: str, costs_money: bool) -> dict:
    """Carte d'accord (écran 6) : « passer au forfait à 2 €, à partir du 1er décembre » →
    titre « Passer au forfait à 2 € ? », puces « À partir du 1er décembre. » (+ prix), « Oui, passer »."""
    head, _, rest = action.partition(",")
    head = head.strip() or action
    bullets = [p.strip()[:1].upper() + p.strip()[1:] + "." for p in rest.split(",") if p.strip()]
    if costs_money:
        bullets.append("Cela change ce que vous payez.")
    verb = head.split()[0].lower() if head.split() else "valider"
    return {"title": head[:1].upper() + head[1:] + " ?", "bullets": bullets[:3],
            "yes": f"Oui, {verb}", "no": "Non, ne rien changer"}


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
            elif isinstance(frame, InterimTranscriptionFrame):
                self.voice.on_user_interim((frame.text or "").strip())
                if self._capturing():
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
                 auto_open: bool = False) -> None:
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
        self._plan_announced = False  # H a appelé annoncer_etapes → la narration n'ajoute plus d'étapes
        self._confirmations: list[tuple[str, bool]] = []  # confirm_change de cette démarche (résumé, oui ?)
        self._approved = False  # la personne a dit oui à une action pendant cette démarche
        self._last_objectif = ""
        self._was_greeted_call = False
        self._narr_task: Optional[asyncio.Task] = None
        self._demarche_task: Optional[asyncio.Task] = None
        self._started = asyncio.Event()
        self._bot_started_evt = asyncio.Event()

        self.worker: Optional[PipelineWorker] = None
        self.gate = VoiceGate(self)
        self.narrator = Narrator()
        state.on_client_message(self.on_client_message)
        state.update(shortcuts=list_shortcuts())

    # ---- état partagé entre processeurs ------------------------------------
    def mic_open(self) -> bool:
        st = self.state.state
        if not st.open or not (st.call or st.busy):
            return False
        if st.status == "paused" and not self.working:
            return False  # « Pause » pendant l'appel : Colette n'écoute plus
        if self.barge_in:
            return True
        if self.bot_speaking:
            return False
        return time.monotonic() - self.last_bot_stop > ECHO_TAIL_S

    def on_user_final(self, text: str) -> None:
        self._last_user_final_at = time.monotonic()
        if not is_noise(text):  # « Merci. » fantôme, « euh » : pas affiché
            self.state.update(heard=text)

    def on_user_interim(self, text: str) -> None:
        """Transcription partielle → « Vous dites : … » dans la bulle (en direct)."""
        if text and not is_noise(text) and self.mic_open() and text != self.state.state.heard:
            self.state.update(heard=text)

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
            self.state.update(open=True, call=True, status="listening")
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
        if t == "call":
            if self._started.is_set():
                if not self.greeted:
                    await self.greet()
                else:
                    self.state.set_subtitle("Je vous écoute.")
                    await self.say("Je vous écoute.")
        elif t == "shortcut":
            label = next((s["label"] for s in self.state.state.shortcuts if s["id"] == msg.get("id")), "")
            if label and not running:
                request = f"Je voudrais {_lower_first(label)}."
                self.greeted = True  # pas d'accueil par-dessus : la demande part tout de suite
                self.state.update(heard=request)
                logger.info("🔘 Raccourci {} → {!r}", msg.get("id"), request)
                await self._ask_llm(request)
        elif t in ("hangup", "close", "later"):
            if running and not self._stopped:
                await self.state.handle_message({"type": "stop", "source": t})
            elif t == "hangup":
                await self.say("Au revoir, à bientôt.")
        elif t == "reset":
            if not running:
                await self.say("Que puis-je faire d'autre pour vous ?")
        elif t == "replay":
            await self.say(self._outcome_speech())
        elif t == "advisor":
            await self.say(ADVISOR_TEXT)
        elif t == "retry":
            if not running and self._last_objectif:
                self.state.update(outcome=None, call=True, open=True)
                await self._ask_llm(f"Réessaie une fois la même démarche : {self._last_objectif}")
        elif t == "stop":
            self.gate.cancel_pending()
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
        self._plan_announced = False
        self._confirmations = []
        self._approved = False
        self._last_objectif = objectif
        title = (objectif or "Votre démarche").rstrip(" .")
        self.state.update(steps=[], status="working", open=True, busy=True, outcome=None,
                          title=title[:1].upper() + title[1:], heard="")
        self.state.add_step("Comprendre votre demande")
        result: dict
        speak = True  # le LLM résume-t-il ? (non : on a déjà tout dit nous-mêmes)
        try:
            goal = H_GOAL_TEMPLATE.format(objectif=objectif or "changer de forfait Free Mobile")
            answer = await self.runner.run(
                goal, on_step=self._on_step, ask_user=self._ask_user,
                on_plan=self._on_plan, on_step_done=self._on_step_done, confirm=self._confirm_change,
            )
            body, action = split_confirmation(answer)
            asked = self._confirmations[-1] if self._confirmations else None
            logger.info("🛠️  Phase 1 terminée ; confirm_change : {} ; ligne CONFIRMATION : {!r}", asked, action)
            if self._stopped:
                result, speak = {"statut": "arrêtée par la personne"}, False
            elif asked is not None and not asked[1]:
                # Refus via confirm_change : jamais de 2e question, rien n'est validé.
                result, speak = {"statut": "non validé : la personne a dit non, rien n'a été changé",
                                 "resultat": body}, False
            elif action is None:
                self.state.finish_steps()
                statut = "validé avec l'accord oral de la personne" if asked else "terminé"
                result = {"statut": statut, "resultat": body or "(l'agent n'a rien répondu)"}
            elif asked is not None or await self._approve(action):
                # Garde-fou deux phases : H s'est arrêté au récapitulatif. Si la personne a déjà dit
                # oui via confirm_change, on ne redemande pas.
                self._start_validate_step()
                answer2 = await self.runner.follow_up(CONFIRMED_FOLLOW_UP)
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
                result = {"statut": "échec", "erreur": str(e)}
        finally:
            self.working = False
            self.paused = False
            self.gate.cancel_pending()
            self.state.resolve_confirm(False)
            try:
                await self.runner.close()
            except Exception as e:
                logger.warning("Fermeture de la session H : {}", e)
            self.state.update(status="done", busy=False)
        self.state.update(outcome=self._outcome(result))
        result["suite"] = ("Cette démarche est terminée. Si la personne demande une nouvelle démarche, "
                           "reformule puis rappelle run_demarche normalement.")
        logger.info("🛠️  run_demarche → {}", result)
        await params.result_callback(result, properties=FunctionCallResultProperties(run_llm=speak))

    # ---- plan annoncé par H (annoncer_etapes / etape_terminee) ----------------
    async def _on_plan(self, labels: list[str]) -> None:
        labels = [l.rstrip(" .") for l in labels]
        if labels and "accord" in labels[-1].lower() and labels[-1] != VALIDATE_STEP:
            labels[-1] = VALIDATE_STEP  # libellé imposé pour la dernière étape
        self._plan_announced = True
        self.state.set_steps(labels)
        self.state.advance_step()  # 1re étape en cours
        validate = labels[-1] == VALIDATE_STEP
        todo = labels[:-1] if validate else labels
        nums = ("un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit")
        spoken = " ; ".join(f"{nums[i] if i < len(nums) else i + 1}, {_lower_first(l)}" for i, l in enumerate(todo))
        text = f"Voici ce que je vais faire : {spoken}."
        if validate:
            text += " Et je vous demanderai votre accord avant de valider."
        logger.info("📋 Plan lu : {}", text)
        self._last_narration = time.monotonic() + 3.0  # pas de narration par-dessus le plan
        await self.say(text)

    def _on_step_done(self, number: int) -> None:
        if not self._plan_announced:
            return
        steps = self.state.state.steps
        if steps and steps[-1]["label"] == VALIDATE_STEP:
            number = min(number, len(steps) - 1)  # « Valider » ne se coche qu'après le oui
        self.state.complete_through(number)

    def _start_validate_step(self) -> None:
        """Met « Valider avec votre accord » en cours (l'ajoute s'il n'était pas annoncé)."""
        steps = self.state.state.steps
        if not any(s["label"] == VALIDATE_STEP for s in steps):
            self.state.add_step(VALIDATE_STEP)
            return
        idx = next(i for i, s in enumerate(steps) if s["label"] == VALIDATE_STEP)
        self.state.complete_through(idx)  # étapes d'avant faites, « Valider » en cours

    async def _confirm_change(self, summary: str, costs_money: bool) -> bool:
        """Tool H `confirm_change` : carte + question orale, bloque jusqu'au oui/non."""
        if self._stopped:
            return False
        self._start_validate_step()
        ok = await self._approve(summary or "valider cette action", costs_money=costs_money)
        self._confirmations.append((summary, ok))
        return ok and not self._stopped

    async def _approve(self, action: str, *, costs_money: bool = False) -> bool:
        ok = await self._confirm(action, costs_money=costs_money)
        if ok and not self._stopped:
            self._approved = True  # à partir d'ici, le compte a pu être modifié
        return ok

    # ---- écrans de fin (7 terminé / arrêté / refusé, 10 échec) ------------------
    def _outcome(self, result: dict) -> dict:
        statut = result.get("statut", "")
        nothing_changed = not self._approved
        if statut.startswith("échec"):
            return {"kind": "failed", "title": "Je n'ai pas pu terminer",
                    "text": "Le site ne répond pas comme prévu.", "summary": [], "nothing_changed": nothing_changed}
        if statut.startswith("arrêtée"):
            return {"kind": "stopped", "title": "D'accord, j'ai arrêté",
                    "text": "Je me suis arrêtée à votre demande.", "summary": [], "nothing_changed": nothing_changed}
        if statut.startswith("non validé"):
            return {"kind": "refused", "title": "Rien n'a été changé",
                    "text": "Vous avez dit non : je n'ai rien validé.", "summary": [], "nothing_changed": True}
        text = _URL_RE.sub("la page", str(result.get("resultat") or "")).strip()
        if text.startswith("("):
            text = ""
        summary = [s["label"] for s in self.state.state.steps
                   if s["state"] == "done" and s["label"] != "Comprendre votre demande"]
        return {"kind": "success", "title": "C'est fait !", "text": text, "summary": summary[-6:],
                "nothing_changed": False}

    def _outcome_speech(self) -> str:
        o = self.state.state.outcome
        if not o:
            return "Je n'ai rien fait pour l'instant. Que puis-je faire pour vous ?"
        parts = [o.get("title", "").rstrip(" !.") + ".", o.get("text", "")]
        if o.get("summary"):
            parts.append("Voici ce que j'ai fait : " + " ; ".join(_lower_first(s) for s in o["summary"]) + ".")
        if o.get("kind") != "success" and o.get("nothing_changed"):
            parts.append("Rien n'a été modifié sur votre compte.")
        return " ".join(p for p in parts if p)

    async def _ask_llm(self, text: str) -> None:
        """Envoie une phrase au LLM comme si la personne l'avait dite."""
        if self.worker is not None:
            await self.worker.queue_frame(
                LLMMessagesAppendFrame(messages=[{"role": "user", "content": text}], run_llm=True)
            )

    async def _confirm(self, action: str, *, costs_money: bool = False) -> bool:
        """Carte OUI/NON + question orale. Seul un oui explicite (voix ou bouton) renvoie True."""
        action = action.strip().rstrip(".") or "valider cette action"
        card = action[0].upper() + action[1:] + " ?"
        money = " Attention, cela change ce que vous payez." if costs_money else ""
        question = f"Je m'apprête à {_lower_first(action)}.{money} Je valide ? Dites oui ou non."
        logger.info("✋ Confirmation demandée : {}", action)
        fut = self.state.ask_confirm(card, **_confirm_card(action, costs_money))
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
                if not self._plan_announced:  # sans plan annoncé : étapes tirées de la narration
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
        self.state.update(status="listening", subtitle=question, heard="")
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
