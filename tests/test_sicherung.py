"""tests/test_sicherung.py -- Datenbank sichern und zurückspielen.

Eine Sammlung mit tausenden Karten ist Handarbeit von Jahren. Eine Sicherung,
die nie zurückgespielt wurde, ist nur eine Vermutung -- deshalb spielt der
zentrale Test hier tatsächlich zurück und prüft die Daten danach.
"""

import sqlite3

import pytest

from werkzeuge import sicherung


def _lege_datenbank_an(pfad, konten=("anna", "bert"), karten=3):
    conn = sqlite3.connect(pfad)
    conn.execute("CREATE TABLE nutzer (benutzername TEXT PRIMARY KEY, rolle TEXT)")
    conn.execute("CREATE TABLE sammlung_alben (id INTEGER PRIMARY KEY, benutzername TEXT, karten_name TEXT)")
    for name in konten:
        conn.execute("INSERT INTO nutzer VALUES (?, 'free')", (name,))
        for i in range(karten):
            conn.execute("INSERT INTO sammlung_alben (benutzername, karten_name) VALUES (?, ?)",
                         (name, f"Karte {i}"))
    conn.commit()
    conn.close()
    return pfad


@pytest.fixture
def datenbank(tmp_path):
    return _lege_datenbank_an(tmp_path / "app.db")


def _url(pfad):
    return f"sqlite+aiosqlite:///{pfad}"


# ----------------------------------------------------------------------
# Pfade und Befehle
# ----------------------------------------------------------------------
def test_pfad_aus_url():
    assert sicherung.sqlite_pfad("sqlite+aiosqlite:///mtg_app.db") == "mtg_app.db"
    assert sicherung.sqlite_pfad("sqlite+aiosqlite:////var/lib/app.db") == "/var/lib/app.db"


def test_postgres_wird_erkannt():
    assert sicherung.ist_sqlite("sqlite+aiosqlite:///x.db") is True
    assert sicherung.ist_sqlite("postgresql+asyncpg://u:p@host/db") is False


def test_pg_dump_befehl_ohne_treiber_im_schema(tmp_path):
    """pg_dump kennt "postgresql+asyncpg://" nicht -- der Treiber muss raus."""
    befehl = sicherung.pg_dump_befehl(
        "postgresql+asyncpg://nutzer:geheim@localhost/grana", tmp_path / "x.dump")

    assert befehl[0] == "pg_dump"
    assert "postgresql://nutzer:geheim@localhost/grana" in befehl
    assert not any("asyncpg" in teil for teil in befehl)


# ----------------------------------------------------------------------
# Sichern
# ----------------------------------------------------------------------
def test_sicherung_enthaelt_die_daten(datenbank, tmp_path):
    ziel = sicherung.sichern(str(tmp_path / "sicherungen"), url=_url(datenbank))

    assert ziel.exists()
    conn = sqlite3.connect(ziel)
    assert conn.execute("SELECT COUNT(*) FROM nutzer").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM sammlung_alben").fetchone()[0] == 6
    conn.close()


def test_fehlende_datenbank_meldet_sich(tmp_path):
    with pytest.raises(FileNotFoundError):
        sicherung.sichern(str(tmp_path / "s"), url=_url(tmp_path / "gibtsnicht.db"))


def test_kaputte_sicherung_wird_nicht_behalten(datenbank, tmp_path, monkeypatch):
    """Eine unbrauchbare Sicherung ist schlimmer als keine: man verlässt sich
    darauf. Sie wird deshalb verworfen und der Lauf meldet einen Fehler."""
    def kaputt_schreiben(quelle, ziel):
        ziel.write_bytes(b"kein sqlite")

    monkeypatch.setattr(sicherung, "sqlite_sichern", kaputt_schreiben)

    with pytest.raises(RuntimeError, match="fehlerhaft"):
        sicherung.sichern(str(tmp_path / "s"), url=_url(datenbank))

    assert sicherung.sicherungen(str(tmp_path / "s")) == []


def test_fremde_datenbank_wird_erkannt(tmp_path):
    """Eine SQLite-Datei ohne die Tabelle 'nutzer' ist nicht unsere."""
    fremd = tmp_path / "fremd.db"
    conn = sqlite3.connect(fremd)
    conn.execute("CREATE TABLE irgendwas (a TEXT)")
    conn.commit()
    conn.close()

    ok, meldung = sicherung.sqlite_pruefen(fremd)
    assert ok is False
    assert "nutzer" in meldung


# ----------------------------------------------------------------------
# Aufräumen
# ----------------------------------------------------------------------
def test_alte_sicherungen_werden_entfernt(tmp_path):
    ordner = tmp_path / "s"
    ordner.mkdir()
    for tag in range(1, 21):
        (ordner / f"grana-2026-08-{tag:02d}_03-00-00.db").write_bytes(b"x")

    entfernt = sicherung.aufraeumen(str(ordner), behalten=14)

    assert len(entfernt) == 6
    uebrig = sicherung.sicherungen(str(ordner))
    assert len(uebrig) == 14
    # Die neuesten bleiben -- nicht die ältesten.
    assert uebrig[0].name.endswith("2026-08-20_03-00-00.db")


def test_fremde_dateien_bleiben_liegen(tmp_path):
    ordner = tmp_path / "s"
    ordner.mkdir()
    (ordner / "grana-2026-08-01_03-00-00.db").write_bytes(b"x")
    (ordner / "wichtige-notizen.txt").write_text("nicht anfassen")

    sicherung.aufraeumen(str(ordner), behalten=0)

    assert (ordner / "wichtige-notizen.txt").exists()


# ----------------------------------------------------------------------
# Zurückspielen -- der eigentliche Zweck
# ----------------------------------------------------------------------
def test_zuruecksichern_stellt_die_daten_wieder_her(datenbank, tmp_path):
    ziel = sicherung.sichern(str(tmp_path / "s"), url=_url(datenbank))

    # Katastrophe: alle Daten weg.
    conn = sqlite3.connect(datenbank)
    conn.execute("DELETE FROM sammlung_alben")
    conn.execute("DELETE FROM nutzer")
    conn.commit()
    conn.close()

    sicherung.zuruecksichern(str(ziel), url=_url(datenbank))

    conn = sqlite3.connect(datenbank)
    assert conn.execute("SELECT COUNT(*) FROM nutzer").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM sammlung_alben").fetchone()[0] == 6
    conn.close()


def test_vor_dem_zuruecksichern_wird_der_stand_gesichert(datenbank, tmp_path):
    """Wer die falsche Datei erwischt, soll nicht auch noch den bisherigen
    Stand verloren haben."""
    ziel = sicherung.sichern(str(tmp_path / "s"), url=_url(datenbank))

    conn = sqlite3.connect(datenbank)
    conn.execute("INSERT INTO nutzer VALUES ('clara', 'premium')")
    conn.commit()
    conn.close()

    sicherung.zuruecksichern(str(ziel), url=_url(datenbank))

    vorher = list(datenbank.parent.glob("app-vor-ruecksicherung-*.db"))
    assert len(vorher) == 1
    conn = sqlite3.connect(vorher[0])
    namen = {r[0] for r in conn.execute("SELECT benutzername FROM nutzer").fetchall()}
    conn.close()
    assert "clara" in namen, "der Stand vor dem Zurückspielen fehlt"


def test_unbrauchbare_datei_wird_nicht_eingespielt(datenbank, tmp_path):
    kaputt = tmp_path / "kaputt.db"
    kaputt.write_bytes(b"kein sqlite")

    with pytest.raises(RuntimeError, match="unbrauchbar"):
        sicherung.zuruecksichern(str(kaputt), url=_url(datenbank))

    # Die bestehende Datenbank ist unangetastet.
    conn = sqlite3.connect(datenbank)
    assert conn.execute("SELECT COUNT(*) FROM nutzer").fetchone()[0] == 2
    conn.close()


def test_postgres_verweist_auf_pg_restore(tmp_path):
    datei = tmp_path / "x.dump"
    datei.write_bytes(b"x")

    with pytest.raises(NotImplementedError, match="pg_restore"):
        sicherung.zuruecksichern(str(datei), url="postgresql+asyncpg://u@h/db")
