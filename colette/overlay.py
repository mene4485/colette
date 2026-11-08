"""Injecte la bulle Colette (static/widget.js) dans chaque page du Chrome :9222 via CDP.

Une connexion CDP navigateur (en plus de celle du chromedriver de H) :
Target.setDiscoverTargets → pour chaque onglet : attachToTarget(flatten) puis, sur la session,
Page.enable, Page.setBypassCSP (connect-src de free.fr), addScriptToEvaluateOnNewDocument
(chaque navigation) et Runtime.evaluate (page déjà chargée). Reconnexion si Chrome redémarre.

Transport bulle ↔ serveur aussi par CDP (Chrome bloque ws://localhost depuis free.fr :
Local Network Access) : Runtime.addBinding("__coletteSend") → Runtime.bindingCalled → StateServer ;
état poussé dans chaque onglet par Runtime.evaluate("window.__colette.onState(...)").
"""

from __future__ import annotations

import asyncio
import itertools
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import httpx
from loguru import logger
from websockets.asyncio.client import ClientConnection, connect

from colette.chrome import PORT

if TYPE_CHECKING:
    from colette.state import StateServer

WIDGET_PATH = Path(__file__).resolve().parent / "static" / "widget.js"
BINDING = "__coletteSend"


class CDPError(RuntimeError):
    pass


class OverlayInjector:
    def __init__(self, state: "Optional[StateServer]" = None, script_path: Path = WIDGET_PATH,
                 port: int = PORT) -> None:
        self.state = state
        self.script_path = script_path
        self.port = port
        self._ws: Optional[ClientConnection] = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._attached: dict[str, str] = {}  # targetId → sessionId
        self._attaching: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
        self.injections = 0  # nb de pages initialisées (debug / tests)
        if state is not None:
            state.add_listener(self._on_state)
            state.scanner = self.scan_active  # guide pas à pas : lecture de la page de la personne

    # ---- CDP bas niveau -----------------------------------------------------
    async def send(self, method: str, params: Optional[dict] = None, session_id: Optional[str] = None,
                   timeout: float = 10.0) -> dict:
        if self._ws is None:
            raise CDPError("CDP non connecté")
        msg_id = next(self._ids)
        msg: dict[str, Any] = {"id": msg_id, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        fut = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut
        await self._ws.send(json.dumps(msg))
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(msg_id, None)

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ---- boucle principale --------------------------------------------------
    async def run_forever(self) -> None:
        while True:
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Overlay CDP déconnecté ({}) — nouvelle tentative dans 2 s", e)
            await asyncio.sleep(2)

    async def _browser_ws_url(self) -> str:
        async with httpx.AsyncClient(trust_env=False, timeout=3.0) as http:
            r = await http.get(f"http://127.0.0.1:{self.port}/json/version")
            return r.json()["webSocketDebuggerUrl"]

    async def _run_once(self) -> None:
        url = await self._browser_ws_url()
        async with connect(url, max_size=None, ping_interval=None) as ws:
            self._ws = ws
            self._attached.clear()
            self._attaching.clear()
            logger.info("Overlay connecté au CDP navigateur ({})", url)
            reader = asyncio.create_task(self._reader(ws))
            try:
                await self.send("Target.setDiscoverTargets", {"discover": True})
                targets = (await self.send("Target.getTargets"))["targetInfos"]
                for t in targets:
                    self._maybe_attach(t)
                await reader
            finally:
                reader.cancel()
                self._ws = None
                self._attached.clear()
                self._maybe_close()  # Chrome fermé : plus de bulle, plus de micro
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(CDPError("connexion CDP fermée"))
                self._pending.clear()

    async def _reader(self, ws: ClientConnection) -> None:
        async for raw in ws:
            msg = json.loads(raw)
            if "id" in msg:
                fut = self._pending.get(msg["id"])
                if fut is not None and not fut.done():
                    if "error" in msg:
                        fut.set_exception(CDPError(f"{msg['error'].get('message')} ({msg['error'].get('code')})"))
                    else:
                        fut.set_result(msg.get("result") or {})
                continue
            method = msg.get("method")
            params = msg.get("params") or {}
            if method == "Target.targetCreated":
                self._maybe_attach(params["targetInfo"])
            elif method == "Target.targetDestroyed":
                self._attached.pop(params.get("targetId"), None)
                self._maybe_close()
            elif method == "Fetch.requestPaused":
                self._spawn(self._on_paused(msg.get("sessionId"), params))
            elif method == "Runtime.bindingCalled" and params.get("name") == BINDING:
                self._on_binding(msg.get("sessionId"), params.get("payload") or "")
            elif method == "Target.detachedFromTarget":
                tid = params.get("targetId")
                if tid and self._attached.get(tid) == params.get("sessionId"):
                    self._attached.pop(tid, None)
                    self._maybe_close()

    def _maybe_close(self) -> None:
        """Plus aucun onglet avec la bulle ? On revérifie dans 3 s : une navigation ou un nouvel
        onglet (PDF de facture…) ne doit jamais fermer Colette ni arrêter la démarche."""
        if self._attached or self.state is None:
            return
        if self._ws is None:  # Chrome fermé (connexion CDP perdue)
            self._close_call("Chrome fermé")
            return
        self._spawn(self._recheck_targets())

    async def _recheck_targets(self) -> None:
        await asyncio.sleep(3)
        if self._attached or self._ws is None:
            return
        try:
            targets = (await self.send("Target.getTargets"))["targetInfos"]
        except Exception:
            return
        pages = [t for t in targets if t.get("type") == "page"]
        for t in pages:  # onglet détaché (changement de processus) : on le reprend
            self._maybe_attach(t)
        if not pages:
            self._close_call("plus aucun onglet")

    def _close_call(self, why: str) -> None:
        st = self.state.state
        if st.open or st.call:
            logger.info("{} → bulle fermée, micro coupé (la démarche n'est pas arrêtée)", why)
            self.state.update(open=False, call=False)

    # ---- pont bulle ↔ StateServer ------------------------------------------
    def _on_binding(self, session_id: Optional[str], payload: str) -> None:
        try:
            msg = json.loads(payload)
        except ValueError:
            logger.warning("Message bulle illisible : {!r}", payload)
            return
        if not isinstance(msg, dict) or not msg.get("type"):
            return
        if msg["type"] == "hello":  # nouvelle page : on lui envoie l'état courant
            if self.state is not None and session_id:
                self._spawn(self._push(session_id, self.state.snapshot()))
                self._spawn(self.state.handle_message({"type": "page_loaded"}))  # guide pas à pas
            return
        if self.state is not None:
            self._spawn(self.state.handle_message(msg))

    def _on_state(self, snapshot: dict) -> None:
        if self._ws is None:
            return
        for sid in list(self._attached.values()):
            self._spawn(self._push(sid, snapshot))

    async def _push(self, session_id: str, snapshot: dict) -> None:
        expr = ("window.__colette && window.__colette.onState && window.__colette.onState("
                + json.dumps(snapshot, ensure_ascii=False) + ")")
        try:
            await self.send("Runtime.evaluate", {"expression": expr}, session_id=session_id, timeout=5.0)
        except Exception as e:  # onglet en pleine navigation : la page renverra « hello »
            logger.debug("Push d'état impossible ({}) : {}", session_id[:8], e)

    # ---- barrière fichiers (téléchargement / ouverture d'un PDF) ---------------------
    @staticmethod
    def _is_file(params: dict) -> bool:
        headers = {h.get("name", "").lower(): h.get("value", "") for h in params.get("responseHeaders") or []}
        ctype = headers.get("content-type", "").lower()
        disp = headers.get("content-disposition", "").lower()
        url = (params.get("request") or {}).get("url", "").lower()
        return ("attachment" in disp or "application/pdf" in ctype or "application/octet-stream" in ctype
                or url.split("?")[0].endswith(".pdf"))

    async def _on_paused(self, session_id: Optional[str], params: dict) -> None:
        rid = params.get("requestId")
        allow = True
        url = (params.get("request") or {}).get("url", "")
        if "responseStatusCode" not in params and "responseErrorReason" not in params:  # étape requête
            if params.get("resourceType") == "Document" and self.state is not None and self.state.nav_gate is not None:
                allow = bool(self.state.nav_gate(url))
            try:
                if allow:
                    await self.send("Fetch.continueRequest", {"requestId": rid}, session_id=session_id, timeout=5.0)
                else:
                    await self.send("Fetch.failRequest", {"requestId": rid, "errorReason": "BlockedByClient"},
                                    session_id=session_id, timeout=5.0)
            except Exception as e:
                logger.debug("Fetch : requête {} déjà partie ({})", rid, e)
            return
        if self._is_file(params) and self.state is not None and self.state.file_gate is not None:
            url = (params.get("request") or {}).get("url", "")
            try:
                allow = bool(await self.state.file_gate(url))
            except Exception as e:
                logger.warning("Barrière fichiers en échec ({}) → bloqué", e)
                allow = False
        try:
            if allow:
                await self.send("Fetch.continueRequest", {"requestId": rid}, session_id=session_id, timeout=5.0)
            else:
                logger.info("🛑 Fichier bloqué (pas d'accord) : {}", (params.get("request") or {}).get("url", "")[:120])
                await self.send("Fetch.failRequest", {"requestId": rid, "errorReason": "BlockedByClient"},
                                session_id=session_id, timeout=5.0)
        except Exception as e:
            logger.debug("Fetch : requête {} déjà partie ({})", rid, e)

    # ---- évaluation dans l'onglet de la personne (guide pas à pas) ---------------
    async def _eval(self, session_id: str, expr: str, timeout: float = 5.0):
        res = await self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True},
                              session_id=session_id, timeout=timeout)
        if res.get("exceptionDetails"):
            raise CDPError(str(res["exceptionDetails"].get("text") or "exception JS"))
        return (res.get("result") or {}).get("value")

    async def active_session(self) -> Optional[str]:
        """Onglet que la personne regarde : focus d'abord, sinon onglet visible."""
        best, best_score = None, -1
        probe = "({f: document.hasFocus(), v: document.visibilityState === 'visible'})"
        for sid in list(self._attached.values()):
            try:
                info = await self._eval(sid, probe, timeout=2.0) or {}
            except Exception:
                continue
            score = 2 * bool(info.get("f")) + bool(info.get("v"))
            if score > best_score:
                best, best_score = sid, score
        return best

    async def scan_active(self) -> Optional[dict]:
        sid = await self.active_session()
        if sid is None:
            return None
        return await self._eval(sid, "window.__colette && window.__colette.scan ? window.__colette.scan() : null")

    # ---- injection par onglet ----------------------------------------------
    def _maybe_attach(self, info: dict) -> None:
        tid = info.get("targetId")
        if info.get("type") != "page" or not tid:
            return
        if tid in self._attached or tid in self._attaching:
            return
        if (info.get("url") or "").startswith(("devtools://", "chrome-extension://")):
            return
        self._attaching.add(tid)
        self._spawn(self._setup_target(tid, info.get("url") or ""))

    async def _setup_target(self, target_id: str, url: str) -> None:
        try:
            script = self.script_path.read_text(encoding="utf-8")  # relu à chaque fois : itérer sans redémarrer
            res = await self.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})
            sid = res["sessionId"]
            self._attached[target_id] = sid
            await self.send("Page.enable", session_id=sid)
            await self.send("Page.setBypassCSP", {"enabled": True}, session_id=sid)
            await self.send("Runtime.enable", session_id=sid)
            await self.send("Runtime.addBinding", {"name": BINDING}, session_id=sid)
            # Barrière fichiers : toute page / requête qui renvoie un fichier (PDF, facture, pièce jointe)
            # est mise en pause par Chrome ; elle ne passe qu'après l'accord oral de la personne.
            await self.send("Fetch.enable", {"patterns": [
                {"urlPattern": "*", "resourceType": "Document", "requestStage": "Request"},  # autre site ?
                {"urlPattern": "*", "resourceType": "Document", "requestStage": "Response"},
                {"urlPattern": "*invoice*", "requestStage": "Response"},
                {"urlPattern": "*facture*", "requestStage": "Response"},
                {"urlPattern": "*.pdf*", "requestStage": "Response"},
                {"urlPattern": "*download*", "requestStage": "Response"},
            ]}, session_id=sid)
            await self.send("Page.addScriptToEvaluateOnNewDocument", {"source": script}, session_id=sid)
            await self.send("Runtime.evaluate", {"expression": script, "awaitPromise": False}, session_id=sid)
            if self.state is not None:  # page déjà ouverte (bulle déjà là) : état courant
                await self._push(sid, self.state.snapshot())
            self.injections += 1
            logger.info("Bulle injectée dans l'onglet {} ({})", target_id[:8], url or "?")
        except Exception as e:
            self._attached.pop(target_id, None)
            logger.warning("Injection impossible dans {} : {}", target_id[:8], e)
        finally:
            self._attaching.discard(target_id)
