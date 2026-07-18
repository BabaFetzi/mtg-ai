// Alle Premium-KI-Endpunkte (Judge, Deck-Analyse, Deck-Roast, Combo-Scanner)
// antworten bei fehlendem Premium-Status mit HTTP 200 und { error: "paywall" }
// statt einem Fehlerstatus -- ein `fetch(...).ok`-Check reicht hier also NICHT,
// die JSON-Antwort muss explizit darauf geprüft werden.
export function isPaywallResponse(data) {
  return !!data && data.error === "paywall";
}

const DEFAULT_PAYWALL_MESSAGE =
  "Dieses Feature steht nur Premium-Mitgliedern zur Verfügung. Bitte upgrade deine Rolle im Premium-Tab!";

// Einheitliche Reaktion auf eine erkannte Paywall-Antwort: öffnet das
// Premium-Upgrade-Modal, falls vorhanden, sonst ein Alert mit der
// vom Backend gelieferten (oder einer Standard-) Nachricht.
export function handlePaywallResponse(data, onShowPremiumModal) {
  if (onShowPremiumModal) {
    onShowPremiumModal();
  } else {
    alert(data?.message || DEFAULT_PAYWALL_MESSAGE);
  }
}

export { DEFAULT_PAYWALL_MESSAGE };
