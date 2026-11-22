#!/usr/bin/env python3
"""Richtet Discords eingebautes AutoMod für den Community-Server ein.

Regeln mit gleichem Namen werden aktualisiert statt doppelt angelegt.
Owner und Moderatoren sind von den Wort- und Link-Filtern ausgenommen.

Aufruf:
    DISCORD_BOT_TOKEN=... python3 automod.py <SERVER_ID>
"""
import os
import sys

from setup_discord import MOD, OWNER, DiscordAPI, DiscordFehler

MELDUNG_KANAL = "mod-log"

# Trigger-Typen laut Discord-API
KEYWORD, SPAM, PRESET, MENTION_SPAM = 1, 3, 4, 5
# Aktionen
BLOCKIEREN, MELDEN, TIMEOUT = 1, 2, 3


def regeln(log_id, ausnahmen):
    def blockieren(text):
        return {"type": BLOCKIEREN, "metadata": {"custom_message": text}}

    melden = {"type": MELDEN, "metadata": {"channel_id": log_id}}

    return [
        {
            "name": "Fremde Einladungslinks",
            "trigger_type": KEYWORD,
            "trigger_metadata": {"regex_patterns": [
                r"(discord\.gg|discord(app)?\.com/invite|dsc\.gg|discord\.me)/\S+",
            ]},
            "actions": [blockieren("Einladungslinks zu anderen Servern sind hier nicht erlaubt."), melden],
            "exempt_roles": ausnahmen,
        },
        {
            "name": "Casinos ohne deutsche Lizenz & Referral-Spam",
            "trigger_type": KEYWORD,
            "trigger_metadata": {
                "keyword_filter": [
                    "*stake.com*", "*stake.us*", "*stake.bet*", "*roobet*", "*rollbit*", "*bc.game*",
                    "*duelbits*", "*gamdom*", "*shuffle.com*", "*rainbet*", "*500casino*", "*csgoempire*",
                    "*crypto casino*", "*kryptocasino*", "*krypto casino*",
                    "*ref code*", "*referral code*", "*referralcode*", "*promocode*", "*promo code*",
                    "*bonuscode*", "*bonus code*", "*code: *",
                ],
                "allow_list": [],
            },
            "actions": [blockieren("Wir erlauben nur Anbieter mit deutscher Lizenz (GGL) – keine Codes oder Fremdwerbung."), melden],
            "exempt_roles": ausnahmen,
        },
        {
            "name": "Betrug, Geldgeschäfte & Phishing",
            "trigger_type": KEYWORD,
            "trigger_metadata": {
                "keyword_filter": [
                    "*sichere strategie*", "*100% gewinn*", "*garantierter gewinn*", "*garantiert gewinn*",
                    "*signal gruppe*", "*signalgruppe*", "*vip signals*", "*slot signals*",
                    "*geld leihen*", "*leih mir*", "*geld verleihen*", "*paypal mir*",
                    "*account verkauf*", "*verkaufe account*",
                    "*free nitro*", "*gratis nitro*", "*dlscord*", "*discorcl*", "*steamcommunlty*",
                ],
            },
            "actions": [blockieren("Diese Nachricht wurde blockiert (Verdacht auf Betrug oder Geldgeschäfte)."), melden],
            "exempt_roles": ausnahmen,
        },
        {
            "name": "Beleidigungen & anstößige Inhalte",
            "trigger_type": PRESET,
            "trigger_metadata": {"presets": [1, 2, 3], "allow_list": []},  # Schimpfwörter, sexuell, Beleidigungen
            "actions": [blockieren("Bitte bleib respektvoll – siehe #regeln."), melden],
            "exempt_roles": [],
        },
        {
            "name": "Spam",
            "trigger_type": SPAM,
            "trigger_metadata": {},
            "actions": [blockieren("Deine Nachricht wurde als Spam erkannt."), melden],
            "exempt_roles": ausnahmen,
        },
        {
            "name": "Massen-Erwähnungen",
            "trigger_type": MENTION_SPAM,
            "trigger_metadata": {"mention_total_limit": 5, "mention_raid_protection_enabled": True},
            "actions": [
                blockieren("Bitte nicht so viele Leute auf einmal erwähnen."),
                melden,
                {"type": TIMEOUT, "metadata": {"duration_seconds": 600}},
            ],
            "exempt_roles": ausnahmen,
        },
    ]


def main():
    if len(sys.argv) != 2:
        sys.exit("Aufruf: DISCORD_BOT_TOKEN=... python3 automod.py <SERVER_ID>")
    sid = sys.argv[1]
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        sys.exit("DISCORD_BOT_TOKEN ist nicht gesetzt.")
    api = DiscordAPI(token)

    kanaele = {k["name"]: k["id"] for k in api.request("GET", f"/guilds/{sid}/channels")}
    rollen = {r["name"]: r["id"] for r in api.request("GET", f"/guilds/{sid}/roles")}
    ausnahmen = [rollen[n] for n in (OWNER, MOD) if n in rollen]
    vorhanden = {r["name"]: r for r in api.request("GET", f"/guilds/{sid}/auto-moderation/rules")}
    bot_id = api.request("GET", "/users/@me")["id"]

    fehler = 0
    for regel in regeln(kanaele[MELDUNG_KANAL], ausnahmen):
        daten = {**regel, "event_type": 1, "enabled": True}
        try:
            # Discords eigene Standardregeln lassen sich nicht bearbeiten – nur eigene Regeln anfassen
            alt = vorhanden.get(regel["name"])
            if alt and alt["creator_id"] == bot_id:
                daten.pop("trigger_type")
                daten.pop("event_type")
                api.request("PATCH", f"/guilds/{sid}/auto-moderation/rules/{alt['id']}", daten)
                print(f"  = {regel['name']}")
            else:
                api.request("POST", f"/guilds/{sid}/auto-moderation/rules", daten)
                print(f"  + {regel['name']}")
        except DiscordFehler as e:
            fehler += 1
            print(f"  ! {regel['name']}: {e}")
    print("\nAutoMod fertig." if not fehler else f"\n{fehler} Regel(n) fehlgeschlagen.")


if __name__ == "__main__":
    main()
