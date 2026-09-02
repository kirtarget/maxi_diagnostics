"""One logging shape for both entrypoints."""

from __future__ import annotations

import logging
import os
from typing import Final


LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s %(message)s"
DEFAULT_LEVEL: Final[str] = "INFO"


def configure_logging(level: str | None = None) -> str:
    """Format the root logger and set its level, leaving uvicorn's own alone.

    Uvicorn configures ``uvicorn``, ``uvicorn.error`` and ``uvicorn.access`` with
    their own handlers and no propagation, so replacing the root handler here
    does not change access log formatting or verbosity.
    """
    resolved = (level or os.getenv("LOG_LEVEL", "") or DEFAULT_LEVEL).strip().upper()
    if not isinstance(logging.getLevelName(resolved), int):
        resolved = DEFAULT_LEVEL
    logging.basicConfig(level=resolved, format=LOG_FORMAT, force=True)
    logging.getLogger().setLevel(resolved)
    return resolved
