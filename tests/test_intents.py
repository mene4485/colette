"""Tests des commandes vocales.  .venv/bin/python tests/test_intents.py  (ou pytest)"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from colette.intents import is_noise, parse_intent  # noqa: E402

CASES = [
    # (phrase, contexte, intention attendue)
    ("Oui", "confirm", "yes"),
    ("Oui, vas-y.", "confirm", "yes"),
    ("D'accord, allez-y", "confirm", "yes"),
    ("Je confirme.", "confirm", "yes"),
    ("C'est bon, validez", "confirm", "yes"),
    ("Non.", "confirm", "no"),
    ("Non merci", "confirm", "no"),
    ("Surtout pas !", "confirm", "no"),
    ("Je ne confirme pas", "confirm", "no"),
    ("Pas d'accord", "confirm", "no"),
    ("N'en faites rien", "confirm", "no"),
    ("Stop !", "confirm", "stop"),
    ("Arrêtez de parler !", "idle", "hush"),
    ("Taisez-vous", "working", "hush"),
    ("Chut.", "confirm", "hush"),
    ("Quittez l'appel", "idle", "hangup"),
    ("Quittez la pelle.", "idle", "hangup"),
    ("Arrêtez l'appel s'il vous plaît", "working", "hangup"),
    ("Raccrochez", "confirm", "hangup"),
    ("Arrêtez", "idle", "stop"),
    ("Arrêtez tout", "working", "stop"),
    ("Arrête.", "working", "stop"),
    ("Attendez, je reprends la main", "working", "pause"),
    ("Pause", "working", "pause"),
    ("Continuez", "paused", "resume"),
    ("C'est bon, vous pouvez continuer", "paused", "resume"),
    ("Reprends", "paused", "resume"),
    ("Stop", "paused", "stop"),
    # Pas de fausse détection évidente
    ("Mon forfait est trop cher", "idle", None),
    ("Je voudrais changer de forfait", "working", None),
    ("Bonjour", "confirm", None),
    ("Combien ça coûte ?", "confirm", None),
    ("Le forfait à deux euros", "working", None),
    ("Je sais pas", "paused", None),
    ("Bonnet", "confirm", None),     # « non » est un mot entier, pas une sous-chaîne
    ("Ouistiti", "confirm", None),
    ("Continuer la démarche", "idle", None),  # hors pause : part au LLM
]

NOISE = ["", "   ", ".", "Euh", "euh...", "Hum hum", "Bah", "Sous-titrage ST' 501", "a", "Merci."]
NOT_NOISE = ["Oui", "Le forfait à deux euros", "C'est bon", "Non", "Deux euros"]


def test_intents():
    failures = [(t, c, e, parse_intent(t, c)) for t, c, e in CASES if parse_intent(t, c) != e]
    assert not failures, "\n".join(f"{t!r} [{c}] → {g!r}, attendu {e!r}" for t, c, e, g in failures)


def test_noise():
    assert all(is_noise(t) for t in NOISE), [t for t in NOISE if not is_noise(t)]
    assert not any(is_noise(t) for t in NOT_NOISE), [t for t in NOT_NOISE if is_noise(t)]


if __name__ == "__main__":
    test_intents()
    test_noise()
    print(f"OK : {len(CASES)} phrases, {len(NOISE) + len(NOT_NOISE)} cas de bruit")
