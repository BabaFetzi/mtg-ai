// ============================================================================
// utils/format.js – Zentrale Zahlen-/Währungsformatierung (de-DE)
//
// Vorher zeigte die App Kartenpreise als "1.14 €" (Punkt) und den Abo-Preis
// als "3,90 CHF" (Komma). Ein Format für alles: deutsches Zahlenformat mit
// Komma, zwei Nachkommastellen.
// ============================================================================

/** Parst "1.14", "1,14", 1.14 oder null robust zu einer Zahl (sonst 0). */
export function parsePreis(value) {
  if (typeof value === "number") return isNaN(value) ? 0 : value;
  if (value == null) return 0;
  const n = parseFloat(String(value).replace(",", "."));
  return isNaN(n) ? 0 : n;
}

/** Formatiert einen Betrag als "1,14 €" (de-DE, 2 Nachkommastellen). */
export function formatEuro(value) {
  return `${parsePreis(value).toLocaleString("de-DE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} €`;
}

/** Formatiert eine Zahl im deutschen Format (z.B. Ø Manakosten "2,53"). */
export function formatZahl(value, nachkommastellen = 2) {
  return parsePreis(value).toLocaleString("de-DE", {
    minimumFractionDigits: nachkommastellen,
    maximumFractionDigits: nachkommastellen,
  });
}
