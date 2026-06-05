"""
services/combos.py – Lokale Datenbank & Detektor für bekannte MTG-Kombinationen
"""

from typing import List, Dict, Any
from services.scryfall import parse_decklist

KNOWN_COMBOS = [
    {
        "cards": {"thassa's oracle", "demonic consultation"},
        "name": "Thassa's Oracle + Demonic Consultation",
        "grund": "Exiliere deine gesamte Bibliothek für 1 schwarzes Mana und gewinne das Spiel auf der Stelle durch den ETB-Trigger von Thassa's Oracle."
    },
    {
        "cards": {"thassa's oracle", "tainted pact"},
        "name": "Thassa's Oracle + Tainted Pact",
        "grund": "Exiliere deine gesamte Bibliothek mit Tainted Pact (falls dein Deck keine doppelten Standardländer enthält) und gewinne mit Thassa's Oracle."
    },
    {
        "cards": {"kiki-jiki, mirror breaker", "zealous conscripts"},
        "name": "Kiki-Jiki + Zealous Conscripts",
        "grund": "Erzeuge unendlich viele Eile-Kopien von Zealous Conscripts, die bei ihrem ETB wiederum Kiki-Jiki enttappen. Infinite Damage."
    },
    {
        "cards": {"kiki-jiki, mirror breaker", "pestermite"},
        "name": "Kiki-Jiki + Pestermite",
        "grund": "Erzeuge unendlich viele fliegende Eile-Kopien von Pestermite, die bei ihrem ETB wiederum Kiki-Jiki enttappen. Infinite Damage."
    },
    {
        "cards": {"kiki-jiki, mirror breaker", "deceiver exarch"},
        "name": "Kiki-Jiki + Deceiver Exarch",
        "grund": "Erzeuge unendlich viele Eile-Kopien von Deceiver Exarch, die bei ihrem ETB wiederum Kiki-Jiki enttappen. Infinite Damage."
    },
    {
        "cards": {"godo, bandit warlord", "helm of the host"},
        "name": "Godo, Bandit Warlord + Helm of the Host",
        "grund": "Godo sucht beim Eintritt ins Spiel den Helm des Wirts und rüstet ihn aus. In jeder zusätzlichen Kampfphase erzeugt der Helm eine neue Eile-Kopie von Godo für unendlich viele Angriffe."
    },
    {
        "cards": {"heliod, sun-crowned", "walking ballista"},
        "name": "Heliod, Sun-Crowned + Walking Ballista",
        "grund": "Verleihe Walking Ballista Lebensverknüpfung durch Heliod. Jede abgezogene +1/+1 Marke schießt 1 Schaden, heilt dich und erzeugt eine neue Marke für unendlich viel Schaden."
    },
    {
        "cards": {"sanguine bond", "exquisite blood"},
        "name": "Sanguine Bond + Exquisite Blood",
        "grund": "Sobald ein Gegner Schaden erleidet oder du Leben erhältst, startet eine Endlosschleife, die allen Gegnern sämtliche Lebenspunkte entzieht."
    },
    {
        "cards": {"devoted druid", "swift reconfiguration"},
        "name": "Devoted Druid + Swift Reconfiguration",
        "grund": "Verwandelt Devoted Druid in ein Fahrzeug. Da sie keine Kreatur mehr ist, stirbt sie nicht an -1/-1 Marken und generiert unendlich viel grünes Mana."
    },
    {
        "cards": {"devoted druid", "vizier of remedies"},
        "name": "Devoted Druid + Vizier of Remedies",
        "grund": "Vizier of Remedies verhindert, dass -1/-1 Marken auf Devoted Druid gelegt werden, wodurch sie unendlich oft für grünes Mana enttappt werden kann."
    },
    {
        "cards": {"painter's servant", "grindstone"},
        "name": "Painter's Servant + Grindstone",
        "grund": "Painter's Servant macht alle Karten im Spiel und in Bibliotheken zu einer Farbe. Aktiviere Grindstone, um die gesamte Bibliothek eines Gegners in den Friedhof zu legen."
    },
    {
        "cards": {"underworld breach", "lion's eye diamond", "brain freeze"},
        "name": "Underworld Breach + Lion's Eye Diamond + Brain Freeze",
        "grund": "Mühle dich selbst mit Brain Freeze, bringe LED per Breach-Escape zurück, opfere für Mana, und wiederhole das Ganze für unendlich viel Storm-Count und Mill."
    },
    {
        "cards": {"sensei's divining top", "aetherflux reservoir", "bolas's citadel"},
        "name": "Sensei's Divining Top + Aetherflux Reservoir + Bolas's Citadel",
        "grund": "Ziehe eine Karte mit Sensei's Top, spiele sie umsonst von oben mit Bolas's Citadel. Aetherflux Reservoir generiert dabei unendlich viel Leben, um das Spiel zu beenden."
    }
]

def detect_local_combos(karten_liste: str) -> List[Dict[str, str]]:
    """
    Parst die Kartenliste und prüft, ob bekannte Combos vorliegen.
    Gibt eine Liste von Dictionaries mit 'name' und 'grund' zurück.
    """
    if not karten_liste or not karten_liste.strip():
        return []
    
    parsed = parse_decklist(karten_liste)
    deck_card_names = {c["name"].lower().strip() for c in parsed if c.get("name")}
    
    found = []
    for combo in KNOWN_COMBOS:
        if combo["cards"].issubset(deck_card_names):
            found.append({
                "name": combo["name"],
                "grund": combo["grund"]
            })
    return found
