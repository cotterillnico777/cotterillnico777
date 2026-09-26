"""SQLite-Journal: jeder Trade, jede Order, jedes Signal ist später nachvollziehbar."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..core.types import Order

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, started_at TEXT, mode TEXT, git_commit TEXT, version TEXT, config TEXT);
CREATE TABLE IF NOT EXISTS heartbeat (
    run_id TEXT PRIMARY KEY, ts TEXT, status TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS signals (
    ts TEXT, run_id TEXT, symbol TEXT, value REAL, stop_distance REAL, regime TEXT,
    strategy TEXT, features TEXT);
CREATE TABLE IF NOT EXISTS orders (
    client_id TEXT PRIMARY KEY, run_id TEXT, symbol TEXT, side TEXT, type TEXT, qty REAL,
    price REAL, stop_price REAL, reduce_only INTEGER, status TEXT, exchange_id TEXT,
    filled_qty REAL, avg_price REAL, fee REAL, reason TEXT, error TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT, client_id TEXT, run_id TEXT, symbol TEXT, side TEXT,
    qty REAL, price REAL, fee REAL, ts TEXT);
CREATE TABLE IF NOT EXISTS equity (
    ts TEXT, run_id TEXT, equity REAL, gross_exposure REAL, net_exposure REAL, drawdown REAL);
CREATE TABLE IF NOT EXISTS positions (
    ts TEXT, run_id TEXT, symbol TEXT, qty REAL, entry_price REAL, stop REAL, take_profit REAL,
    unrealized REAL);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, symbol TEXT, direction TEXT,
    entry_time TEXT, exit_time TEXT, entry_price REAL, exit_price REAL, qty REAL, leverage REAL,
    stop REAL, take_profit REAL, gross_pnl REAL, fees REAL, funding REAL, net_pnl REAL,
    regime TEXT, strategy TEXT, strategy_version TEXT, signal_strength REAL,
    entry_reason TEXT, exit_reason TEXT, mfe_pct REAL, mae_pct REAL, features TEXT);
CREATE TABLE IF NOT EXISTS events (
    ts TEXT, run_id TEXT, level TEXT, type TEXT, message TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Journal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.run_id = ""

    def _exec(self, sql: str, args: tuple = ()) -> None:
        with self.lock:
            self.db.execute(sql, args)
            self.db.commit()

    def query(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    # ------------------------------------------------------------------ Lauf
    def start_run(self, run_id: str, mode: str, git_commit: str, version: str, config: dict) -> None:
        self.run_id = run_id
        self._exec("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?)",
                   (run_id, now(), mode, git_commit, version, json.dumps(config, default=str)))

    def heartbeat(self, status: str, detail: str = "") -> None:
        self._exec("INSERT OR REPLACE INTO heartbeat VALUES (?,?,?,?)", (self.run_id, now(), status, detail))

    # ---------------------------------------------------------------- Daten
    def signal(self, ts, symbol, value, stop_distance, regime, strategy, features: str) -> None:
        self._exec("INSERT INTO signals VALUES (?,?,?,?,?,?,?,?)",
                   (str(ts), self.run_id, symbol, value, stop_distance, regime, strategy, features))

    def order(self, o: Order) -> None:
        self._exec(
            "INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (o.client_id, self.run_id, o.symbol, o.side.value, o.type.value, o.qty, o.price, o.stop_price,
             int(o.reduce_only), o.status.value, o.exchange_id, o.filled_qty, o.avg_price, o.fee, o.reason,
             o.error, o.created_at or now(), now()),
        )

    def get_order_row(self, client_id: str):
        rows = self.query("SELECT * FROM orders WHERE client_id=?", (client_id,))
        return rows[0] if rows else None

    def fill(self, client_id, symbol, side, qty, price, fee, ts=None) -> None:
        self._exec("INSERT INTO fills (client_id, run_id, symbol, side, qty, price, fee, ts) VALUES (?,?,?,?,?,?,?,?)",
                   (client_id, self.run_id, symbol, side, qty, price, fee, ts or now()))

    def equity(self, ts, equity, gross, net, drawdown) -> None:
        self._exec("INSERT INTO equity VALUES (?,?,?,?,?,?)", (str(ts), self.run_id, equity, gross, net, drawdown))

    def position(self, ts, symbol, qty, entry, stop, tp, unrealized) -> None:
        self._exec("INSERT INTO positions VALUES (?,?,?,?,?,?,?,?)",
                   (str(ts), self.run_id, symbol, qty, entry, stop, tp, unrealized))

    def trade(self, t: dict) -> None:
        cols = ["symbol", "direction", "entry_time", "exit_time", "entry_price", "exit_price", "qty", "leverage",
                "stop", "take_profit", "gross_pnl", "fees", "funding", "net_pnl", "regime", "strategy",
                "strategy_version", "signal_strength", "entry_reason", "exit_reason", "mfe_pct", "mae_pct",
                "features"]
        vals = [str(t.get(c)) if c.endswith("time") else t.get(c) for c in cols]
        self._exec(f"INSERT INTO trades (run_id, {', '.join(cols)}) VALUES (?{', ?' * len(cols)})",
                   (self.run_id, *vals))

    def event(self, level: str, type_: str, message: str, data: dict | None = None) -> None:
        self._exec("INSERT INTO events VALUES (?,?,?,?,?,?)",
                   (now(), self.run_id, level, type_, message, json.dumps(data or {}, default=str)))

    def set(self, key: str, value) -> None:
        self._exec("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, json.dumps(value, default=str)))

    def get(self, key: str, default=None):
        rows = self.query("SELECT value FROM kv WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default
