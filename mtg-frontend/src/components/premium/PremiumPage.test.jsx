import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PremiumPage from './PremiumPage';

function renderPremiumPage({ userRole, setUserRole = vi.fn() } = {}) {
  render(
    <MemoryRouter>
      <PremiumPage currentUser="hovertest" userRole={userRole} setUserRole={setUserRole} />
    </MemoryRouter>
  );
  return { setUserRole };
}

describe('PremiumPage – Status-Anzeige je nach Rolle', () => {
  beforeEach(() => {
    // usePremiumPrice() ruft beim Mount immer /api/checkout/price ab.
    global.fetch = vi.fn().mockResolvedValue({
      json: async () => ({ konfiguriert: true, betrag: 3.9, waehrung: 'CHF', intervall: 'month' }),
    });
    vi.spyOn(window, 'alert').mockImplementation(() => {});
    vi.spyOn(window, 'confirm').mockImplementation(() => true);
  });

  test('Free-Nutzer sieht "Aktueller Tarif" bei Free und den Abo-Button bei Pro, aber nicht "Premium Aktiv"', async () => {
    renderPremiumPage({ userRole: 'free' });

    expect(screen.getByRole('button', { name: 'Aktueller Tarif' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Jetzt abonnieren' })).toBeInTheDocument();
    expect(screen.queryByText('Premium Aktiv')).not.toBeInTheDocument();
  });

  test('Premium-Nutzer sieht "Premium Aktiv" und den Downgrade-Button, nicht den Abo-Button', async () => {
    renderPremiumPage({ userRole: 'premium' });

    expect(screen.getByText('Premium Aktiv')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Als Entwickler downgraden (Testen)' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Jetzt abonnieren' })).not.toBeInTheDocument();
    // Freier Tarif ist für einen Premium-Nutzer nicht "aktuell".
    expect(screen.getByRole('button', { name: 'Kostenloses Basis-Konto' })).toBeInTheDocument();
  });

  test('zeigt den echten, live von Stripe geladenen Preis an (kein fest einprogrammierter Wert)', async () => {
    renderPremiumPage({ userRole: 'free' });

    expect(await screen.findByText('3,90 CHF')).toBeInTheDocument();
  });

  test('Downgrade-Button: bei abgelaufener Session (401) erscheint ein klarer Re-Login-Hinweis, kein stiller Fehlschlag', async () => {
    const user = userEvent.setup();
    const { setUserRole } = renderPremiumPage({ userRole: 'premium' });

    // Der Preis-Fetch beim Mount läuft schon über den Default-Mock aus
    // beforeEach; hier nur den nächsten (Downgrade-)Aufruf gezielt auf 401 setzen.
    await screen.findByText('3,90 CHF');

    global.fetch.mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) });

    await user.click(screen.getByRole('button', { name: 'Als Entwickler downgraden (Testen)' }));

    await waitFor(() => {
      expect(window.alert).toHaveBeenCalledWith(
        'Deine Sitzung ist abgelaufen. Bitte logge dich erneut ein und versuche es noch einmal.'
      );
    });
    // Rolle darf bei einem fehlgeschlagenen Downgrade NICHT lokal auf "free" gesetzt werden.
    expect(setUserRole).not.toHaveBeenCalled();
  });

  test('Downgrade-Button: bei Erfolg wird die Rolle lokal auf "free" gesetzt', async () => {
    const user = userEvent.setup();
    const { setUserRole } = renderPremiumPage({ userRole: 'premium' });
    await screen.findByText('3,90 CHF');

    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ erfolg: true }) });

    await user.click(screen.getByRole('button', { name: 'Als Entwickler downgraden (Testen)' }));

    await waitFor(() => {
      expect(setUserRole).toHaveBeenCalledWith('free');
    });
  });
});
