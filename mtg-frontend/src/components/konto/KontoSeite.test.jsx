import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import KontoSeite from './KontoSeite';
import MeldungProvider from '../layout/Meldungen';

// Zwei Rechte, die es bisher gar nicht gab: Daten mitnehmen (Artikel 20 DSGVO)
// und Konto löschen (Artikel 17). Beim Löschen zählt vor allem, dass es NICHT
// zu leicht geht -- eine über Jahre gepflegte Sammlung ist danach weg.

function zeigeSeite(props = {}) {
  render(
    <MeldungProvider>
      <KontoSeite currentUser="tester" {...props} />
    </MeldungProvider>
  );
}

beforeEach(() => {
  global.fetch = vi.fn(() => Promise.resolve({
    ok: true, status: 200,
    json: async () => ({ erfolg: true, geloescht: {}, abo_beendet: false, abo_hinweis: '' }),
    blob: async () => new Blob(['{}'], { type: 'application/json' }),
  }));
  global.URL.createObjectURL = vi.fn(() => 'blob:test');
  global.URL.revokeObjectURL = vi.fn();
});

test('der Export lädt die Daten herunter', async () => {
  const nutzer = userEvent.setup();
  zeigeSeite();

  await nutzer.click(screen.getByRole('button', { name: /Daten herunterladen/ }));

  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith('/api/konto/export');
  });
  expect(await screen.findByText(/Daten wurden heruntergeladen/)).toBeInTheDocument();
});

test('das Löschformular ist erst nach einem Zwischenschritt da', async () => {
  const nutzer = userEvent.setup();
  zeigeSeite();

  expect(screen.queryByLabelText(/Dein Passwort/)).not.toBeInTheDocument();

  await nutzer.click(screen.getByRole('button', { name: 'Konto löschen' }));
  expect(screen.getByLabelText(/Dein Passwort/)).toBeInTheDocument();
});

test('ohne Bestätigungswort wird nichts gesendet', async () => {
  const nutzer = userEvent.setup();
  zeigeSeite();

  await nutzer.click(screen.getByRole('button', { name: 'Konto löschen' }));
  await nutzer.type(screen.getByLabelText(/Dein Passwort/), 'geheim');
  await nutzer.click(screen.getByRole('button', { name: 'Endgültig löschen' }));

  expect(await screen.findByText(/LÖSCHEN eintippen/)).toBeInTheDocument();
  expect(global.fetch).not.toHaveBeenCalledWith('/api/konto/loeschen', expect.anything());
});

test('ohne Passwort wird nichts gesendet', async () => {
  const nutzer = userEvent.setup();
  zeigeSeite();

  await nutzer.click(screen.getByRole('button', { name: 'Konto löschen' }));
  await nutzer.type(screen.getByLabelText(/LÖSCHEN/), 'LÖSCHEN');
  await nutzer.click(screen.getByRole('button', { name: 'Endgültig löschen' }));

  expect(await screen.findByText(/Passwort ein/)).toBeInTheDocument();
});

test('mit Passwort, Wort und Rückfrage wird gelöscht und abgemeldet', async () => {
  const nutzer = userEvent.setup();
  const abgemeldet = vi.fn();
  zeigeSeite({ onAbgemeldet: abgemeldet });

  await nutzer.click(screen.getByRole('button', { name: 'Konto löschen' }));
  await nutzer.type(screen.getByLabelText(/Dein Passwort/), 'geheim');
  await nutzer.type(screen.getByLabelText(/LÖSCHEN/), 'löschen');
  await nutzer.click(screen.getByRole('button', { name: 'Endgültig löschen' }));

  // Letzte Rückfrage -- erst danach geht etwas an den Server.
  await nutzer.click(await screen.findByRole('button', { name: 'Ja, alles löschen' }));

  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith('/api/konto/loeschen', expect.objectContaining({
      method: 'POST',
    }));
  });
  await waitFor(() => expect(abgemeldet).toHaveBeenCalled());
});

test('die Rückfrage abzubrechen löscht nichts', async () => {
  const nutzer = userEvent.setup();
  const abgemeldet = vi.fn();
  zeigeSeite({ onAbgemeldet: abgemeldet });

  await nutzer.click(screen.getByRole('button', { name: 'Konto löschen' }));
  await nutzer.type(screen.getByLabelText(/Dein Passwort/), 'geheim');
  await nutzer.type(screen.getByLabelText(/LÖSCHEN/), 'LÖSCHEN');
  await nutzer.click(screen.getByRole('button', { name: 'Endgültig löschen' }));

  // Gezielt der Abbrechen-Knopf IM Dialog: das Formular darunter hat auch
  // einen, und beide sind gleichzeitig im DOM.
  const dialog = await screen.findByRole('alertdialog');
  await nutzer.click(within(dialog).getByRole('button', { name: 'Abbrechen' }));

  expect(global.fetch).not.toHaveBeenCalledWith('/api/konto/loeschen', expect.anything());
  expect(abgemeldet).not.toHaveBeenCalled();
});

test('ein falsches Passwort wird gemeldet und meldet nicht ab', async () => {
  const nutzer = userEvent.setup();
  const abgemeldet = vi.fn();
  global.fetch = vi.fn(() => Promise.resolve({
    ok: false, status: 403, json: async () => ({ detail: 'Passwort stimmt nicht.' }),
  }));
  zeigeSeite({ onAbgemeldet: abgemeldet });

  await nutzer.click(screen.getByRole('button', { name: 'Konto löschen' }));
  await nutzer.type(screen.getByLabelText(/Dein Passwort/), 'falsch');
  await nutzer.type(screen.getByLabelText(/LÖSCHEN/), 'LÖSCHEN');
  await nutzer.click(screen.getByRole('button', { name: 'Endgültig löschen' }));
  await nutzer.click(await screen.findByRole('button', { name: 'Ja, alles löschen' }));

  expect(await screen.findByText('Das Passwort stimmt nicht.')).toBeInTheDocument();
  expect(abgemeldet).not.toHaveBeenCalled();
});

test('die Folgen stehen auf der Seite, bevor man etwas anklickt', () => {
  zeigeSeite();

  expect(screen.getByText(/unwiderruflich gelöscht/)).toBeInTheDocument();
  expect(screen.getByText(/bezahlte Restlaufzeit verfällt/)).toBeInTheDocument();
});
