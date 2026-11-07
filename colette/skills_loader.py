"""Charge `colette/skills/*.md` en skills H inline `{name, description, body}`.

Chaque fichier commence par un front matter :

    ---
    name: free-plan
    description: Use when …
    ---
    # Corps markdown (la procédure)

Aucune liste en dur : tout fichier `.md` déposé dans le dossier est envoyé à l'agent.
Champs facultatifs (bulle seulement, jamais envoyés à H) : `label` (raccourci de l'écran 2,
en français), `order` (tri des raccourcis), `keywords`, `steps` et `steps_view` (séparés par
« | ») : plan affiché dès le début quand un mot-clé apparaît dans l'objectif de la démarche
(`steps_view` quand la personne veut seulement consulter).
"""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

SKILLS_DIR = Path(__file__).parent / "skills"
# Ajouté en tête de chaque skill : Holo suit le corps du skill bien plus que les instructions
# générales (vu au vrai run du 7 nov : skill suivi à la lettre, annoncer_etapes jamais appelé).
PREAMBLE = """\
## Before anything else (Colette)
1. Call `annoncer_etapes` FIRST, before any action on the website: 3 to 6 short steps in simple
   French that follow this skill (e.g. « Ouvrir votre espace abonné », « Trouver vos factures »).
   If something will need to be validated, the last step is exactly « Valider avec votre accord ».
2. After finishing each of those steps, call `etape_terminee` with its number (starting at 1).
3. Before any click that validates, saves, pays or cancels, call `confirm_change` and click only
   if the reply starts with "Approved".
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


def load_skills(directory: Path = SKILLS_DIR) -> list[dict]:
    skills = []
    for path in sorted(directory.glob("*.md")):
        try:
            skills.append(parse_skill(path.read_text(encoding="utf-8"), path.stem))
        except Exception as e:
            logger.warning("Skill ignoré ({}) : {}", path.name, e)
    return skills


def list_shortcuts(directory: Path = SKILLS_DIR) -> list[dict]:
    """Raccourcis de la bulle : [{"id": name, "label": str}] pour chaque skill qui a un `label`."""
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
            items.append((order, {"id": meta.get("name") or path.stem, "label": meta["label"]}))
    return [item for _, item in sorted(items, key=lambda x: (x[0], x[1]["label"]))]


VIEW_WORDS = ("voir", "consulter", "récupérer", "recuperer", "afficher", "regarder", "connaître",
              "connaitre", "vérifier", "verifier", "lire", "savoir", "quelle est", "quel est", "retrouver")
CHANGE_WORDS = ("modifier", "changer", "mettre à jour", "remplacer", "corriger", "passer à", "passer au")


def is_view_request(objectif: str) -> bool:
    """Vrai si la personne veut seulement voir une information (pas la changer)."""
    text = f" {(objectif or '').lower()} "
    view = any(f" {w}" in text for w in VIEW_WORDS)
    change = any(f" {w}" in text for w in CHANGE_WORDS)
    return view and not change


def match_plan(objectif: str, directory: Path = SKILLS_DIR) -> "tuple[str, list[str]] | None":
    """(skill, étapes) du premier skill dont un mot-clé apparaît dans l'objectif, sinon None.
    Demande de consultation → `steps_view` du skill s'il en a (rien à modifier ni à valider)."""
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
        if pos >= 0 and (best is None or pos < best[0]):  # le mot-clé cité en premier gagne
            best = (pos, meta.get("name") or path.stem, steps)
    return (best[1], best[2]) if best else None
