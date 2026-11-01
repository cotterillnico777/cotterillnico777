"""Inhaltsprüfung vor dem Posten.

FEHLER (blockiert): zu lang, leer, Kursversprechen / Kaufaufforderungen, Contract-Adressen.
HINWEIS (erlaubt):  Cashtags ($XYZ) – erwähnt einen konkreten Coin, bewusst prüfen.

Ziel: ein Meme-Account über Krypto-Kultur, kein Werbe- oder Pump-Kanal.
"""

from __future__ import annotations

import re
import unicodedata

MAX_LEN = 280
URL_LEN = 23  # X zählt jede URL als 23 Zeichen

# Kursversprechen und Kaufaufforderungen (Deutsch/Englisch)
PROMISE_PATTERNS = [
    r"\b\d{2,}\s?x\b",                     # 100x, 1000 x
    r"\bguarantee(d|s)?\b", r"\bgarantiert\b",
    r"\brisk[\s-]?free\b", r"\bohne risiko\b", r"\brisikolos\b",
    r"\bcan'?t lose\b", r"\bsure ?thing\b", r"\bsichere?r? gewinn",
    r"\bbuy (it )?now\b", r"\bape in\b", r"\bjetzt kaufen\b", r"\bschnell kaufen\b",
    r"\bnext (100|1000)\s?x\b", r"\bpassive income\b",
    r"\bpresale\b", r"\bairdrop\b.*\b(claim|connect)\b", r"\bconnect (your )?wallet\b",
]
# Contract-Adressen: EVM (0x + 40 Hex) und Solana-artige Base58-Strings (32–44 Zeichen)
CA_PATTERNS = [r"\b0x[a-fA-F0-9]{40}\b", r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"]
CASHTAG = r"(?<![\w$])\$[A-Za-z][A-Za-z0-9]{1,9}\b"
URL = r"https?://\S+"


def x_length(text: str) -> int:
    """Näherung der X-Zählweise: URLs = 23, Emoji/CJK = 2, sonst 1."""
    n = 0
    rest = re.sub(URL, "", text)
    n += URL_LEN * len(re.findall(URL, text))
    for ch in rest:
        if unicodedata.category(ch) in ("Mn", "Me", "Cf") or ch in "️":
            continue  # Kombinationszeichen / Variation Selector / ZWJ
        n += 2 if ord(ch) > 0x10FF else 1
    return n


def check(text: str) -> tuple[list[str], list[str]]:
    errors, notes = [], []
    if not text.strip():
        errors.append("leerer Text")
    length = x_length(text)
    if length > MAX_LEN:
        errors.append(f"zu lang: {length} Zeichen (max. {MAX_LEN})")
    low = text.lower()
    for p in PROMISE_PATTERNS:
        if re.search(p, low):
            errors.append(f"Kursversprechen/Kaufaufforderung ({p})")
    for p in CA_PATTERNS:
        if re.search(p, text):
            errors.append("Contract-Adresse im Text (kein Shilling einzelner Tokens)")
            break
    tags = re.findall(CASHTAG, text)
    if tags:
        notes.append(f"erwähnt konkrete Coins: {', '.join(sorted(set(tags)))}")
    return errors, notes
