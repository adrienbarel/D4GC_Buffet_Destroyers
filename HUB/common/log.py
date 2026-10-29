"""Timestamped console logging shared by every process (hub, devices, cloud, scripts).

Usage:
    from common.log import get_logger
    log = get_logger("hub")
    log.info("budget changed to %s MB", 150)
"""
from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"
_DATEFMT = "%H:%M:%S"
_configured = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger that prints ``HH:MM:SS LEVEL [name] message`` to stderr."""
    global _configured
    if not _configured:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
        root = logging.getLogger("d4gc")
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False
        _configured = True
    return logging.getLogger(f"d4gc.{name}")
