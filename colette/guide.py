"""Step-by-step manual guide (fallback): when the H agent can't run (quota full) or fails,
Colette shows the person where to click on HER OWN page, one step at a time (LLM via OpenRouter).

Loop (one step at a time):
1. reads the person's page (`window.__colette.scan()` in static/widget.js, through `state.scan_page()`:
   CDP in local mode, the WebSocket in online mode): visible clickable elements (`data-colette-id`),
   headings, a text excerpt;
2. asks the LLM for the NEXT action: element + short instruction in English;
3. pushes `state.guide` → the bubble rings the element and shows a small instruction box;
   Colette says it aloud;
4. waits for the person to click the element (seen by the bubble), fill the field (change / Enter),
   click "Done", say "done", or for the page to change;
5. starts again until the LLM says the goal is reached (or stop / give up).

The person clicks herself: she is the one who validates. Final buttons (confirm, pay, cancel)
are shown in orange with a warning. Field values (passwords) are never read: labels only.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from loguru import logger

if TYPE_CHECKING:
    from colette.state import StateServer

MAX_STEPS = 25
REMIND_AFTER_S = 60.0  # pas de clic → on redit la consigne une fois
GIVE_UP_AFTER_S = 300.0
LLM_TIMEOUT_S = 20.0

Say = Callable[[str], Awaitable[None]]

PROMPT = """\
You guide an elderly person who is doing an online task HERSELF on a website. An automatic agent \
could not do it for her: now she clicks, and you show her, one step at a time, where to click.

Her goal: <<GOAL>>
What happened before: <<CONTEXT>>
Steps already shown (oldest first):
<<HISTORY>>

Current page: <<TITLE>> — <<URL>>
Page headings: <<HEADINGS>>
Visible text (excerpt): <<TEXT>>

Page elements (id | type | label | visible on screen without scrolling):
<<ELEMENTS>>

Choose the NEXT action, only one. Answer ONLY with a JSON object:
{"done": false, "id": "c12", "action": "click", "instruction": "...", "irreversible": false}
"action" is "click", "type" (type in a field) or "select" (choose in a list).
If the goal is reached on this page, or cannot be done online, answer:
{"done": true, "summary": "..."}

Rules for "instruction" and "summary":
- English, polite, one or two very short sentences, simple words;
- quote the button label between quotes and say where it is (top, left, middle…);
- never a URL, an id or a technical word (link, tab, element, dropdown → "list").
For an ID, a password or a code: tell her to type it herself in the circled box; never ask her \
to say it aloud.
If the click confirms, pays, cancels, sends, downloads a file or changes something for good: "irreversible": true, \
and the instruction recalls what will be confirmed (price, date if shown) and tells her to click \
only if she agrees.
Prefer elements visible on screen. If a cookie banner or a popup is in the way, close it first \
("Continue without accepting" or "Refuse" preferably). \
Steps marked "(done by the person)" were done: NEVER give the same instruction again, even if the \
page looks the same (a download or a click may not change the page). If that step was the last one \
needed for her goal, answer {"done": true, ...}.
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
        lines.append(f"{e.get('id')} | {kind} | {e.get('text') or '(no label)'} | "
                     f"{'yes' if e.get('inView') else 'no'}")
    return "\n".join(lines) or "(none)"


class ManualGuide:
    """Guides the person by hand, step by step, on her own page (`state.scan_page()`)."""

    def __init__(self, state: "StateServer", say: Say, model: Optional[str] = None) -> None:
        from openai import AsyncOpenAI  # import paresseux : les tests n'en ont pas besoin

        self.state = state
        self.say = say
        self.model = model or os.getenv("OPENROUTER_MODEL") or "google/gemini-2.5-flash"
        self._client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1",
                                   api_key=os.environ["OPENROUTER_API_KEY"])
        self._events: asyncio.Queue[dict] = asyncio.Queue()
        self._step = 0
        self.active = False
        self._stopped = False
        self.intro = ("I'll show you where to click, step by step. You click, I guide you. "
                      "The button to click is circled on your page.")
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
        last_target: Optional[str] = None
        outcome, summary = "gave_up", ""
        self._drain()
        try:
            self.state.update(status="guiding", open=True, steps=[])
            self.state.add_step("I guide you step by step")
            await self.say(self.intro)
            for n in range(1, MAX_STEPS + 1):
                if self._stopped:
                    outcome = "stopped"
                    break
                page = await self._scan()
                if page is None:
                    summary = "I can't read the page. I'm sorry."
                    break
                decision = await self._decide(goal, context, history, page)
                if decision is None:
                    summary = "I can't find the next step on this page. I'm sorry."
                    break
                if not decision["done"] and history and (
                        decision["instruction"] == history[-1].rsplit(" (done", 1)[0]
                        or (decision["id"] and decision["id"] == last_target)):
                    # même élément que l'étape que la personne vient de faire (téléchargement…) : c'était la dernière
                    decision = {"done": True, "summary": "Very good, you did it. That was the last step."}
                if decision["done"]:
                    outcome, summary = "done", decision["summary"] or "It's done."
                    break
                label = next((e.get("text") or "" for e in page.get("elements") or [] if e.get("id") == decision["id"]), "")
                if re.search(r"download|confirm|validat|save|pay|cancel|delete|submit|send|activate|deactivate", label, re.I):
                    decision["irreversible"] = True  # avertissement orange même si le LLM l'oublie
                self._step = n
                last_target = decision["id"]
                await self._show(n, page["pageId"], decision)
                event = await self._wait_advance(n, decision["instruction"])
                if event == "stop":
                    outcome = "stopped"
                    break
                if event == "timeout":
                    summary = "I don't hear you anymore, so I'm stopping the guide. Call me back whenever you want."
                    break
                history.append(decision["instruction"] + (" (done by the person, the page changed)"
                                                          if event == "page_loaded" else " (done by the person)"))
                await self._settle(event)
            else:
                summary = "We did many steps without reaching the end. I'm stopping the guide."
        finally:
            self.active = False
            self._step = 0
            self.state.update(guide=None)
        if outcome == "stopped":
            summary = summary or "OK, I'm stopping the guide."
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
                page = await self.state.scan_page()
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
                  .replace("<<CONTEXT>>", context or "(nothing)")
                  .replace("<<HISTORY>>", "\n".join(f"- {h}" for h in history[-10:]) or "(none)")
                  .replace("<<TITLE>>", page.get("title") or "")
                  .replace("<<URL>>", page.get("url") or "")
                  .replace("<<HEADINGS>>", " / ".join(page.get("headings") or []) or "(none)")
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
                note = "\n\nYour previous answer was not valid JSON. Answer only with the JSON."
                continue
            if not decision["done"] and decision["id"] not in ids:
                logger.warning("Guide : id inconnu {!r}", decision["id"])
                note = f"\n\nThe id {decision['id']!r} is not in the list. Choose an id from the list."
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
                    await self.say("I'm waiting for you. " + instruction)
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
