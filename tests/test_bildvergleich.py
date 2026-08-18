"""Hat sich am Kamerabild überhaupt etwas geändert?

Live-Vision schickte alle 12,5 Sekunden ein Bild an Gemini, solange die
Verbindung offen war -- ohne zu prüfen, ob sich davor etwas verändert hat. Wer
die Kamera eine Minute lang still hält, zahlte fünf identische Anfragen.
Vision ist rund 40 Prozent der KI-Kosten je Nutzer.

Der heikle Test steht in der Mitte: eine GETAPPTE Karte. Die Erkennung liefert
nicht nur, welche Karten liegen, sondern auch, ob eine gedreht ist. Ein
globaler Bild-Hash hätte diese örtlich begrenzte Änderung übersehen, "unverändert"
gesagt, und die Anzeige wäre auf einem veralteten Spielstand stehengeblieben --
ein Fehler, den niemand als Fehler erkennt.
"""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from services import bildvergleich


def _jpeg(bild) -> bytes:
    erfolg, puffer = cv2.imencode(".jpg", bild, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
    assert erfolg
    return puffer.tobytes()


def _spielfeld(getappt=False, zusatzkarte=False):
    """Ein Bild wie von der Kamera: grüner Untergrund, helle Karten darauf."""
    bild = np.full((720, 1280, 3), 40, dtype=np.uint8)
    bild[:, :, 1] = 90  # grünliche Spielmatte

    # Vier Karten nebeneinander, aufrecht (100x150 Pixel).
    for i, x in enumerate((100, 300, 500, 700)):
        if getappt and i == 1:
            # Getappt = um 90 Grad gedreht: aus 100x150 wird 150x100.
            cv2.rectangle(bild, (x, 250), (x + 150, 350), (235, 228, 210), -1)
        else:
            cv2.rectangle(bild, (x, 200), (x + 100, 350), (235, 228, 210), -1)

    if zusatzkarte:
        cv2.rectangle(bild, (900, 200), (1000, 350), (235, 228, 210), -1)
    return bild


def _mit_rauschen(bild, staerke=3):
    """Sensorrauschen, wie es zwischen zwei Aufnahmen immer entsteht."""
    rauschen = np.random.default_rng(42).integers(
        -staerke, staerke + 1, bild.shape, dtype=np.int16)
    return np.clip(bild.astype(np.int16) + rauschen, 0, 255).astype(np.uint8)


# ----------------------------------------------------------------------
# Was gespart werden soll
# ----------------------------------------------------------------------

def test_dasselbe_bild_gilt_als_unveraendert():
    daten = _jpeg(_spielfeld())
    a = bildvergleich.signatur(daten)
    b = bildvergleich.signatur(daten)

    assert bildvergleich.unveraendert(a, b)


def test_ruhige_kamera_gilt_als_unveraendert():
    """Zwei Aufnahmen derselben Szene sind nie bitgleich -- Sensorrauschen und
    Autofokus sorgen dafür. Genau das ist der Fall, den es zu sparen gilt."""
    feld = _spielfeld()
    a = bildvergleich.signatur(_jpeg(feld))
    b = bildvergleich.signatur(_jpeg(_mit_rauschen(feld)))

    assert bildvergleich.unveraendert(a, b)


# ----------------------------------------------------------------------
# Was AUF KEINEN FALL übersehen werden darf
# ----------------------------------------------------------------------

def test_eine_getappte_karte_wird_bemerkt():
    """Der Grund für das Raster statt eines Bild-Hashes.

    Eine getappte Karte ist eine um 90 Grad gedrehte Karte -- eine örtlich
    begrenzte Änderung, die einen globalen Hash kaum bewegt. Übersieht der
    Vergleich sie, zeigt die Anwendung einen veralteten Spielstand an, ohne
    dass irgendetwas nach einem Fehler aussieht.
    """
    a = bildvergleich.signatur(_jpeg(_spielfeld(getappt=False)))
    b = bildvergleich.signatur(_jpeg(_spielfeld(getappt=True)))

    assert not bildvergleich.unveraendert(a, b)


def test_eine_zusaetzlich_ausgespielte_karte_wird_bemerkt():
    a = bildvergleich.signatur(_jpeg(_spielfeld()))
    b = bildvergleich.signatur(_jpeg(_spielfeld(zusatzkarte=True)))

    assert not bildvergleich.unveraendert(a, b)


def test_ein_ganz_anderes_bild_wird_bemerkt():
    a = bildvergleich.signatur(_jpeg(_spielfeld()))
    b = bildvergleich.signatur(_jpeg(np.zeros((720, 1280, 3), dtype=np.uint8)))

    assert not bildvergleich.unveraendert(a, b)


# ----------------------------------------------------------------------
# Im Zweifel wird gefragt
# ----------------------------------------------------------------------
# Ist der Vergleich unsicher, muss "verändert" herauskommen. Das kostet dann
# einen Aufruf -- also genau das, was vorher immer passiert ist. Ein
# übersehener Zug wäre dagegen ein falsches Ergebnis auf dem Bildschirm.

def test_unlesbare_daten_ergeben_keine_signatur():
    assert bildvergleich.signatur(b"das ist kein JPEG") is None
    assert bildvergleich.signatur(b"") is None
    assert bildvergleich.signatur(None) is None


def test_ohne_signatur_gilt_das_bild_als_veraendert():
    gueltig = bildvergleich.signatur(_jpeg(_spielfeld()))

    assert not bildvergleich.unveraendert(None, gueltig)
    assert not bildvergleich.unveraendert(gueltig, None)
    assert not bildvergleich.unveraendert(None, None)


def test_erstes_bild_einer_sitzung_wird_immer_gefragt():
    """Zu Beginn gibt es nichts zu vergleichen."""
    erstes = bildvergleich.signatur(_jpeg(_spielfeld()))

    assert not bildvergleich.unveraendert(None, erstes)


def test_verschiedene_groessen_gelten_als_veraendert():
    a = bildvergleich.signatur(_jpeg(_spielfeld()))
    b = np.zeros((8, 8), dtype="float32")

    assert not bildvergleich.unveraendert(a, b)


# ----------------------------------------------------------------------
# Einstellbarkeit
# ----------------------------------------------------------------------

def test_die_schwelle_laesst_sich_verschaerfen():
    feld = _spielfeld()
    a = bildvergleich.signatur(_jpeg(feld))
    b = bildvergleich.signatur(_jpeg(_mit_rauschen(feld)))

    assert bildvergleich.unveraendert(a, b)
    # Mit Schwelle 0 zählt jede noch so kleine Abweichung.
    assert not bildvergleich.unveraendert(a, b, schwelle=0.0)


def test_die_signatur_ist_klein_genug_zum_mitfuehren():
    """Sie wird je offener Verbindung im Speicher gehalten."""
    sig = bildvergleich.signatur(_jpeg(_spielfeld()))

    assert sig.shape == (bildvergleich.RASTER, bildvergleich.RASTER)
    assert sig.nbytes < 8 * 1024


def test_die_schwelle_liegt_mit_abstand_zwischen_den_faellen():
    """Dass die Tests oben gruen sind, heisst noch nicht, dass die Schwelle gut
    gewaehlt ist -- sie koennte knapp danebenliegen und beim naechsten
    Kameramodell kippen. Deshalb wird der ABSTAND gemessen.

    Gemessen (groesste Abweichung einer Rasterzelle, 0-255):
        Sensorrauschen        1
        eine getappte Karte 154
    Die Schwelle muss deutlich ueber dem ersten und deutlich unter dem
    zweiten Wert liegen.
    """
    feld = _spielfeld()

    rauschen = float(np.max(np.abs(
        bildvergleich.signatur(_jpeg(feld))
        - bildvergleich.signatur(_jpeg(_mit_rauschen(feld, 10))))))
    echte_aenderung = float(np.max(np.abs(
        bildvergleich.signatur(_jpeg(_spielfeld(getappt=False)))
        - bildvergleich.signatur(_jpeg(_spielfeld(getappt=True))))))

    assert rauschen * 3 < bildvergleich.SCHWELLE, (
        f"Schwelle {bildvergleich.SCHWELLE} liegt zu nah am Rauschen ({rauschen})")
    assert bildvergleich.SCHWELLE * 3 < echte_aenderung, (
        f"Schwelle {bildvergleich.SCHWELLE} liegt zu nah an einer echten "
        f"Aenderung ({echte_aenderung}) -- ein Zug koennte uebersehen werden")
