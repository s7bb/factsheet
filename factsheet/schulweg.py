#!/usr/bin/env python3
"""
Erzeugt das monatliche S7-Baierbrunn-Schulweg-Datenblatt (DIN A4, eine Seite,
deutsch) als PDF: Morgenverkehr Mo-Fr 06:30-08:30, beide Richtungen, je Fahrt.

Datenquelle:  https://github.com/s7bb/s7bb-data  ->  archive/<YYYY-MM>.json
Aufruf:       python schulweg.py [--month YYYY-MM] [--outdir output]

Ohne --month wird der zuletzt abgeschlossene Kalendermonat verwendet.
Das Skript ist deterministisch und benoetigt kein LLM. Die Praesentation von
generate.py wird nicht veraendert, nur wiederverwendet.
"""
import datetime as dt

# Feste gesetzliche Feiertage in Bayern (Monat, Tag).
# Mariae Himmelfahrt gilt in ueberwiegend katholischen Gemeinden; Baierbrunn
# (Landkreis Muenchen) gehoert dazu.
FEIERTAGE_FEST = [(1, 1), (1, 6), (5, 1), (8, 15), (10, 3), (11, 1), (12, 25), (12, 26)]

# Bewegliche Feiertage als Abstand in Tagen zum Ostersonntag.
FEIERTAGE_OSTERN = [-2, 1, 39, 50, 60]  # Karfreitag, Ostermontag, Himmelfahrt,
                                        # Pfingstmontag, Fronleichnam


def easter(year):
    """Ostersonntag nach dem anonymen gregorianischen Algorithmus."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def feiertage(year):
    """Gesetzliche Feiertage in Bayern fuer ein Kalenderjahr."""
    days = {dt.date(year, mo, da) for mo, da in FEIERTAGE_FEST}
    ostern = easter(year)
    days |= {ostern + dt.timedelta(days=off) for off in FEIERTAGE_OSTERN}
    return days
