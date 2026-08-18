"""services/bildvergleich.py -- hat sich am Bild überhaupt etwas geändert?

Wozu
----
Live-Vision schickt alle 12,5 Sekunden ein Bild an Gemini, solange die
Verbindung offen ist -- ohne zu prüfen, ob sich davor etwas verändert hat. Wer
die Kamera eine Minute lang auf dasselbe Spielfeld hält, zahlt fünf identische
Anfragen. Vision ist rund 40 Prozent der KI-Kosten je Nutzer.

Warum ein Vergleich hier sicher ist
-----------------------------------
Gleiches Bild heisst gleiche Antwort. Das ist keine Schätzung, sondern der
gleiche Gedanke wie beim Zwischenspeichern: Es wird nichts geraten, es wird nur
nicht zweimal dasselbe gefragt.

Warum NICHT einfach ein Bild-Hash
---------------------------------
Der naheliegende Weg wäre ein perzeptueller Hash über das ganze Bild. Für
diesen Zweck ist er falsch: Die Erkennung liefert nicht nur, WELCHE Karten
liegen, sondern auch, ob eine davon getappt ist. Eine getappte Karte ist eine
um 90 Grad gedrehte Karte -- eine örtlich begrenzte Änderung, die einen
globalen Hash kaum bewegt. Der Vergleich hätte "unverändert" gesagt, und die
Anzeige wäre auf einem veralteten Spielstand stehengeblieben. Ein Fehler, den
niemand als Fehler erkennt.

Deshalb wird das Bild in ein Raster zerlegt und die GRÖSSTE Abweichung einer
einzelnen Zelle betrachtet, nicht der Durchschnitt. Eine Karte, die sich dreht,
verändert mehrere Zellen deutlich -- Sensorrauschen und leichte
Helligkeitsschwankungen verändern alle Zellen ein bisschen. Das eine löst aus,
das andere nicht.

Die Richtung des Irrtums
------------------------
Im Zweifel wird gefragt. Ist der Vergleich unsicher (unlesbares Bild, andere
Grösse, cv2 fehlt), gilt das Bild als verändert. Das kostet dann einen Aufruf
-- also genau das, was vorher immer passiert ist. Ein übersehener Zug wäre
dagegen ein falsches Ergebnis auf dem Bildschirm.
"""

from __future__ import annotations

import logging
from typing import Optional

from services import umgebung

logger = logging.getLogger(__name__)

# Kantenlänge des Rasters. 32x32 = 1024 Zellen; bei 1280x720 deckt eine Zelle
# rund 40x22 Pixel ab. Eine Magic-Karte im Bild ist ein Vielfaches davon, eine
# Drehung verändert also sicher mehrere Zellen.
RASTER = 32

# Ab welcher Abweichung einer EINZELNEN Zelle (0-255) das Bild als verändert
# gilt. 12 liegt deutlich über dem, was Sensorrauschen und Autofokus erzeugen,
# und deutlich unter dem, was eine bewegte Karte auslöst.
STANDARD_SCHWELLE = 12.0

# Abschaltbar, falls sich der Vergleich im Betrieb als zu grob erweist.
AKTIV = umgebung.schalter("VISION_BILDVERGLEICH", True)
SCHWELLE = umgebung.zahl("VISION_BILDVERGLEICH_SCHWELLE", STANDARD_SCHWELLE)


def signatur(jpeg_bytes: bytes):
    """Verkleinertes Graustufenraster des Bildes, oder None.

    None heisst "nicht vergleichbar" -- der Aufrufer behandelt das wie
    "verändert" und fragt.
    """
    if not jpeg_bytes:
        return None
    try:
        import cv2
        import numpy as np

        puffer = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        bild = cv2.imdecode(puffer, cv2.IMREAD_GRAYSCALE)
        if bild is None or bild.size == 0:
            return None
        # INTER_AREA mittelt beim Verkleinern über die Fläche und dämpft damit
        # das Rauschen einzelner Pixel -- genau das, was hier stören würde.
        klein = cv2.resize(bild, (RASTER, RASTER), interpolation=cv2.INTER_AREA)
        return klein.astype("float32")
    except Exception:
        logger.debug("Bildsignatur nicht berechenbar", exc_info=True)
        return None


def unveraendert(vorher, nachher, schwelle: Optional[float] = None) -> bool:
    """Ob sich zwischen zwei Signaturen praktisch nichts getan hat.

    Betrachtet wird die grösste Abweichung einer einzelnen Rasterzelle, nicht
    der Durchschnitt: Eine einzelne gedrehte Karte würde im Mittelwert
    untergehen, und genau die soll auffallen.
    """
    if vorher is None or nachher is None:
        return False
    if getattr(vorher, "shape", None) != getattr(nachher, "shape", None):
        return False

    grenze = SCHWELLE if schwelle is None else schwelle
    try:
        import numpy as np

        return float(np.max(np.abs(vorher - nachher))) <= grenze
    except Exception:
        logger.debug("Bildvergleich fehlgeschlagen", exc_info=True)
        return False
