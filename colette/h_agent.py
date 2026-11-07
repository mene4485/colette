"""Mini-agent H jetable derrière une interface stable (`DemarcheRunner`).

L'agent H (Agents API, environnement `host: user_device`) pilote le Chrome local
(port 9222, profil persistant ~/.hai/chrome-profile). L'agent d'Oleksander
remplacera l'implémentation en gardant le même contrat.
"""

from __future__ import annotations

import inspect
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Union

from hai_agents import AsyncClient
from hai_agents.tools import tool
from loguru import logger


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
    "Ne clique jamais sur un bouton qui valide, paie, résilie ou envoie quelque chose sans "
    "confirmation explicite obtenue via ask_user."
)


async def _maybe_await(value: Any) -> None:
    if inspect.isawaitable(value):
        await value


class DemarcheRunner:
    """Lance une démarche dans le Chrome local et remonte les étapes.

    Contrat stable :
        await run(goal, on_step, ask_user=None) -> str  (réponse finale de l'agent)
        await cancel() / pause() / resume()
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

        self.log_dir.mkdir(parents=True, exist_ok=True)
        raw_path = self.log_dir / f"h_events_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
        logger.info("Events bruts → {}", raw_path)

        self._session = await self._client.start_session(
            agent=self._agent_spec(tools),
            messages=goal,
            tools=tools or None,
            max_time_s=self.max_time_s,
            timezone="Europe/Paris",
        )
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
            async for ev in self._session.stream(timeout_seconds=self.max_time_s + 60):
                d = ev.model_dump(mode="json")
                raw.write(json.dumps(d, ensure_ascii=False) + "\n")
                raw.flush()
                etype = d.get("type")
                data = d.get("data") or {}

                if etype == "AgentEvent":
                    kind = data.get("kind")
                    if kind == "policy_event":
                        content = (data.get("content") or "").strip()
                        actions = [r.get("tool_name") for r in data.get("tool_reqs") or []]
                        logger.debug("policy actions={}", actions)
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
        final = result.answer if result.answer is not None else answer
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
        if self._session is not None:
            await self._session.resume()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
