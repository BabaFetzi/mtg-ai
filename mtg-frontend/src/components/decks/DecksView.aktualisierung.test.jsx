import { deckAenderung } from './DecksView';

// Gemeldet: "Wenn ich was im Deck ändere, muss ich zuerst in ein anderes Menü
// wechseln, bevor ich auf Analyse gehen kann und die Änderungen übernommen
// werden."
//
// Ursache: das ausgewählte Deck wurde nur ersetzt, wenn sich die Deck-ID
// änderte. Nach dem Bearbeiten kam dieselbe ID mit neuer Kartenliste zurück --
// und wurde verworfen. Analyse, Farbquellen und Sammlungsabgleich rechneten
// weiter auf dem alten Text.

const DECK = { id: 7, name: 'Krenko', liste: '4 Lightning Bolt\n56 Mountain', format: 'standard' };

test('geänderte Kartenliste bei gleicher ID wird übernommen', () => {
  const bearbeitet = { ...DECK, liste: '4 Lightning Bolt\n20 Island\n36 Mountain' };
  const { anderesDeck, listeGeaendert } = deckAenderung(DECK, bearbeitet);

  expect(listeGeaendert).toBe(true);
  expect(anderesDeck).toBe(false);
});

test('unveränderte Liste löst kein Neuladen aus', () => {
  const { anderesDeck, listeGeaendert } = deckAenderung(DECK, { ...DECK });

  expect(anderesDeck).toBe(false);
  expect(listeGeaendert).toBe(false);
});

test('anderes Deck wird als Deckwechsel erkannt', () => {
  const anderes = { id: 8, name: 'Mono Blue', liste: '60 Island', format: 'standard' };
  const { anderesDeck, listeGeaendert } = deckAenderung(DECK, anderes);

  expect(anderesDeck).toBe(true);
  // Beim Wechsel ist die Liste zwangsläufig anders -- das ist kein
  // zusätzlicher Grund und würde sonst doppelt zurückgesetzt.
  expect(listeGeaendert).toBe(false);
});

test('ohne vorher ausgewähltes Deck ist es ein Deckwechsel', () => {
  expect(deckAenderung(null, DECK)).toEqual({ anderesDeck: true, listeGeaendert: false });
});

test('ID als Zahl und als Text gelten als dasselbe Deck', () => {
  // Die Liste kommt aus JSON, der Parameter aus der Adresszeile.
  const { anderesDeck } = deckAenderung({ ...DECK, id: '7' }, DECK);
  expect(anderesDeck).toBe(false);
});

test('fehlende Liste wird wie eine leere behandelt', () => {
  const ohne = { id: 7, name: 'Krenko', format: 'standard' };
  expect(deckAenderung(ohne, { ...ohne, liste: null }).listeGeaendert).toBe(false);
  expect(deckAenderung(ohne, { ...ohne, liste: '1 Sol Ring' }).listeGeaendert).toBe(true);
});
