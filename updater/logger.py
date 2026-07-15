from __future__ import annotations

import logging
from pathlib import Path


def get_logger(name: str, log_file: str | Path) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger

