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


FAKE_STEPS_VALIDATE = [
    ("Je clique sur « Valider »", 3.0),
    ("Je vérifie que le changement est bien enregistré", 3.0),
]


class FakeDemarcheRunner:
    """Même contrat que `DemarcheRunner` (run / follow_up / close / cancel / pause / resume / aclose).

    Phase 1 : s'arrête au récapitulatif et termine par une ligne `CONFIRMATION: …`.
    follow_up() simule le clic sur « Valider » (rien n'est fait pour de vrai).
    """

    def __init__(self, speed: float = 1.0, fail_after: Optional[int] = None) -> None:
        self.speed = speed
        self.fail_after = fail_after  # simule une erreur de l'agent H après N étapes (test du guide manuel)
        self.status: Optional[str] = None
        self._resumed = asyncio.Event()
        self._resumed.set()
        self._cancelled = False
        self._on_step: Optional[OnStep] = None
        self._choice = "le forfait à deux euros"
        self.validated = False  # vrai seulement si follow_up() a « cliqué » sur Valider

    async def _sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds / self.speed)
        await self._resumed.wait()
        if self._cancelled:
            self.status = "interrupted"
            raise RuntimeError("Démarche annulée par la personne")

    async def run(self, goal: str, on_step: OnStep, ask_user: Optional[AskUser] = None) -> str:
        logger.info("[fake] démarche : {}", goal.splitlines()[0])
        self._cancelled = False
        self.validated = False
        self._on_step = on_step
        self.status = "running"
        url = "https://mobile.free.fr/account/"
        for i, (text, delay) in enumerate(FAKE_STEPS):
            if self.fail_after is not None and i >= self.fail_after:
                self.status = "failed"
                raise RuntimeError("Erreur simulée de l'agent H (--fake-fail)")
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
        self._choice = choice
        self.status = "idle"
        price = "neuf euros quatre-vingt-dix-neuf" if "9" in choice or "neuf" in choice.lower() else "deux euros"
        return (
            f"La personne a choisi : « {choice} ». Je suis sur la page de récapitulatif du "
            "changement de forfait ; le nouveau forfait démarrerait le 1er décembre. "
            "Il reste à cliquer sur « Valider » (non fait).\n"
            f"CONFIRMATION: passer au forfait à {price} par mois, à partir du 1er décembre"
        )

    async def follow_up(self, message: str) -> str:
        if self._on_step is None:
            raise RuntimeError("follow_up() sans session ouverte")
        logger.info("[fake] follow-up : {}", message)
        self._cancelled = False
        self.status = "running"
        for text, delay in FAKE_STEPS_VALIDATE:
            await self._sleep(delay)
            await _maybe_await(self._on_step(Step(text=text, url="https://mobile.free.fr/account/")))
        self.validated = True
        self.status = "idle"
        logger.info("[fake] ✅ « Valider » cliqué (simulé)")
        return "C'est validé : le nouveau forfait démarre le 1er décembre. Un e-mail de confirmation a été envoyé."

    async def close(self) -> None:
        if self._on_step is not None:
            logger.info("[fake] session fermée (validé={})", self.validated)
        self._on_step = None
        if self.status not in ("interrupted",):
            self.status = "completed"

    async def cancel(self) -> None:
        self._cancelled = True
        self._resumed.set()

    async def pause(self) -> None:
        self._resumed.clear()

    async def resume(self) -> None:
        self._resumed.set()

    async def aclose(self) -> None:
        pass
