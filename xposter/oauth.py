"""OAuth 1.0a (HMAC-SHA1) für X-API-Aufrufe im Namen eines Accounts (User Context).

Bei JSON-Bodies (z. B. POST /2/tweets) fließen nur URL-Query- und OAuth-Parameter in die
Signatur ein, nicht der Body.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit


def _enc(s: str) -> str:
    return quote(str(s), safe="~")  # RFC 3986: nur A-Z a-z 0-9 - . _ ~ unkodiert


def signature(method: str, url: str, params: dict[str, str], consumer_secret: str, token_secret: str) -> str:
    parts = urlsplit(url)
    base_url = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))
    all_params = list(params.items()) + parse_qsl(parts.query, keep_blank_values=True)
    # Schlüssel und Werte kodieren, dann sortieren (nach Schlüssel, bei Gleichheit nach Wert)
    norm = "&".join(f"{k}={v}" for k, v in sorted((_enc(k), _enc(v)) for k, v in all_params))
    base = "&".join([method.upper(), _enc(base_url), _enc(norm)])
    key = f"{_enc(consumer_secret)}&{_enc(token_secret)}"
    digest = hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def auth_header(method: str, url: str, consumer_key: str, consumer_secret: str, token: str, token_secret: str,
                extra_params: dict[str, str] | None = None, nonce: str | None = None,
                timestamp: str | None = None) -> str:
    oauth = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    sig = signature(method, url, {**oauth, **(extra_params or {})}, consumer_secret, token_secret)
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{_enc(k)}="{_enc(v)}"' for k, v in sorted(oauth.items()))
