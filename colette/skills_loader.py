"""Charge `colette/skills/*.md` en skills H inline `{name, description, body}`.

Chaque fichier commence par un front matter :

    ---
    name: free-plan
    description: Use when …
    ---
    # Corps markdown (la procédure)

Aucune liste en dur : tout fichier `.md` déposé dans le dossier est envoyé à l'agent.
Champs facultatifs (bulle seulement, jamais envoyés à H) : `label` (raccourci de l'écran 2,
en français), `ask` (phrase envoyée comme si la personne l'avait dite), `order` (tri des raccourcis), `keywords`, `steps` et `steps_view` (séparés par
« | ») : plan affiché dès le début quand un mot-clé apparaît dans l'objectif de la démarche
(`steps_view` quand la personne veut seulement consulter).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from loguru import logger

from colette import site

SKILLS_DIR = Path(__file__).parent / "skills"  # vrai Free ; la maquette : site.skills_dir()
# Ajouté en tête de chaque skill : Holo suit le corps du skill bien plus que les instructions
# générales (vu au vrai run du 7 nov : skill suivi à la lettre, annoncer_etapes jamais appelé).
PREAMBLE = """\
## Before anything else (Colette)
1. Call `annoncer_etapes` FIRST, before any action on the website: 3 to 6 short steps in simple
   English that follow this skill (e.g. "Open your customer area", "Find your bills").
   If something will need to be validated, the last step is exactly "Confirm with your approval".
2. After finishing each of those steps, call `etape_terminee` with its number (starting at 1).
3. Before any click that validates, saves, pays or cancels, call `confirm_change` and click only
   if the reply starts with "Approved".
4. Asking the person (`ask_user`): she is elderly and speaks in small pieces. Ask ONE short question
   per piece of information (e.g. for an address: number and street name, then postal code, then
   city). Keep every piece she already gave you, even partial, and only ask for what is still
   missing. Never ask her to repeat everything, never insist on getting it all in one answer.
5. Dropdown lists (street names, cities, street types…) accept typing: click the field to open it,
   then type the first 3 letters of the wanted option (or the digits if it is a number: postal code,
   street number…) with `write` in that field; the list filters or jumps to the matching option.
   Then click that option. Only if typing changes nothing, scroll THE LIST itself with `scroll_web`
   and `scroll_element` set to the open list of options (not the page), reading the options after
   each scroll. Options are often written "NAME (TYPE)", e.g.
   "REPUBLIQUE (PLACE DE LA)": look for the name, ignore accents. Do not press the arrow keys one by
   one. After 6 unsuccessful actions on the same list, stop and call `ask_user` (or answer that you
   are stuck) instead of trying again.
"""
_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _front_matter(text: str) -> tuple[dict[str, str], str]:
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        _, front, body = text.split("---", 2)
        for line in front.strip().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip().lower()] = value.strip().strip("\"'")
    return meta, body


def parse_skill(text: str, fallback_name: str) -> dict:
    """Front matter `name` / `description` + corps. Lève ValueError si incomplet."""
    meta, body = _front_matter(text)
    name = meta.get("name") or fallback_name
    description = meta.get("description", "")
    body = body.strip()
    if not _NAME_RE.match(name):
        raise ValueError(f"nom de skill invalide : {name!r} (minuscules, chiffres, tirets)")
    if not description or not body:
        raise ValueError(f"skill {name!r} : description ou corps manquant")
    return {"name": name, "description": description, "body": PREAMBLE + "\n" + body}


def load_skills(directory: Optional[Path] = None) -> list[dict]:
    directory = directory or site.skills_dir()
    skills = []
    for path in sorted(directory.glob("*.md")):
        try:
            skills.append(parse_skill(path.read_text(encoding="utf-8"), path.stem))
        except Exception as e:
            logger.warning("Skill ignoré ({}) : {}", path.name, e)
    return skills


def list_shortcuts(directory: Optional[Path] = None) -> list[dict]:
    """Raccourcis de la bulle : [{"id": name, "label": str}] pour chaque skill qui a un `label`."""
    directory = directory or site.skills_dir()
    items = []
    for path in directory.glob("*.md"):
        try:
            meta, _ = _front_matter(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Skill illisible ({}) : {}", path.name, e)
            continue
        if meta.get("label"):
            try:
                order = int(meta.get("order", "99"))
            except ValueError:
                order = 99
            items.append((order, {"id": meta.get("name") or path.stem, "label": meta["label"],
                                  "ask": meta.get("ask", "")}))
    return [item for _, item in sorted(items, key=lambda x: (x[0], x[1]["label"]))]


VIEW_WORDS = ("see", "check", "view", "give me", "tell me", "how much", "does my", "is my", "do i need",
              "do i have to", "will my", "can i use", "does it work", "work there", "work in", "find the", "find my", "what s the", "look at", "show me", "find out", "what is", "what s", "read",
              "know", "get my", "voir", "consulter", "récupérer", "recuperer", "afficher", "regarder", "connaître",
              "connaitre", "vérifier", "verifier", "lire", "savoir", "quelle est", "quel est", "retrouver")
CHANGE_WORDS = ("change", "update", "modify", "edit", "replace", "correct", "switch", "move to",
                "modifier", "changer", "mettre à jour", "remplacer", "corriger", "passer à", "passer au")


def is_view_request(objectif: str) -> bool:
    """Vrai si la personne veut seulement voir une information (pas la changer)."""
    text = f" {(objectif or '').lower()} "
    view = any(f" {w}" in text for w in VIEW_WORDS)
    change = any(f" {w}" in text for w in CHANGE_WORDS)
    return view and not change


def match_plan(objectif: str, directory: Optional[Path] = None) -> "tuple[str, list[str]] | None":
    """(skill, étapes) du premier skill dont un mot-clé apparaît dans l'objectif, sinon None.
    Demande de consultation → `steps_view` du skill s'il en a (rien à modifier ni à valider)."""
    directory = directory or site.skills_dir()
    text = (objectif or "").lower()
    view = is_view_request(objectif)
    best = None
    for path in sorted(directory.glob("*.md")):
        try:
            meta, _ = _front_matter(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        keywords = [k.strip().lower() for k in meta.get("keywords", "").split("|") if k.strip()]
        steps = [st.strip() for st in meta.get("steps", "").split("|") if st.strip()]
        if view and meta.get("steps_view"):
            steps = [st.strip() for st in meta["steps_view"].split("|") if st.strip()]
        if not steps:
            continue
        pos = min((text.find(k) for k in keywords if k in text), default=-1)
        try:
            prio = int(meta.get("priority", "0"))  # ex. voyage > forfait : « my plan works in China »
        except ValueError:
            prio = 0
        # priorité la plus haute d'abord, puis le mot-clé cité en premier
        if pos >= 0 and (best is None or (prio, -pos) > (best[3], -best[0])):
            best = (pos, meta.get("name") or path.stem, steps, prio)
    return (best[1], best[2]) if best else None
