"""Transforme les actions de l'agent H en phrases simples pour une personne âgée.

Holo décrit ses actions pour lui-même, souvent en anglais et avec des détails de position
(« Click "Empty area in the main content to deselect text" »). On :
1. ignore les actions techniques (attendre, raccourcis clavier, défilement, recharger…) ;
2. fait réécrire le reste par le LLM en une phrase courte en français (ou SKIP) ;
3. ne répète pas deux fois la même phrase (Holo reclique souvent sur le même lien).
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from loguru import logger
from openai import AsyncOpenAI

from colette.h_agent import Step

# Actions jamais racontées : sans intérêt pour la personne.
NOISE_TOOLS = {
    "wait_web", "press_keys_web", "refresh_web", "web_fetch", "switch_tab_web", "scroll_web",
    "ctrl_f_web", "go_back_web", "back_web", "answer", "ask_user",
}

PROMPT = """\
Tu écris la narration d'une assistante vocale qui fait une démarche sur le site Free à la place
d'une personne âgée. On te donne ce que l'agent vient de faire (souvent en anglais, technique).
Réécris-le en UNE phrase très courte en français (8 mots maximum), au présent, à la première
personne, avec des mots simples, comme on l'expliquerait à sa grand-mère.
Ne mentionne jamais : coordonnées, position à l'écran, couleur, onglet du navigateur, barre
d'adresse, URL, bouton de la bulle Colette, sélection de texte, zone vide.
Si l'action est technique ou sans intérêt pour la personne, réponds exactement : SKIP

Exemples :
- « Click "Conso et factures" link in the left sidebar » → Je vais dans « Conso et factures ».
- « Disagree and close button on cookie consent modal » → Je ferme le message sur les cookies.
- « Empty area in the main content to deselect text » → SKIP
- « Browser address bar at the top of the window » → SKIP
- « Je vais fermer la bulle Colette » / « Stop button of the Colette popup » → SKIP
- « J'ouvre https://mobile.free.fr/account/ » → J'ouvre votre espace abonné.

Action : {action}
Phrase :"""


class Narrator:
    def __init__(self, model: Optional[str] = None, timeout_s: float = 3.0) -> None:
        self.model = model or os.getenv("OPENROUTER_MODEL") or "google/gemini-2.5-flash"
        self.timeout_s = timeout_s
        self._client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])
        self._cache: dict[str, Optional[str]] = {}
        self._said: list[str] = []

    @staticmethod
    def raw_action(step: Step) -> Optional[str]:
        """Texte brut à réécrire, ou None si l'étape n'est que du bruit technique."""
        data = step.raw or {}
        content = (data.get("content") or "").strip()
        if content:
            return content
        reqs = data.get("tool_reqs") or []
        if reqs and all((r.get("tool_name") or "") in NOISE_TOOLS for r in reqs):
            return None
        useful = [r for r in reqs if (r.get("tool_name") or "") not in NOISE_TOOLS]
        if useful:
            parts = []
            for r in useful:
                args = r.get("args") or {}
                target = args.get("element") or args.get("url") or ""
                parts.append(f"{r.get('tool_name')}: {target}".strip(": "))
            return " ; ".join(parts)
        return step.text or None  # étape sans données brutes (faux runner)

    async def simplify(self, step: Step) -> Optional[str]:
        action = self.raw_action(step)
        if not action:
            return None
        if action in self._cache:
            phrase = self._cache[action]
        else:
            phrase = await self._rewrite(action)
            self._cache[action] = phrase
        if not phrase or phrase in self._said[-3:]:
            return None  # rien à dire, ou déjà dit à l'instant
        self._said.append(phrase)
        return phrase

    async def _rewrite(self, action: str) -> Optional[str]:
        try:
            resp = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": PROMPT.format(action=action[:400])}],
                    max_tokens=40,
                    temperature=0,
                ),
                self.timeout_s,
            )
            text = (resp.choices[0].message.content or "").strip().strip("«»\"' ")
        except Exception as e:
            logger.debug("Narration non réécrite ({}) : {}", type(e).__name__, action)
            return None
        if not text or text.upper().startswith("SKIP"):
            return None
        text = text.splitlines()[0].strip()
        for prefix in ("Action :", "Action:", "Phrase :", "Phrase:", "→"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip().strip("«»\"' ")
        if not text or text.upper().startswith("SKIP"):
            return None
        return text if text.endswith((".", "!", "?")) else text + "."
