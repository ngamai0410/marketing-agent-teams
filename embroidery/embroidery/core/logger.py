"""
Centralised logging for all agents and infrastructure.

Console : INFO+ (human-readable, goes to stdout)
File    : DEBUG+ → logs/<YYYYMMDD_HHMMSS>.log (one file per process)

Usage in any module:
    from embroidery.core.logger import get_logger
    log = get_logger(__name__)
    log.info("something happened")
    log.debug("tool=%s input=%s", name, inputs)
"""

import logging
import sys
from datetime import datetime

from embroidery.core.config import settings

# One shared run ID + log file per Python process
RUN_ID: str = datetime.now().strftime("%Y%m%d_%H%M%S")

_LOG_DIR = settings.paths.logs
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_file_handler: logging.FileHandler | None = None


def _shared_file_handler() -> logging.FileHandler:
    global _file_handler
    if _file_handler is None:
        path = _LOG_DIR / f"{RUN_ID}.log"
        _file_handler = logging.FileHandler(path, encoding="utf-8")
        _file_handler.setLevel(logging.DEBUG)
        _file_handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
            datefmt="%H:%M:%S",
        ))
    return _file_handler


def get_logger(name: str) -> logging.Logger:
    """Return a logger wired to console (INFO) and the run log file (DEBUG)."""
    log = logging.getLogger(name)
    if log.handlers:
        return log  # already configured

    log.setLevel(logging.DEBUG)
    log.propagate = False  # don't bubble up to root logger

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    ))
    log.addHandler(ch)
    log.addHandler(_shared_file_handler())

    return log
