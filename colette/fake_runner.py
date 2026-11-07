"""Faux DemarcheRunner : rejoue un scénario Free Mobile sans consommer de session H."""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from loguru import logger

from colette.h_agent import VALIDATE_STEP, AskUser, Confirm, OnPlan, OnStep, OnStepDone, Step, _maybe_await

FAKE_PLAN = ["Ouvrir votre espace abonné", "Trouver les forfaits disponibles",
             "Choisir le forfait avec vous", VALIDATE_STEP]

FAKE_STEPS = [
    ("J'ouvre votre espace abonné Free Mobile", 3.0),
    ("Je clique sur « Mon forfait »", 3.5),
    ("Je regarde les forfaits disponibles", 4.0),
]
FAKE_QUESTION = "Je vois deux forfaits moins chers : le forfait à deux euros, ou celui à neuf euros quatre-vingt-dix-neuf. Lequel préférez-vous ?"
FAKE_LOGIN = ("Il faut vous connecter. Tapez vous-même votre identifiant et votre mot de passe, je ne "
              "regarde pas. Dites-moi « c'est bon » quand c'est fait.")
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

    Appelle on_plan (annoncer_etapes) puis on_step_done (etape_terminee) au fil des étapes, puis
    confirm (confirm_change) au récapitulatif : oui → « Valider » cliqué (simulé) dans la même phase,
    non → rien. Sans `confirm` (ou use_confirm_tool=False, env COLETTE_FAKE_LEGACY=1) : garde-fou deux
    phases, s'arrête au récapitulatif avec une ligne `CONFIRMATION: …` et follow_up() simule le clic.
    Rien n'est jamais fait pour de vrai. `COLETTE_FAKE_FAIL=1` : échec après l'étape 2 (écran 10). `COLETTE_FAKE_LOGIN=1` : question de connexion.
    """

    def __init__(self, speed: float = 1.0, use_confirm_tool: Optional[bool] = None) -> None:
        self.speed = speed
        if use_confirm_tool is None:
            use_confirm_tool = os.getenv("COLETTE_FAKE_LEGACY", "") not in ("1", "true")
        self.use_confirm_tool = use_confirm_tool
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
        logger.info("[fake] démarche : {}", goal.splitlines()[0])
        self._cancelled = False
        self.validated = False
        self._on_step = on_step
        self.status = "running"
        url = "https://mobile.free.fr/account/"

        async def done(n: int) -> None:
            if on_step_done is not None:
                logger.info("[fake] etape_terminee({})", n)
                await _maybe_await(on_step_done(n))

        await self._sleep(1.0)
        if on_plan is not None:
            logger.info("[fake] annoncer_etapes {}", FAKE_PLAN)
            await _maybe_await(on_plan(list(FAKE_PLAN)))
            await self._sleep(8.0)  # le temps que Colette lise le plan
        for i, (text, delay) in enumerate(FAKE_STEPS):
            await self._sleep(delay)
            await _maybe_await(on_step(Step(text=text, url=url)))
            if i == 0:
                await done(1)
                if ask_user is not None and os.getenv("COLETTE_FAKE_LOGIN", "") in ("1", "true"):
                    await _maybe_await(on_step(Step(text=FAKE_LOGIN, kind="question")))
                    logger.info("[fake] réponse connexion : {}", await ask_user(FAKE_LOGIN))
        await done(2)
        if os.getenv("COLETTE_FAKE_FAIL", "") in ("1", "true"):
            self.status = "failed"
            raise RuntimeError("[fake] la page « Changer de forfait » ne répond pas (COLETTE_FAKE_FAIL)")
        choice = "le forfait à deux euros"
        if ask_user is not None:
            await _maybe_await(on_step(Step(text=FAKE_QUESTION, kind="question")))
            choice = (await ask_user(FAKE_QUESTION)) or choice
            logger.info("[fake] réponse : {}", choice)
        for text, delay in FAKE_STEPS_AFTER:
            await self._sleep(delay)
            await _maybe_await(on_step(Step(text=text, url=url)))
        await done(3)
        self._choice = choice
        price = "neuf euros quatre-vingt-dix-neuf" if "9" in choice or "neuf" in choice.lower() else "deux euros"
        if confirm is not None and self.use_confirm_tool:
            summary = f"passer au forfait à {price} par mois, à partir du 1er décembre"
            logger.info("[fake] confirm_change({!r}, costs_money=True)", summary)
            ok = await confirm(summary, True)
            if self._cancelled:
                self.status = "interrupted"
                raise RuntimeError("Démarche annulée par la personne")
            if not ok:
                self.status = "idle"
                logger.info("[fake] ❌ refusé : « Valider » non cliqué")
                return ("La personne a refusé : je n'ai pas cliqué sur « Valider ». Rien n'a été changé.\n"
                        "CONFIRMATION: aucune")
            for text, delay in FAKE_STEPS_VALIDATE:
                await self._sleep(delay)
                await _maybe_await(on_step(Step(text=text, url=url)))
            await done(4)
            self.validated = True
            self.status = "idle"
            logger.info("[fake] ✅ « Valider » cliqué (simulé) après confirm_change")
            return ("C'est validé : le nouveau forfait démarre le 1er décembre. Un e-mail de confirmation "
                    "a été envoyé.\nCONFIRMATION: aucune")
        self.status = "idle"
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
