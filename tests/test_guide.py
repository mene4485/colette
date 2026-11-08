"""Tests du guide manuel (lecture de la réponse du LLM).  .venv/bin/python tests/test_guide.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from colette.guide import format_elements, parse_decision  # noqa: E402


def test_parse_step():
    d = parse_decision('```json\n{"done": false, "id": "c3", "action": "click", '
                       '"instruction": "Cliquez sur « Mon forfait ».", "irreversible": true}\n```')
    assert d == {"done": False, "id": "c3", "action": "click",
                 "instruction": "Cliquez sur « Mon forfait ».", "irreversible": True}


def test_parse_done():
    assert parse_decision('{"done": true, "summary": "C\'est fait."}') == {"done": True, "summary": "C'est fait."}


def test_parse_invalid():
    assert parse_decision("pas du json") is None
    assert parse_decision('{"done": false}') is None  # pas de consigne
    assert parse_decision('{"done": false, "instruction": "x", "action": "hover"}')["action"] == "click"


def test_format_elements():
    out = format_elements([{"id": "c1", "tag": "input", "type": "password", "text": "", "inView": False}])
    assert out == "c1 | input[password] | (no label) | no"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK : guide")
