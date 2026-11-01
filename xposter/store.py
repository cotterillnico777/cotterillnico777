"""Warteschlange der Posts (JSON-Datei, atomar geschrieben).

Status: draft -> approved -> posted   (oder rejected / failed)
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ("draft", "approved", "posted", "rejected", "failed")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def text_key(text: str) -> str:
    return hashlib.sha1(" ".join(text.split()).lower().encode()).hexdigest()[:12]


@dataclass
class Post:
    id: int
    text: str
    status: str = "draft"
    created_at: str = field(default_factory=lambda: utcnow().isoformat(timespec="seconds"))
    not_before: str | None = None  # frühester Zeitpunkt (UTC, ISO), None = sofort nach Freigabe
    approved_at: str | None = None
    posted_at: str | None = None
    x_id: str | None = None
    error: str | None = None
    tags: list[str] = field(default_factory=list)


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.posts: list[Post] = []
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.posts = [Post(**p) for p in data["posts"]]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"posts": [asdict(p) for p in self.posts]}, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, pid: int) -> Post:
        for p in self.posts:
            if p.id == pid:
                return p
        raise KeyError(f"Kein Post mit ID {pid}")

    def add(self, text: str, tags: list[str] | None = None) -> Post | None:
        """Neuer Entwurf; None, wenn derselbe Text schon existiert (egal in welchem Status)."""
        key = text_key(text)
        if any(text_key(p.text) == key for p in self.posts):
            return None
        post = Post(id=max((p.id for p in self.posts), default=0) + 1, text=text.strip(), tags=tags or [])
        self.posts.append(post)
        return post

    def posted_since(self, since: datetime) -> list[Post]:
        return [p for p in self.posts if p.status == "posted" and p.posted_at
                and datetime.fromisoformat(p.posted_at) >= since]

    def last_posted_at(self) -> datetime | None:
        ts = [datetime.fromisoformat(p.posted_at) for p in self.posts if p.status == "posted" and p.posted_at]
        return max(ts) if ts else None

    def due(self, now: datetime) -> list[Post]:
        out = [p for p in self.posts if p.status == "approved"
               and (p.not_before is None or datetime.fromisoformat(p.not_before) <= now)]
        return sorted(out, key=lambda p: (p.not_before or "", p.id))
