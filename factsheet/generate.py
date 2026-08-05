#!/usr/bin/env python3
"""
Erzeugt das monatliche S7-Baierbrunn-Datenblatt (DIN A4, eine Seite, deutsch) als PDF.

Datenquelle:  https://github.com/s7bb/s7bb-data  ->  archive/<YYYY-MM>.json
Aufruf:       python generate.py [--month YYYY-MM] [--outdir output]

Ohne --month wird der zuletzt abgeschlossene Kalendermonat (Vormonat) verwendet.
Das Skript ist deterministisch und benoetigt kein LLM.
"""
import argparse
import datetime as dt
import json
import math
import sys
import urllib.request
import zoneinfo

import pandas as pd

TZ = zoneinfo.ZoneInfo("Europe/Berlin")
RAW = "https://raw.githubusercontent.com/s7bb/s7bb-data/main/archive/{month}.json"

MONATE = {
    1: "Januar", 2: "Februar", 3: "M\u00e4rz", 4: "April", 5: "Mai", 6: "Juni",
    7: "Juli", 8: "August", 9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}
MONATE_DATEI = {**MONATE, 3: "Maerz"}  # ASCII-Dateiname statt "M\u00e4rz"

# --------------------------------------------------------------------------- #
# Deutsche Zahlenformatierung
# --------------------------------------------------------------------------- #
def dth(n):
    """Ganzzahl mit Tausenderpunkt: 2913 -> '2.913'."""
    return f"{int(round(n)):,}".replace(",", ".")


def dn(x, dec=2):
    """Dezimalzahl mit Komma: 3.18 -> '3,18'."""
    return f"{x:.{dec}f}".replace(".", ",")


# --------------------------------------------------------------------------- #
# Datenbeschaffung
# --------------------------------------------------------------------------- #
def prev_month(today):
    first = today.replace(day=1)
    last_prev = first - dt.timedelta(days=1)
    return f"{last_prev.year:04d}-{last_prev.month:02d}"


def load_month(month):
    url = RAW.format(month=month)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = json.load(r)
    except Exception as e:
        sys.exit(f"FEHLER: Konnte {url} nicht laden: {e}")
    if not data.get("finalized", False):
        print(f"WARNUNG: {month} ist noch nicht finalisiert - Zahlen koennen sich aendern.",
              file=sys.stderr)
    df = pd.DataFrame(data["arrivals"])
    if df.empty:
        sys.exit(f"FEHLER: Keine Ankuenfte in {month}.")
    df["scheduled_time"] = pd.to_datetime(df["scheduled_time"], utc=True)
    df["local"] = df["scheduled_time"].dt.tz_convert(TZ)
    df["date"] = df["local"].dt.date
    # Spalten defensiv anlegen (aeltere Monate haben ein schlankeres Schema)
    for col in ("terminus_status", "direction_bucket", "delay_minutes", "cancelled"):
        if col not in df.columns:
            df[col] = pd.NA
    df["cancelled"] = df["cancelled"].fillna(False).astype(bool)
    return df, data


# --------------------------------------------------------------------------- #
# Kennzahlen
# --------------------------------------------------------------------------- #
def compute_stats(df):
    total = len(df)
    canc = int(df["cancelled"].sum())
    ran = total - canc
    nc = df[~df["cancelled"]]
    dl = nc["delay_minutes"].dropna()

    s = {
        "total": total, "cancelled": canc, "ran": ran,
        "availability": 100 * ran / total,
        "days": int(df["date"].nunique()),
        "ontime_pct": 100 * (dl <= 0).mean(),
        "lt5_pct": 100 * (dl < 5).mean(),
        "gt5_pct": 100 * (dl > 5).mean(),
        "gt15_pct": 100 * (dl > 15).mean(),
        "avg": float(dl.mean()), "median": float(dl.median()),
        "p90": float(dl.quantile(.9)), "maxd": float(dl.max()),
    }

    # Zielbahnhof-Erreichbarkeit
    ts = df["terminus_status"]
    s["reached"] = int((ts == "arrived").sum())
    s["shortturn"] = int((ts == "short_turn").sum())
    s["onward_canc"] = int((ts == "cancelled").sum())
    known = s["reached"] + s["shortturn"] + s["onward_canc"]
    s["not_reached"] = s["shortturn"] + s["onward_canc"]
    s["term_unknown"] = total - known - canc
    s["e2e"] = 100 * s["reached"] / total if total else 0.0
    s["reached_pct"] = 100 * s["reached"] / known if known else 0.0

    # Nach Richtung
    d2 = df[df["direction_bucket"].isin(["muenchen", "wolfratshausen"])].copy()
    s["bydir"] = {}
    for b in ("muenchen", "wolfratshausen"):
        g = d2[d2["direction_bucket"] == b]
        gd = g.loc[~g["cancelled"], "delay_minutes"].dropna()
        s["bydir"][b] = {
            "ontime": 100 * (gd <= 0).mean() if len(gd) else 0.0,
            "avg": float(gd.mean()) if len(gd) else 0.0,
            "canc": 100 * g["cancelled"].mean() if len(g) else 0.0,
        }

    # Verspaetungsverteilung (durchgefuehrte Fahrten)
    bins = [-1e9, 0, 2, 5, 10, 15, 1e9]
    labels = ["early/on-time", "1-2", "3-5", "6-10", "11-15", ">15"]
    hist = pd.cut(dl, bins=bins, labels=labels, right=True).value_counts().reindex(labels)
    s["hist"] = {k: int(v) for k, v in hist.items()}

    # Taegliche Durchschnittsverspaetung
    daily = nc.groupby(nc["local"].dt.day)["delay_minutes"].mean().round(2)
    s["daily"] = {int(k): float(v) for k, v in daily.items()}

    # Verspaetung, wenn Ausfaelle als Verspaetung zaehlen
    s["base"] = s["avg"]
    s["flat20"] = float(pd.Series(dl.tolist() + [20] * canc).mean())
    s["svc"] = service_aware_avg(d2)
    return s


def service_aware_avg(d2, headway=20):
    """Durchschnitt inkl. Ausfaellen: Strafzeit = Fahrplanluecke bis zur naechsten
    S-Bahn gleicher Richtung; fuer die letzte Fahrt des Betriebstags eine Taktluecke
    (Headway) statt des leeren Nachtfensters."""
    d2 = d2.sort_values("scheduled_time")
    d2 = d2.assign(svc_date=(d2["local"] - pd.Timedelta(hours=3)).dt.date)
    d2["next_sched"] = d2.groupby("direction_bucket")["scheduled_time"].shift(-1)
    d2["next_svc"] = d2.groupby("direction_bucket")["svc_date"].shift(-1)
    d2["gap"] = (d2["next_sched"] - d2["scheduled_time"]).dt.total_seconds() / 60
    last_of_day = (d2["next_svc"] != d2["svc_date"]) | d2["next_sched"].isna()
    pen = d2["gap"].where(~last_of_day, headway).where(d2["cancelled"])
    real = d2.loc[~d2["cancelled"], "delay_minutes"].dropna().tolist()
    vals = real + pen.dropna().tolist()
    return float(pd.Series(vals).mean()) if vals else 0.0


# --------------------------------------------------------------------------- #
# SVG-Bausteine
# --------------------------------------------------------------------------- #
def donut(pct, color, track="#e6ebf1", r=52, sw=13):
    c = 2 * math.pi * r
    fill = c * pct / 100
    return (f'<svg viewBox="0 0 140 140" class="donut">'
            f'<circle cx="70" cy="70" r="{r}" fill="none" stroke="{track}" stroke-width="{sw}"/>'
            f'<circle cx="70" cy="70" r="{r}" fill="none" stroke="{color}" stroke-width="{sw}" '
            f'stroke-dasharray="{fill:.2f} {c:.2f}" stroke-linecap="round" transform="rotate(-90 70 70)"/>'
            f'<text x="70" y="70" dominant-baseline="central" class="donut-num">'
            f'{dn(pct,1)}<tspan class="donut-pct">%</tspan></text>'
            f'</svg>')


def histogram(hist):
    labelmap = {"early/on-time": "fr\u00fch/p\u00fcnktl.", "1-2": "1-2", "3-5": "3-5",
                "6-10": "6-10", "11-15": "11-15", ">15": "&gt;15"}
    palette = {"early/on-time": "#2e9e5b", "1-2": "#7cc47f", "3-5": "#f2c744",
               "6-10": "#f0902f", "11-15": "#e2622c", ">15": "#c8371f"}
    maxh = max(hist.values()) or 1
    bars = ""
    bw, gap, x = 60, 14, 8
    for label, v in hist.items():
        h = 126 * v / maxh
        y = 150 - h
        bars += f'<rect x="{x}" y="{y:.1f}" width="{bw}" height="{h:.1f}" rx="3" fill="{palette[label]}"/>'
        bars += f'<text x="{x+bw/2}" y="{y-6:.1f}" class="hbar-val">{dth(v)}</text>'
        bars += f'<text x="{x+bw/2}" y="166" class="hbar-lab">{labelmap[label]}</text>'
        x += bw + gap
    return f'<svg viewBox="0 0 {x} 172" class="hist">{bars}</svg>'


def sparkline(daily):
    days = sorted(daily)
    vmax = max(daily.values()) or 1
    W, H = 700, 80
    pts = []
    for i, d in enumerate(days):
        px = 10 + (W - 20) * i / (len(days) - 1 or 1)
        py = H - 18 - (H - 30) * daily[d] / vmax
        pts.append((px, py))
    poly = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = f"10,{H-18} " + poly + f" {pts[-1][0]:.1f},{H-18}"
    dots = "".join(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.3" fill="#1b4f8a"/>' for px, py in pts)
    xlab = "".join(f'<text x="{pts[i][0]:.1f}" y="{H-4}" class="spark-lab">{d}</text>'
                   for i, d in enumerate(days) if d % 5 == 0 or d == 1)
    return (f'<svg viewBox="0 0 {W} {H}" class="spark">'
            f'<polygon points="{area}" fill="#dbe7f5"/>'
            f'<polyline points="{poly}" fill="none" stroke="#1b4f8a" stroke-width="2"/>'
            f'{dots}{xlab}</svg>')


def calc_bars(s):
    calc = [("Basiswert\n(Ausf\u00e4lle ausgeschlossen)", s["base"], "#9aa7b4"),
            ("Pauschal 20 Min.\nje Ausfall", s["flat20"], "#3f7cc0"),
            ("Fahrplanbasierte L\u00fccke\n(bis zur n\u00e4chsten S-Bahn)", s["svc"], "#1b4f8a")]
    cmax = max(v for _, v, _ in calc) or 1
    rows = ""
    for lab, v, col in calc:
        w = 100 * v / cmax
        l1, l2 = lab.split("\n")
        rows += (f'<div class="calc-row"><div class="calc-lab"><b>{l1}</b><span>{l2}</span></div>'
                 f'<div class="calc-track"><div class="calc-fill" style="width:{w:.1f}%;background:{col}">'
                 f'<span>{dn(v,2)} Min.</span></div></div></div>')
    return rows


def dircard(disp, d):
    return (f'<div class="dircard"><div class="dirname">{disp}</div>'
            f'<div class="dirstat"><span class="dv">{dn(d["ontime"],0)}%</span><span class="dl">p\u00fcnktlich</span></div>'
            f'<div class="dirstat"><span class="dv">{dn(d["avg"],2)}</span><span class="dl">&Oslash; Versp. (Min.)</span></div>'
            f'<div class="dirstat"><span class="dv">{dn(d["canc"],1)}%</span><span class="dl">ausgefallen</span></div></div>')


# --------------------------------------------------------------------------- #
# HTML-Rendering
# --------------------------------------------------------------------------- #
def render_html(s, month_label, month_file, year, archive_month):
    bd = s["bydir"]
    css = """
@page { size: A4; margin: 0; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Helvetica Neue',Arial,sans-serif; color:#1c2733; width:210mm; }
.page { padding:6mm 13mm 0; }
.head { display:flex; align-items:center; justify-content:space-between;
  border-bottom:3px solid #1b4f8a; padding-bottom:7px; margin-bottom:10px; }
.brand { display:flex; align-items:center; gap:12px; }
.logo { width:44px;height:44px;border-radius:9px;background:#1b4f8a;color:#fff;
  font-weight:800;font-size:19px;display:flex;align-items:center;justify-content:center;letter-spacing:-1px; }
h1 { font-size:21px; font-weight:800; letter-spacing:-.3px; }
.sub { font-size:12px; color:#6a7684; margin-top:1px; }
.period { text-align:right;font-size:12px;color:#6a7684; }
.period b { display:block;font-size:17px;color:#1b4f8a;font-weight:800; }
.section-t { font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:1.1px;
  color:#1b4f8a;margin:0 0 6px; display:flex;align-items:center;gap:7px; }
.section-t::before { content:"";width:5px;height:14px;background:#1b4f8a;border-radius:2px; }
.grid2 { display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:8px; }
.card { border:1px solid #e2e8ef;border-radius:11px;padding:10px 14px;background:#fbfcfd; }
.kpi-row { display:flex;align-items:center;gap:16px; }
.donut { width:118px;height:118px;flex:none; }
.donut-num { font-size:24px;font-weight:800;fill:#1c2733;text-anchor:middle; }
.donut-pct { font-size:12px;font-weight:700; }
.kpi-side .big { font-size:13px;color:#48566a;line-height:1.5; }
.kpi-side .big b { color:#1c2733; }
.pill { display:inline-block;font-size:11px;font-weight:700;padding:2px 9px;border-radius:20px;margin-top:6px; }
.mini { display:flex;gap:6px;margin-top:7px; }
.mini div { flex:1;text-align:center;background:#fff;border:1px solid #e9eef4;border-radius:8px;padding:7px 3px; }
.mini .v { font-size:17px;font-weight:800;color:#1b4f8a; }
.mini .l { font-size:8.5px;color:#6a7684;text-transform:uppercase;letter-spacing:0;
  margin-top:1px;white-space:nowrap; }
.hist { width:100%;height:auto; }
.hbar-val { font-size:12px;font-weight:700;text-anchor:middle;fill:#48566a; }
.hbar-lab { font-size:10px;fill:#6a7684;text-anchor:middle; }
.dircards { display:grid;grid-template-columns:1fr 1fr;gap:10px; }
.dircard { background:#fff;border:1px solid #e9eef4;border-radius:9px;padding:10px 12px; }
.dirname { font-size:12px;font-weight:800;color:#1b4f8a;margin-bottom:7px;
  padding-bottom:5px;border-bottom:1px solid #eef2f6; }
.dirstat { display:flex;justify-content:space-between;align-items:baseline;margin:3px 0; }
.dirstat .dv { font-size:15px;font-weight:800; }
.dirstat .dl { font-size:10px;color:#6a7684; }
.term { display:flex;gap:12px;align-items:stretch; }
.termbar { flex:none;width:150px;display:flex;flex-direction:column;border-radius:9px;overflow:hidden;border:1px solid #e2e8ef; }
.termseg { padding:8px 11px;color:#fff; }
.termseg .tv { font-size:18px;font-weight:800;line-height:1; }
.termseg .tl { font-size:9.5px;opacity:.92;margin-top:2px; }
.termnote { font-size:11.5px;color:#48566a;line-height:1.55;align-self:center; }
.termnote b { color:#1c2733; }
.calc-row { display:flex;align-items:center;gap:12px;margin:6px 0; }
.calc-lab { width:190px;flex:none;font-size:11px;line-height:1.25; }
.calc-lab b { display:block;font-size:12px; }
.calc-lab span { color:#6a7684;font-size:10px; }
.calc-track { flex:1;background:#eef2f6;border-radius:6px;height:30px;position:relative; }
.calc-fill { height:100%;border-radius:6px;display:flex;align-items:center;justify-content:flex-end; }
.calc-fill span { color:#fff;font-weight:800;font-size:12px;padding-right:10px; }
.spark { width:100%;height:auto; }
.spark-lab { font-size:9px;fill:#8592a1;text-anchor:middle; }
.foot { margin-top:0;padding-top:5px;border-top:1px solid #e2e8ef;
  font-size:9.5px;color:#8592a1;display:flex;justify-content:space-between; }
.notemark { font-size:10px;color:#6a7684;margin-top:5px;line-height:1.45; }
"""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head>
<body><div class="page">

<div class="head">
  <div class="brand">
    <div class="logo">S7</div>
    <div><h1>S-Bahn S7 &middot; Baierbrunn</h1>
      <div class="sub">Monatliches Leistungsdatenblatt &middot; beide Richtungen (M&uuml;nchen &harr; Wolfratshausen)</div></div>
  </div>
  <div class="period">Berichtszeitraum<b>{month_label} {year}</b>{s['days']} Betriebstage</div>
</div>

<div class="grid2">
  <div class="card">
    <div class="section-t">Verf&uuml;gbarkeit</div>
    <div class="kpi-row">{donut(s['availability'],'#2e9e5b')}
      <div class="kpi-side">
        <div class="big"><b>{dth(s['ran'])}</b> von <b>{dth(s['total'])}</b> geplanten Fahrten durchgef&uuml;hrt.<br>
        <b>{s['cancelled']}</b> Ausf&auml;lle ({dn(100-s['availability'],1)}%).</div>
        <span class="pill" style="background:#e4f4ea;color:#1f7a44">{dn(s['availability'],0)}% Verf&uuml;gbarkeit</span>
      </div>
    </div>
  </div>
  <div class="card">
    <div class="section-t">P&uuml;nktlichkeit</div>
    <div class="kpi-row">{donut(s['ontime_pct'],'#f0902f')}
      <div class="kpi-side">
        <div class="big">Z&uuml;ge mit <b>p&uuml;nktlicher</b> Ankunft (&le;0 Min.).<br>
        &Oslash; Versp&auml;tung <b>{dn(s['avg'],2)} Min.</b>, Median <b>{dn(s['median'],0)} Min.</b></div>
        <span class="pill" style="background:#fdeede;color:#b45f10">{dn(s['lt5_pct'],0)}% unter 5 Min. Versp&auml;tung</span>
      </div>
    </div>
    <div class="mini">
      <div><div class="v">{dn(s['lt5_pct'],0)}%</div><div class="l">unter 5 Min.</div></div>
      <div><div class="v">{dn(s['gt5_pct'],0)}%</div><div class="l">&uuml;ber 5 Min.</div></div>
      <div><div class="v">{dn(s['gt15_pct'],0)}%</div><div class="l">&uuml;ber 15 Min.</div></div>
      <div><div class="v">{dn(s['p90'],0)}</div><div class="l">p90 (Min.)</div></div>
    </div>
  </div>
</div>

<div class="grid2">
  <div class="card">
    <div class="section-t">Versp&auml;tungsverteilung &middot; durchgef&uuml;hrte Fahrten</div>
    {histogram(s['hist'])}
  </div>
  <div class="card">
    <div class="section-t">Nach Richtung</div>
    <div class="dircards">
      {dircard('&rarr; M&uuml;nchen', bd['muenchen'])}
      {dircard('&rarr; Wolfratshausen', bd['wolfratshausen'])}
    </div>
    <div class="notemark">Z&uuml;ge Richtung Wolfratshausen sind im Schnitt sp&auml;ter und seltener p&uuml;nktlich als Richtung M&uuml;nchen.</div>
  </div>
</div>

<div class="card" style="margin-bottom:10px">
  <div class="section-t">Konnte der Zielbahnhof erreicht werden?</div>
  <div class="term">
    <div class="termbar">
      <div class="termseg" style="background:#2e9e5b;flex:{max(s['reached'],1)}">
        <div class="tv">{dth(s['reached'])}</div><div class="tl">Ziel erreicht</div></div>
      <div class="termseg" style="background:#f0902f;flex:{max(s['shortturn'],4)}">
        <div class="tv">{s['shortturn']}</div><div class="tl">vorzeitig gewendet</div></div>
      <div class="termseg" style="background:#c8371f;flex:{max(s['onward_canc'],4)}">
        <div class="tv">{s['onward_canc']}</div><div class="tl">unterwegs ausgefallen</div></div>
    </div>
    <div class="termnote">
      Von den Z&uuml;gen mit Halt in Baierbrunn fuhren <b>{dn(s['reached_pct'],1)}%</b> bis zum Zielbahnhof durch.
      <b>{s['not_reached']}</b> Z&uuml;ge nicht: <b>{s['shortturn']}</b> wurden vor dem Ziel vorzeitig gewendet
      und <b>{s['onward_canc']}</b> fielen nach Baierbrunn aus.
      Bezogen auf alle {dth(s['total'])} geplanten Fahrten erreichten <b>{dn(s['e2e'],1)}%</b> das Ziel durchg&auml;ngig
      (bei {s['term_unknown']} Z&uuml;gen wurde kein Zielergebnis erfasst).
    </div>
  </div>
</div>

<div class="card" style="margin-bottom:10px">
  <div class="section-t">Durchschnittliche Versp&auml;tung: Ausf&auml;lle als Versp&auml;tung gewertet</div>
  <div class="calc">{calc_bars(s)}</div>
  <div class="notemark">Ein ausgefallener Zug liefert keine Ankunft und bleibt daher im Haupt-Versp&auml;tungswert unber&uuml;cksichtigt.
  Wird jedem Ausfall die Wartezeit auf die n&auml;chste Fahrt angerechnet, steigt der Durchschnitt von <b>{dn(s['base'],2)}</b> auf rund <b>{dn(s['svc'],2)} Min.</b>
  Die fahrplanbasierte Methode nutzt die tats&auml;chliche L&uuml;cke bis zur n&auml;chsten S-Bahn (auf dem Ast meist 20 Min.) und rechnet f&uuml;r die letzte
  Fahrt des Betriebstags eine Taktl&uuml;cke statt des leeren Nachtfensters (02:00&ndash;04:40).</div>
</div>

<div class="card">
  <div class="section-t">T&auml;gliche Durchschnittsversp&auml;tung im Monatsverlauf (Min.)</div>
  {sparkline(s['daily'])}
</div>

<div class="foot">
  <span>Quelle: s7bb-data (github.com/s7bb/s7bb-data) &middot; archive/{archive_month}.json</span>
  <span>Bahnhof Baierbrunn &middot; Versp&auml;tungen &amp; Ausf&auml;lle gg&uuml;. Fahrplan</span>
</div>

</div></body></html>"""


def render_pdf(html, pdf_path):
    from playwright.sync_api import sync_playwright
    import pathlib
    html_path = pathlib.Path(pdf_path).with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("file://" + str(html_path.resolve()))
        height = page.evaluate('document.querySelector(".page").scrollHeight')
        page.pdf(path=str(pdf_path), format="A4", print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        browser.close()
    # A4 @96dpi ~ 1123px; warnen, falls das Datenblatt nicht mehr auf eine Seite passt
    if height > 1123:
        print(f"WARNUNG: Inhalt {height}px > eine A4-Seite (1123px) - Layout pruefen.",
              file=sys.stderr)
    html_path.unlink(missing_ok=True)
    return height


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="S7-Baierbrunn-Datenblatt (PDF) erzeugen.")
    ap.add_argument("--month", help="Berichtsmonat YYYY-MM (Standard: Vormonat)")
    ap.add_argument("--outdir", default="output", help="Ausgabeverzeichnis (Standard: output)")
    args = ap.parse_args()

    month = args.month or prev_month(dt.datetime.now(TZ).date())
    year, mo = month.split("-")
    year, mo = int(year), int(mo)

    print(f"Berichtsmonat: {month} ({MONATE[mo]} {year})")
    df, _ = load_month(month)
    s = compute_stats(df)
    html = render_html(s, MONATE[mo], MONATE_DATEI[mo], year, month)

    import pathlib
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    pdf_path = outdir / f"S7_Baierbrunn_{MONATE_DATEI[mo]}{year}_Datenblatt.pdf"
    render_pdf(html, pdf_path)

    print(f"Erstellt: {pdf_path}")
    print(f"  Verf\u00fcgbarkeit {dn(s['availability'],1)}% | "
          f"p\u00fcnktlich {dn(s['ontime_pct'],1)}% | "
          f"\u00d8 Versp. {dn(s['avg'],2)} Min. | "
          f"Ziel erreicht {dn(s['e2e'],1)}%")


if __name__ == "__main__":
    main()
