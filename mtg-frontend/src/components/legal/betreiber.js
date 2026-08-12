/**
 * betreiber.js – Angaben zum Betreiber an EINER Stelle.
 *
 * Diese Werte erscheinen im Impressum, in der Datenschutzerklärung und in den
 * AGB. Sie stehen bewusst zentral, damit eine Adressänderung nicht an drei
 * Stellen nachgezogen werden muss.
 *
 * ACHTUNG: Die Platzhalter in eckigen Klammern MÜSSEN vor dem Start durch die
 * echten Angaben ersetzt werden. Ein Impressum mit unvollständigen Angaben ist
 * schlechter als gar keines -- es ist abmahnfähig.
 */

export const BETREIBER = {
  // Rechtlich verantwortliche Person oder Firma
  name: '[Vor- und Nachname bzw. Firmenname]',
  rechtsform: '[z. B. Einzelunternehmen / GmbH]',

  // Ladungsfähige Anschrift -- ein Postfach genügt nicht
  strasse: '[Strasse und Hausnummer]',
  plz: '[PLZ]',
  ort: '[Ort]',
  land: 'Schweiz',

  // Kontakt: die E-Mail muss tatsächlich gelesen werden
  email: '[kontakt@deine-domain.tld]',
  telefon: '[+41 ...]',

  // Nur ausfüllen, sofern vorhanden
  handelsregister: '[CHE-123.456.789 oder leer lassen]',
  mwstNummer: '[CHE-123.456.789 MWST oder leer lassen]',

  // Für die Datenschutzerklärung
  domain: '[deine-domain.tld]',
  hostingAnbieter: '[Name und Sitz deines Hosting-Anbieters]',
};

/** Stand der Rechtstexte. Bei jeder inhaltlichen Änderung mit aktualisieren. */
export const RECHTSSTAND = '11. August 2026';

/** true, sobald alle Pflichtangaben ersetzt wurden. */
export function betreiberAngabenVollstaendig() {
  return !Object.values(BETREIBER).some(
    (wert) => typeof wert === 'string' && wert.trim().startsWith('[')
  );
}
