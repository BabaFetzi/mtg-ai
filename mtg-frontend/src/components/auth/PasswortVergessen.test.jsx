import { MemoryRouter } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AuthScreen from './AuthScreen';
import PasswortNeu from './PasswortNeu';

// Vor dieser Ergänzung gab es keinen Weg zurück ins eigene Konto: Wer sein
// Passwort vergass, verlor seine Sammlung.

function rendereAuth() {
  render(<MemoryRouter><AuthScreen onLoginSuccess={vi.fn()} /></MemoryRouter>);
}

describe('AuthScreen – Passwort vergessen', () => {
  test('der Weg ist von der Anmeldung aus erreichbar', async () => {
    const user = userEvent.setup();
    rendereAuth();

    await user.click(screen.getByRole('button', { name: /Passwort vergessen/ }));

    expect(screen.getByText('Passwort zurücksetzen.')).toBeInTheDocument();
    // Im Vergessen-Modus darf kein Passwortfeld stehen.
    expect(screen.queryByPlaceholderText('Passwort')).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText('Benutzername oder E-Mail')).toBeInTheDocument();
  });

  test('zeigt den Hinweis des Servers und verrät nicht, ob das Konto existiert', async () => {
    const user = userEvent.setup();
    const hinweis = 'Falls ein Konto zu dieser Angabe existiert, haben wir eine E-Mail verschickt.';
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: async () => ({ erfolg: true, hinweis }) })
    );
    rendereAuth();

    await user.click(screen.getByRole('button', { name: /Passwort vergessen/ }));
    await user.type(screen.getByPlaceholderText('Benutzername oder E-Mail'), 'anna');
    await user.click(screen.getByRole('button', { name: 'Link anfordern' }));

    expect(await screen.findByText(hinweis)).toBeInTheDocument();
    // Als Statusmeldung, nicht als Fehler.
    expect(screen.getByRole('status')).toHaveTextContent(hinweis);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    const [url, optionen] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/passwort/vergessen');
    expect(JSON.parse(optionen.body)).toEqual({ kennung: 'anna' });
  });

  test('Textlinks sind echte Schaltflächen und damit per Tastatur erreichbar', () => {
    rendereAuth();
    // Vorher waren das <span onClick> -- unsichtbar für Screenreader.
    expect(screen.getByRole('button', { name: /Passwort vergessen/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Konto erstellen' })).toBeInTheDocument();
  });
});

describe('PasswortNeu', () => {
  const rendereMitToken = (suche) =>
    render(<MemoryRouter initialEntries={[`/passwort-neu${suche}`]}><PasswortNeu /></MemoryRouter>);

  test('ohne Token wird gar kein Formular angeboten', () => {
    rendereMitToken('');
    expect(screen.getByText('Link unvollständig')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /speichern/i })).not.toBeInTheDocument();
  });

  test('zu kurzes Passwort wird ohne Netzaufruf abgefangen', async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn();
    rendereMitToken('?token=abc123');

    await user.type(screen.getByLabelText('Neues Passwort'), 'kurz');
    await user.type(screen.getByLabelText('Neues Passwort wiederholen'), 'kurz');
    await user.click(screen.getByRole('button', { name: 'Passwort speichern' }));

    expect(screen.getByRole('alert')).toHaveTextContent(/mindestens 8 Zeichen/);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('abweichende Wiederholung wird abgefangen', async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn();
    rendereMitToken('?token=abc123');

    await user.type(screen.getByLabelText('Neues Passwort'), 'LangGenug123');
    await user.type(screen.getByLabelText('Neues Passwort wiederholen'), 'LangGenug999');
    await user.click(screen.getByRole('button', { name: 'Passwort speichern' }));

    expect(screen.getByRole('alert')).toHaveTextContent(/stimmen nicht überein/);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('erfolgreicher Ablauf sendet das Token mit und bestätigt', async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: async () => ({ erfolg: true }) })
    );
    rendereMitToken('?token=abc123');

    await user.type(screen.getByLabelText('Neues Passwort'), 'LangGenug123');
    await user.type(screen.getByLabelText('Neues Passwort wiederholen'), 'LangGenug123');
    await user.click(screen.getByRole('button', { name: 'Passwort speichern' }));

    expect(await screen.findByText('Passwort geändert')).toBeInTheDocument();
    const [url, optionen] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/passwort/zuruecksetzen');
    expect(JSON.parse(optionen.body)).toEqual({ token: 'abc123', neues_passwort: 'LangGenug123' });
  });

  test('abgelaufener Link erklärt, was zu tun ist', async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 400, json: async () => ({ detail: 'Dieser Link ist nicht mehr gültig. Fordere bitte einen neuen an.' }) })
    );
    rendereMitToken('?token=alt');

    await user.type(screen.getByLabelText('Neues Passwort'), 'LangGenug123');
    await user.type(screen.getByLabelText('Neues Passwort wiederholen'), 'LangGenug123');
    await user.click(screen.getByRole('button', { name: 'Passwort speichern' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/nicht mehr gültig/);
  });
});
