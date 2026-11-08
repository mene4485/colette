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
import re
from typing import Optional

from loguru import logger
from openai import AsyncOpenAI

from colette.h_agent import Step

_STOP = {"i", "i'm", "im", "am", "is", "the", "a", "an", "your", "you", "to", "of", "on", "in", "now",
         "will", "my", "for", "and", "it", "this", "that", "page", "please", "just", "let", "me", "i'll"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", text.lower()) if w not in _STOP}


def similar(a: str, b: str, threshold: float = 0.5) -> bool:
    """Même idée dite deux fois (« I'm logging in » / « I'm logging you in now »)."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= threshold

# Actions jamais racontées : sans intérêt pour la personne.
NOISE_TOOLS = {
    "wait_web", "press_keys_web", "refresh_web", "web_fetch", "switch_tab_web", "scroll_web",
    "ctrl_f_web", "go_back_web", "back_web", "answer", "ask_user",
    "annoncer_etapes", "etape_terminee", "confirm_change", "load_skill", "read_skill", "use_skill",
    "update_plan",
}

PROMPT = """\
You write the narration of a voice assistant that does an online task on the Free website for an
elderly person. You get what the agent just did (often technical). Rewrite it as ONE very short
sentence in English (8 words max), present tense, first person, simple words, as you would explain
it to your grandmother.
Never mention: coordinates, position on screen, colour, browser tab, address bar, URL, the Colette
bubble's buttons, text selection, empty area.
If the action is technical or of no interest to the person, answer exactly: SKIP

Examples:
- "Click 'Usage & bills' link in the left sidebar" → I'm opening "Usage & bills".
- "Disagree and close button on cookie consent modal" → I'm closing the cookie message.
- "Empty area in the main content to deselect text" → SKIP
- "Browser address bar at the top of the window" → SKIP
- "Stop button of the Colette popup" → SKIP
- "Open https://mobile.free.fr/account/" → I'm opening your customer area.

Action: {action}
Sentence:"""


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
        if not phrase or any(similar(phrase, said) for said in self._said):
            return None  # rien à dire, ou même idée déjà dite pendant cette démarche
        self._said.append(phrase)
        return phrase

    def reset(self) -> None:
        """Nouvelle démarche : on oublie ce qui a été dit."""
        self._said.clear()

    def remember(self, phrase: str) -> None:
        """Phrase dite par Colette hors narration (plan, « Maintenant je vais… ») : pas de redite."""
        if phrase:
            self._said.append(phrase)

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
        for prefix in ("Action :", "Action:", "Phrase :", "Phrase:", "Sentence:", "→"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip().strip("«»\"' ")
        if not text or text.upper().startswith("SKIP"):
            return None
        return text if text.endswith((".", "!", "?")) else text + "."
