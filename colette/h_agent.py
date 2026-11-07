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

from hai_agents import AsyncClient
from hai_agents.tools import tool
from loguru import logger

from colette.chrome import ensure_chrome
from colette.h_cleanup import delete_pending_channels, utcnow

TERMINAL = {"completed", "failed", "timed_out", "interrupted"}


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

DEFAULT_INSTRUCTIONS = (
    "Tu aides une personne âgée à faire une démarche en ligne dans SON navigateur. "
    "À chaque étape, écris dans ton message une phrase courte et simple en français qui dit "
    "ce que tu fais (ex. « J'ouvre la page de votre forfait. »). "
    "Si une information te manque (identifiant, choix, code reçu par SMS), ou si une page de "
    "connexion apparaît, appelle l'outil ask_user et attends la réponse ; ne devine jamais. "
    "Ne tape jamais de mot de passe toi-même : demande à la personne de le taper. "
    "Ne clique jamais sur un bouton qui valide, paie, résilie ou envoie quelque chose tant qu'un "
    "message ne t'a pas dit explicitement que la personne a confirmé à voix haute ; arrête-toi "
    "avant et réponds. "
    "Une bulle violette « Colette » (et son panneau) s'affiche en bas à droite de chaque page : "
    "c'est ton interface avec la personne, elle ne fait pas partie du site. Ignore-la, ne clique "
    "jamais dessus (ni sur ses boutons Pause, Stop ou ×), n'essaie pas de la fermer et ne la "
    "confonds pas avec le chat d'assistance du site. Elle laisse passer les clics : si un élément "
    "du site est en partie caché derrière elle, clique simplement sur cet élément."
)


def describe_action(req: dict) -> str:
    """Phrase courte en français décrivant une action Holo (go_to_web, click_web…)."""
    name = req.get("tool_name") or ""
    args = req.get("args") or {}
    element = (args.get("element") or "").strip()
    if name in ("ask_user", "answer"):
        return ""  # la question est déjà remontée par le tool
    if name == "go_to_web":
        return f"J'ouvre {args.get('url', 'la page')}"
    if name in ("click_web", "double_click_web"):
        return f"Je clique sur {element}" if element else "Je clique"
    if name in ("write_web", "type_web", "fill_web"):
        return f"J'écris dans {element}" if element else "J'écris"
    if name == "scroll_web":
        return "Je fais défiler la page"
    if name == "wait_web":
        return "J'attends que la page se charge"
    if name == "refresh_web":
        return "Je recharge la page"
    if name == "press_keys_web":
        return f"J'appuie sur {'+'.join(args.get('keys') or [])}"
    if name in ("go_back_web", "back_web"):
        return "Je reviens à la page précédente"
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


class DemarcheRunner:
    """Lance une démarche dans le Chrome local et remonte les étapes.

    Contrat (à garder pour l'agent d'Oleksander ; `colette/fake_runner.py` le suit aussi) :

        answer = await run(goal, on_step, ask_user=None) -> str
            Phase 1. L'agent va jusqu'au récapitulatif et S'ARRÊTE sans rien valider.
            La réponse se termine par une ligne `CONFIRMATION: <action + prix, verbe à
            l'infinitif>` (ou `CONFIRMATION: aucune`) — voir `split_confirmation()`.
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
        instructions: str = DEFAULT_INSTRUCTIONS,
        max_time_s: float = 900,
        log_dir: Union[str, Path] = "logs",
    ) -> None:
        self.model = model or os.getenv("HAI_MODEL") or None
        self.instructions = instructions
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
        spec: dict[str, Any] = {
            "name": "colette-local",
            "description": "Aide une personne âgée à faire une démarche dans son propre Chrome.",
            "instructions": self.instructions,
            "environments": [{"id": "laptop", "kind": "web", "host": "user_device"}],
        }
        if self.model:
            spec["model"] = self.model
        return spec

    async def run(self, goal: str, on_step: OnStep, ask_user: Optional[AskUser] = None) -> str:
        if self._client is None:
            self._client = AsyncClient()  # lit HAI_API_KEY

        tools = []
        if ask_user is not None:

            async def ask_user_tool(question: str) -> str:
                """Pose une question à la personne (à l'oral) et renvoie sa réponse.
                À utiliser pour toute information manquante, une connexion à faire,
                ou une confirmation avant une action irréversible."""
                await _maybe_await(on_step(Step(text=question, kind="question")))
                answer = await ask_user(question)
                return answer or "(pas de réponse)"

            tools.append(tool(ask_user_tool, name="ask_user"))

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
