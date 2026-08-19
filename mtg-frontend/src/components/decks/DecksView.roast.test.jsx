import { MemoryRouter } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DecksView from './DecksView';

const DECK = { id: 1, name: 'Testdeck', liste: '1 Sol Ring\n1 Lightning Bolt', format: 'commander' };

// Sehr gezielter fetch-Mock: liefert die Deckliste beim Mount und lässt
// /api/deck/roast konfigurierbar antworten -- alle anderen möglichen Aufrufe
// (es gibt für den "roast"-Tab keine weiteren) würden hier auffallen.
function mockFetch(roastResponse) {
  global.fetch = vi.fn((url) => {
    if (typeof url === 'string' && url.startsWith('/api/decks/')) {
      return Promise.resolve({ json: async () => [DECK] });
    }
    if (url === '/api/deck/roast') {
      return Promise.resolve({ json: async () => roastResponse });
    }
    // Die Ordnernamen holt DecksView beim Mount fuer die Zielauswahl im
    // Sammlungsabgleich. Fuer den Roast-Tab belanglos, aber der Aufruf
    // passiert -- und dieser Mock laesst bewusst nichts Unbekanntes durch.
    if (typeof url === 'string' && url.endsWith('/alben')) {
      return Promise.resolve({ json: async () => ({ erfolg: true, alben: [] }) });
    }
    throw new Error(`Unerwarteter fetch-Aufruf in diesem Test: ${url}`);
  });
}

function renderRoastTab({ userRole = 'premium', onShowPremiumModal } = {}) {
  render(
    <MemoryRouter initialEntries={['/decks?tab=roast&deckId=1']}>
      <DecksView currentUser="hovertest" userRole={userRole} onShowPremiumModal={onShowPremiumModal} />
    </MemoryRouter>
  );
}

describe('DecksView – Deck-Roast', () => {
  test('zeigt bei Erfolg Urteil, Roast-Text und Salt-Score aus der echten Antwort', async () => {
    const user = userEvent.setup();
    mockFetch({ verdict: 'Grausam.', roast: 'Dein Deck hat mehr Text als Wincons.', salt_score: 87 });
    renderRoastTab({ userRole: 'premium' });

    await user.click(await screen.findByRole('button', { name: /Deck-Roast starten/i }));

    expect(await screen.findByText(/Urteil: Grausam\./)).toBeInTheDocument();
    expect(screen.getByText(/Dein Deck hat mehr Text als Wincons\./)).toBeInTheDocument();
    expect(screen.getByText('87%')).toBeInTheDocument();
  });

  // Regression für den gemeldeten Bug: bei einer veralteten Rollenangabe im
  // Frontend (userRole="premium") kann der echte Request trotzdem durchgehen
  // und vom Backend die Paywall-Antwort (HTTP 200, {error: "paywall", ...})
  // zurückbekommen. Vorher landete die als "echte" Roast-Daten im State und
  // zeigte "Urteil: Autsch." mit einem leeren Zitat und einem erfundenen
  // 50%-Salt-Score an, statt eines klaren Hinweises.
  test('Paywall-Antwort erzeugt KEINE kaputten Fake-Daten, sondern das Premium-Upgrade-Modal', async () => {
    const user = userEvent.setup();
    const onShowPremiumModal = vi.fn();
    mockFetch({ error: 'paywall', message: 'Dieses Premium-Feature (KI-Deck-Roast) steht nur Premium-Mitgliedern zur Verfügung.' });
    renderRoastTab({ userRole: 'premium', onShowPremiumModal });

    await user.click(await screen.findByRole('button', { name: /Deck-Roast starten/i }));

    expect(onShowPremiumModal).toHaveBeenCalledTimes(1);
    // Der alte Bug in einem einzigen Satz: "Autsch." mit leerem Zitat und 50% Fake-Score.
    expect(screen.queryByText(/Urteil: Autsch\./)).not.toBeInTheDocument();
    expect(screen.queryByText('50%')).not.toBeInTheDocument();
    // State wurde zurückgesetzt -- der Start-Button ist wieder da, kein "Ergebnis".
    expect(await screen.findByRole('button', { name: /Deck-Roast starten/i })).toBeInTheDocument();
  });

  test('Free-Nutzer sieht das Premium-Overlay über dem Roast-Tab', async () => {
    renderRoastTab({ userRole: 'free' });

    expect(await screen.findByText('Premium Feature')).toBeInTheDocument();
    expect(screen.getByText('Deck-Roast & Kritik')).toBeInTheDocument();
  });
});
