import { isPaywallResponse, handlePaywallResponse, DEFAULT_PAYWALL_MESSAGE } from './paywall';

describe('isPaywallResponse', () => {
  test('erkennt die Standard-Paywall-Form { error: "paywall" }', () => {
    expect(isPaywallResponse({ error: 'paywall', message: 'Nur für Premium.' })).toBe(true);
  });

  test('erkennt die Judge-Paywall-Form mit zusätzlichem antwort-Feld', () => {
    expect(isPaywallResponse({ error: 'paywall', antwort: 'PAYWALL: ...' })).toBe(true);
  });

  test('ist false bei echten Erfolgsantworten', () => {
    expect(isPaywallResponse({ verdict: 'Autsch.', roast: 'Dein Deck ist zu langsam.', salt_score: 73 })).toBe(false);
  });

  test('ist false bei einem anderen Fehler-Code (z.B. Monatslimit erreicht)', () => {
    expect(isPaywallResponse({ error: 'limit_reached', message: 'Monatslimit erreicht.' })).toBe(false);
  });

  test('ist false bei null/undefined/leerem Objekt, ohne zu crashen', () => {
    expect(isPaywallResponse(null)).toBe(false);
    expect(isPaywallResponse(undefined)).toBe(false);
    expect(isPaywallResponse({})).toBe(false);
  });

  test('ist false bei Primitiven statt einem Objekt', () => {
    expect(isPaywallResponse('paywall')).toBe(false);
    expect(isPaywallResponse(0)).toBe(false);
  });
});

describe('handlePaywallResponse', () => {
  test('öffnet das Premium-Modal, wenn onShowPremiumModal vorhanden ist -- statt eines Alerts', () => {
    const onShowPremiumModal = vi.fn();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    handlePaywallResponse({ error: 'paywall', message: 'Nur für Premium.' }, onShowPremiumModal);

    expect(onShowPremiumModal).toHaveBeenCalledTimes(1);
    expect(alertSpy).not.toHaveBeenCalled();

    alertSpy.mockRestore();
  });

  test('fällt auf einen Alert mit der Backend-Nachricht zurück, wenn kein Modal-Callback übergeben wurde', () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    handlePaywallResponse({ error: 'paywall', message: 'Nur für Premium-Mitglieder.' }, undefined);

    expect(alertSpy).toHaveBeenCalledWith('Nur für Premium-Mitglieder.');

    alertSpy.mockRestore();
  });

  test('nutzt die Standardnachricht, wenn das Backend keine message mitschickt', () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    handlePaywallResponse({ error: 'paywall' }, undefined);

    expect(alertSpy).toHaveBeenCalledWith(DEFAULT_PAYWALL_MESSAGE);

    alertSpy.mockRestore();
  });
});
