import datetime as dt
import re
import zoneinfo

import pandas as pd

import schulweg
from schulweg import (SLOTS, compute_schulweg, fmt, render_html_schulweg,
                      school_spark, SPARK_LABELS)

TZ = zoneinfo.ZoneInfo("Europe/Berlin")


def label_count(svg):
    return len(re.findall(r'class="spark-lab"', svg))


def test_spark_labels_never_exceed_the_target_count():
    """Eine Schulmonatsreihe hat je nach Monat 14 bis 23 Punkte."""
    for n in range(14, 24):
        daily = {dt.date(2026, 7, 1) + dt.timedelta(days=i): 3.0 for i in range(n)}
        assert label_count(school_spark(daily)) == SPARK_LABELS, f"n={n}"


def test_spark_always_labels_first_and_last_point():
    daily = {dt.date(2026, 7, 1) + dt.timedelta(days=i): 3.0 for i in range(18)}
    svg = school_spark(daily)
    assert ">1<" in svg
    assert ">18<" in svg


def test_spark_handles_single_point():
    svg = school_spark({dt.date(2026, 7, 1): 3.0})
    assert "<svg" in svg
    assert "nan" not in svg


def test_spark_handles_empty_series():
    svg = school_spark({})
    assert "<svg" in svg
    assert "nan" not in svg


def test_spark_handles_all_zero_delays():
    daily = {dt.date(2026, 7, 1) + dt.timedelta(days=i): 0.0 for i in range(5)}
    svg = school_spark(daily)
    assert "nan" not in svg


def test_fmt_renders_none_as_dash():
    assert fmt(None) == "–"
    assert fmt(None, suffix="%") == "–"


def test_fmt_uses_german_decimal_comma():
    assert fmt(5.39, dec=2) == "5,39"
    assert fmt(90.58, dec=1, suffix="%") == "90,6%"


def empty_stats(fallback=False):
    leer = {"n": 0, "canc": 0, "avail": None, "ontime": None,
            "avg": None, "gt5": None, "p90": None}
    return {
        "days": 23, "fallback": fallback,
        "win": {"wolfratshausen": dict(leer), "muenchen": dict(leer)},
        "mon": {"wolfratshausen": dict(leer), "muenchen": dict(leer)},
        "slots": [{"label": "–",
                   "dirs": {"wolfratshausen": dict(leer), "muenchen": dict(leer)}}
                  for _ in range(6)],
        "daily": {}, "warnungen": [], "quelle": "OpenHolidays API",
    }


def test_html_survives_an_entirely_empty_month():
    html = render_html_schulweg(empty_stats(), "Juli", 2026, "2026-07")
    assert "nan" not in html
    assert "None" not in html


def test_html_has_the_page_wrapper_render_pdf_needs():
    html = render_html_schulweg(empty_stats(), "Juli", 2026, "2026-07")
    assert '<div class="page">' in html
    assert "@page { size: A4; margin: 0; }" in html
    assert "width:210mm" in html


def test_html_defines_the_spark_css_it_uses():
    html = render_html_schulweg(empty_stats(), "Juli", 2026, "2026-07")
    assert ".spark-lab {" in html


def test_html_has_no_em_dash():
    html = render_html_schulweg(empty_stats(), "Juli", 2026, "2026-07")
    assert "—" not in html


def test_html_shows_six_slot_rows():
    assert len(empty_stats()["slots"]) == SLOTS
    html = render_html_schulweg(empty_stats(), "Juli", 2026, "2026-07")
    assert html.count('class="slot-row"') == SLOTS


def test_fallback_month_is_labelled_in_the_header():
    html = render_html_schulweg(empty_stats(fallback=True), "August", 2026, "2026-08")
    assert "Werktage" in html
    assert "keine Schultage" in html


def test_daily_average_card_title_matches_the_basis():
    """Card 3's title must switch basis with the header, so gapped day-number
    labels under a fallback month read as weekends/Ferien, not missing data."""
    normal_html = render_html_schulweg(empty_stats(), "Juli", 2026, "2026-07")
    assert "Versp&auml;tung je Schultag" in normal_html
    assert "Versp&auml;tung je Werktag" not in normal_html

    fallback_html = render_html_schulweg(empty_stats(fallback=True), "August", 2026, "2026-08")
    assert "Versp&auml;tung je Werktag" in fallback_html
    assert "Versp&auml;tung je Schultag" not in fallback_html


def test_ferien_source_is_named_on_the_sheet():
    """Ein Rueckfall auf die Tabelle darf nie unsichtbar sein."""
    s = empty_stats()
    s["quelle"] = "hinterlegte Tabelle (Stand 2026-08-05)"
    html = render_html_schulweg(s, "Juli", 2026, "2026-07")
    assert "hinterlegte Tabelle (Stand 2026-08-05)" in html


def test_slot_grid_handles_all_zero_delays():
    """Mirrors test_spark_handles_all_zero_delays: every slot average is
    exactly 0.0, which must not raise ZeroDivisionError in slot_grid's
    vmax computation."""
    voll = {"n": 1, "canc": 0, "avail": 100.0, "ontime": 100.0,
            "avg": 0.0, "gt5": 0.0, "p90": 0.0}
    s = empty_stats()
    s["slots"] = [{"label": "06:40",
                   "dirs": {"wolfratshausen": dict(voll), "muenchen": dict(voll)}}
                  for _ in range(6)]
    html = render_html_schulweg(s, "Juli", 2026, "2026-07")
    assert "nan" not in html


SPALTEN = ["scheduled_time", "local", "date", "direction_bucket",
           "delay_minutes", "cancelled"]


def make_df(records):
    """records: (date, minute_of_day, richtung, delay_or_None_for_cancelled).
    Mirrors tests/test_stats.py's make_df."""
    rows = []
    for day, minute, richtung, delay in records:
        local = dt.datetime.combine(day, dt.time(minute // 60, minute % 60), TZ)
        rows.append({
            "scheduled_time": local.astimezone(dt.timezone.utc),
            "local": local,
            "date": day,
            "direction_bucket": richtung,
            "delay_minutes": delay,
            "cancelled": delay is None,
        })
    df = pd.DataFrame(rows)
    df["scheduled_time"] = pd.to_datetime(df["scheduled_time"], utc=True)
    df["local"] = pd.to_datetime(df["local"]).dt.tz_convert(TZ)
    return df


def test_compute_schulweg_feeds_render_html_schulweg_directly(monkeypatch):
    """No other test composes the two halves: compute_schulweg -> render_html_
    schulweg. Force the offline Ferien path (as tests/test_stats.py does) so
    this stays deterministic and does not hit the network."""
    monkeypatch.setattr(schulweg, "ferien_api", lambda von, bis: None)
    df = make_df([
        (dt.date(2026, 7, 1), 400, "muenchen", 1.0),
        (dt.date(2026, 7, 1), 410, "wolfratshausen", 2.0),
        (dt.date(2026, 7, 2), 400, "muenchen", None),
        (dt.date(2026, 7, 3), 405, "wolfratshausen", 6.0),
    ])
    s = compute_schulweg(df, "2026-07")
    html = render_html_schulweg(s, "Juli", 2026, "2026-07")

    assert "nan" not in html
    assert "None" not in html
    assert html.count('class="slot-row"') == SLOTS
