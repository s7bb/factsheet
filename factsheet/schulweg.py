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

from generate import (MONATE, MONATE_DATEI, TZ, dn, load_month, prev_month,
                      render_pdf)

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
    ("2028-02-28", "2028-03-03"),   # Frühjahrsferien
    ("2028-04-10", "2028-04-21"),   # Osterferien
    ("2028-06-06", "2028-06-16"),   # Pfingstferien
    ("2028-07-31", "2028-09-11"),   # Sommerferien
    ("2028-10-30", "2028-11-03"),   # Herbstferien
    ("2028-11-22", "2028-11-22"),   # Buß- und Bettag
    ("2028-12-23", "2029-01-05"),   # Weihnachtsferien
]
FERIEN_ABGEDECKT = ("2025-08-01", "2028-12-31")


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
SPARK_LABELS = 6   # Zielzahl der Beschriftungen der Sparkline


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
        "win": {r: kennzahlen(fenster[fenster["direction_bucket"] == r])
                for r in RICHTUNGEN},
        "mon": {r: kennzahlen(d[d["direction_bucket"] == r])
                for r in RICHTUNGEN},
        "slots": slots, "daily": daily, "warnungen": warnungen,
    }


def school_spark(daily):
    """Sparkline der taeglichen Durchschnittsverspaetung.

    Eigene Kopie statt Import aus generate.py: die dortige Fassung beschriftet
    nur Tage mit 'd % 5 == 0 or d == 1', was bei einer Reihe aus reinen
    Schultagen (Luecken an Wochenenden und in Ferien) je nach Monat 3 bis 6
    Beschriftungen ergibt. Hier wird stattdessen jeder n-te Punkt beschriftet,
    plus erster und letzter.

    Die Punkte sind gleichmaessig ueber den Index verteilt, nicht ueber das
    Datum: eine Luecke Fr->Mo sieht aus wie Mo->Di. Fuer eine Reihe 'je
    Schultag' ist das beabsichtigt."""
    days = sorted(daily)
    W, H = 700, 80
    if not days:
        return f'<svg viewBox="0 0 {W} {H}" class="spark"></svg>'

    vmax = max(daily.values()) or 1
    pts = []
    for i, day in enumerate(days):
        px = 10 + (W - 20) * i / (len(days) - 1 or 1)
        py = H - 18 - (H - 30) * daily[day] / vmax
        pts.append((px, py))

    poly = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = f"10,{H-18} " + poly + f" {pts[-1][0]:.1f},{H-18}"
    dots = "".join(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.3" fill="#1b4f8a"/>'
                   for px, py in pts)

    # Gleichmaessig verteilte Beschriftungen: immer hoechstens SPARK_LABELS,
    # erster und letzter Punkt immer dabei. Eine feste Zielzahl statt einer
    # Schrittweite, damit die Anzahl nicht je nach Monatslaenge ueberlaeuft.
    letzter = len(days) - 1
    marked = {round(i * letzter / (SPARK_LABELS - 1)) for i in range(SPARK_LABELS)}
    xlab = "".join(f'<text x="{pts[i][0]:.1f}" y="{H-4}" class="spark-lab">'
                   f'{days[i].day}</text>'
                   for i in sorted(marked))

    return (f'<svg viewBox="0 0 {W} {H}" class="spark">'
            f'<polygon points="{area}" fill="#dbe7f5"/>'
            f'<polyline points="{poly}" fill="none" stroke="#1b4f8a" stroke-width="2"/>'
            f'{dots}{xlab}</svg>')


def fmt(value, dec=1, suffix=""):
    """Zahl deutsch formatieren; leere Stichproben werden zum Gedankenstrich."""
    if value is None:
        return "–"
    return dn(value, dec) + suffix


KPI_ZEILEN = [
    ("Verfügbarkeit", "avail", 1, "%"),
    ("pünktlich", "ontime", 1, "%"),
    ("Ø Verspätung", "avg", 2, ""),
    ("über 5 Min.", "gt5", 1, "%"),
    ("p90 (Min.)", "p90", 0, ""),
]

DIR_LABEL = {"wolfratshausen": "&rarr; Wolfratshausen", "muenchen": "&rarr; M&uuml;nchen"}


def kpi_strip(s):
    rows = ""
    for label, key, dec, suffix in KPI_ZEILEN:
        cells = ""
        for richtung in RICHTUNGEN:
            win = fmt(s["win"][richtung][key], dec, suffix)
            mon = fmt(s["mon"][richtung][key], dec, suffix)
            cells += (f'<div class="kpi-cell"><span class="kv">{win}</span>'
                      f'<span class="kr">Monat {mon}</span></div>')
        rows += f'<div class="kpi-row"><div class="kpi-lab">{label}</div>{cells}</div>'
    return rows


def slot_grid(s):
    werte = [d[r]["avg"] for d in (x["dirs"] for x in s["slots"])
             for r in RICHTUNGEN if d[r]["avg"] is not None]
    vmax = (max(werte) if werte else 0) or 1
    rows = ""
    for slot in s["slots"]:
        cells = ""
        for richtung in RICHTUNGEN:
            k = slot["dirs"][richtung]
            breite = 100 * k["avg"] / vmax if k["avg"] is not None else 0
            farbe = "#2e9e5b"
            if k["avg"] is not None and k["avg"] > 5:
                farbe = "#c8371f"
            elif k["avg"] is not None and k["avg"] > 3:
                farbe = "#f0902f"
            ausf = (f'<span class="slot-canc">{k["canc"]} Ausf.</span>'
                    if k["canc"] else '<span class="slot-canc"></span>')
            cells += (f'<div class="slot-cell"><div class="slot-track">'
                      f'<div class="slot-fill" style="width:{breite:.1f}%;'
                      f'background:{farbe}"></div></div>'
                      f'<span class="slot-val">{fmt(k["avg"], 2)}</span>{ausf}</div>')
        rows += (f'<div class="slot-row"><div class="slot-lab">{slot["label"]}</div>'
                 f'{cells}</div>')
    return rows


CSS = """
@page { size: A4; margin: 0; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Helvetica Neue',Arial,sans-serif; color:#1c2733; width:210mm; }
.page { padding:6mm 13mm 2mm; }
.head { display:flex; align-items:center; justify-content:space-between;
  border-bottom:3px solid #1b4f8a; padding-bottom:7px; margin-bottom:12px; }
.brand { display:flex; align-items:center; gap:12px; }
.logo { width:44px;height:44px;border-radius:9px;background:#1b4f8a;color:#fff;
  font-weight:800;font-size:19px;display:flex;align-items:center;justify-content:center;letter-spacing:-1px; }
h1 { font-size:21px; font-weight:800; letter-spacing:-.3px; }
.sub { font-size:12px; color:#6a7684; margin-top:1px; }
.period { text-align:right;font-size:12px;color:#6a7684; }
.period b { display:block;font-size:17px;color:#1b4f8a;font-weight:800; }
.section-t { font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:1.1px;
  color:#1b4f8a;margin:0 0 8px; display:flex;align-items:center;gap:7px; }
.section-t::before { content:"";width:5px;height:14px;background:#1b4f8a;border-radius:2px; }
.card { border:1px solid #e2e8ef;border-radius:11px;padding:12px 14px;background:#fbfcfd;margin-bottom:12px; }
.colhead { display:flex;font-size:11px;font-weight:800;color:#1b4f8a;margin-bottom:6px; }
.colhead .kpi-lab, .colhead .slot-lab { flex:none; }
.colhead span { flex:1;text-align:center; }
.kpi-row { display:flex;align-items:center;border-top:1px solid #eef2f6;padding:5px 0; }
.kpi-lab { width:150px;flex:none;font-size:12px;font-weight:700; }
.kpi-cell { flex:1;text-align:center; }
.kpi-cell .kv { display:block;font-size:17px;font-weight:800;color:#1c2733; }
.kpi-cell .kr { display:block;font-size:10px;color:#6a7684;margin-top:1px; }
.slot-row { display:flex;align-items:center;border-top:1px solid #eef2f6;padding:6px 0; }
.slot-lab { width:66px;flex:none;font-size:13px;font-weight:800;color:#1b4f8a; }
.slot-cell { flex:1;display:flex;align-items:center;gap:8px;padding-right:14px; }
.slot-track { flex:1;background:#eef2f6;border-radius:5px;height:16px; }
.slot-fill { height:100%;border-radius:5px; }
.slot-val { width:38px;flex:none;text-align:right;font-size:12px;font-weight:800; }
.slot-canc { width:58px;flex:none;font-size:10px;color:#c8371f;font-weight:700; }
.spark { width:100%;height:auto; }
.spark-lab { font-size:9px;fill:#8592a1;text-anchor:middle; }
.notemark { font-size:10px;color:#6a7684;margin-top:6px;line-height:1.45; }
.foot { margin-top:4px;padding-top:5px;border-top:1px solid #e2e8ef;
  font-size:9.5px;color:#8592a1;display:flex;justify-content:space-between; }
"""


def render_html_schulweg(s, month_label, year, archive_month):
    if s["fallback"]:
        tage = (f'{s["days"]} Werktage'
                f'<br><span style="color:#c8371f">keine Schultage im Monat</span>')
        basis = ("Im Berichtsmonat lagen keine Schultage. Ausgewiesen sind "
                 "ersatzweise alle Werktage (Mo–Fr).")
    else:
        tage = f'{s["days"]} Schultage'
        basis = ("Basis: Schultage in Bayern (ohne Wochenenden, gesetzliche "
                 "Feiertage und bayerische Schulferien).")

    proben = [d[r]["n"] for d in (x["dirs"] for x in s["slots"])
              for r in RICHTUNGEN if d[r]["n"]]
    if not proben:
        spanne = "0"
    elif min(proben) == max(proben):
        spanne = str(min(proben))
    else:
        spanne = f"{min(proben)}–{max(proben)}"

    kopf = ('<div class="colhead"><div class="kpi-lab"></div>'
            + "".join(f"<span>{DIR_LABEL[r]}</span>" for r in RICHTUNGEN)
            + "</div>")
    kopf_slots = ('<div class="colhead"><div class="slot-lab"></div>'
                  + "".join(f"<span>{DIR_LABEL[r]}</span>" for r in RICHTUNGEN)
                  + "</div>")

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body><div class="page">

<div class="head">
  <div class="brand">
    <div class="logo">S7</div>
    <div><h1>S-Bahn S7 &middot; Baierbrunn &middot; Schulweg</h1>
      <div class="sub">Morgenverkehr Mo&ndash;Fr 06:30&ndash;08:30 &middot; planm&auml;&szlig;ige Ank&uuml;nfte in Baierbrunn</div></div>
  </div>
  <div class="period">Berichtszeitraum<b>{month_label} {year}</b>{tage}</div>
</div>

<div class="card">
  <div class="section-t">Morgenverkehr im Vergleich zum Gesamtmonat</div>
  {kopf}
  {kpi_strip(s)}
  <div class="notemark">{basis} Die Zeile <b>Monat</b> je Zelle ist der
  Vergleichswert &uuml;ber alle Tage und alle Stunden und entspricht dem Wert
  im Monatsdatenblatt.</div>
</div>

<div class="card">
  <div class="section-t">Je Fahrt &middot; planm&auml;&szlig;ige Ankunft in Baierbrunn</div>
  {kopf_slots}
  {slot_grid(s)}
  <div class="notemark">Balkenl&auml;nge: &Oslash; Versp&auml;tung in Minuten,
  gemeinsame Skala f&uuml;r beide Richtungen. Stichprobe je Fahrt und Richtung:
  {spanne} Ank&uuml;nfte im Monat.</div>
</div>

<div class="card">
  <div class="section-t">&Oslash; Versp&auml;tung je {'Werktag' if s['fallback'] else 'Schultag'} (Min.)</div>
  {school_spark(s['daily'])}
</div>

<div class="foot">
  <span>Quelle: s7bb-data (github.com/s7bb/s7bb-data) &middot; archive/{archive_month}.json
  &middot; Ferien: {s['quelle']}</span>
  <span>Bahnhof Baierbrunn &middot; Versp&auml;tungen &amp; Ausf&auml;lle gg&uuml;. Fahrplan</span>
</div>

</div></body></html>"""


def main():
    import argparse
    import pathlib

    ap = argparse.ArgumentParser(
        description="S7-Baierbrunn-Schulweg-Datenblatt (PDF) erzeugen.")
    ap.add_argument("--month", help="Berichtsmonat YYYY-MM (Standard: Vormonat)")
    ap.add_argument("--outdir", default="output",
                    help="Ausgabeverzeichnis (Standard: output)")
    args = ap.parse_args()

    month = args.month or prev_month(dt.datetime.now(TZ).date())
    year, mo = (int(x) for x in month.split("-"))

    print(f"Berichtsmonat: {month} ({MONATE[mo]} {year})")
    df, _ = load_month(month)
    s = compute_schulweg(df, month)
    for warnung in s["warnungen"]:
        print(warnung, file=sys.stderr)

    html = render_html_schulweg(s, MONATE[mo], year, month)

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    pdf_path = outdir / f"S7_Baierbrunn_{MONATE_DATEI[mo]}{year}_Schulweg.pdf"
    render_pdf(html, pdf_path)

    print(f"Erstellt: {pdf_path}")
    basis = "Werktage" if s["fallback"] else "Schultage"
    for richtung in RICHTUNGEN:
        k = s["win"][richtung]
        print(f"  {richtung}: {k['n']} Fahrten an {s['days']} {basis} | "
              f"Verf. {fmt(k['avail'], 1, '%')} | "
              f"pünktlich {fmt(k['ontime'], 1, '%')} | "
              f"Ø Versp. {fmt(k['avg'], 2)} Min.")


if __name__ == "__main__":
    main()
