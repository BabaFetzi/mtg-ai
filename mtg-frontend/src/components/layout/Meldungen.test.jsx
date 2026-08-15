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
