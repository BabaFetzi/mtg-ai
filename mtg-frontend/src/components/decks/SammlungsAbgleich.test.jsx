import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
  expect(screen.getByText(/Exemplare fehlen/)).toBeInTheDocument();
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

test('der Übernahme-Knopf meldet die Auswahl nach oben', async () => {
  const nutzer = userEvent.setup();
  const uebernehmen = vi.fn();
  render(<SammlungsAbgleich
    daten={{ karten: [BOLT, BERG], benoetigt: 28, vorhanden: 2, fehlend: 2,
             standardlaender_fehlend: 24, fehlender_wert: '6.00' }}
    onUebernehmen={uebernehmen}
  />);

  await nutzer.click(screen.getByRole('button', { name: /Fehlende Karten in die Sammlung/ }));
  expect(uebernehmen).toHaveBeenCalledWith({ mitStandardlaendern: false, nurKarten: null });

  // Standardländer sind bewusst abgewählt -- wer sie will, hakt sie an.
  await nutzer.click(screen.getByLabelText(/Standardländer mit übernehmen/));
  await nutzer.click(screen.getByRole('button', { name: /Fehlende Karten in die Sammlung/ }));
  expect(uebernehmen).toHaveBeenLastCalledWith({ mitStandardlaendern: true, nurKarten: null });
});

test('während der Übernahme ist der Knopf gesperrt', () => {
  render(<SammlungsAbgleich
    daten={{ karten: [BOLT], benoetigt: 4, vorhanden: 2, fehlend: 2,
             standardlaender_fehlend: 0, fehlender_wert: '6.00' }}
    onUebernehmen={() => {}}
    uebernimmt
  />);

  expect(screen.getByRole('button', { name: /Wird übernommen/ })).toBeDisabled();
});

test('ohne fehlende Karten gibt es nichts zu übernehmen', () => {
  render(<SammlungsAbgleich
    daten={{ karten: [SOL], benoetigt: 1, vorhanden: 1, fehlend: 0,
             standardlaender_fehlend: 0, fehlender_wert: '0.00' }}
    onUebernehmen={() => {}}
  />);

  expect(screen.queryByRole('button', { name: /in die Sammlung/ })).not.toBeInTheDocument();
});

test('lange Fehlliste wird gekürzt und lässt sich aufklappen', async () => {
  const nutzer = userEvent.setup();
  const viele = Array.from({ length: 20 }, (_, i) => ({
    name: `Karte ${i + 1}`, benoetigt: 2, vorhanden: 0, fehlt: 2,
    preis: '1.00', standardland: false, gefunden: true,
  }));
  render(<SammlungsAbgleich daten={{
    karten: viele, benoetigt: 40, vorhanden: 0, fehlend: 40,
    standardlaender_fehlend: 0, fehlender_wert: '40.00',
  }} />);

  expect(screen.getByText('Karte 12')).toBeInTheDocument();
  expect(screen.queryByText('Karte 13')).not.toBeInTheDocument();

  await nutzer.click(screen.getByRole('button', { name: /Alle 20 fehlenden Karten anzeigen/ }));
  expect(screen.getByText('Karte 20')).toBeInTheDocument();
});

// ======================================================================
// Einzelne Karten auswaehlen
// ======================================================================
// Gewuenscht: "dass man die Karten auch einzeln auswaehlen kann, welche man in
// die Sammlung uebernehmen will."
//
// Gesammelt werden die ABGEWAEHLTEN, nicht die ausgewaehlten Karten: Der
// Normalfall ist "alles uebernehmen". Andersherum stuende man vor einer leeren
// Menge und muesste erst alles ankreuzen, bevor der Knopf etwas tut.

const ADLER = { name: 'Serra Angel', benoetigt: 3, vorhanden: 0, fehlt: 3, preis: '2.00', standardland: false, gefunden: true };

const AUSWAHL_DATEN = {
  karten: [BOLT, ADLER, BERG], benoetigt: 31, vorhanden: 2, fehlend: 5,
  standardlaender_fehlend: 24, fehlender_wert: '12.00',
};

function rendereAuswahl(uebernehmen = vi.fn()) {
  render(<SammlungsAbgleich daten={AUSWAHL_DATEN} onUebernehmen={uebernehmen} />);
  return uebernehmen;
}

test('zu Beginn sind alle fehlenden Karten ausgewaehlt', () => {
  rendereAuswahl();

  // Wer nichts anfasst und einfach drueckt, bekommt das bisherige Verhalten.
  for (const kaestchen of screen.getAllByRole('checkbox', { name: /Lightning Bolt|Serra Angel/ })) {
    expect(kaestchen).toBeChecked();
  }
});

test('ohne Auswahl wird KEINE Liste mitgeschickt', async () => {
  const nutzer = userEvent.setup();
  const uebernehmen = rendereAuswahl();

  await nutzer.click(screen.getByRole('button', { name: /in die Sammlung übernehmen/ }));

  // null statt einer Liste aller Namen: ohne Liste nimmt der Server, was
  // gerade fehlt. Hat sich die Sammlung zwischenzeitlich geaendert, stimmt
  // das -- eine mitgeschickte Liste waere dann veraltet.
  expect(uebernehmen).toHaveBeenCalledWith({ mitStandardlaendern: false, nurKarten: null });
});

test('eine abgewaehlte Karte wird nicht mitgeschickt', async () => {
  const nutzer = userEvent.setup();
  const uebernehmen = rendereAuswahl();

  await nutzer.click(screen.getByRole('checkbox', { name: /Lightning Bolt/ }));
  await nutzer.click(screen.getByRole('button', { name: /übernehmen/ }));

  expect(uebernehmen).toHaveBeenCalledWith({
    mitStandardlaendern: false, nurKarten: ['Serra Angel'],
  });
});

test('der Knopf nennt Anzahl und Preis der Auswahl', async () => {
  const nutzer = userEvent.setup();
  rendereAuswahl();

  await nutzer.click(screen.getByRole('checkbox', { name: /Lightning Bolt/ }));

  // Serra Angel: 3 fehlende Exemplare zu je 2.00 = 6,00 EUR.
  // Gezaehlt werden EXEMPLARE, nicht Kartennamen -- sonst stuende hier 1.
  expect(screen.getByRole('button', { name: /3 Exemplare übernehmen — 6,00/ })).toBeInTheDocument();
});

test('ist nichts ausgewaehlt, laesst sich nichts uebernehmen', async () => {
  const nutzer = userEvent.setup();
  rendereAuswahl();

  await nutzer.click(screen.getByRole('button', { name: 'Keine' }));

  // Ein Knopf, der nichts anlegen wuerde, muss gesperrt sein -- sonst
  // druecken und nichts passiert, genau der gemeldete Eindruck.
  expect(screen.getByRole('button', { name: /übernehmen/ })).toBeDisabled();
});

test('Standardlaender lassen sich auch ohne Kartenauswahl uebernehmen', async () => {
  const nutzer = userEvent.setup();
  rendereAuswahl();

  await nutzer.click(screen.getByRole('button', { name: 'Keine' }));
  await nutzer.click(screen.getByLabelText(/Standardländer mit übernehmen/));

  // Sie stehen nicht in der Liste und lassen sich deshalb nicht einzeln
  // abwaehlen -- fuer sie gilt nur das Haekchen unten.
  expect(screen.getByRole('button', { name: /übernehmen/ })).toBeEnabled();
});

test('"Alle auswaehlen" macht eine Abwahl rueckgaengig', async () => {
  const nutzer = userEvent.setup();
  const uebernehmen = rendereAuswahl();

  await nutzer.click(screen.getByRole('checkbox', { name: /Lightning Bolt/ }));
  await nutzer.click(screen.getByRole('button', { name: 'Alle auswählen' }));
  await nutzer.click(screen.getByRole('button', { name: /in die Sammlung übernehmen/ }));

  expect(uebernehmen).toHaveBeenCalledWith({ mitStandardlaendern: false, nurKarten: null });
});

test('vollstaendig vorhandene Karten bekommen kein Kaestchen', () => {
  render(<SammlungsAbgleich
    daten={{ karten: [BOLT, SOL], benoetigt: 5, vorhanden: 3, fehlend: 2,
             standardlaender_fehlend: 0, fehlender_wert: '6.00' }}
    onUebernehmen={vi.fn()}
  />);

  // Sol Ring fehlt nicht -- ein Haekchen ohne Wirkung waere irrefuehrend.
  expect(screen.queryByRole('checkbox', { name: /Sol Ring/ })).not.toBeInTheDocument();
});

test('ohne Uebernahme-Moeglichkeit gibt es auch keine Kaestchen', () => {
  render(<SammlungsAbgleich daten={AUSWAHL_DATEN} />);

  expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
});

test('Exemplare und verschiedene Karten werden auseinandergehalten', () => {
  rendereAuswahl();

  // Vorher stand oben "5 Karten fehlen" und darunter "Alle 2 fehlenden Karten
  // anzeigen" -- beides richtig, zusammen aber wie ein Widerspruch zu lesen.
  expect(screen.getByText(/5/)).toBeInTheDocument();
  expect(screen.getByText(/2 verschiedene Karten/)).toBeInTheDocument();
});
