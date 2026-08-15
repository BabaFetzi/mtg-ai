import { render, screen } from '@testing-library/react';
import SammlungsAbgleich from './SammlungsAbgleich';

// Fachlicher Zweck: "Was aus diesem Deck habe ich schon, was muss ich noch
// kaufen?" -- die Anzeige muss beide Zahlen nennen und darf Standardländer
// nicht in den Betrag einrechnen.

const BOLT = { name: 'Lightning Bolt', benoetigt: 4, vorhanden: 2, fehlt: 2, preis: '3.00', standardland: false, gefunden: true };
const SOL = { name: 'Sol Ring', benoetigt: 1, vorhanden: 1, fehlt: 0, preis: '1.50', standardland: false, gefunden: true };
const BERG = { name: 'Mountain', benoetigt: 24, vorhanden: 0, fehlt: 24, preis: '0.10', standardland: true, gefunden: true };

test('während des Ladens steht eine Rückmeldung da', () => {
  render(<SammlungsAbgleich daten={null} laedt />);
  expect(screen.getByText(/Sammlung wird abgeglichen/)).toBeInTheDocument();
});

test('ohne Daten wird nichts angezeigt', () => {
  const { container } = render(<SammlungsAbgleich daten={null} />);
  expect(container).toBeEmptyDOMElement();
});

test('fehlende Karten werden mit Anzahl und Preis genannt', () => {
  render(<SammlungsAbgleich daten={{
    karten: [BOLT, SOL], benoetigt: 5, vorhanden: 3, fehlend: 2,
    standardlaender_fehlend: 0, fehlender_wert: '6.00',
  }} />);

  expect(screen.getByText('3 von 5 Karten vorhanden')).toBeInTheDocument();
  expect(screen.getByText(/Karten fehlen/)).toBeInTheDocument();
  expect(screen.getByText('6,00 €')).toBeInTheDocument();
  expect(screen.getByText('Lightning Bolt')).toBeInTheDocument();
  // Vollständig vorhandene Karten sind kein Handlungsbedarf und stehen nicht
  // in der Liste.
  expect(screen.queryByText('Sol Ring')).not.toBeInTheDocument();
});

test('Standardländer stehen separat und nicht im Betrag', () => {
  render(<SammlungsAbgleich daten={{
    karten: [BOLT, BERG], benoetigt: 28, vorhanden: 2, fehlend: 2,
    standardlaender_fehlend: 24, fehlender_wert: '6.00',
  }} />);

  expect(screen.getByText(/24 Standardländer, die hier nicht mitgerechnet sind/)).toBeInTheDocument();
  expect(screen.queryByText('Mountain')).not.toBeInTheDocument();
});

test('vollständiges Deck wird als solches gemeldet', () => {
  render(<SammlungsAbgleich daten={{
    karten: [SOL], benoetigt: 1, vorhanden: 1, fehlend: 0,
    standardlaender_fehlend: 0, fehlender_wert: '0.00',
  }} />);

  expect(screen.getByText('Du besitzt alle Karten dieses Decks.')).toBeInTheDocument();
});
