"""Tests für xposter. Es wird nie die echte X-API aufgerufen."""

import argparse
import json
from datetime import timedelta

import pytest

from xposter import cli
from xposter.client import XClient, XError
from xposter.lint import check, x_length
from xposter.oauth import auth_header, signature
from xposter.store import Store, utcnow

KEYS = {"X_API_KEY": "ck", "X_API_SECRET": "cs", "X_ACCESS_TOKEN": "tk", "X_ACCESS_SECRET": "ts"}


def test_oauth_signature_matches_documented_reference():
    params = {
        "status": "Hello Ladies + Gentlemen, a signed OAuth request!", "include_entities": "true",
        "oauth_consumer_key": "xvz1evFS4wEEPTGEFPHBog", "oauth_nonce": "kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg",
        "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": "1318622958",
        "oauth_token": "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb", "oauth_version": "1.0",
    }
    sig = signature("POST", "https://api.twitter.com/1.1/statuses/update.json", params,
                    "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw", "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE")
    assert sig == "hCtSmYh+iHYCEqBWrE7C7hYmtUk="


def test_auth_header_contains_all_oauth_fields():
    h = auth_header("POST", "https://api.x.com/2/tweets", "ck", "cs", "tk", "ts", nonce="n", timestamp="1")
    assert h.startswith("OAuth ")
    for f in ("oauth_consumer_key", "oauth_nonce", "oauth_signature", "oauth_token", "oauth_timestamp"):
        assert f + '="' in h


@pytest.mark.parametrize("text", [
    "This will 100x guaranteed", "buy now before it's too late", "risk-free gains",
    "CA: 0x52908400098527886E0F7030069857D2E4169EE7", "jetzt kaufen!", "connect your wallet to claim",
    "x" * 281,
])
def test_lint_blocks(text):
    errors, _ = check(text)
    assert errors


def test_lint_allows_memes_and_notes_cashtags():
    assert check("Bought the dip. The dip had a basement.") == ([], [])
    errors, notes = check("$DOGE holders at 3am")
    assert not errors and "$DOGE" in notes[0]
    assert x_length("gm 🐸") == 5  # Emoji zählt doppelt
    assert x_length("see https://example.com/very/long/path/abc") == 4 + 23


def _args(**kw):
    base = dict(dry_run=False, max_per_day=4, min_gap=90)
    base.update(kw)
    return argparse.Namespace(**base)


class FakeClient:
    def __init__(self, fail=False):
        self.posted, self.fail = [], fail

    def create_post(self, text):
        if self.fail:
            raise XError("X-API 403 keine Schreibrechte")
        self.posted.append(text)
        return str(1000 + len(self.posted))


def _store(tmp_path, n=3):
    s = Store(tmp_path / "q.json")
    for i in range(n):
        s.add(f"meme number {i}")
    s.save()
    return s


def test_nothing_is_posted_without_approval(tmp_path):
    s = _store(tmp_path)
    fake = FakeClient()
    assert cli.cmd_post_due(_args(), s, client_factory=lambda: fake) == 0
    assert fake.posted == []


def test_post_due_posts_one_approved_and_records_id(tmp_path):
    s = _store(tmp_path)
    s.get(2).status = "approved"
    s.get(3).status = "approved"
    fake = FakeClient()
    assert cli.cmd_post_due(_args(), s, client_factory=lambda: fake) == 0
    assert fake.posted == ["meme number 1"]  # nur einer pro Aufruf
    reloaded = Store(tmp_path / "q.json")
    assert reloaded.get(2).status == "posted" and reloaded.get(2).x_id == "1001"
    assert reloaded.get(3).status == "approved"


def test_min_gap_and_daily_limit(tmp_path):
    s = _store(tmp_path, n=6)
    for p in s.posts:
        p.status = "approved"
    fake = FakeClient()
    now = utcnow()
    cli.cmd_post_due(_args(), s, client_factory=lambda: fake, now=now)
    cli.cmd_post_due(_args(), s, client_factory=lambda: fake, now=now + timedelta(minutes=30))
    assert len(fake.posted) == 1  # Mindestabstand 90 min
    for p in s.posts:  # Zeitstempel künstlich in die Vergangenheit, um das Tageslimit zu prüfen
        if p.status == "posted":
            p.posted_at = (now - timedelta(hours=1)).isoformat()
    for k in range(3):
        s.add(f"filler {k}")
        f = s.posts[-1]
        f.status, f.posted_at = "posted", (now - timedelta(hours=2 + k)).isoformat()
    cli.cmd_post_due(_args(), s, client_factory=lambda: fake, now=now)
    assert len(fake.posted) == 1  # 4 in 24 h erreicht


def test_not_before_and_dry_run(tmp_path):
    s = _store(tmp_path, n=1)
    p = s.get(1)
    p.status, p.not_before = "approved", (utcnow() + timedelta(hours=2)).isoformat()
    fake = FakeClient()
    cli.cmd_post_due(_args(), s, client_factory=lambda: fake)
    assert fake.posted == []
    p.not_before = None
    cli.cmd_post_due(_args(dry_run=True), s, client_factory=lambda: fake)
    assert fake.posted == [] and p.status == "approved"


def test_api_failure_marks_failed_and_keeps_text(tmp_path):
    s = _store(tmp_path, n=1)
    s.get(1).status = "approved"
    assert cli.cmd_post_due(_args(), s, client_factory=lambda: FakeClient(fail=True)) == 1
    p = Store(tmp_path / "q.json").get(1)
    assert p.status == "failed" and "403" in p.error and p.text == "meme number 0"


def test_edit_requires_new_approval_and_duplicates_rejected(tmp_path):
    s = _store(tmp_path, n=1)
    s.get(1).status = "approved"
    cli.cmd_edit(argparse.Namespace(id=1, text="new meme"), s)
    assert s.get(1).status == "draft"
    assert s.add("NEW   meme") is None  # gleicher Text (normalisiert)


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, status=201, body=None):
        self.calls, self.status = [], status
        self.body = body or {"data": {"id": "42", "text": "hi"}}

    def request(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append((method, url, json, headers))
        return FakeResponse(self.status, self.body)


def test_client_sends_signed_json_post(monkeypatch):
    for k, v in KEYS.items():
        monkeypatch.setenv(k, v)
    sess = FakeSession()
    c = XClient(session=sess, base="https://api.x.com")
    assert c.create_post("gm") == "42"
    method, url, body, headers = sess.calls[0]
    assert (method, url, body) == ("POST", "https://api.x.com/2/tweets", {"text": "gm"})
    assert headers["Authorization"].startswith("OAuth ") and 'oauth_consumer_key="ck"' in headers["Authorization"]
    assert "cs" not in repr(c) and "ts" not in repr(c)


def test_client_errors_are_explained(monkeypatch):
    for k, v in KEYS.items():
        monkeypatch.setenv(k, v)
    c = XClient(session=FakeSession(status=403, body={"detail": "forbidden"}))
    with pytest.raises(XError, match="Read and write"):
        c.create_post("gm")
    for k in KEYS:
        monkeypatch.delenv(k)
    with pytest.raises(XError, match="Fehlende Zugangsdaten"):
        XClient()
