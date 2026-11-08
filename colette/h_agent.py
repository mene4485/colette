"""Mini-agent H jetable derrière une interface stable (`DemarcheRunner`).

L'agent H (Agents API, environnement `host: user_device`) pilote le Chrome local
(port 9222, profil persistant ~/.hai/chrome-profile). L'agent d'Oleksander
remplacera l'implémentation en gardant le même contrat.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Union

import httpx
from hai_agents import AsyncClient
from hai_agents.tools import tool
from loguru import logger

from colette.chrome import ensure_chrome
from colette.h_cleanup import delete_pending_channels, utcnow
from colette import site
from colette.skills_loader import load_skills

TERMINAL = {"completed", "failed", "timed_out", "interrupted"}

DEMO_EXCEPTION = (
    " On the online demo, after the login, the ask_user reply may contain an http address: open it in "
    "the address bar, it logs you in with the person's session."
)


@dataclass
class Step:
    """Une étape visible par l'utilisateur (narration, page, capture)."""

    text: str
    url: Optional[str] = None
    screenshot_url: Optional[str] = None
    kind: str = "step"  # "step" (message de l'agent) | "page" (nouvelle page) | "status"
    raw: dict = field(default_factory=dict, repr=False)


OnStep = Callable[[Step], Union[None, Awaitable[None]]]
AskUser = Callable[[str], Awaitable[str]]
OnPlan = Callable[[list[str]], Union[None, Awaitable[None]]]  # annoncer_etapes
OnStepDone = Callable[[int], Union[None, Awaitable[None]]]  # etape_terminee (numéro à partir de 1)
Confirm = Callable[[str, bool], Awaitable[bool]]  # confirm_change(summary, costs_money) → oui ?

H_SKILLS = ["h/visual-browser", "h/answering", "h/planning"]
VALIDATE_STEP = "Confirm with your approval"
APPROVED = "Approved by the user: proceed."
REFUSED = "Not done: the user refused. Stop."

DEFAULT_INSTRUCTIONS = (
    "You help an elderly person do an online task in HER browser. "
    "At each step, write in your message a short and simple English sentence saying what you are doing "
    "(e.g. \"I'm opening your plan page.\"). "
    "If some information is missing (ID, a choice, a code received by text message), or if a login page "
    "appears, call the ask_user tool and wait for the answer; never guess. "
    "Ask aloud only for short choices. " + 'Information to TYPE (address, email, phone number, name, any text): never ask for it aloud and never type it from what she said. Open the form, click the first field to fill, then call `ask_user` with exactly: "Please type your new <what> yourself in the form, then say done." Wait for her answer. If the answer is the text itself, type it in the field; otherwise read what she typed in the fields. Then call `confirm_change` with the old and new values before saving. ' +
    "Never type a password yourself: ask the person to type it. "
    "Never click a button that validates, pays, cancels, sends or downloads something until confirm_change has "
    "answered \"Approved\" (or a message explicitly told you the person confirmed aloud); otherwise stop "
    "before it and answer. "
    "A purple \"Colette\" bubble (and its panel) is shown at the bottom right of every page: it is your "
    "interface with the person, it is not part of the website. Ignore it, never click it (nor its Pause, "
    "Stop or × buttons), never try to close it and don't confuse it with the website's support chat. "
    "Clicks go through it: if a website element is partly hidden behind it, just click that element. "
    "Before any action on the website, read the skill that matches the task (if there is one), then "
    "call annoncer_etapes with 3 to 6 short English steps the person can understand "
    f"(e.g. \"Open your customer area\"). If an action will need to be validated, the last step is "
    f"exactly \"{VALIDATE_STEP}\". Then call etape_terminee(numero) at the end of each step. "
    "Before any irreversible action (a click that validates, pays, cancels, saves, sends, submits, "
    "deletes or downloads a file), call confirm_change "
    "with a short English summary (what the button would do, price and date) and costs_money=true if it "
    "changes what the person pays; click only if the reply says \"Approved\". If a login, a password or "
    "a text-message code is requested, call ask_user so that the person types it herself, then wait."
)


def describe_action(req: dict) -> str:
    """Phrase courte en français décrivant une action Holo (go_to_web, click_web…)."""
    name = req.get("tool_name") or ""
    args = req.get("args") or {}
    element = (args.get("element") or "").strip()
    if name in ("ask_user", "answer", "annoncer_etapes", "etape_terminee", "confirm_change"):
        return ""  # déjà remonté par le tool lui-même (question, plan, carte OUI/NON)
    if name == "go_to_web":
        return f"I'm opening {args.get('url', 'the page')}"
    if name in ("click_web", "double_click_web"):
        return f"I'm clicking {element}" if element else "I'm clicking"
    if name in ("write_web", "type_web", "fill_web"):
        return f"I'm typing in {element}" if element else "I'm typing"
    if name == "scroll_web":
        return "I'm scrolling the page"
    if name == "wait_web":
        return "I'm waiting for the page to load"
    if name == "refresh_web":
        return "I'm reloading the page"
    if name == "press_keys_web":
        return f"I'm pressing {'+'.join(args.get('keys') or [])}"
    if name in ("go_back_web", "back_web"):
        return "I'm going back to the previous page"
    return name.replace("_web", "").replace("_", " ")


async def _maybe_await(value: Any) -> None:
    if inspect.isawaitable(value):
        await value


CONFIRMATION_PREFIX = "CONFIRMATION:"


def split_confirmation(answer: str) -> tuple[str, Optional[str]]:
    """Sépare la ligne `CONFIRMATION: …` de la réponse de phase 1.

    Renvoie (réponse sans la ligne, action à confirmer) ; action = None si absente ou « aucune ».
    """
    body, action = [], None
    for line in (answer or "").splitlines():
        stripped = line.strip().lstrip("*-# ").strip()
        if stripped.upper().startswith(CONFIRMATION_PREFIX):
            value = stripped[len(CONFIRMATION_PREFIX):].strip().strip("*«»\"' ").rstrip(".")
            if value and value.lower() not in ("aucune", "aucun", "rien", "none", "non"):
                action = value
        else:
            body.append(line)
    return "\n".join(body).strip(), action


def make_tools(
    *,
    on_plan: Optional[OnPlan] = None,
    on_step_done: Optional[OnStepDone] = None,
    confirm: Optional[Confirm] = None,
) -> list:
    """Custom tools H reliés à la bulle : annoncer_etapes, etape_terminee, confirm_change."""
    tools = []
    if on_plan is not None:

        async def annoncer_etapes(etapes: list[str]) -> str:
            """Call FIRST, before any action on the website (after reading the task's skill): the list of
            the 3 to 6 steps you will follow, each short, in simple English an elderly person understands
            (e.g. "Open your customer area"). If an action will need to be validated, the last step is
            exactly "Confirm with your approval". They are shown and read to the person."""
            labels = [str(e).strip() for e in etapes or [] if str(e).strip()][:8]
            if not labels:
                return "Empty list: give at least one step."
            logger.info("📋 annoncer_etapes {}", labels)
            await _maybe_await(on_plan(labels))
            return ("Steps shown to the person. Call etape_terminee(numero) at the end of each step "
                    "(numbers start at 1).")

        tools.append(tool(annoncer_etapes, name="annoncer_etapes"))
    if on_step_done is not None:

        async def etape_terminee(numero: int) -> str:
            """Call at the end of each step announced with annoncer_etapes (numero starts at 1).
            Ticks the step in the person's display."""
            logger.info("✅ etape_terminee({})", numero)
            await _maybe_await(on_step_done(int(numero)))
            return "OK"

        tools.append(tool(etape_terminee, name="etape_terminee"))
    if confirm is not None:

        async def confirm_change(summary: str, costs_money: bool = False) -> str:
            """Call RIGHT BEFORE any click that validates, pays, cancels, saves or sends something.
            summary: in English, what the button would do, starting with a verb, with the price and date
            shown (e.g. "switch to the €2 Plan, €2 per month, starting December 1"). costs_money: true if
            it changes what the person pays. The person answers yes or no aloud. Click only if the reply
            starts with "Approved"; if it starts with "Not done", follow its instructions (the person may
            want another choice), otherwise do not click, stop and answer."""
            logger.info("✋ confirm_change({!r}, costs_money={})", summary, costs_money)
            ok = await confirm(str(summary or "").strip(), bool(costs_money))
            if isinstance(ok, str):  # correction de la personne (« non, celui à 29,99 € ») : consigne pour H
                return ok
            return APPROVED if ok else REFUSED

        tools.append(tool(confirm_change, name="confirm_change"))
    return tools


class DemarcheRunner:
    """Lance une démarche dans le Chrome local et remonte les étapes.

    Contrat (à garder pour l'agent d'Oleksander ; `colette/fake_runner.py` le suit aussi) :

        answer = await run(goal, on_step, ask_user=None, *, on_plan=None, on_step_done=None,
                           confirm=None) -> str
            on_plan(étapes) : l'agent annonce son plan (tool `annoncer_etapes`, en premier).
            on_step_done(n) : l'étape n (à partir de 1) est finie (tool `etape_terminee`).
            confirm(summary, costs_money) -> bool : tool `confirm_change`, appelé juste avant le
            clic qui valide ; bloque jusqu'au oui/non de la personne. Si oui, l'agent valide
            lui-même dans la même phase.
            Garde-fou si l'agent n'appelle pas confirm_change : il s'arrête au récapitulatif et
            termine par une ligne `CONFIRMATION: <action + prix, verbe à l'infinitif>`
            (ou `CONFIRMATION: aucune`) — voir `split_confirmation()`.
            La session H reste ouverte (`idle`, idle_timeout_s=300) pour la phase 2.
        answer = await follow_up(message) -> str
            Phase 2, DANS LA MÊME SESSION, appelée par notre code (jamais par le LLM)
            seulement après un « oui » oral explicite ou un clic OUI. Mêmes on_step / ask_user.
        await close()
            Termine la session et libère le slot du quota H. Toujours appelée à la fin de la
            démarche (oui, non, stop ou erreur). Idempotente.
        await cancel() / pause() / resume()
            Bouton ou commande vocale Stop / Pause / Reprise pendant que l'agent travaille.
            Après cancel(), run()/follow_up() rendent la main (réponse vide ou exception).

        on_step(Step) peut être sync ou async ; il doit rendre la main vite (pas d'attente longue).
        ask_user(question) -> réponse orale de la personne (str).
    """

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        instructions: Optional[str] = None,
        max_time_s: float = 900,
        log_dir: Union[str, Path] = "logs",
        host: str = "user_device",
        on_screen: Optional[Callable[[dict], Union[None, Awaitable[None]]]] = None,
    ) -> None:
        self.model = model or os.getenv("HAI_MODEL") or None
        if instructions is None:
            instructions = DEFAULT_INSTRUCTIONS + (DEMO_EXCEPTION if site.is_demo() else "")
        self.instructions = instructions
        # "user_device" : Chrome local :9222 (bridge) · "cloud" : navigateur hébergé par H (mode en ligne)
        self.host = host
        # mode cloud : appelé à chaque capture {"url", "title", "image": bytes PNG, "cursor": [x, y], "viewport": [w, h]}
        self.on_screen = on_screen
        self.start_url_override: Optional[str] = None
        self.max_time_s = max_time_s
        self.log_dir = Path(log_dir)
        self._client: Optional[AsyncClient] = None
        self._session = None
        self.session_id: Optional[str] = None
        self.status: Optional[str] = None
        self.idle_timeout_s = 300  # la session reste ouverte après la phase 1 (follow_up)
        self._on_step: Optional[OnStep] = None
        self._raw_path: Optional[Path] = None
        self._run_started: Optional[datetime] = None
        self._next_index = 0  # curseur d'events déjà lus (le follow_up repart d'ici)

    def _agent_spec(self, tools: list) -> dict:
        skills = load_skills()
        logger.info("Skills : {} + {}", H_SKILLS, [s["name"] for s in skills])
        spec: dict[str, Any] = {
            "name": "colette-local",
            "description": "Helps an elderly person do an online task in her own browser.",
            "instructions": self.instructions,
            "environments": [self._environment()],
            "skills": H_SKILLS + skills,
        }
        if self.model:
            spec["model"] = self.model
        return spec

    def _environment(self) -> dict:
        if self.host == "cloud":
            # start_url_override : session de la personne (déjà connectée, sur sa page actuelle)
            url = getattr(self, "start_url_override", None) or site.start_url()
            return {"id": "web", "kind": "web", "host": "cloud", "start_url": url}
        return {"id": "laptop", "kind": "web", "host": "user_device"}

    async def _push_screen(self, image_url: str, meta: dict) -> None:
        """Mode cloud : télécharge la capture (URL protégée par la clé H) et la passe à on_screen."""
        if self.on_screen is None or self._client is None:
            return
        try:
            key = os.getenv("HAI_API_KEY", "")
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as http:
                r = await http.get(image_url, headers={"Authorization": f"Bearer {key}"})
            if r.status_code != 200:
                logger.debug("Capture H {} → HTTP {}", image_url[-40:], r.status_code)
                return
            await _maybe_await(self.on_screen({
                "url": meta.get("url"), "title": meta.get("title"), "image": r.content,
                "media_type": r.headers.get("content-type", "image/png"),
                "cursor": meta.get("cursor_position"), "viewport": meta.get("viewport_size"),
            }))
        except Exception as e:
            logger.debug("Capture H non relayée : {}", e)

    async def run(
        self,
        goal: str,
        on_step: OnStep,
        ask_user: Optional[AskUser] = None,
        *,
        on_plan: Optional[OnPlan] = None,
        on_step_done: Optional[OnStepDone] = None,
        confirm: Optional[Confirm] = None,
    ) -> str:
        if self._client is None:
            self._client = AsyncClient()  # lit HAI_API_KEY

        tools = make_tools(on_plan=on_plan, on_step_done=on_step_done, confirm=confirm)
        if ask_user is not None:

            async def ask_user_tool(question: str) -> str:
                """Asks the person a question (aloud) and returns her answer.
                Use it for any missing information or a login to do."""
                await _maybe_await(on_step(Step(text=question, kind="question")))
                answer = await ask_user(question)
                # La page a pu changer pendant l'attente (la personne s'est connectée, a cliqué…) :
                # sa dernière capture est périmée. Constaté au vrai run : Holo recliquait sur
                # « Se connecter » alors que la personne était déjà connectée.
                return (f"{answer or '(no answer)'}\n"
                        "Careful: the page may have changed while you were waiting (the person may have "
                        "logged in or clicked herself). Before any other action, do wait_web 1 second to "
                        "see the updated page, then decide from that new screenshot; do not click "
                        "\"Log in\" again if the person is already logged in.")

            tools.append(tool(ask_user_tool, name="ask_user"))

        if self.host != "cloud":
            await asyncio.to_thread(ensure_chrome)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        raw_path = self.log_dir / f"h_events_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
        logger.info("Events bruts → {}", raw_path)

        # Marge de 5 s : le canal du bridge est créé juste après la session.
        self._run_started = utcnow() - timedelta(seconds=5)
        self._session = None
        self._on_step = on_step
        self._raw_path = raw_path
        self._next_index = 0
        try:
            self._session = await self._client.start_session(
                agent=self._agent_spec(tools),
                messages=goal,
                tools=tools or None,
                max_time_s=self.max_time_s,
                idle_timeout_s=self.idle_timeout_s,
                timezone="Europe/Paris",
            )
            return await self._stream(raw_path, on_step)
        except BaseException:
            await self.close()
            raise

    async def follow_up(self, message: str) -> str:
        """Phase 2 : envoie un message dans la même session et attend la nouvelle réponse."""
        if self._session is None or self._on_step is None:
            raise RuntimeError("follow_up() sans session ouverte (run() d'abord, close() pas encore appelé)")
        status = str((await self._client.sessions.get_session_status(self._session.id)).status)
        if status in TERMINAL:
            raise RuntimeError(f"La session H est déjà terminée ({status}) : impossible de valider")
        logger.info("Follow-up H : {}", message)
        try:
            await self._session.send_message(message)
            # Le stream s'arrête dès que la session est « settled » (idle) : attendre qu'elle
            # reparte, sinon on relirait l'état idle de la phase 1.
            for _ in range(40):
                status = str((await self._client.sessions.get_session_status(self._session.id)).status)
                if status != "idle":
                    break
                await asyncio.sleep(0.5)
            else:
                logger.warning("La session H est restée idle après le follow-up")
            return await self._stream(self._raw_path, self._on_step)
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        """Termine la session (si besoin) et libère son canal. Idempotente."""
        if self._session is None and self._run_started is None:
            return
        since = self._run_started or utcnow()
        await self._cleanup(since)
        self._session = None
        self._run_started = None
        self._on_step = None

    async def _cleanup(self, since: datetime) -> None:
        """Termine la session si besoin et supprime son canal : libère le slot du quota H."""
        try:
            if self._session is not None:
                status = str((await self._client.sessions.get_session_status(self._session.id)).status)
                if status not in TERMINAL:
                    logger.info("Session {} encore `{}` → cancel", self._session.id[:8], status)
                    await self._session.cancel()
        except Exception as e:
            logger.debug("Fin de session H non confirmée : {}", e)
        if self.host == "cloud":
            return
        try:
            n = await delete_pending_channels(since=since)
            if n:
                logger.info("{} canal(aux) H libéré(s)", n)
        except Exception as e:
            logger.warning("Nettoyage des canaux H impossible : {}", e)

    async def _stream(self, raw_path: Path, on_step: OnStep) -> str:
        self.session_id = self._session.id
        logger.info("Session H {}", self.session_id)
        try:
            info = await self._session.get()
            url = getattr(info, "agent_view_url", None)
            if url:
                logger.info("Agent View : {}", url)
        except Exception as e:  # non bloquant
            logger.debug("get() impossible : {}", e)

        answer: Optional[str] = None
        last_url: Optional[str] = None
        with raw_path.open("a") as raw:
            async for ev in self._session.stream(from_index=self._next_index, timeout_seconds=self.max_time_s + 60):
                self._next_index += 1
                d = ev.model_dump(mode="json")
                raw.write(json.dumps(d, ensure_ascii=False) + "\n")
                raw.flush()
                etype = d.get("type")
                data = d.get("data") or {}

                if etype == "AgentEvent":
                    kind = data.get("kind")
                    if kind == "policy_event":
                        content = (data.get("content") or "").strip()
                        # Holo n'écrit souvent aucun message : on narre à partir des actions.
                        content = content or "; ".join(
                            filter(None, (describe_action(r) for r in data.get("tool_reqs") or []))
                        )
                        if content:
                            await _maybe_await(on_step(Step(text=content, url=last_url, raw=data)))
                    elif kind == "observation_event":
                        meta = data.get("metadata") or {}
                        url = meta.get("url")
                        image = data.get("image") or {}
                        if self.on_screen is not None and image.get("type") == "url" and image.get("source"):
                            asyncio.create_task(self._push_screen(image["source"], meta))
                        if url and url != last_url:
                            last_url = url
                            image = data.get("image") or {}
                            await _maybe_await(
                                on_step(
                                    Step(
                                        text=meta.get("title") or url,
                                        url=url,
                                        screenshot_url=image.get("source") if image.get("type") == "url" else None,
                                        kind="page",
                                        raw={"metadata": {k: meta.get(k) for k in ("url", "title")}},
                                    )
                                )
                            )
                    elif kind == "answer_event":
                        answer = data.get("answer")
                    elif kind == "error_event":
                        logger.warning("Erreur d'étape H : {}", data.get("error"))
                elif etype == "AgentRunStatusChangeEvent":
                    await _maybe_await(on_step(Step(text=str(data.get("status")), kind="status")))
                elif etype == "AgentErrorEvent":
                    logger.error("Agent H en échec : {}", data.get("error"))

        result = await self._session.wait_for_completion()
        self.status = str(result.status)
        logger.info("Fin de session : status={} outcome={}", result.status, result.outcome)
        if result.error:
            logger.error("Erreur : {} ({})", result.error, result.error_code)
        # La réponse de CE tour (answer_event) d'abord : après un follow-up, result.answer
        # pourrait encore être celle de la phase 1.
        final = answer if answer is not None else result.answer
        if final is None:
            return ""
        return final if isinstance(final, str) else json.dumps(final, ensure_ascii=False, default=str)

    async def cancel(self) -> None:
        if self._session is not None:
            await self._session.cancel()

    async def h_available(self) -> Optional[int]:
        """Places libres dans le quota de sessions H (3 sur notre plan), ou None si inconnu."""
        try:
            base = os.getenv("HAI_BASE_URL", "https://agp.eu.hcompany.ai")
            async with httpx.AsyncClient(base_url=base, timeout=4, trust_env=False,
                                         headers={"Authorization": f"Bearer {os.getenv('HAI_API_KEY', '')}"}) as http:
                r = await http.get("/api/v2/sessions/quota")
            return int(r.json()["available"]) if r.status_code == 200 else None
        except Exception as e:
            logger.debug("Quota H inconnu : {}", e)
            return None

    async def pause(self) -> None:
        if self._session is not None:
            await self._session.pause()

    async def resume(self) -> None:
        # Pas de message « regarde à nouveau » : Holo prend une capture à chaque action, il voit
        # donc la page telle que la personne l'a laissée. (Un message envoyé pendant que l'agent
        # travaille ouvrirait un tour en plus après sa réponse et fausserait la phase 2.)
        if self._session is not None:
            await self._session.resume()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
