/**
 * Wie viele Exemplare eine Auswahl wirklich umfasst.
 *
 * Steht bewusst ausserhalb von DecksView: Die Zahl landet in der Rückfrage
 * ("3 Exemplare werden angelegt"), und sie MUSS mit dem übereinstimmen, was
 * der Knopf anbietet und der Server hinterher anlegt. Weichen sie ab, bestätigt
 * jemand etwas anderes, als danach passiert -- und merkt es nicht.
 *
 * Genau das war passiert: Die Auswahlliste enthält zwei Formen,
 *
 *     "Sol Ring"                       -> alles, was von der Karte fehlt
 *     { name: "Bolt", anzahl: 2 }      -> genau so viele
 *
 * und die Zählung suchte nur mit includes(name). Die zweite Form fiel damit
 * heraus: Der Knopf bot 3 Exemplare an, die Rückfrage kündigte 1 an, angelegt
 * wurden 3. Aufgefallen ist das erst im Browser, nicht in den Tests.
 */
export function zaehleAuswahl(nurKarten, karten, fehlendGesamt) {
  // Keine Liste heisst "alles, was fehlt" -- dann steht die Zahl schon fest.
  if (!Array.isArray(nurKarten)) return fehlendGesamt || 0;

  return nurKarten.reduce((summe, eintrag) => {
    const name = typeof eintrag === 'string' ? eintrag : eintrag?.name;
    const karte = (karten || []).find(
      (k) => k.name === name && !k.standardland && k.fehlt > 0);
    if (!karte) return summe;

    const gewuenscht = typeof eintrag === 'string' ? karte.fehlt : eintrag.anzahl;
    // Deckeln wie der Server: die Rückfrage darf nie mehr ankündigen, als
    // wirklich angelegt wird.
    return summe + Math.max(0, Math.min(karte.fehlt || 0, gewuenscht ?? karte.fehlt));
  }, 0);
}
