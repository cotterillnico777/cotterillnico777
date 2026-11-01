"""Minimaler X-API-Client (v2): Post erstellen, eigenen Account abfragen.

Schlüssel kommen ausschließlich aus der Umgebung:
  X_API_KEY, X_API_SECRET           (App: "API Key and Secret" / Consumer Keys)
  X_ACCESS_TOKEN, X_ACCESS_SECRET   (Account: "Access Token and Secret", Read+Write)
"""

from __future__ import annotations

import os

import requests

from .oauth import auth_header

API_BASE = os.environ.get("X_API_BASE", "https://api.x.com")
ENV_KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")


class XError(RuntimeError):
    pass


class XClient:
    def __init__(self, session: requests.Session | None = None, base: str = API_BASE, timeout: float = 20) -> None:
        missing = [k for k in ENV_KEYS if not os.environ.get(k)]
        if missing:
            raise XError("Fehlende Zugangsdaten in .env: " + ", ".join(missing))
        self._ck, self._cs = os.environ["X_API_KEY"], os.environ["X_API_SECRET"]
        self._tk, self._ts = os.environ["X_ACCESS_TOKEN"], os.environ["X_ACCESS_SECRET"]
        self.session = session or requests.Session()
        self.base, self.timeout = base.rstrip("/"), timeout

    def __repr__(self) -> str:  # Schlüssel nie ausgeben
        return f"XClient(base={self.base!r}, keys=***)"

    def _request(self, method: str, path: str, json_body: dict | None = None) -> dict:
        url = self.base + path
        headers = {"Authorization": auth_header(method, url, self._ck, self._cs, self._tk, self._ts)}
        resp = self.session.request(method, url, json=json_body, headers=headers, timeout=self.timeout)
        if resp.status_code >= 400:
            detail = resp.text[:300]
            hint = {401: "Schlüssel falsch oder abgelaufen",
                    403: "keine Schreibrechte (App auf 'Read and write' stellen und Access Token NEU erzeugen) "
                         "oder Guthaben/Abrechnung fehlt",
                    429: "Rate Limit erreicht, später erneut versuchen"}.get(resp.status_code, "")
            raise XError(f"X-API {resp.status_code} {hint}: {detail}")
        return resp.json()

    def me(self) -> dict:
        return self._request("GET", "/2/users/me")["data"]

    def create_post(self, text: str) -> str:
        data = self._request("POST", "/2/tweets", {"text": text})
        return data["data"]["id"]
