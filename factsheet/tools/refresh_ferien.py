#!/usr/bin/env python3
"""Erzeugt den FERIEN-Block fuer schulweg.py aus der OpenHolidays-API.

Aufruf:  python tools/refresh_ferien.py --von 2025-08-01 --bis 2028-01-31

Gibt den Block auf stdout aus. Inhalt in schulweg.py ersetzen und committen.
Die Tabelle wird nie von Hand getippt: genau das hat beim Entwurf ein falsches
Startdatum der Weihnachtsferien 2026/27 erzeugt (23.12. statt 24.12.).

Das Abfragefenster der API ist auf drei Jahre begrenzt.
"""
import argparse
import json
import urllib.parse
import urllib.request

API = "https://openholidaysapi.org/SchoolHolidays"


def _name(eintrag):
    for n in eintrag.get("name", []):
        if n.get("language") == "DE":
            return n["text"]
    return "?"


def hole(von, bis):
    query = urllib.parse.urlencode({
        "countryIsoCode": "DE",
        "subdivisionCode": "DE-BY",
        "languageIsoCode": "DE",
        "validFrom": von,
        "validTo": bis,
    })
    with urllib.request.urlopen(f"{API}?{query}", timeout=30) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser(
        description="FERIEN-Block fuer schulweg.py erzeugen.")
    ap.add_argument("--von", required=True, help="YYYY-MM-DD")
    ap.add_argument("--bis", required=True, help="YYYY-MM-DD (max. 3 Jahre)")
    args = ap.parse_args()

    eintraege = sorted(
        (e["startDate"], e["endDate"], _name(e))
        for e in hole(args.von, args.bis) if e.get("type") == "School")

    print("# Erzeugt mit tools/refresh_ferien.py aus der OpenHolidays-API.")
    print("# Nicht von Hand bearbeiten - Skript erneut laufen lassen.")
    print("FERIEN = [")
    for start, ende, name in eintraege:
        print(f'    ("{start}", "{ende}"),   # {name}')
    print("]")
    print(f'FERIEN_ABGEDECKT = ("{args.von}", "{args.bis}")')


if __name__ == "__main__":
    main()
