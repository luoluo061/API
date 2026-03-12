from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def log_event(event: str, **fields: object) -> str:
    payload = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
        **fields,
    }
    line = json.dumps(payload, ensure_ascii=True, default=str)
    logging.getLogger("web_adapter").info(line)
    return line


def append_request_log(path: Path, event: str, **fields: object) -> None:
    line = log_event(event, **fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
