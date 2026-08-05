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
import json
import sys
import urllib.parse
import urllib.request
from collections import Counter

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


API_SCHULFERIEN = "https://openholidaysapi.org/SchoolHolidays"

# Bayern hat sieben Ferienzeitraeume pro Jahr (inkl. Buss- und Bettag). Eine
# Antwort mit weniger als fuenf gilt als unplausibel: ein HTTP 200 mit leerer
# Liste wuerde sonst jeden Werktag zum Schultag machen, und das PDF saehe dabei
# voellig normal aus.
MIN_FERIEN_PRO_JAHR = 5

QUELLE_API = "OpenHolidays API"
FERIEN_STAND = "2026-08-05"
QUELLE_TABELLE = f"hinterlegte Tabelle (Stand {FERIEN_STAND})"

# Erzeugt mit tools/refresh_ferien.py aus der OpenHolidays-API.
# Nicht von Hand bearbeiten - Skript erneut laufen lassen.
FERIEN = [
    ("2025-08-01", "2025-09-15"),   # Sommerferien
    ("2025-11-03", "2025-11-07"),   # Herbstferien
    ("2025-11-19", "2025-11-19"),   # Buß- und Bettag
    ("2025-12-22", "2026-01-05"),   # Weihnachtsferien
    ("2026-02-16", "2026-02-20"),   # Frühjahrsferien
    ("2026-03-30", "2026-04-10"),   # Osterferien
    ("2026-05-26", "2026-06-05"),   # Pfingstferien
    ("2026-08-03", "2026-09-14"),   # Sommerferien
    ("2026-11-02", "2026-11-06"),   # Herbstferien
    ("2026-11-18", "2026-11-18"),   # Buß- und Bettag
    ("2026-12-24", "2027-01-08"),   # Weihnachtsferien
    ("2027-02-08", "2027-02-12"),   # Frühjahrsferien
    ("2027-03-22", "2027-04-02"),   # Osterferien
    ("2027-05-18", "2027-05-28"),   # Pfingstferien
    ("2027-08-02", "2027-09-13"),   # Sommerferien
    ("2027-11-02", "2027-11-05"),   # Herbstferien
    ("2027-11-17", "2027-11-17"),   # Buß- und Bettag
    ("2027-12-24", "2028-01-07"),   # Weihnachtsferien
]
FERIEN_ABGEDECKT = ("2025-08-01", "2028-01-31")


def ferien_api(von, bis, timeout=15):
    """Bayerische Schulferien von OpenHolidays.

    Gibt None zurueck, wenn die Abfrage fehlschlaegt ODER die Antwort
    unplausibel ist. Beides fuehrt zum Tabellen-Fallback."""
    query = urllib.parse.urlencode({
        "countryIsoCode": "DE",
        "subdivisionCode": "DE-BY",
        "languageIsoCode": "DE",
        "validFrom": von,
        "validTo": bis,
    })
    try:
        with urllib.request.urlopen(f"{API_SCHULFERIEN}?{query}", timeout=timeout) as r:
            data = json.load(r)
    except Exception as e:
        print(f"WARNUNG: OpenHolidays nicht erreichbar ({e}) - "
              f"{QUELLE_TABELLE} wird verwendet.", file=sys.stderr)
        return None

    try:
        ranges = sorted((e["startDate"], e["endDate"]) for e in data
                        if e.get("type") == "School")
    except (AttributeError, KeyError, TypeError) as e:
        print(f"WARNUNG: Unerwartete Antwort von OpenHolidays ({e}) - "
              f"{QUELLE_TABELLE} wird verwendet.", file=sys.stderr)
        return None

    if len(ranges) < MIN_FERIEN_PRO_JAHR:
        print(f"WARNUNG: OpenHolidays liefert nur {len(ranges)} Ferienzeitraeume "
              f"fuer {von}..{bis} (mindestens {MIN_FERIEN_PRO_JAHR} erwartet) - "
              f"{QUELLE_TABELLE} wird verwendet.", file=sys.stderr)
        return None
    return ranges


def ferien_ranges(year):
    """(Zeitraeume, Quellenbezeichnung) fuer ein Kalenderjahr.

    Eine Jahresabfrage liefert auch die Weihnachtsferien, die im Dezember
    beginnen und ins Folgejahr laufen - die API gibt jeden Zeitraum zurueck,
    der das Fenster ueberschneidet."""
    aus_api = ferien_api(f"{year}-01-01", f"{year}-12-31")
    if aus_api is not None:
        return aus_api, QUELLE_API
    return [tuple(r) for r in FERIEN], QUELLE_TABELLE


def ist_ferientag(day, ranges):
    """True, wenn der Tag in einem der Ferienzeitraeume liegt."""
    return any(dt.date.fromisoformat(a) <= day <= dt.date.fromisoformat(b)
               for a, b in ranges)


def _monatsgrenzen(month):
    year, mo = (int(x) for x in month.split("-"))
    first = dt.date(year, mo, 1)
    last = dt.date(year + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(days=1)
    return first, last


def pruefe_abdeckung(month):
    """Bricht ab, wenn der Monat nicht vollstaendig von FERIEN abgedeckt ist.
    Gilt nur fuer den Tabellen-Fallback; antwortet die API, ist die Tabelle
    nicht im Spiel."""
    first, last = _monatsgrenzen(month)
    lo, hi = (dt.date.fromisoformat(x) for x in FERIEN_ABGEDECKT)
    if first < lo or last > hi:
        raise SystemExit(
            f"FEHLER: OpenHolidays nicht verfuegbar und {month} liegt "
            f"ausserhalb der hinterlegten Ferientabelle "
            f"({FERIEN_ABGEDECKT[0]}..{FERIEN_ABGEDECKT[1]}). "
            f"Tabelle mit tools/refresh_ferien.py erneuern."
        )


def tage_im_monat(month):
    """Schultage des Monats plus Quellenangabe.

    Gibt es keine Schultage (reiner Ferienmonat), werden alle Werktage
    zurueckgegeben; das zweite Element zeigt diesen Fallback an. Ein
    Kalendermonat liegt immer in genau einem Jahr, daher genuegt ein
    Jahresaufruf."""
    first, last = _monatsgrenzen(month)
    ranges, quelle = ferien_ranges(first.year)
    if quelle != QUELLE_API:
        pruefe_abdeckung(month)

    werktage = []
    day = first
    while day <= last:
        if day.weekday() < 5:
            werktage.append(day)
        day += dt.timedelta(days=1)

    frei = feiertage(first.year)
    schultage = [d for d in werktage
                 if d not in frei and not ist_ferientag(d, ranges)]
    if schultage:
        return schultage, False, quelle
    return werktage, True, quelle


# Zeitfenster Morgenverkehr als Minute des Tages, Ortszeit, beide Grenzen
# eingeschlossen: 06:30 bis 08:30.
WINDOW_VON, WINDOW_BIS = 390, 510

SLOTS = 6          # feste Zeilenzahl im Raster
SLOT_ABSTAND = 10  # Mindestabstand zweier Slot-Mitten in Minuten


def hhmm(minute):
    """Minute des Tages -> 'HH:MM'."""
    return f"{minute // 60:02d}:{minute % 60:02d}"


def slot_centres(minutes):
    """Slot-Mitten aus den Daten ableiten statt sie fest zu verdrahten.

    Haeufigste Ankunftsminuten zuerst, jede neue Mitte muss mindestens
    SLOT_ABSTAND Minuten von allen bisherigen entfernt sein. Damit werden
    Fahrplan-Abweichungen von +/-1 Minute eingesammelt, unabhaengig davon, wo
    in der Stunde die Zuege liegen."""
    counts = Counter(minutes)
    centres = []
    for minute, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if all(abs(minute - c) >= SLOT_ABSTAND for c in centres):
            centres.append(minute)
        if len(centres) == SLOTS:
            break
    return sorted(centres)


def assign_slot(minute, centres):
    """Index der naechstgelegenen Slot-Mitte; bei Gleichstand die fruehere."""
    if not centres:
        return None
    return min(range(len(centres)),
               key=lambda i: (abs(minute - centres[i]), centres[i]))


RICHTUNGEN = ("wolfratshausen", "muenchen")


def kennzahlen(rows):
    """Kennzahlen einer Teilmenge. Leere Stichproben liefern None statt NaN -
    dth()/dn() wuerden sonst 'nan' ins PDF schreiben bzw. abbrechen."""
    n = len(rows)
    canc = int(rows["cancelled"].sum()) if n else 0
    dl = rows.loc[~rows["cancelled"], "delay_minutes"].dropna() if n else []
    if len(dl) == 0:
        return {"n": n, "canc": canc,
                "avail": 100 * (n - canc) / n if n else None,
                "ontime": None, "avg": None, "gt5": None, "p90": None}
    return {
        "n": n, "canc": canc,
        "avail": 100 * (n - canc) / n,
        "ontime": 100 * float((dl <= 0).mean()),
        "avg": float(dl.mean()),
        "gt5": 100 * float((dl > 5).mean()),
        "p90": float(dl.quantile(.9)),
    }


def compute_schulweg(df, month):
    """Alle Kennzahlen des Schulweg-Datenblatts."""
    tage, fallback, quelle = tage_im_monat(month)
    tage_set = set(tage)

    d = df[df["direction_bucket"].isin(RICHTUNGEN)].copy()
    d["minute"] = d["local"].dt.hour * 60 + d["local"].dt.minute

    fenster = d[d["date"].isin(tage_set)
                & d["minute"].between(WINDOW_VON, WINDOW_BIS)].copy()

    centres = slot_centres(fenster["minute"].tolist())
    fenster["slot"] = fenster["minute"].map(lambda m: assign_slot(m, centres))

    warnungen = []
    if not fenster.empty:
        doppelt = fenster.groupby(["date", "direction_bucket", "slot"]).size()
        for (day, richtung, idx), anzahl in doppelt[doppelt > 1].items():
            warnungen.append(
                f"WARNUNG: {day} {richtung} Slot {hhmm(centres[int(idx)])}: "
                f"mehr als eine Fahrt ({anzahl}) - Werte werden gemittelt.")

    slots = []
    for i in range(SLOTS):
        label = hhmm(centres[i]) if i < len(centres) else "–"
        dirs = {}
        for richtung in RICHTUNGEN:
            teil = fenster[(fenster["slot"] == i)
                           & (fenster["direction_bucket"] == richtung)]
            dirs[richtung] = kennzahlen(teil)
        slots.append({"label": label, "dirs": dirs})

    nc = fenster[~fenster["cancelled"]]
    daily = {}
    if not nc.empty:
        means = nc.groupby("date")["delay_minutes"].mean()
        daily = {day: float(v) for day, v in means.sort_index().items()}

    return {
        "days": len(tage), "fallback": fallback, "quelle": quelle,
        "centres": centres,
        "win": {r: kennzahlen(fenster[fenster["direction_bucket"] == r])
                for r in RICHTUNGEN},
        "mon": {r: kennzahlen(d[d["direction_bucket"] == r])
                for r in RICHTUNGEN},
        "slots": slots, "daily": daily, "warnungen": warnungen,
    }
