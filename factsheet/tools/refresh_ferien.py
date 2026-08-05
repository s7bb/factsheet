#!/usr/bin/env python3
"""Aktualisiert FERIEN_STAND und den FERIEN-Block in schulweg.py aus der
OpenHolidays-API.

Aufruf:
    python tools/refresh_ferien.py --write          # schulweg.py direkt patchen
    python tools/refresh_ferien.py                  # nur auf stdout ausgeben
    python tools/refresh_ferien.py --write --bis 2029-12-31

Ohne --von wird der Beginn der bisherigen Abdeckung uebernommen, ohne --bis
der 31.12. des uebernaechsten Jahres. Die Abdeckung wird dadurch nur nach
vorne verlaengert, nie verkuerzt - sonst verloeren Backfills alter Monate
ihren Fallback.

Die Tabelle wird nie von Hand getippt: genau das hat beim Entwurf ein
falsches Startdatum der Weihnachtsferien 2026/27 erzeugt (23.12. statt
24.12.).

Die API begrenzt ein Abfragefenster auf drei Jahre; laengere Zeitraeume
werden hier automatisch in Teilfenster zerlegt und wieder zusammengefuehrt.

Exit-Codes:
    0  Erfolg (mit --write zusaetzlich: "geaendert" bzw. "unveraendert" auf stdout)
    1  Abfrage oder Pruefung fehlgeschlagen - schulweg.py bleibt unangetastet
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

API = "https://openholidaysapi.org/SchoolHolidays"
SCHULWEG = pathlib.Path(__file__).resolve().parents[1] / "schulweg.py"

# Bayern hat sieben Ferienzeitraeume pro Jahr (inkl. Buss- und Bettag). Wie
# zur Laufzeit in schulweg.py gilt eine Antwort mit weniger als fuenf pro Jahr
# als unplausibel - ein HTTP 200 mit halber Liste wuerde sonst stillschweigend
# Ferientage zu Schultagen machen.
MIN_PRO_JAHR = 5
MAX_FENSTER_JAHRE = 3     # Limit der API


def _name(eintrag):
    for n in eintrag.get("name", []):
        if n.get("language") == "DE":
            return n["text"]
    return "?"


def _fenster(von, bis):
    """Zerlegt [von, bis] in Teilfenster von hoechstens MAX_FENSTER_JAHRE."""
    start = von
    while start <= bis:
        ende = min(bis, start.replace(year=start.year + MAX_FENSTER_JAHRE) - dt.timedelta(days=1))
        yield start, ende
        start = ende + dt.timedelta(days=1)


def hole(von, bis, timeout=30):
    """Alle Schulferien-Zeitraeume fuer DE-BY, ueber Teilfenster zusammengefuehrt."""
    roh = {}
    for a, b in _fenster(von, bis):
        query = urllib.parse.urlencode({
            "countryIsoCode": "DE",
            "subdivisionCode": "DE-BY",
            "languageIsoCode": "DE",
            "validFrom": a.isoformat(),
            "validTo": b.isoformat(),
        })
        with urllib.request.urlopen(f"{API}?{query}", timeout=timeout) as r:
            for e in json.load(r):
                if e.get("type") == "School":
                    roh[(e["startDate"], e["endDate"])] = _name(e)
    return sorted((s, e, roh[(s, e)]) for s, e in roh)


def pruefe(eintraege, von, bis):
    """Gibt eine Liste von Beanstandungen zurueck; leer heisst plausibel."""
    fehler = []
    if not eintraege:
        return ["keine Ferienzeitraeume geliefert"]

    paare = []
    for start, ende, name in eintraege:
        try:
            a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(ende)
        except ValueError:
            fehler.append(f"unlesbares Datum: {start!r}..{ende!r} ({name})")
            continue
        if a > b:
            fehler.append(f"Ende vor Beginn: {start}..{ende} ({name})")
        paare.append((a, b, name))

    for (a1, b1, n1), (a2, b2, n2) in zip(paare, paare[1:]):
        if a2 <= b1:
            fehler.append(f"ueberlappende Zeitraeume: {n1} {a1}..{b1} und {n2} {a2}..{b2}")

    jahre = bis.year - von.year + 1
    erwartet = MIN_PRO_JAHR * jahre
    if len(eintraege) < erwartet:
        fehler.append(f"nur {len(eintraege)} Zeitraeume fuer {jahre} Jahr(e), "
                      f"mindestens {erwartet} erwartet")

    for jahr in range(von.year, bis.year + 1):
        if not any(a.year == jahr or b.year == jahr for a, b, _ in paare):
            fehler.append(f"kein Zeitraum im Jahr {jahr}")
    return fehler


def block(eintraege, von, bis, stand):
    zeilen = [f'FERIEN_STAND = "{stand.isoformat()}"',
              "# Erzeugt mit tools/refresh_ferien.py aus der OpenHolidays-API.",
              "# Nicht von Hand bearbeiten - Skript erneut laufen lassen.",
              "FERIEN = ["]
    zeilen += [f'    ("{s}", "{e}"),   # {n}' for s, e, n in eintraege]
    zeilen.append("]")
    zeilen.append(f'FERIEN_ABGEDECKT = ("{von.isoformat()}", "{bis.isoformat()}")')
    return "\n".join(zeilen)


def bisherige_abdeckung(text):
    m = re.search(r'^FERIEN_ABGEDECKT = \("(\d{4}-\d{2}-\d{2})", "(\d{4}-\d{2}-\d{2})"\)',
                  text, re.M)
    if not m:
        sys.exit("FEHLER: FERIEN_ABGEDECKT in schulweg.py nicht gefunden.")
    return dt.date.fromisoformat(m.group(1)), dt.date.fromisoformat(m.group(2))


def schreibe(text, eintraege, von, bis, stand):
    """Ersetzt FERIEN_STAND und den erzeugten Block; laesst alles andere stehen."""
    neu, n1 = re.subn(r'^FERIEN_STAND = "\d{4}-\d{2}-\d{2}"$',
                      f'FERIEN_STAND = "{stand.isoformat()}"', text, count=1, flags=re.M)
    rumpf = "\n".join(block(eintraege, von, bis, stand).split("\n")[1:])
    neu, n2 = re.subn(r'^# Erzeugt mit tools/refresh_ferien\.py.*?^FERIEN_ABGEDECKT = \([^)]*\)',
                      lambda _: rumpf, neu, count=1, flags=re.M | re.S)
    if n1 != 1 or n2 != 1:
        sys.exit("FEHLER: FERIEN-Block in schulweg.py nicht eindeutig gefunden - "
                 "Datei von Hand veraendert?")
    return neu


def main():
    ap = argparse.ArgumentParser(description="FERIEN-Tabelle in schulweg.py aktualisieren.")
    ap.add_argument("--von", help="YYYY-MM-DD (Standard: bisheriger Abdeckungsbeginn)")
    ap.add_argument("--bis", help="YYYY-MM-DD (Standard: 31.12. des uebernaechsten Jahres)")
    ap.add_argument("--write", action="store_true", help="schulweg.py direkt patchen")
    ap.add_argument("--allow-shrink", action="store_true",
                    help="Verkuerzung der Abdeckung ausnahmsweise zulassen")
    args = ap.parse_args()

    text = SCHULWEG.read_text(encoding="utf-8")
    alt_von, alt_bis = bisherige_abdeckung(text)
    heute = dt.date.today()

    von = dt.date.fromisoformat(args.von) if args.von else alt_von
    bis = dt.date.fromisoformat(args.bis) if args.bis else dt.date(heute.year + 2, 12, 31)

    if not args.allow_shrink and (von > alt_von or bis < alt_bis):
        sys.exit(f"FEHLER: {von}..{bis} wuerde die Abdeckung {alt_von}..{alt_bis} "
                 f"verkuerzen. Backfills aelterer Monate verloeren ihren Fallback. "
                 f"Mit --allow-shrink erzwingen.")
    if von > bis:
        sys.exit(f"FEHLER: --von {von} liegt nach --bis {bis}.")

    try:
        eintraege = hole(von, bis)
    except Exception as e:
        sys.exit(f"FEHLER: OpenHolidays nicht erreichbar oder Antwort unlesbar: {e}")

    fehler = pruefe(eintraege, von, bis)
    if fehler:
        for f in fehler:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(f"FEHLER: Antwort unplausibel ({len(fehler)} Beanstandung(en)) - "
                 f"schulweg.py bleibt unveraendert.")

    if not args.write:
        print(block(eintraege, von, bis, heute))
        return

    neu = schreibe(text, eintraege, von, bis, heute)
    # FERIEN_STAND aendert sich taeglich; ohne Sachaenderung nicht committen.
    ohne_stand = lambda s: re.sub(r'^FERIEN_STAND = "\d{4}-\d{2}-\d{2}"$', "", s, flags=re.M)
    if ohne_stand(neu) == ohne_stand(text):
        print("unveraendert")
        return
    SCHULWEG.write_text(neu, encoding="utf-8")
    print("geaendert")


if __name__ == "__main__":
    main()
