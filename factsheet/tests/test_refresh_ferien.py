"""Tests fuer tools/refresh_ferien.py.

Der Refresher ueberschreibt die Fallback-Tabelle. Faellt seine Pruefung aus,
zerstoert genau der API-Zustand, gegen den die Tabelle absichert, die Tabelle
selbst. Diese Tests pinnen die Pruefung.
"""
import datetime as dt
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import refresh_ferien as rf  # noqa: E402


def eintraege(n, jahr=2026, tag_abstand=30):
    """n plausible, disjunkte Zeitraeume im gegebenen Jahr."""
    out, tag = [], dt.date(jahr, 1, 5)
    for i in range(n):
        out.append((tag.isoformat(), (tag + dt.timedelta(days=4)).isoformat(), f"Ferien {i}"))
        tag += dt.timedelta(days=tag_abstand)
    return out


VON, BIS = dt.date(2026, 1, 1), dt.date(2026, 12, 31)


def test_plausible_antwort_wird_akzeptiert():
    assert rf.pruefe(eintraege(7), VON, BIS) == []


def test_leere_antwort_wird_abgelehnt():
    """Ein HTTP 200 mit leerer Liste ist der gefaehrlichste Fall."""
    assert rf.pruefe([], VON, BIS) != []


def test_zu_wenige_zeitraeume_werden_abgelehnt():
    fehler = rf.pruefe(eintraege(rf.MIN_PRO_JAHR - 1), VON, BIS)
    assert any("mindestens" in f for f in fehler)


def test_unlesbares_datum_wird_abgelehnt():
    kaputt = eintraege(7)
    kaputt[0] = ("01.08.2026", "14.09.2026", "Sommerferien")
    fehler = rf.pruefe(kaputt, VON, BIS)
    assert any("unlesbar" in f for f in fehler)


def test_ende_vor_beginn_wird_abgelehnt():
    kaputt = eintraege(7)
    kaputt[0] = ("2026-09-14", "2026-08-01", "Sommerferien")
    fehler = rf.pruefe(kaputt, VON, BIS)
    assert any("Ende vor Beginn" in f for f in fehler)


def test_ueberlappende_zeitraeume_werden_abgelehnt():
    kaputt = sorted(eintraege(7) + [("2026-01-06", "2026-01-20", "Doppelt")])
    fehler = rf.pruefe(kaputt, VON, BIS)
    assert any("ueberlappend" in f for f in fehler)


def test_fehlendes_jahr_wird_abgelehnt():
    """Mehrjahresfenster, aber Daten nur fuer ein Jahr."""
    fehler = rf.pruefe(eintraege(12), dt.date(2026, 1, 1), dt.date(2027, 12, 31))
    assert any("kein Zeitraum im Jahr 2027" in f for f in fehler)


def test_mehrjahresfenster_verlangt_mehr_zeitraeume():
    zwei_jahre = eintraege(6) + eintraege(6, jahr=2027)
    fehler = rf.pruefe(zwei_jahre, dt.date(2026, 1, 1), dt.date(2027, 12, 31))
    assert fehler == []
    fehler = rf.pruefe(eintraege(6) + eintraege(2, jahr=2027),
                       dt.date(2026, 1, 1), dt.date(2027, 12, 31))
    assert any("mindestens" in f for f in fehler)


# --- Fensterzerlegung (API-Limit drei Jahre) ------------------------------- #

def test_kurzes_fenster_bleibt_ein_stueck():
    f = list(rf._fenster(dt.date(2026, 1, 1), dt.date(2027, 6, 30)))
    assert f == [(dt.date(2026, 1, 1), dt.date(2027, 6, 30))]


def test_langes_fenster_wird_zerlegt_und_deckt_lueckenlos_ab():
    von, bis = dt.date(2025, 8, 1), dt.date(2030, 12, 31)
    f = list(rf._fenster(von, bis))
    assert len(f) > 1
    assert f[0][0] == von and f[-1][1] == bis
    for a, b in f:
        assert (b - a).days <= 366 * rf.MAX_FENSTER_JAHRE
    for (_, ende), (start, _) in zip(f, f[1:]):
        assert start == ende + dt.timedelta(days=1)   # keine Luecke, keine Ueberlappung


# --- Patchen von schulweg.py ---------------------------------------------- #

def test_schreibe_ersetzt_stand_und_block():
    alt = rf.SCHULWEG.read_text(encoding="utf-8")
    neu = rf.schreibe(alt, eintraege(7), VON, BIS, dt.date(2027, 3, 1))
    assert 'FERIEN_STAND = "2027-03-01"' in neu
    assert 'FERIEN_ABGEDECKT = ("2026-01-01", "2026-12-31")' in neu
    assert neu.count("FERIEN = [") == 1
    assert neu.count("FERIEN_ABGEDECKT = (") == 1
    # QUELLE_TABELLE steht zwischen Stand und Block und darf nicht verlorengehen
    assert "QUELLE_TABELLE = f\"hinterlegte Tabelle (Stand {FERIEN_STAND})\"" in neu


def test_schreibe_laesst_den_rest_der_datei_unangetastet():
    alt = rf.SCHULWEG.read_text(encoding="utf-8")
    neu = rf.schreibe(alt, eintraege(7), VON, BIS, dt.date(2027, 3, 1))
    for anker in ("def compute_schulweg(", "def render_html_schulweg(",
                  "def slot_centres(", "MIN_FERIEN_PRO_JAHR"):
        assert anker in neu


def test_ergebnis_ist_weiterhin_gueltiges_python():
    import ast
    alt = rf.SCHULWEG.read_text(encoding="utf-8")
    neu = rf.schreibe(alt, eintraege(7), VON, BIS, dt.date(2027, 3, 1))
    ast.parse(neu)


def test_bisherige_abdeckung_wird_gelesen():
    von, bis = rf.bisherige_abdeckung(rf.SCHULWEG.read_text(encoding="utf-8"))
    assert von < bis
    assert von.year >= 2025


def test_schreibe_meldet_veraenderte_datei():
    """Ein von Hand zerstoerter Block muss auffallen, statt still zu misslingen."""
    with pytest.raises(SystemExit):
        rf.schreibe("nur irgendein Text ohne Block", eintraege(7), VON, BIS, dt.date(2027, 3, 1))


@pytest.mark.network
def test_live_api_liefert_plausible_daten():
    von, bis = dt.date(2026, 1, 1), dt.date(2027, 12, 31)
    daten = rf.hole(von, bis)
    assert rf.pruefe(daten, von, bis) == []
