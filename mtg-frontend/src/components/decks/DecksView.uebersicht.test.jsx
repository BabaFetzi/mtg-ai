import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DecksView from './DecksView';

// Punkt 3 der Oberflächen-Überarbeitung: "Liste vor Formular".
// Vorher füllte "Neues Deck erstellen" den ersten Bildschirm, die eigenen Decks
// begannen erst darunter -- obwohl der übliche Zweck des Aufrufs das Öffnen
// eines vorhandenen Decks ist.

const DECKS = [
  { id: 1, name: 'Krenko Goblins', format: 'commander', card_count: 100 },
  { id: 2, name: 'Mono Blue Tempo', format: 'standard', card_count: 60 },
];

function mockFetch(decks = DECKS) {
  global.fetch = vi.fn((url) => {
    if (typeof url === 'string' && url.startsWith('/api/decks/')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => decks });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
  });
}

function zeigeUebersicht(pfad = '/decks?tab=overview', decks = DECKS) {
  mockFetch(decks);
  render(
    <MemoryRouter initialEntries={[pfad]}>
      <DecksView currentUser="tester" userRole="premium" />
    </MemoryRouter>
  );
}

describe('DecksView – Deck-Übersicht', () => {
  test('die Deckliste ist sofort da, das Anlageformular nicht', async () => {
    zeigeUebersicht();

    expect(await screen.findByText('Krenko Goblins')).toBeInTheDocument();
    expect(screen.getByText('Mono Blue Tempo')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Deckname...')).not.toBeInTheDocument();
  });

  test('"+ Neues Deck" klappt das Formular auf, "Abbrechen" wieder zu', async () => {
    const nutzer = userEvent.setup();
    zeigeUebersicht();

    await nutzer.click(await screen.findByRole('button', { name: '+ Neues Deck' }));
    expect(await screen.findByPlaceholderText('Deckname...')).toBeInTheDocument();

    await nutzer.click(screen.getByRole('button', { name: 'Abbrechen' }));
    await waitFor(() => {
      expect(screen.queryByPlaceholderText('Deckname...')).not.toBeInTheDocument();
    });
  });

  test('?focus=create öffnet das Formular direkt', async () => {
    zeigeUebersicht('/decks?tab=overview&focus=create');

    expect(await screen.findByPlaceholderText('Deckname...')).toBeInTheDocument();
  });

  test('ohne Decks führt "Jetzt erstellen" zum aufgeklappten Namensfeld', async () => {
    const nutzer = userEvent.setup();
    zeigeUebersicht('/decks?tab=overview', []);

    await nutzer.click(await screen.findByRole('button', { name: 'Jetzt erstellen' }));
    expect(await screen.findByPlaceholderText('Deckname...')).toBeInTheDocument();
  });

  test('ohne Decks öffnet "Liste eintragen" dasselbe Formular mit dem Importfeld', async () => {
    const nutzer = userEvent.setup();
    zeigeUebersicht('/decks?tab=overview', []);

    await nutzer.click(await screen.findByRole('button', { name: 'Liste eintragen' }));
    expect(
      await screen.findByPlaceholderText(/Kopiere hier direkt eine komplette Deckliste/)
    ).toBeInTheDocument();
  });
});
