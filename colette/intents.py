"""Commandes vocales déterministes : oui / non / stop / pause / reprise, reconnues AVANT le LLM.

`parse_intent(text, context)` → "yes" | "no" | "stop" | "pause" | "resume" | "next" | None
Contextes (ce que Colette attend) :
- "guide"   : guide manuel pas à pas → next (« c'est fait », « suivant ») / stop
- "confirm" : carte OUI/NON affichée → yes / no / stop / pause
- "working" : démarche en cours → stop / pause
- "paused"  : démarche en pause → resume / stop
- "idle"    : rien en cours → stop seulement (le reste part au LLM)

Normalisation : minuscules, sans accents, apostrophes et ponctuation → espaces, mots entiers.
`is_noise(text)` repère les transcriptions sans contenu (bruit, « euh », hallucinations STT).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """« Arrêtez, s'il vous plaît ! » → « arretez s il vous plait »."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return _NON_WORD.sub(" ", text).strip()


def _has(norm: str, phrases: tuple[str, ...]) -> bool:
    padded = f" {norm} "
    return any(f" {p} " in padded for p in phrases)


# Expressions déjà normalisées (sans accents, apostrophes → espace).
STOP = ("stop", "stoppe", "stoppez", "arrete", "arretez", "arrete tout", "arretez tout",
        "annule tout", "annulez tout", "laisse tomber", "laissez tomber")
PAUSE = ("pause", "attends", "attendez", "attend", "je reprends la main", "je prends la main",
         "une seconde", "une minute", "deux secondes", "un instant", "minute")
RESUME = ("continue", "continuez", "reprends", "reprenez", "c est bon", "vas y", "allez y",
          "on continue", "tu peux continuer", "vous pouvez continuer", "go")
YES = ("oui", "ouais", "d accord", "ok", "okay", "vas y", "allez y", "je confirme", "confirme",
       "confirmez", "c est bon", "validez", "valide", "valider", "bien sur", "exactement",
       "parfait", "tout a fait", "absolument", "allez")
NO = ("non", "surtout pas", "annule", "annulez", "n en fais rien", "n en faites rien",
      "ne valide pas", "ne validez pas", "pas du tout", "jamais", "pas question", "nan")
# Négations qui transforment un « oui-mot » en refus (« je ne confirme pas », « pas d'accord »).
NEGATED = ("pas d accord", "ne confirme pas", "ne confirmez pas", "ne valide pas", "ne validez pas",
           "je ne veux pas", "veux pas", "c est pas bon", "ce n est pas bon", "n est pas bon")


NEXT = ("suivant", "etape suivante", "c est fait", "c est bon", "voila", "j ai clique", "j ai fini",
        "j ai tape", "et maintenant", "et ensuite", "ok c est fait")


def parse_intent(text: str, context: str = "idle") -> Optional[str]:
    norm = normalize(text)
    if not norm:
        return None
    # « Stop » / « arrêtez » partout. « Arrêtez » seul en pleine confirmation = stop aussi.
    if _has(norm, STOP):
        return "stop"
    if context == "guide":  # guide manuel : la personne dit qu'elle a fait l'étape
        if _has(norm, NEGATED) or _has(norm, ("pas encore", "je trouve pas", "je ne trouve pas")):
            return None
        return "next" if _has(norm, NEXT) else None
    if context == "confirm":
        if _has(norm, NEGATED) or _has(norm, NO):
            return "no"
        if _has(norm, YES):
            return "yes"
        if _has(norm, PAUSE):
            return "pause"
        return None
    if context == "paused":
        if _has(norm, NEGATED):
            return None
        if _has(norm, RESUME):
            return "resume"
        return None
    if context == "working":
        if _has(norm, PAUSE):
            return "pause"
        return None
    return None


# Bruit : onomatopées et hallucinations classiques du STT sur du silence.
FILLERS = {"euh", "heu", "hum", "hmm", "hm", "mmh", "mm", "bah", "ben", "beh", "ah", "oh", "eh",
           "hein", "pff", "ouf", "hop", "la", "et", "alors", "donc", "bon", "voila", "ha", "hu",
           "merci"}  # « Merci. » : hallucination fréquente de Gladia sur la fin d'écho
HALLUCINATIONS = ("sous titrage", "sous titres", "merci d avoir regarde", "abonnez vous",
                  "amara org", "st 501")


def is_noise(text: str) -> bool:
    norm = normalize(text)
    if len(norm.replace(" ", "")) < 2:
        return True
    if _has(norm, HALLUCINATIONS):
        return True
    return all(w in FILLERS for w in norm.split())
