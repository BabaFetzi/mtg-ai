import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MeldungProvider, useMeldung } from './Meldungen';

// Ersetzt 63 alert()- und einen confirm()-Aufruf. Die nativen Dialoge
// blockieren die Seite, lassen sich nicht gestalten und zeigen auf dem Handy
// die technische Herkunftsadresse an ("localhost:5175 sagt:").

function Testfläche() {
  const { melde, bestaetige } = useMeldung();
  return (
    <div>
      <button onClick={() => melde.erfolg('Deck gespeichert.')}>erfolg</button>
      <button onClick={() => melde.fehler('Speichern fehlgeschlagen.')}>fehler</button>
      <button onClick={() => melde.info('Import läuft…')}>info</button>
      <button
        onClick={async () => {
          const ja = await bestaetige({ titel: 'Deck löschen?', text: 'Das lässt sich nicht rückgängig machen.' });
          melde.info(ja ? 'bestätigt' : 'abgebrochen');
        }}
      >
        fragen
      </button>
    </div>
  );
}

const rendere = () =>
  render(<MeldungProvider><Testfläche /></MeldungProvider>);

describe('Meldungen', () => {
  test('zeigt eine Erfolgsmeldung an', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'erfolg' }));
    expect(await screen.findByText('Deck gespeichert.')).toBeInTheDocument();
  });

  test('mehrere Meldungen stehen nebeneinander, statt sich zu verdrängen', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'erfolg' }));
    await user.click(screen.getByRole('button', { name: 'fehler' }));
    expect(screen.getByText('Deck gespeichert.')).toBeInTheDocument();
    expect(screen.getByText('Speichern fehlgeschlagen.')).toBeInTheDocument();
  });

  test('lässt sich von Hand schliessen', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'info' }));
    expect(await screen.findByText('Import läuft…')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Meldung schliessen' }));
    await waitFor(() => expect(screen.queryByText('Import läuft…')).not.toBeInTheDocument());
  });

  test('ist für Screenreader lesbar, ohne den Nutzer zu unterbrechen', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'erfolg' }));
    const bereich = await screen.findByRole('status');
    // "polite" statt "assertive": die Meldung wird vorgelesen, unterbricht aber
    // keinen laufenden Satz.
    expect(bereich).toHaveAttribute('aria-live', 'polite');
  });
});

describe('Rückfrage', () => {
  test('liefert true beim Bestätigen', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'fragen' }));

    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText('Deck löschen?')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Ja, weiter' }));
    expect(await screen.findByText('bestätigt')).toBeInTheDocument();
  });

  test('liefert false beim Abbrechen', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'fragen' }));
    await user.click(screen.getByRole('button', { name: 'Abbrechen' }));
    expect(await screen.findByText('abgebrochen')).toBeInTheDocument();
  });

  test('Escape bricht ab -- wie bei einem nativen Dialog erwartet', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'fragen' }));
    await screen.findByRole('alertdialog');

    await user.keyboard('{Escape}');
    expect(await screen.findByText('abgebrochen')).toBeInTheDocument();
  });

  test('blockiert die Seite nicht: der Dialog verschwindet nach der Antwort', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'fragen' }));
    await user.click(await screen.findByRole('button', { name: 'Ja, weiter' }));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  });
});

// ======================================================================
// Sichtbarkeit -- das eigentliche Versagen
// ======================================================================
// Die Tests oben fanden Dialog und Meldungen ueber Rolle und Text. Beides war
// im DOM, beide Tests gruen -- und trotzdem hat kein Nutzer je eine Rueckfrage
// gesehen. Die Gestaltung hing an CSS-Klassen (.rueckfrage-hintergrund,
// .meldungs-liste), die es in keiner Stilvorlage gab: im ausgelieferten Paket
// null Treffer. Die Rueckfrage erschien deshalb als schmuckloses <div> am Ende
// der Seite, weit unterhalb des Bildschirms.
//
// Fuer den Nutzer sah das so aus, als taete der Knopf nichts. Betroffen war
// jede Rueckfrage der Anwendung -- auch "Konto endgueltig loeschen" und
// "Premium-Abo kuendigen".
//
// Deshalb pruefen diese Tests nicht mehr nur, DASS etwas da ist, sondern dass
// es auch obenauf liegt. Moeglich ist das nur, weil die Werte jetzt inline am
// Element stehen: die Tests laufen mit css:false, eine ausgelagerte
// Stilvorlage waere hier unsichtbar.

describe('Sichtbarkeit', () => {
  test('die Rueckfrage liegt als Ueberlagerung ueber der Seite', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'fragen' }));

    const hintergrund = await screen.findByTestId('rueckfrage-hintergrund');

    // Ohne feste Position steht der Dialog dort, wo er im DOM haengt --
    // also ganz unten und ausserhalb des Sichtbereichs.
    expect(hintergrund.style.position).toBe('fixed');
    // Ohne z-index verschwindet er hinter Kartenvorschauen (z-index 1000)
    // und anderen Ueberlagerungen.
    expect(Number(hintergrund.style.zIndex)).toBeGreaterThan(1000);
  });

  test('die Rueckfrage hat einen sichtbaren Hintergrund', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'fragen' }));

    const hintergrund = await screen.findByTestId('rueckfrage-hintergrund');

    // Der abgedunkelte Hintergrund macht die Rueckfrage als solche erkennbar
    // und trennt sie von der Seite darunter.
    expect(hintergrund.style.background).toContain('rgba');
  });

  test('die Meldungsleiste liegt fest oben, nicht im Seitenfluss', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'erfolg' }));

    const leiste = await screen.findByRole('status');

    expect(leiste.style.position).toBe('fixed');
    expect(Number(leiste.style.zIndex)).toBeGreaterThan(1000);
  });

  test('die Leiste faengt keine Klicks ab, die Meldung selbst schon', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'erfolg' }));

    const leiste = await screen.findByRole('status');
    // Eine fest positionierte Leiste ueber der halben Seite wuerde sonst
    // Klicks auf alles darunter schlucken.
    expect(leiste.style.pointerEvents).toBe('none');
    expect(leiste.firstChild.style.pointerEvents).toBe('auto');
  });

  test('Fehler und Erfolg sind auch ohne Text zu unterscheiden', async () => {
    const user = userEvent.setup();
    rendere();
    await user.click(screen.getByRole('button', { name: 'erfolg' }));
    await user.click(screen.getByRole('button', { name: 'fehler' }));

    const leiste = await screen.findByRole('status');
    const arten = [...leiste.children].map((k) => k.dataset.art);
    expect(arten).toEqual(['erfolg', 'fehler']);

    const raender = [...leiste.children].map((k) => k.style.borderLeftColor);
    expect(raender[0]).not.toBe(raender[1]);
  });

  test('kein einziger Klassenname mehr, der ins Leere zeigt', async () => {
    // Die Ursache in einem Satz: Klassennamen ohne Stilvorlage. Solange hier
    // keine stehen, kann der Fehler nicht auf demselben Weg zurueckkommen.
    const { readFileSync } = await import('node:fs');
    // Ueber das Arbeitsverzeichnis statt ueber import.meta.url: unter vitest
    // ist das keine file:-Adresse, fileURLToPath scheitert daran.
    const text = readFileSync('src/components/layout/Meldungen.jsx', 'utf-8');

    const klassen = text.match(/className=/g) || [];
    expect(klassen.length).toBe(0);
  });
});
