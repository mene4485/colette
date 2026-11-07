"""Relance le process en arm64 si le terminal tourne sous Rosetta (x86_64).

Le .venv contient des wheels arm64 (pydantic_core, etc.) : sous Rosetta, le Python
universel démarre en x86_64 et l'import échoue. À importer AVANT toute dépendance.
"""

import os
import platform
import subprocess
import sys


def ensure_arm64() -> None:
    if sys.platform != "darwin" or platform.machine() != "x86_64":
        return
    try:
        translated = subprocess.run(
            ["sysctl", "-n", "sysctl.proc_translated"], capture_output=True, text=True
        ).stdout.strip()
    except OSError:
        return
    if translated == "1" and not os.environ.get("COLETTE_ARCH_REEXEC"):
        os.environ["COLETTE_ARCH_REEXEC"] = "1"
        os.execv("/usr/bin/arch", ["arch", "-arm64", sys.executable, *sys.argv])


ensure_arm64()
