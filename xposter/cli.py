"""Kommandozeile: python -m xposter <befehl>

Ablauf: import/add (Entwurf) -> approve (Freigabe, optional mit Zeitpunkt) -> post-due (veröffentlichen)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from quantbot.config import load_dotenv

from .lint import check, x_length
from .store import STATUSES, Store, utcnow

DEFAULT_STORE = "state/xposter.json"


def _parse_time(s: str) -> datetime:
    """'2026-11-02 18:00' (deutsche Zeit) oder ISO mit Zeitzone -> UTC."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        from zoneinfo import ZoneInfo

        dt = dt.replace(tzinfo=ZoneInfo("Europe/Berlin"))
    return dt.astimezone(timezone.utc)


def _show(p, verbose: bool = False) -> str:
    when = f" ab {p.not_before}" if p.not_before and p.status == "approved" else ""
    posted = f" -> x.com/i/status/{p.x_id}" if p.x_id else ""
    head = f"[{p.id:>3}] {p.status:<8}{when}{posted}  ({x_length(p.text)} Z.)"
    text = p.text if verbose else (p.text.replace("\n", " / ")[:110] + ("…" if len(p.text) > 110 else ""))
    out = f"{head}\n      {text}"
    if p.error:
        out += f"\n      Fehler: {p.error}"
    return out


def cmd_import(args, store: Store) -> int:
    items = yaml.safe_load(Path(args.file).read_text(encoding="utf-8")) or []
    added = skipped = 0
    for it in items:
        text = it["text"] if isinstance(it, dict) else str(it)
        tags = it.get("tags", []) if isinstance(it, dict) else []
        errors, _ = check(text)
        if errors:
            print(f"übersprungen (Prüfung): {text[:60]}… -> {'; '.join(errors)}")
            skipped += 1
            continue
        if store.add(text, tags) is None:
            skipped += 1
        else:
            added += 1
    store.save()
    print(f"{added} Entwürfe hinzugefügt, {skipped} übersprungen (doppelt oder Prüfung).")
    return 0


def cmd_add(args, store: Store) -> int:
    errors, notes = check(args.text)
    for n in notes:
        print("Hinweis:", n)
    if errors:
        print("Nicht übernommen:", "; ".join(errors))
        return 1
    p = store.add(args.text)
    if p is None:
        print("Diesen Text gibt es schon.")
        return 1
    store.save()
    print(_show(p))
    return 0


def cmd_list(args, store: Store) -> int:
    posts = [p for p in store.posts if not args.status or p.status == args.status]
    if not posts:
        print("Keine Posts.")
    for p in posts:
        print(_show(p, args.full))
    counts = {s: sum(p.status == s for p in store.posts) for s in STATUSES}
    print("\n" + ", ".join(f"{k}: {v}" for k, v in counts.items() if v))
    return 0


def cmd_approve(args, store: Store) -> int:
    for pid in args.ids:
        p = store.get(pid)
        if p.status not in ("draft", "failed", "approved"):
            print(f"[{pid}] Status {p.status} – kann nicht freigegeben werden")
            continue
        errors, notes = check(p.text)
        if errors:
            print(f"[{pid}] blockiert: {'; '.join(errors)}")
            continue
        for n in notes:
            print(f"[{pid}] Hinweis: {n}")
        p.status, p.error = "approved", None
        p.approved_at = utcnow().isoformat(timespec="seconds")
        p.not_before = _parse_time(args.at).isoformat(timespec="seconds") if args.at else None
        print(_show(p))
    store.save()
    return 0


def cmd_reject(args, store: Store) -> int:
    for pid in args.ids:
        p = store.get(pid)
        if p.status == "posted":
            print(f"[{pid}] ist bereits veröffentlicht – auf X selbst löschen.")
            continue
        p.status = "rejected"
        print(_show(p))
    store.save()
    return 0


def cmd_edit(args, store: Store) -> int:
    p = store.get(args.id)
    if p.status == "posted":
        print("Bereits veröffentlicht – nicht änderbar.")
        return 1
    errors, notes = check(args.text)
    for n in notes:
        print("Hinweis:", n)
    if errors:
        print("Nicht übernommen:", "; ".join(errors))
        return 1
    p.text, p.status, p.not_before = args.text.strip(), "draft", None  # geänderter Text braucht neue Freigabe
    store.save()
    print(_show(p))
    print("Text geändert – bitte erneut freigeben (approve).")
    return 0


def cmd_post_due(args, store: Store, client_factory=None, now: datetime | None = None) -> int:
    now = now or utcnow()
    due = store.due(now)
    if not due:
        print("Nichts fällig.")
        return 0
    today = store.posted_since(now - timedelta(hours=24))
    budget = max(0, args.max_per_day - len(today))
    last = store.last_posted_at()
    if budget == 0:
        print(f"Tageslimit erreicht ({args.max_per_day} in 24 h). Nichts gepostet.")
        return 0
    if last and now - last < timedelta(minutes=args.min_gap):
        wait = timedelta(minutes=args.min_gap) - (now - last)
        print(f"Mindestabstand: nächster Post frühestens in {int(wait.total_seconds() // 60)} min.")
        return 0
    post = due[0]  # pro Aufruf höchstens ein Post -> Abstand bleibt gewahrt
    errors, _ = check(post.text)
    if errors:
        post.status, post.error = "failed", "; ".join(errors)
        store.save()
        print(_show(post))
        return 1
    if args.dry_run:
        print("PROBELAUF – würde jetzt posten:\n" + _show(post, verbose=True))
        return 0
    client = (client_factory or _client)()
    try:
        post.x_id = client.create_post(post.text)
        post.status, post.error = "posted", None
        post.posted_at = utcnow().isoformat(timespec="seconds")
    except Exception as exc:  # noqa: BLE001
        post.status, post.error = "failed", str(exc)[:300]
    store.save()
    print(_show(post, verbose=True))
    return 0 if post.status == "posted" else 1


def cmd_whoami(args, store: Store, client_factory=None) -> int:
    me = (client_factory or _client)().me()
    print(f"Verbunden als @{me['username']} ({me.get('name', '')}), ID {me['id']}")
    return 0


def _client():
    from .client import XClient

    return XClient()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xposter", description="Posts vorbereiten, freigeben, veröffentlichen")
    p.add_argument("--store", default=DEFAULT_STORE)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("import", help="Entwürfe aus YAML übernehmen")
    s.add_argument("file")
    s.set_defaults(func=cmd_import)
    s = sub.add_parser("add", help="neuen Entwurf anlegen")
    s.add_argument("text")
    s.set_defaults(func=cmd_add)
    s = sub.add_parser("list", help="Posts anzeigen")
    s.add_argument("--status", choices=STATUSES)
    s.add_argument("--full", action="store_true", help="ganzen Text zeigen")
    s.set_defaults(func=cmd_list)
    s = sub.add_parser("approve", help="Entwürfe freigeben")
    s.add_argument("ids", type=int, nargs="+")
    s.add_argument("--at", help="frühester Zeitpunkt, z. B. '2026-11-02 18:00' (deutsche Zeit)")
    s.set_defaults(func=cmd_approve)
    s = sub.add_parser("reject", help="Entwürfe verwerfen")
    s.add_argument("ids", type=int, nargs="+")
    s.set_defaults(func=cmd_reject)
    s = sub.add_parser("edit", help="Text ändern (braucht danach neue Freigabe)")
    s.add_argument("id", type=int)
    s.add_argument("text")
    s.set_defaults(func=cmd_edit)
    s = sub.add_parser("post-due", help="nächsten fälligen, freigegebenen Post veröffentlichen")
    s.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts posten")
    s.add_argument("--max-per-day", type=int, default=4)
    s.add_argument("--min-gap", type=int, default=90, help="Minuten zwischen zwei Posts")
    s.set_defaults(func=cmd_post_due)
    s = sub.add_parser("whoami", help="Zugangsdaten prüfen (zeigt den verbundenen Account)")
    s.set_defaults(func=cmd_whoami)
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    store = Store(args.store)
    try:
        return args.func(args, store)
    except Exception as exc:  # noqa: BLE001 – verständliche Meldung statt Traceback
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
