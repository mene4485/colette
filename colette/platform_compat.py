"""Petites différences macOS / Linux / Windows, réunies ici.

- `setup_console()` : console en UTF-8 (Windows : accents et émojis des logs sinon illisibles,
  voire UnicodeEncodeError en cp1252).
- `add_stop_handler(loop, callback)` : Ctrl+C (et SIGTERM hors Windows) → callback dans la boucle.
  `loop.add_signal_handler` n'existe pas sous Windows (NotImplementedError).
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Callable

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def add_stop_handler(loop: asyncio.AbstractEventLoop, callback: Callable[[], None]) -> None:
    if not IS_WINDOWS:
        loop.add_signal_handler(signal.SIGINT, callback)
        loop.add_signal_handler(signal.SIGTERM, callback)
        return
    # Windows : handler Python classique ; call_soon_threadsafe réveille la boucle (Proactor).
    signal.signal(signal.SIGINT, lambda *_: loop.call_soon_threadsafe(callback))
    if hasattr(signal, "SIGBREAK"):  # Ctrl+Pause / fermeture de la console
        signal.signal(signal.SIGBREAK, lambda *_: loop.call_soon_threadsafe(callback))
