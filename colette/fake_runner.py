"""Faux DemarcheRunner : rejoue un scénario Free Mobile sans consommer de session H."""

from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger

from colette.h_agent import AskUser, OnStep, Step, _maybe_await

FAKE_STEPS = [
    ("J'ouvre votre espace abonné Free Mobile", 3.0),
    ("Je clique sur « Mon forfait »", 3.5),
    ("Je regarde les forfaits disponibles", 4.0),
]
FAKE_QUESTION = "Je vois deux forfaits moins chers : le forfait à deux euros, ou celui à neuf euros quatre-vingt-dix-neuf. Lequel préférez-vous ?"
FAKE_STEPS_AFTER = [
    ("Je sélectionne le forfait choisi", 3.0),
    ("J'ouvre la page de récapitulatif", 3.5),
]


class FakeDemarcheRunner:
    """Même contrat que `DemarcheRunner` (run / cancel / pause / resume / aclose)."""

    def __init__(self, speed: float = 1.0) -> None:
        self.speed = speed
        self.status: Optional[str] = None
        self._resumed = asyncio.Event()
        self._resumed.set()
        self._cancelled = False

    async def _sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds / self.speed)
        await self._resumed.wait()
        if self._cancelled:
            self.status = "interrupted"
            raise RuntimeError("Démarche annulée par la personne")

    async def run(self, goal: str, on_step: OnStep, ask_user: Optional[AskUser] = None) -> str:
        logger.info("[fake] démarche : {}", goal.splitlines()[0])
        self._cancelled = False
        self.status = "running"
        url = "https://mobile.free.fr/account/"
        for text, delay in FAKE_STEPS:
            await self._sleep(delay)
            await _maybe_await(on_step(Step(text=text, url=url)))
        choice = "le forfait à deux euros"
        if ask_user is not None:
            await _maybe_await(on_step(Step(text=FAKE_QUESTION, kind="question")))
            choice = (await ask_user(FAKE_QUESTION)) or choice
            logger.info("[fake] réponse : {}", choice)
        for text, delay in FAKE_STEPS_AFTER:
            await self._sleep(delay)
            await _maybe_await(on_step(Step(text=text, url=url)))
        self.status = "completed"
        return (
            f"La personne a choisi : « {choice} ». Je suis sur la page de récapitulatif du "
            "changement de forfait ; le nouveau forfait démarrerait le 1er décembre. "
            "Il reste à cliquer sur « Valider » (non fait)."
        )

    async def cancel(self) -> None:
        self._cancelled = True
        self._resumed.set()

    async def pause(self) -> None:
        self._resumed.clear()

    async def resume(self) -> None:
        self._resumed.set()

    async def aclose(self) -> None:
        pass
