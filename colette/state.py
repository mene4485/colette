"""État Colette côté serveur, diffusé à la bulle.

L'état vit ici (pas dans la page) pour survivre aux navigations : la bulle est réinjectée
à chaque page et reçoit l'état complet.

Deux transports :
- CDP (principal, via colette/overlay.py) : Chrome ≥ 142 bloque ws://localhost depuis un site
  public (Local Network Access, net::ERR_BLOCKED_BY_LOCAL_NETWORK_ACCESS_CHECKS) ;
  l'overlay s'abonne avec add_listener() et relaie les messages via handle_message().
- WebSocket ws://localhost:8765 (secours : maquette servie en localhost, outils de debug).

Serveur → bulle : {"type": "state", "state": {...}} à chaque changement et à chaque connexion.
Bulle → serveur : {"type": "open"|"close"|"call"|"hangup"|"stop"|"pause"|"resume"|"reset"|"replay"
|"retry"|"advisor"|"later"}, {"type": "confirm", "value": bool} ou {"type": "shortcut", "id": "<skill>"}.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Callable, Optional, Union

from loguru import logger
from websockets.asyncio.server import ServerConnection, broadcast, serve

HOST = "localhost"
WS_PORT = 8765

STATUSES = ("idle", "listening", "speaking", "working", "paused", "awaiting_confirm", "done")

ClientMessageCallback = Callable[[dict], Union[None, Awaitable[None]]]


@dataclass
class ColetteState:
    open: bool = False
    status: str = "idle"
    steps: list[dict] = field(default_factory=list)  # [{"label": str, "state": "todo|doing|done"}]
    subtitle: str = ""  # ce que dit Colette (mots Cartesia) ou la question de l'agent H
    # {"text", "title", "bullets": [str], "yes", "no"} — carte d'accord (écran 6)
    confirm: Optional[dict] = None
    call: bool = False  # appel en cours (écran 3) : micro ouvert, conversation continue
    busy: bool = False  # démarche en cours : l'agent H agit sur la page (écran 5)
    heard: str = ""  # transcription en direct de la personne (« Vous dites : … »)
    title: str = ""  # titre de la démarche en cours
    # {"kind": "success|stopped|refused|failed", "title", "text", "summary": [str], "nothing_changed": bool}
    outcome: Optional[dict] = None
    shortcuts: list[dict] = field(default_factory=list)  # [{"id": skill, "label": str}] (écran 2)
    # mode en ligne : la personne se connecte elle-même sur SA page ; la bulle partage ensuite la session
    login_handoff: bool = False
    login_check: float = 0.0  # « c'est bon » entendu → la bulle vérifie la connexion et envoie le jeton
    transcript: list[dict] = field(default_factory=list)  # [{"who": "colette|vous", "text": str}] (6 dernières)
    # guide pas à pas (repli quand l'agent H ne peut pas agir) :
    # {"step", "text", "page", "target", "action", "irreversible"} — la bulle entoure l'élément
    guide: Optional[dict] = None


class StateServer:
    def __init__(self, host: str = HOST, port: int = WS_PORT) -> None:
        self.host = host
        self.port = port
        self.state = ColetteState()
        self._clients: set[ServerConnection] = set()
        self._callbacks: list[ClientMessageCallback] = []
        self._listeners: list[Callable[[dict], None]] = []
        self._confirm_future: Optional[asyncio.Future[bool]] = None
        self._status_before_confirm = "working"
        self._server = None
        # Lecture de la page de la personne pour le guide pas à pas (local : branché par l'overlay CDP).
        self.scanner: Optional[Callable[[], Awaitable[Optional[dict]]]] = None

    # ---- cycle de vie -------------------------------------------------------
    async def start(self) -> None:
        self._server = await serve(self._handler, self.host, self.port)
        logger.info("Serveur d'état WS sur ws://{}:{}", self.host, self.port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def on_client_message(self, callback: ClientMessageCallback) -> None:
        """Enregistre un callback appelé pour chaque message de la bulle (après traitement interne)."""
        self._callbacks.append(callback)

    def add_listener(self, listener: Callable[[dict], None]) -> None:
        """Appelé (synchrone) avec l'état complet à chaque changement — utilisé par l'overlay CDP."""
        self._listeners.append(listener)

    # ---- helpers d'état -----------------------------------------------------
    def snapshot(self) -> dict:
        return asdict(self.state)

    def _broadcast(self) -> None:
        snap = self.snapshot()
        if self._clients:
            broadcast(self._clients, json.dumps({"type": "state", "state": snap}, ensure_ascii=False))
        for listener in list(self._listeners):
            try:
                listener(snap)
            except Exception:
                logger.exception("Listener d'état en échec")

    def update(self, **changes: Any) -> None:
        for key, value in changes.items():
            if not hasattr(self.state, key):
                raise AttributeError(key)
            setattr(self.state, key, value)
        self._broadcast()

    def set_open(self, value: bool) -> None:
        self.update(open=value)

    def set_status(self, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(status)
        self.update(status=status)

    def set_subtitle(self, text: str) -> None:
        self.update(subtitle=text)

    def add_line(self, who: str, text: str) -> None:
        """Ajoute une phrase à la transcription affichée (petites lignes sous les étapes)."""
        text = " ".join((text or "").split())
        if not text:
            return
        lines = self.state.transcript
        if lines and lines[-1] == {"who": who, "text": text}:
            return
        self.update(transcript=(lines + [{"who": who, "text": text}])[-6:])

    def set_steps(self, labels: list[str]) -> None:
        self.update(steps=[{"label": label, "state": "todo"} for label in labels])

    def advance_step(self) -> None:
        """Termine l'étape en cours et démarre la suivante (ou la première)."""
        steps = self.state.steps
        for s in steps:
            if s["state"] == "doing":
                s["state"] = "done"
                break
        for s in steps:
            if s["state"] == "todo":
                s["state"] = "doing"
                break
        self._broadcast()

    def complete_through(self, number: int) -> None:
        """Étapes 1..number faites, la suivante en cours (etape_terminee de l'agent H)."""
        steps = self.state.steps
        if not steps or number < 1:
            return
        for i, s in enumerate(steps, start=1):
            if i <= number:
                s["state"] = "done"
            elif i == number + 1:
                s["state"] = "doing"
            elif s["state"] == "doing":
                s["state"] = "todo"
        self._broadcast()

    def finish_steps(self) -> None:
        for s in self.state.steps:
            s["state"] = "done"
        self._broadcast()

    def add_step(self, label: str) -> None:
        """Termine l'étape en cours et ajoute une nouvelle étape « doing » (étapes dynamiques)."""
        for s in self.state.steps:
            if s["state"] == "doing":
                s["state"] = "done"
        self.state.steps.append({"label": label, "state": "doing"})
        self._broadcast()

    @property
    def confirm_pending(self) -> bool:
        return self._confirm_future is not None and not self._confirm_future.done()

    def ask_confirm(self, text: str, *, title: str = "", bullets: Optional[list[str]] = None,
                    yes: str = "", no: str = "") -> asyncio.Future[bool]:
        """Affiche la carte d'accord ; la Future se résout au clic (ou via resolve_confirm)."""
        self.resolve_confirm(False)  # une seule question à la fois
        self._confirm_future = asyncio.get_running_loop().create_future()
        self._status_before_confirm = self.state.status
        card = {"text": text, "title": title or text, "bullets": list(bullets or []),
                "yes": yes or "Yes, I agree", "no": no or "No, don't change anything"}
        self.update(confirm=card, status="awaiting_confirm", open=True)
        return self._confirm_future

    def resolve_confirm(self, value: bool) -> None:
        """Résout la question en cours (clic bulle, ou réponse orale à l'étape 3)."""
        fut, self._confirm_future = self._confirm_future, None
        if fut is not None and not fut.done():
            fut.set_result(value)
        if self.state.confirm is not None:
            self.update(confirm=None, status=getattr(self, "_status_before_confirm", "working"))

    # ---- WebSocket ----------------------------------------------------------
    async def _handler(self, ws: ServerConnection) -> None:
        self._clients.add(ws)
        logger.debug("Bulle connectée ({} client(s))", len(self._clients))
        try:
            await ws.send(json.dumps({"type": "state", "state": self.snapshot()}, ensure_ascii=False))
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (TypeError, ValueError):
                    logger.warning("Message bulle illisible : {!r}", raw)
                    continue
                if isinstance(msg, dict) and msg.get("type"):
                    await self.handle_message(msg)
        except Exception as e:  # déconnexion brutale (navigation) : normal
            logger.debug("Bulle déconnectée : {}", e)
        finally:
            self._clients.discard(ws)

    def _on_scan_result(self, msg: dict) -> None:
        pass

    async def scan_page(self) -> Optional[dict]:
        """Page de la personne lue par la bulle (window.__colette.scan()), ou None."""
        return await self.scanner() if self.scanner is not None else None

    @property
    def can_scan(self) -> bool:
        return self.scanner is not None

    async def handle_message(self, msg: dict) -> None:
        """Traite un message de la bulle (quel que soit le transport)."""
        mtype = msg["type"]
        if mtype == "scan_result":  # réponse de la bulle à une lecture de page (mode en ligne)
            self._on_scan_result(msg)
            return
        if mtype == "debug_click":
            logger.info("🖱️  clic {}x{} sur {}x{} → {} (trusted={})", msg.get("x"), msg.get("y"),
                        msg.get("w"), msg.get("h"), msg.get("target"), msg.get("trusted"))
            return
        if mtype == "text":  # texte tapé (peut être un mot de passe) : jamais dans les logs
            logger.info("Bulle → texte tapé ({} caractères)", len(str(msg.get("text") or "")))
        else:
            logger.info("Bulle → {}", json.dumps(msg, ensure_ascii=False))
        if mtype == "open":
            self.set_open(True)
        elif mtype == "close":  # replie le panneau ; l'appel et la démarche continuent
            self.update(open=False)
        elif mtype == "later":
            self.update(open=False, call=False, heard="")
        elif mtype in ("call", "shortcut"):
            self.update(open=True, call=True, heard="",
                        status="listening" if self.state.status in ("idle", "done", "paused") else self.state.status)
        elif mtype == "hangup":
            self.update(call=False, heard="", status="idle" if not self.state.busy else self.state.status)
        elif mtype == "reset":
            self.update(outcome=None, steps=[], title="", heard="")
        elif mtype == "new_session":  # « New request » en local : tout repart de zéro
            self.resolve_confirm(False)
            self.update(outcome=None, steps=[], title="", heard="", subtitle="", transcript=[],
                        guide=None, confirm=None, login_handoff=False)
        elif mtype == "confirm":
            self.resolve_confirm(bool(msg.get("value")))
        elif mtype == "pause":
            self.set_status("paused")
        elif mtype == "resume":
            if self.state.status == "paused":
                self.set_status("working" if self.state.busy else "listening")
        elif mtype == "stop":
            self.resolve_confirm(False)
            self.set_status("idle")
        for cb in list(self._callbacks):
            try:
                result = cb(msg)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Callback on_client_message en échec")
