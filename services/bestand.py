"""services/bestand.py -- Deckliste gegen den eigenen Bestand.

Zwei Stellen brauchen dieselbe Rechnung: die Anzeige "was fehlt dir noch" und
der Knopf "fehlende Karten in die Sammlung übernehmen". Liefen sie
auseinander, würde der Knopf etwas anderes hinzufügen, als danebensteht --
deshalb steht die Rechnung genau einmal hier.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from format_engine import BASIC_LANDS


def schluessel(name: str) -> str:
    """Vergleichsform eines Kartennamens.

    Doppelseitige Karten stehen in der Sammlung mal als "Vorderseite" und mal
    als "Vorderseite // Rückseite". Ohne diese Angleichung gilt dieselbe Karte
    als nicht vorhanden.
    """
    name = (name or "").strip().lower()
    return name.split("//")[0].strip()


def bestand_aus_zeilen(zeilen: Iterable[Any]) -> Dict[str, int]:
    """Zählt den Bestand aus Zeilen mit `karten_name` und `anzahl`.

    Jede Zeile in `sammlung_alben` ist genau ein physisches Exemplar; die
    Spalte `anzahl` wird von den Inserts nie gefüllt, gezählt wird deshalb per
    COUNT in der Abfrage.
    """
    bestand: Dict[str, int] = {}
    for zeile in zeilen:
        k = schluessel(zeile["karten_name"])
        bestand[k] = bestand.get(k, 0) + int(zeile["anzahl"] or 0)
    return bestand


def bedarf_aus_deck(parsed: Iterable[Dict[str, Any]],
                    scryfall_data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Fasst die Deckliste zu einem Bedarf je Karte zusammen.

    Dieselbe Karte kann mehrfach in der Liste stehen (Hauptdeck und Sideboard);
    gebraucht wird die Summe -- physisch braucht man beide Exemplare.
    """
    bedarf: Dict[str, Dict[str, Any]] = {}
    for p in parsed:
        info = scryfall_data.get((p["name"] or "").lower().strip())
        anzeige = (info or {}).get("name") or p["name"]
        k = schluessel(anzeige)
        eintrag = bedarf.setdefault(k, {
            "name": anzeige,
            "benoetigt": 0,
            "bild": (info or {}).get("image", ""),
            "preis": (info or {}).get("price") or "0.00",
            "standardland": k in BASIC_LANDS,
            "gefunden": bool(info),
            "info": info,
        })
        eintrag["benoetigt"] += int(p["count"])
    return bedarf


def abgleichen(bedarf: Dict[str, Dict[str, Any]],
               bestand: Dict[str, int]) -> Dict[str, Any]:
    """Stellt Bedarf und Bestand gegenüber.

    Standardländer werden getrennt geführt: sie im Fehlbetrag mitzuzählen
    ("dir fehlen Karten im Wert von 2,40 Euro" für 24 Berge) wäre irreführend.
    """
    karten: List[Dict[str, Any]] = []
    fehlender_wert = 0.0
    fehlend_gesamt = 0
    standardlaender_fehlend = 0

    for k, eintrag in bedarf.items():
        vorhanden = min(bestand.get(k, 0), eintrag["benoetigt"])
        fehlt = eintrag["benoetigt"] - vorhanden
        if eintrag["standardland"]:
            standardlaender_fehlend += fehlt
        else:
            fehlend_gesamt += fehlt
            try:
                fehlender_wert += float(eintrag["preis"] or 0) * fehlt
            except (TypeError, ValueError):
                pass
        karten.append({**{s: w for s, w in eintrag.items() if s != "info"},
                       "vorhanden": vorhanden, "fehlt": fehlt})

    # Fehlendes zuerst, Standardländer ans Ende, innerhalb dessen nach Menge.
    karten.sort(key=lambda k: (k["fehlt"] == 0, k["standardland"], -k["fehlt"], k["name"]))

    return {
        "karten": karten,
        "benoetigt": sum(k["benoetigt"] for k in karten),
        "vorhanden": sum(k["vorhanden"] for k in karten),
        "fehlend": fehlend_gesamt,
        "standardlaender_fehlend": standardlaender_fehlend,
        "fehlender_wert": f"{fehlender_wert:.2f}",
    }


def fehlende_exemplare(bedarf: Dict[str, Dict[str, Any]],
                       bestand: Dict[str, int],
                       mit_standardlaendern: bool = False,
                       grenze: Optional[int] = None,
                       nur_namen: Optional[Iterable[str]] = None,
                       mengen: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Welche Exemplare müssten ergänzt werden, damit das Deck vollständig ist?

    Bewusst nur die FEHLENDEN: wird der Knopf zweimal gedrückt, ist beim
    zweiten Mal nichts mehr zu tun. Ein "alle Karten hinzufügen" würde die
    Sammlung bei jedem Druck verdoppeln.

    Args:
        nur_namen: Wenn angegeben, werden nur diese Karten berücksichtigt --
            für die Auswahl einzelner Karten in der Oberfläche.
        mengen: Wunschanzahl je Karte. Wer nur zwei von vier fehlenden
            Exemplaren gekauft hat, trägt hier 2 ein.

    Die Wunschanzahl wird nach OBEN gedeckelt: mehr als fehlt, wird nie
    angelegt. Weniger schon.

    Das ist die Eigenschaft, an der alles hängt. Ohne den Deckel könnte eine
    veränderte Anfrage beliebig viele Karten in eine Sammlung schreiben, und
    zweimal Drücken würde den Bestand verdoppeln. Mit dem Deckel bleibt beides
    unmöglich, und trotzdem lässt sich eine Teilmenge übernehmen -- beim
    nächsten Mal steht dann der Rest zur Auswahl.
    """
    posten: List[Dict[str, Any]] = []
    uebersprungene_laender = 0

    # Über schluessel() vergleichen, nicht über den rohen Namen: die Oberfläche
    # zeigt "Ashling, Rekindled // Ashling, Rimebound", in der Sammlung steht
    # womöglich nur die Vorderseite. Ein Vergleich Zeichen für Zeichen würde
    # genau die Karten übergehen, die man angekreuzt hat.
    auswahl = None if nur_namen is None else {schluessel(n) for n in nur_namen if n}
    gewuenscht = {schluessel(n): a for n, a in (mengen or {}).items() if n}

    for k, eintrag in sorted(bedarf.items(), key=lambda kv: kv[1]["name"]):
        fehlt = eintrag["benoetigt"] - min(bestand.get(k, 0), eintrag["benoetigt"])
        if fehlt <= 0:
            continue
        if auswahl is not None and k not in auswahl:
            continue

        wunsch = gewuenscht.get(k)
        if wunsch is not None:
            try:
                wunsch = int(wunsch)
            except (TypeError, ValueError):
                wunsch = None
        if wunsch is not None:
            # Der Deckel. Nach unten begrenzt auf 0, damit eine negative Zahl
            # aus einer veränderten Anfrage nicht plötzlich als "unendlich"
            # oder als Abzug wirkt.
            fehlt = max(0, min(fehlt, wunsch))
            if fehlt == 0:
                continue

        if eintrag["standardland"] and not mit_standardlaendern:
            uebersprungene_laender += fehlt
            continue
        posten.append({"name": eintrag["name"], "anzahl": fehlt, "info": eintrag["info"],
                       "preis": eintrag["preis"], "bild": eintrag["bild"]})

    gesamt = sum(p["anzahl"] for p in posten)
    abgeschnitten = 0
    if grenze is not None and gesamt > grenze:
        # Nicht stillschweigend abschneiden: die Zahl wird mitgeliefert und in
        # der Oberfläche genannt.
        gekuerzt: List[Dict[str, Any]] = []
        rest = grenze
        for p in posten:
            if rest <= 0:
                break
            nehmen = min(p["anzahl"], rest)
            gekuerzt.append({**p, "anzahl": nehmen})
            rest -= nehmen
        abgeschnitten = gesamt - grenze
        posten = gekuerzt
        gesamt = grenze

    return {
        "posten": posten,
        "gesamt": gesamt,
        "uebersprungene_standardlaender": uebersprungene_laender,
        "abgeschnitten": abgeschnitten,
    }
