"""Bot vocal Colette (Pipecat 1.15) : micro/HP du laptop ⇄ Gladia FR ⇄ OpenRouter ⇄ Cartesia FR.

Pipeline :
    micro → MicGate → Gladia (solaria-1, fr) → VoiceGate → agrégateur user → OpenRouter
          → Cartesia (fr) → haut-parleurs → StateTap → agrégateur assistant

- MicGate : envoie du silence à la place du micro quand la bulle est fermée, et pendant que
  Colette parle (anti-écho : LocalAudioTransport n'a pas d'AEC). `COLETTE_BARGE_IN=1` (casque)
  laisse le micro ouvert pendant que Colette parle.
- VoiceGate : si l'agent H attend une réponse (`ask_user`), la prochaine transcription finale
  résout la question et n'atteint pas le LLM.
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
from colette.h_agent import Step
from colette.prompts import GREETING, H_GOAL_TEMPLATE, SYSTEM_PROMPT
from colette.state import StateServer

DEFAULT_LLM_MODEL = "google/gemini-2.5-flash"
NARRATE_MIN_GAP_S = 5.0  # au plus une phrase de narration toutes les 5 s
ECHO_TAIL_S = 0.4  # micro encore coupé juste après que Colette s'est tue
ASK_TIMEOUT_S = 180.0

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
    """Après le STT : route la réponse orale vers une question H en attente plutôt que vers le LLM."""

    def __init__(self, voice: "ColetteVoice") -> None:
        super().__init__(name="VoiceGate")
        self.voice = voice
        self._pending: Optional[asyncio.Future[str]] = None

    @property
    def pending(self) -> bool:
        return self._pending is not None and not self._pending.done()

    def expect_answer(self) -> asyncio.Future[str]:
        self.cancel_pending()
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

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, TranscriptionFrame):
                text = (frame.text or "").strip()
                if text:
                    logger.info("🗣️  Utilisateur : {}", text)
                    self.voice.on_user_final(text)
                if self.pending:
                    if text:
                        logger.info("↳ réponse à la question de l'agent H")
                        self.resolve(text)
                    return
            elif isinstance(frame, InterimTranscriptionFrame) and self.pending:
                return
            elif isinstance(frame, InputAudioRawFrame) and self.pending:
                # Pas de VAD côté agrégateur pendant une question H : la réponse ne doit pas
                # ouvrir un tour de parole pour le LLM.
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
        self.greeted = False
        self._last_user_final_at: Optional[float] = None
        self._last_narration = 0.0
        self._demarche_task: Optional[asyncio.Task] = None
        self._started = asyncio.Event()
        self._bot_started_evt = asyncio.Event()

        self.worker: Optional[PipelineWorker] = None
        self.gate = VoiceGate(self)
        state.on_client_message(self.on_client_message)

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
                "À appeler une seule fois, quand la personne a confirmé ce qu'elle veut."
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

    # ---- messages de la bulle ----------------------------------------------
    async def on_client_message(self, msg: dict) -> None:
        t = msg.get("type")
        if t == "open":
            if self._started.is_set():
                await self.greet()
        elif t == "stop":
            self.gate.cancel_pending()
            if self._demarche_task and not self._demarche_task.done():
                await self.runner.cancel()
                await self.say("D'accord, j'arrête tout.")
        elif t == "pause":
            if self.working:
                await self.runner.pause()
        elif t == "resume":
            if self.working:
                await self.runner.resume()

    # ---- tool run_demarche -------------------------------------------------
    async def _run_demarche(self, params: FunctionCallParams) -> None:
        objectif = (params.arguments.get("objectif") or "").strip()
        logger.info("🛠️  run_demarche({!r})", objectif)
        if self._demarche_task and not self._demarche_task.done():
            await params.result_callback({"statut": "refusé", "raison": "une démarche est déjà en cours"})
            return
        self._demarche_task = asyncio.current_task()
        self.working = True
        self.state.update(steps=[], status="working", open=True)
        self.state.add_step("Comprendre votre demande")
        result: dict
        try:
            goal = H_GOAL_TEMPLATE.format(objectif=objectif or "changer de forfait Free Mobile")
            answer = await self.runner.run(goal, on_step=self._on_step, ask_user=self._ask_user)
            self.state.finish_steps()
            result = {"statut": "terminé", "resultat": answer or "(l'agent n'a rien répondu)"}
        except asyncio.CancelledError:
            self.working = False
            self.state.set_status("done")
            raise
        except Exception as e:
            logger.exception("Démarche en échec")
            result = {"statut": "échec ou annulée", "erreur": str(e)}
        finally:
            self.working = False
            self.gate.cancel_pending()
        self.state.set_status("done")
        logger.info("🛠️  run_demarche → {}", result)
        await params.result_callback(result)

    async def _on_step(self, step: Step) -> None:
        if step.kind != "step":
            logger.debug("[{}] {}", step.kind, step.text)
            return
        text = _URL_RE.sub("la page", step.text).strip()
        logger.info("👣 {}", text)
        self.state.add_step(text[:80])
        now = time.monotonic()
        if now - self._last_narration >= NARRATE_MIN_GAP_S and not self.bot_speaking and not self.gate.pending:
            self._last_narration = now
            await self.say(text.rstrip(".") + ".")

    async def _ask_user(self, question: str) -> str:
        logger.info("❓ Agent H : {}", question)
        fut = self.gate.expect_answer()
        self.state.set_status("listening")
        self.state.set_subtitle(question)
        await self.say(question)
        try:
            answer = await asyncio.wait_for(fut, ASK_TIMEOUT_S)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            answer = "(pas de réponse)"
        if self.working:
            self.state.set_status("working")
        logger.info("↳ réponse transmise à H : {}", answer)
        return answer

    # ---- mode script (tests sans micro) -------------------------------------
    async def _wait_quiet(self, seconds: float = 2.0) -> None:
        while self.bot_speaking or time.monotonic() - self.last_bot_stop < seconds:
            await asyncio.sleep(0.2)

    async def _play_script(self) -> None:
        """Lignes jouées comme si la personne parlait. « ? texte » = réponse à la prochaine question H."""
        try:  # laisser passer l'accueil
            await asyncio.wait_for(self._bot_started_evt.wait(), 15)
        except asyncio.TimeoutError:
            logger.warning("Accueil non entendu (TTS ?)")
        for line in self.script:
            if line.startswith("?"):
                line = line[1:].strip()
                while not self.gate.pending:
                    await asyncio.sleep(0.2)
                await self._wait_quiet()
                logger.info("📜 (réponse) {}", line)
                self.on_user_final(line)
                self.gate.resolve(line)
                continue
            await self._wait_quiet()
            logger.info("📜 {}", line)
            self.on_user_final(line)
            self._bot_started_evt.clear()
            await self.worker.queue_frame(
                LLMMessagesAppendFrame(messages=[{"role": "user", "content": line}], run_llm=True)
            )
            try:
                await asyncio.wait_for(self._bot_started_evt.wait(), 30)
            except asyncio.TimeoutError:
                logger.warning("Pas de réponse vocale à « {} »", line)
