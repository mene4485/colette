"""Guide manuel pas à pas : quand l'agent H échoue, Colette montre à la personne où cliquer.

Boucle (une étape à la fois) :
1. lit la page de l'onglet actif via CDP (`window.__colette.scan()` dans static/widget.js) :
   éléments cliquables visibles (id `data-colette-id`), titres, extrait de texte ;
2. demande au LLM (OpenRouter) la PROCHAINE action : élément + consigne courte en français ;
3. pousse `state.guide` → la bulle entoure l'élément et affiche une petite fenêtre avec la consigne ;
   Colette la dit à voix haute ;
4. attend que la personne clique sur l'élément (détecté par la bulle), tape dans le champ
   (change / Entrée), clique « Suivant », dise « c'est fait », ou que la page change ;
5. recommence jusqu'à ce que le LLM dise que l'objectif est atteint (ou stop / abandon).

La personne clique elle-même : c'est elle qui valide. Les boutons définitifs (valider, payer,
résilier) sont signalés en orange avec un avertissement.
Jamais de valeur de champ lue (mots de passe) : le scan ne remonte que des libellés.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from loguru import logger

if TYPE_CHECKING:
    from colette.overlay import OverlayInjector
    from colette.state import StateServer

MAX_STEPS = 25
REMIND_AFTER_S = 60.0  # pas de clic → on redit la consigne une fois
GIVE_UP_AFTER_S = 300.0
LLM_TIMEOUT_S = 20.0

Say = Callable[[str], Awaitable[None]]

PROMPT = """\
Tu guides une personne âgée qui fait ELLE-MÊME une démarche sur un site web. Un agent \
automatique a essayé avant et n'a pas réussi : maintenant c'est la personne qui clique, \
et toi tu lui montres, une étape à la fois, où cliquer.

Objectif de la personne : <<GOAL>>
Ce qui s'est passé avant : <<CONTEXT>>
Étapes déjà montrées (de la plus ancienne à la plus récente) :
<<HISTORY>>

Page actuelle : <<TITLE>> — <<URL>>
Titres de la page : <<HEADINGS>>
Texte visible (extrait) : <<TEXT>>

Éléments de la page (id | type | libellé | visible à l'écran sans défiler) :
<<ELEMENTS>>

Choisis la PROCHAINE action, une seule. Réponds UNIQUEMENT avec un objet JSON :
{"done": false, "id": "c12", "action": "click", "instruction": "...", "irreversible": false}
"action" vaut "click", "type" (taper dans un champ) ou "select" (choisir dans une liste).
Si l'objectif est atteint sur cette page, ou impossible à faire en ligne, réponds :
{"done": true, "summary": "..."}

Règles pour "instruction" et "summary" :
- français, vouvoiement, une ou deux phrases très courtes, mots simples ;
- cite le libellé du bouton entre « » et dis où il se trouve (en haut, à gauche, au milieu…) ;
- jamais d'URL, d'id, de mot technique (lien, onglet, élément, menu déroulant → « liste »).
Pour un identifiant, un mot de passe ou un code : dis à la personne de le taper elle-même dans \
la case entourée ; ne lui demande jamais de le dire à voix haute.
Si le clic valide, paie, résilie, envoie ou change quelque chose de définitif : \
"irreversible": true, et l'instruction rappelle ce qui sera validé (prix, date si visibles) et \
dit de cliquer seulement si la personne est d'accord.
Préfère les éléments visibles à l'écran. Si un bandeau de cookies ou une fenêtre gêne, \
commence par le fermer (« Continuer sans accepter » ou « Refuser » de préférence). \
Ne répète pas une étape qui vient d'être faite si la page a changé comme prévu.
"""


def parse_decision(text: str) -> Optional[dict]:
    """Extrait l'objet JSON de la réponse du LLM (tolère ```json … ``` et texte autour)."""
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("done"):
        return {"done": True, "summary": str(data.get("summary") or "").strip()}
    instruction = str(data.get("instruction") or "").strip()
    if not instruction:
        return None
    action = data.get("action") if data.get("action") in ("click", "type", "select") else "click"
    target = data.get("id")
    return {
        "done": False,
        "id": str(target) if target else None,
        "action": action,
        "instruction": instruction,
        "irreversible": bool(data.get("irreversible")),
    }


def format_elements(elements: list[dict], limit: int = 150) -> str:
    lines = []
    for e in elements[:limit]:
        kind = e.get("tag", "")
        if e.get("type"):
            kind += f"[{e['type']}]"
        lines.append(f"{e.get('id')} | {kind} | {e.get('text') or '(sans libellé)'} | "
                     f"{'oui' if e.get('inView') else 'non'}")
    return "\n".join(lines) or "(aucun)"


class ManualGuide:
    """Guide la personne à la main, étape par étape, dans l'onglet actif du Chrome :9222."""

    def __init__(self, state: "StateServer", overlay: "OverlayInjector", say: Say,
                 model: Optional[str] = None) -> None:
        from openai import AsyncOpenAI  # import paresseux : les tests n'en ont pas besoin

        self.state = state
        self.overlay = overlay
        self.say = say
        self.model = model or os.getenv("OPENROUTER_MODEL") or "google/gemini-2.5-flash"
        self._client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1",
                                   api_key=os.environ["OPENROUTER_API_KEY"])
        self._events: asyncio.Queue[dict] = asyncio.Queue()
        self._step = 0
        self.active = False
        self._stopped = False
        state.on_client_message(self._on_client_message)

    # ---- événements de la bulle (clics, Suivant, stop, nouvelle page) ------------
    async def _on_client_message(self, msg: dict) -> None:
        if self.active and msg.get("type") in ("guide_clicked", "guide_next", "page_loaded", "stop"):
            self._events.put_nowait(msg)

    def stop(self) -> None:
        if self.active:
            self._stopped = True
            self._events.put_nowait({"type": "stop"})

    def next(self) -> None:
        """« C'est fait » / « suivant » dit à voix haute."""
        if self.active:
            self._events.put_nowait({"type": "guide_next", "step": self._step})

    def _drain(self) -> None:
        while not self._events.empty():
            self._events.get_nowait()

    # ---- boucle principale ------------------------------------------------------
    async def run(self, goal: str, context: str = "") -> dict:
        """Renvoie {"outcome": "done"|"stopped"|"gave_up", "summary": str, "steps": [str]}."""
        self.active, self._stopped, self._step = True, False, 0
        history: list[str] = []
        outcome, summary = "gave_up", ""
        self._drain()
        try:
            self.state.update(status="guiding", open=True)
            self.state.add_step("Je vous guide pas à pas")
            await self.say("Je n'ai pas réussi à le faire toute seule. Je vais vous montrer où cliquer, "
                           "étape par étape. C'est vous qui cliquez.")
            for n in range(1, MAX_STEPS + 1):
                if self._stopped:
                    outcome = "stopped"
                    break
                page = await self._scan()
                if page is None:
                    summary = "Je n'arrive pas à lire la page. Je suis désolée."
                    break
                decision = await self._decide(goal, context, history, page)
                if decision is None:
                    summary = "Je n'arrive pas à trouver la suite sur cette page. Je suis désolée."
                    break
                if decision["done"]:
                    outcome, summary = "done", decision["summary"] or "C'est terminé."
                    break
                self._step = n
                await self._show(n, page["pageId"], decision)
                event = await self._wait_advance(n, decision["instruction"])
                if event == "stop":
                    outcome = "stopped"
                    break
                if event == "timeout":
                    summary = "Je ne vous entends plus, j'arrête le guide. Rappelez-moi quand vous voulez."
                    break
                history.append(decision["instruction"] + ("" if event != "page_loaded" else " (la page a changé)"))
                await self._settle(event)
            else:
                summary = "Nous avons fait beaucoup d'étapes sans arriver au bout. J'arrête le guide."
        finally:
            self.active = False
            self._step = 0
            self.state.update(guide=None)
        if outcome == "stopped":
            summary = summary or "D'accord, j'arrête le guide."
        elif summary:
            self.state.set_subtitle(summary)
            await self.say(summary)
        if outcome == "done":
            self.state.finish_steps()
        logger.info("🧭 Guide terminé : {} — {}", outcome, summary)
        return {"outcome": outcome, "summary": summary, "steps": history}

    # ---- étapes -----------------------------------------------------------------
    async def _scan(self) -> Optional[dict]:
        for attempt in range(4):
            try:
                page = await self.overlay.evaluate_active(
                    "window.__colette && window.__colette.scan ? window.__colette.scan() : null")
                if page and page.get("elements") is not None:
                    logger.info("🧭 Page lue : {} ({} éléments)", page.get("url"), len(page["elements"]))
                    return page
            except Exception as e:
                logger.debug("Scan impossible ({}) : {}", attempt, e)
            await asyncio.sleep(1.0)  # page en cours de chargement
        return None

    async def _decide(self, goal: str, context: str, history: list[str], page: dict) -> Optional[dict]:
        ids = {e.get("id") for e in page.get("elements") or []}
        prompt = (PROMPT
                  .replace("<<GOAL>>", goal)
                  .replace("<<CONTEXT>>", context or "(rien)")
                  .replace("<<HISTORY>>", "\n".join(f"- {h}" for h in history[-10:]) or "(aucune)")
                  .replace("<<TITLE>>", page.get("title") or "")
                  .replace("<<URL>>", page.get("url") or "")
                  .replace("<<HEADINGS>>", " / ".join(page.get("headings") or []) or "(aucun)")
                  .replace("<<TEXT>>", page.get("text") or "")
                  .replace("<<ELEMENTS>>", format_elements(page.get("elements") or [])))
        note = ""
        fallback: Optional[dict] = None  # consigne sans surlignage si l'id reste inconnu
        for _ in range(2):
            try:
                resp = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt + note}],
                        max_tokens=300,
                        temperature=0,
                    ),
                    LLM_TIMEOUT_S,
                )
                decision = parse_decision(resp.choices[0].message.content or "")
            except Exception as e:
                logger.warning("Guide : LLM en échec ({}) : {}", type(e).__name__, e)
                decision = None
            if decision is None:
                note = "\n\nTa réponse précédente n'était pas un JSON valide. Réponds seulement le JSON."
                continue
            if not decision["done"] and decision["id"] not in ids:
                logger.warning("Guide : id inconnu {!r}", decision["id"])
                note = f"\n\nL'id {decision['id']!r} n'existe pas dans la liste. Choisis un id de la liste."
                fallback = {**decision, "id": None}
                continue
            logger.info("🧭 Décision : {}", decision)
            return decision
        return fallback

    async def _show(self, n: int, page_id: str, d: dict) -> None:
        text = d["instruction"]
        logger.info("🧭 Étape {} : {} → {}", n, text, d["id"])
        self.state.update(
            guide={"step": n, "text": text, "page": page_id, "target": d["id"],
                   "action": d["action"], "irreversible": d["irreversible"]},
            subtitle=text,
        )
        self.state.add_step(text[:80])
        await self.say(text)

    async def _wait_advance(self, n: int, instruction: str) -> str:
        """Renvoie "clicked" | "next" | "page_loaded" | "stop" | "timeout"."""
        self._drain()
        loop = asyncio.get_running_loop()
        remind_at = loop.time() + REMIND_AFTER_S
        deadline = loop.time() + GIVE_UP_AFTER_S
        reminded = False
        while True:
            wait = (deadline if reminded else remind_at) - loop.time()
            try:
                msg = await asyncio.wait_for(self._events.get(), max(wait, 0.1))
            except asyncio.TimeoutError:
                if not reminded:
                    reminded = True
                    await self.say("Je vous attends. " + instruction)
                    continue
                return "timeout"
            t = msg.get("type")
            if t == "stop":
                return "stop"
            if t == "page_loaded":
                return "page_loaded"
            if t in ("guide_clicked", "guide_next") and msg.get("step") in (None, n):
                return "clicked" if t == "guide_clicked" else "next"

    async def _settle(self, event: str) -> None:
        """Laisse la page réagir au clic avant de la relire."""
        if event == "page_loaded":
            await asyncio.sleep(1.2)
            return
        try:  # un clic peut charger une nouvelle page : on l'attend un peu
            while True:
                msg = await asyncio.wait_for(self._events.get(), 2.5)
                if msg.get("type") == "stop":
                    self._stopped = True
                    return
                if msg.get("type") == "page_loaded":
                    await asyncio.sleep(1.2)
                    return
        except asyncio.TimeoutError:
            pass
