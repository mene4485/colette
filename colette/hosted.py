"""Colette en ligne : backend voix + agent H pour le lien de démo public.

    Navigateur de la personne (maquette sur Vercel + bulle widget.js)
        ⇅ un seul WebSocket wss://<backend>/ws
          texte  : état de la bulle (serveur → bulle), clics des boutons (bulle → serveur),
                   captures de l'écran de l'agent {"type": "screen", ...}
          binaire: micro PCM16 16 kHz mono (bulle → serveur), voix PCM16 24 kHz mono (serveur → bulle)
    Backend (ce fichier, FastAPI) : même pipeline que la démo locale (colette/voice.py : Gladia,
    OpenRouter, Cartesia, garde-fous oui/non/stop) + agent H en navigateur CLOUD (host="cloud")
    qui ouvre la maquette publique ; ses captures sont relayées dans la bulle.

    uvicorn colette.hosted:app --host 0.0.0.0 --port $PORT

Variables : HAI_API_KEY, GLADIA_API_KEY, OPENROUTER_API_KEY, CARTESIA_API_KEY, CARTESIA_VOICE_ID,
COLETTE_SITE_URL (https://<projet>.vercel.app/account/), COLETTE_MAX_SESSIONS (défaut 2),
COLETTE_FAKE=1 (faux agent H : aucune session H consommée).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import time
from typing import Optional

os.environ.setdefault("COLETTE_SITE", "demo")

import certifi  # noqa: E402

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from dotenv import load_dotenv  # noqa: E402

from pathlib import Path  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT / "colette" / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import JSONResponse, PlainTextResponse  # noqa: E402
from loguru import logger  # noqa: E402
from pipecat.frames.frames import Frame, InputAudioRawFrame, OutputAudioRawFrame  # noqa: E402
from pipecat.serializers.base_serializer import FrameSerializer  # noqa: E402
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport  # noqa: E402

from colette import site  # noqa: E402
from colette.state import StateServer  # noqa: E402

IN_RATE = 16000
OUT_RATE = 24000
MAX_SESSIONS = int(os.getenv("COLETTE_MAX_SESSIONS", "2"))
SCREEN_WIDTH = 1100  # captures réduites (JPEG) pour la bulle

app = FastAPI(title="Colette backend")
_active: set[str] = set()


def agent_start_url() -> str:
    return site.start_url()


# L'agent cloud ouvre la maquette avec ?agent=1 → elle n'y affiche pas la bulle Colette
# (sinon la bulle, dans le navigateur de l'agent, ouvrirait une deuxième session).
_url = site.start_url()
if "agent=1" not in _url:
    os.environ["COLETTE_SITE_URL"] = _url + ("&" if "?" in _url else "?") + "agent=1"


class HostedState(StateServer):
    """StateServer sans serveur WS : l'état part dans le WebSocket de la personne (ordre garanti)."""

    def __init__(self, websocket: WebSocket) -> None:
        super().__init__()
        self.ws = websocket
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._sender: Optional[asyncio.Task] = None
        self.last_screen: Optional[str] = None

    async def start(self) -> None:
        self._sender = asyncio.create_task(self._send_loop())
        self._queue.put_nowait(json.dumps({"type": "state", "state": self.snapshot()}, ensure_ascii=False))

    async def stop(self) -> None:
        if self._sender:
            self._sender.cancel()

    async def _send_loop(self) -> None:
        while True:
            text = await self._queue.get()
            try:
                await self.ws.send_text(text)
            except Exception as e:
                logger.debug("Envoi bulle impossible : {}", e)
                return

    def _broadcast(self) -> None:
        snap = self.snapshot()
        self._queue.put_nowait(json.dumps({"type": "state", "state": snap}, ensure_ascii=False))
        for listener in list(self._listeners):
            try:
                listener(snap)
            except Exception:
                logger.exception("Listener d'état en échec")

    def push_screen(self, shot: dict) -> None:
        """Capture de l'agent H (PNG) → JPEG réduit → bulle."""
        image, media = shot["image"], shot.get("media_type", "image/png")
        scale = 1.0
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(image)).convert("RGB")
            if img.width > SCREEN_WIDTH:
                scale = SCREEN_WIDTH / img.width
                img = img.resize((SCREEN_WIDTH, round(img.height * scale)))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=70)
            image, media = buf.getvalue(), "image/jpeg"
        except Exception as e:
            logger.debug("Capture non convertie : {}", e)
        msg = {"type": "screen", "image": f"data:{media};base64," + base64.b64encode(image).decode(),
               "url": shot.get("url"), "title": shot.get("title"),
               "cursor": shot.get("cursor"), "viewport": shot.get("viewport"), "at": time.time()}
        self.last_screen = json.dumps(msg, ensure_ascii=False)
        self._queue.put_nowait(self.last_screen)


class WidgetSerializer(FrameSerializer):
    """Binaire = audio PCM16 brut ; texte = messages JSON de la bulle (boutons)."""

    def __init__(self, state: HostedState) -> None:
        super().__init__()
        self.state = state

    async def serialize(self, frame: Frame):
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        return None

    async def deserialize(self, data):
        if isinstance(data, (bytes, bytearray)):
            if len(data) < 2:
                return None
            return InputAudioRawFrame(audio=bytes(data), sample_rate=IN_RATE, num_channels=1)
        try:
            msg = json.loads(data)
        except (TypeError, ValueError):
            return None
        if isinstance(msg, dict) and msg.get("type"):
            if msg["type"] == "ping":
                return None
            asyncio.create_task(self.state.handle_message(msg))
        return None


@app.get("/")
async def root():
    return PlainTextResponse("Colette backend — WebSocket sur /ws")


@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "sessions": len(_active), "max": MAX_SESSIONS,
                         "site": agent_start_url(), "fake": os.getenv("COLETTE_FAKE") == "1"})


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    if len(_active) >= MAX_SESSIONS:
        await websocket.send_text(json.dumps({"type": "busy"}))
        await websocket.close()
        return
    sid = f"{id(websocket):x}"
    _active.add(sid)
    logger.info("Session {} ouverte ({} active(s))", sid, len(_active))

    try:
        await _serve(websocket, sid)
    finally:
        _active.discard(sid)
        logger.info("Session {} fermée ({} active(s))", sid, len(_active))


async def _serve(websocket: WebSocket, sid: str) -> None:
    from colette.voice import ColetteVoice  # import lourd (pipecat)

    state = HostedState(websocket)
    await state.start()

    if os.getenv("COLETTE_FAKE") == "1":
        from colette.fake_runner import FakeDemarcheRunner

        runner = FakeDemarcheRunner()
    else:
        from colette.h_agent import DemarcheRunner

        runner = DemarcheRunner(host="cloud", on_screen=state.push_screen)

    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=IN_RATE,
            audio_out_sample_rate=OUT_RATE,
            add_wav_header=False,
            serializer=WidgetSerializer(state),
            allowed_origins=[],
        ),
    )
    voice = ColetteVoice(state, runner, transport=transport,
                         pipeline_params={"audio_in_sample_rate": IN_RATE, "audio_out_sample_rate": OUT_RATE})

    @transport.event_handler("on_client_disconnected")
    async def _gone(_t, _ws):
        logger.info("Session {} : bulle déconnectée", sid)
        await voice.stop()

    try:
        await voice.run()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Session {} en échec", sid)
    finally:
        try:
            await runner.cancel()
        except Exception:
            pass
        for fn in ("close", "aclose"):
            try:
                await getattr(runner, fn)()
            except Exception as e:
                logger.debug("Fin de l'agent ({}) : {}", fn, e)
        await state.stop()
