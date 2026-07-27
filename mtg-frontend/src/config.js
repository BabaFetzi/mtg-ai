// ============================================================================
// config.js – Zentrale Feature-Schalter (Launch-Steuerung)
//
// Ein Ort, um noch nicht startbereite Funktionen aus der Live-Seite
// auszublenden, ohne Code zu entfernen. Zum Wieder-Aktivieren einfach den
// jeweiligen Wert auf `true` setzen -- Menüpunkt und Routen erscheinen dann
// automatisch wieder.
// ============================================================================

export const FEATURES = {
  // Live-Playfield (Kamera-Erkennung des Spielfelds).
  // Fürs erste Launch bewusst PAUSIERT: hängt an Kamera/HTTPS + KI-Kosten und
  // wird erst weitergebaut, wenn der Rest der Seite live und stabil ist.
  // -> auf `true` setzen, um es zurückzuholen.
  livePlayfield: false,
};
