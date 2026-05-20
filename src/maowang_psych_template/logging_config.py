from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from .config import log_dir


def setup_logging(directory: Path | None = None) -> None:
    directory = directory or log_dir()
    directory.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(sys.stderr, level="INFO", enqueue=True)
    logger.add(
        directory / "app.log",
        level="INFO",
        rotation="10 MB",
        retention="14 days",
        encoding="utf-8",
        enqueue=True,
    )
    logger.add(
        directory / "error.log",
        level="ERROR",
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )


__all__ = ["logger", "setup_logging"]

