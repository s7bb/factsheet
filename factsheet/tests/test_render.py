import datetime as dt
import re

from schulweg import school_spark, SPARK_LABELS


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


import pytest

from schulweg import fmt, render_html_schulweg


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
        "days": 23, "fallback": fallback, "centres": [],
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
    html = render_html_schulweg(empty_stats(), "Juli", 2026, "2026-07")
    assert html.count('class="slot-row"') == 6


def test_fallback_month_is_labelled_in_the_header():
    html = render_html_schulweg(empty_stats(fallback=True), "August", 2026, "2026-08")
    assert "Werktage" in html
    assert "keine Schultage" in html


def test_ferien_source_is_named_on_the_sheet():
    """Ein Rueckfall auf die Tabelle darf nie unsichtbar sein."""
    s = empty_stats()
    s["quelle"] = "hinterlegte Tabelle (Stand 2026-08-05)"
    html = render_html_schulweg(s, "Juli", 2026, "2026-07")
    assert "hinterlegte Tabelle (Stand 2026-08-05)" in html
