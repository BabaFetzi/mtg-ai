import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import DecksView from './DecksView';

// Regression für den gemeldeten Bug: "Gimli, Counter of Kills" stand in einem
// STANDARD-Deck unter der Überschrift "Commander". Ursache war, dass jede
// legendäre Kreatur dorthin einsortiert wurde -- unabhängig vom Format.
// Standard, Modern, Pioneer, Legacy und Vintage kennen gar keinen Commander.

const GIMLI = {
  name: 'Gimli, Counter of Kills',
  type: 'Legendary Creature — Dwarf Warrior',
  image: 'https://example.invalid/gimli.jpg',
  cmc: 4,
};

function mockFetch(deck) {
  global.fetch = vi.fn((url) => {
    if (typeof url === 'string' && url.startsWith('/api/decks/')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => [deck] });
    }
    if (url === '/api/deck/visualize') {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ karten: [GIMLI] }) });
    }
    if (url === '/api/deck/stats') {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ cmc: { 4: 1 }, colors: {} }) });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
  });
}

function renderDeckliste(format) {
  mockFetch({ id: 1, name: 'Hobbit', liste: '1 Gimli, Counter of Kills', format });
  render(
    <MemoryRouter initialEntries={['/decks?tab=visual&deckId=1']}>
      <DecksView currentUser="tester" userRole="premium" />
    </MemoryRouter>
  );
}

describe('DecksView – Commander-Gruppe', () => {
  test('Standard-Deck: legendäre Kreatur steht bei den Kreaturen, nicht unter Commander', async () => {
    renderDeckliste('standard');

    expect(await screen.findByText(/Gimli, Counter of Kills/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Kreaturen')).toBeInTheDocument();
    });
    expect(screen.queryByText('Commander')).not.toBeInTheDocument();
  });

  test('Commander-Deck: dieselbe Karte steht weiterhin unter Commander', async () => {
    renderDeckliste('commander');

    expect(await screen.findByText(/Gimli, Counter of Kills/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Commander')).toBeInTheDocument();
    });
    expect(screen.queryByText('Kreaturen')).not.toBeInTheDocument();
  });
});
