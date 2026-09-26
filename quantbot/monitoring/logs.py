"""Strukturiertes Logging (JSON-Zeilen) mit automatischer Schwärzung von Secrets."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

SECRET_ENV_PATTERN = re.compile(r"(KEY|SECRET|PASSWORD|TOKEN|PASSPHRASE)", re.I)


def _secret_values() -> list[str]:
    return [v for k, v in os.environ.items() if SECRET_ENV_PATTERN.search(k) and v and len(v) >= 6]


def redact(text: str) -> str:
    for value in _secret_values():
        text = text.replace(value, "***")
    return text


class RedactingFilter(logging.Filter):
    """Ersetzt Werte geheimer Umgebungsvariablen in jeder Lognachricht durch ***."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.getMessage()))
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "data", None)
        if isinstance(extra, dict):
            entry["data"] = json.loads(redact(json.dumps(extra, default=str)))
        if record.exc_info:
            entry["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(log_file: str | None = None, level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
    handlers: list[logging.Handler] = [console]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(JsonFormatter())
        handlers.append(fh)
    for h in handlers:
        h.addFilter(RedactingFilter())
        root.addHandler(h)
    for noisy in ("ccxt", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
