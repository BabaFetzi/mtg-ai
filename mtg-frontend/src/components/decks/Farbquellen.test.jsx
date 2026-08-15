import { render, screen } from '@testing-library/react';
import Farbquellen from './Farbquellen';

// Der fachliche Zweck: einem Deck sieht man nicht an, ob seine Länder zu den
// Farbanforderungen passen. Die Anzeige muss deshalb beides nennen -- den
// Bedarf und was fehlt -- und offenlegen, worauf die Zahl beruht.

const ROT_KNAPP = {
  farbe: 'R', farbname: 'Rot', laender: 12, weitere_quellen: 2,
  symbole_gesamt: 14, haertester_bedarf: 3, haerteste_karte: 'Goblin Chainwhirler',
  zug: 3, wahrscheinlichkeit: 0.412, empfohlene_laender: 22, fehlende_laender: 10,
  reicht: false,
};

const BLAU_OK = {
  farbe: 'U', farbname: 'Blau', laender: 24, weitere_quellen: 0,
  symbole_gesamt: 8, haertester_bedarf: 1, haerteste_karte: 'Negate',
  zug: 2, wahrscheinlichkeit: 0.964, empfohlene_laender: 15, fehlende_laender: 0,
  reicht: true,
};

function daten(farben, extra = {}) {
  return { deckgroesse: 60, laender_gesamt: 24, ziel: 0.9, farben, ...extra };
}

test('ohne Daten wird nichts angezeigt', () => {
  const { container } = render(<Farbquellen daten={null} />);
  expect(container).toBeEmptyDOMElement();
});

test('knappe Farbe wird benannt, mit Bedarf und Fehlbetrag', () => {
  render(<Farbquellen daten={daten([ROT_KNAPP, BLAU_OK])} />);

  expect(screen.getByText(/Eine Farbe hat zu wenige Quellen: Rot/)).toBeInTheDocument();
  expect(screen.getByText('10 zu wenig')).toBeInTheDocument();
  expect(screen.getByText('empfohlen: 22')).toBeInTheDocument();
  expect(screen.getByText(/3× Rot auf Zug 3 \(Goblin Chainwhirler\)/)).toBeInTheDocument();
  expect(screen.getByText(/41 % Chance/)).toBeInTheDocument();
});

test('Manasteine werden getrennt ausgewiesen', () => {
  // Sie liegen nicht von Anfang an im Spiel und dürfen die Rechnung nicht
  // beschönigen -- deshalb stehen sie daneben, nicht in der Länderzahl.
  render(<Farbquellen daten={daten([ROT_KNAPP])} />);

  expect(screen.getByText('12 Länder')).toBeInTheDocument();
  expect(screen.getByText('+ 2 weitere Quellen')).toBeInTheDocument();
});

test('passende Manabasis wird als solche gemeldet', () => {
  render(<Farbquellen daten={daten([BLAU_OK])} />);

  expect(screen.getByText(/Jede Farbe hat genug Quellen/)).toBeInTheDocument();
  expect(screen.getByText('reicht')).toBeInTheDocument();
});

test('die Annahme hinter der Zahl steht dabei', () => {
  render(<Farbquellen daten={daten([BLAU_OK])} />);

  expect(screen.getByText(/ohne Mulligan/)).toBeInTheDocument();
  expect(screen.getByText(/90 %/)).toBeInTheDocument();
});

test('nicht gefundene Karten werden genannt', () => {
  render(<Farbquellen daten={daten([BLAU_OK], { nicht_gefunden: ['Fantasiekarte'] })} />);

  expect(screen.getByText(/Nicht gefunden und daher nicht mitgerechnet: Fantasiekarte/)).toBeInTheDocument();
});
