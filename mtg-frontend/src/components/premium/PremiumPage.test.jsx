import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PremiumPage from './PremiumPage';
import { MeldungProvider } from '../layout/Meldungen';

function renderPremiumPage({ userRole, setUserRole = vi.fn() } = {}) {
  render(
    <MemoryRouter>
      {/* Mit Provider: Rückmeldungen laufen nicht mehr über window.alert,
          sondern über sichtbare Einblendungen -- also wird auch das geprüft. */}
      <MeldungProvider>
        <PremiumPage currentUser="hovertest" userRole={userRole} setUserRole={setUserRole} />
      </MeldungProvider>
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

  test('Premium-Nutzer sieht "Premium Aktiv" und den "Abo kündigen"-Button, nicht den Abo-Button', async () => {
    renderPremiumPage({ userRole: 'premium' });

    expect(screen.getByText('Premium Aktiv')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Abo kündigen' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Jetzt abonnieren' })).not.toBeInTheDocument();
    // Freier Tarif ist für einen Premium-Nutzer nicht "aktuell".
    expect(screen.getByRole('button', { name: 'Kostenloses Basis-Konto' })).toBeInTheDocument();
  });

  test('zeigt den echten, live von Stripe geladenen Preis an (kein fest einprogrammierter Wert)', async () => {
    renderPremiumPage({ userRole: 'free' });

    expect(await screen.findByText('3,90 CHF')).toBeInTheDocument();
  });

  test('Abo kündigen: bei abgelaufener Session (401) erscheint ein klarer Re-Login-Hinweis, kein stiller Fehlschlag', async () => {
    const user = userEvent.setup();
    const { setUserRole } = renderPremiumPage({ userRole: 'premium' });

    // Der Preis-Fetch beim Mount läuft schon über den Default-Mock aus
    // beforeEach; hier nur den nächsten (Kündigungs-)Aufruf gezielt auf 401 setzen.
    await screen.findByText('3,90 CHF');

    global.fetch.mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) });

    await user.click(screen.getByRole('button', { name: 'Abo kündigen' }));
    // Die Rückfrage läuft nicht mehr über window.confirm, sondern über einen
    // eigenen Dialog -- also muss der Test sie auch bestätigen.
    await user.click(await screen.findByRole('button', { name: 'Ja, kündigen' }));

    expect(
      await screen.findByText(/Sitzung ist abgelaufen/)
    ).toBeInTheDocument();
    // Rolle darf bei einem Fehlschlag NICHT lokal auf "free" gesetzt werden.
    expect(setUserRole).not.toHaveBeenCalled();
  });

  test('Abo kündigen: bei Erfolg bleibt Premium bis Periodenende aktiv (kein sofortiges Downgrade)', async () => {
    const user = userEvent.setup();
    const { setUserRole } = renderPremiumPage({ userRole: 'premium' });
    await screen.findByText('3,90 CHF');

    // Echte Stripe-Kündigung: cancel_at_period_end -> laeuft_bis-Timestamp
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ erfolg: true, laeuft_bis: 1790000000 }),
    });

    await user.click(screen.getByRole('button', { name: 'Abo kündigen' }));
    // Die Rückfrage läuft nicht mehr über window.confirm, sondern über einen
    // eigenen Dialog -- also muss der Test sie auch bestätigen.
    await user.click(await screen.findByRole('button', { name: 'Ja, kündigen' }));

    // Persistente, eindeutige Rückmeldung im UI (statt eines flüchtigen Popups):
    await waitFor(() => {
      expect(screen.getByText(/Abo gekündigt/i)).toBeInTheDocument();
    });
    // Der Kündigungs-Button verschwindet, sodass das Ergebnis unmissverständlich ist.
    expect(screen.queryByRole('button', { name: 'Abo kündigen' })).not.toBeInTheDocument();
    // Der Kündigungs-Endpoint wurde aufgerufen ...
    expect(global.fetch).toHaveBeenCalledWith('/api/checkout/cancel-subscription', { method: 'POST' });
    // ... aber Premium bleibt bis zum Periodenende aktiv -- das Downgrade
    // macht der Stripe-Webhook, NICHT das Frontend.
    expect(setUserRole).not.toHaveBeenCalled();
  });

  test('Abo kündigen: ohne Stripe-Abo (Dev-Premium) wird die Rolle als Fallback auf "free" gesetzt', async () => {
    const user = userEvent.setup();
    const { setUserRole } = renderPremiumPage({ userRole: 'premium' });
    await screen.findByText('3,90 CHF');

    // 1. Aufruf: cancel-subscription meldet ehrlich "kein Abo"
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ erfolg: false, kein_abo: true, error: 'Kein Abo' }),
    });
    // 2. Aufruf: Fallback update-role auf free
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ erfolg: true }) });

    await user.click(screen.getByRole('button', { name: 'Abo kündigen' }));
    // Die Rückfrage läuft nicht mehr über window.confirm, sondern über einen
    // eigenen Dialog -- also muss der Test sie auch bestätigen.
    await user.click(await screen.findByRole('button', { name: 'Ja, kündigen' }));

    await waitFor(() => {
      expect(setUserRole).toHaveBeenCalledWith('free');
    });
  });
});
