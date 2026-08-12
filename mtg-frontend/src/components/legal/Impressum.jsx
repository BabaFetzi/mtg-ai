import RechtsSeite, { Abschnitt } from './RechtsSeite';
import { BETREIBER } from './betreiber';

/**
 * Impressum.
 *
 * Pflicht nach Art. 3 Abs. 1 lit. s UWG (Schweiz) für jedes Angebot im
 * elektronischen Geschäftsverkehr, und nach § 5 DDG (Deutschland), sobald sich
 * das Angebot auch an deutsche Kundinnen und Kunden richtet. Stripe verlangt
 * für Live-Konten ebenfalls eine erreichbare Anbieterkennzeichnung.
 */
function Impressum() {
  const zeile = { margin: '0 0 4px' };

  return (
    <RechtsSeite
      titel="Impressum"
      untertitel="Angaben zum Anbieter dieses Dienstes."
    >
      <Abschnitt titel="Verantwortlich für dieses Angebot">
        <p style={zeile}>{BETREIBER.name}</p>
        {BETREIBER.rechtsform && <p style={zeile}>{BETREIBER.rechtsform}</p>}
        <p style={zeile}>{BETREIBER.strasse}</p>
        <p style={zeile}>{BETREIBER.plz} {BETREIBER.ort}</p>
        <p style={zeile}>{BETREIBER.land}</p>
      </Abschnitt>

      <Abschnitt titel="Kontakt">
        <p style={zeile}>
          E-Mail:{' '}
          <a href={`mailto:${BETREIBER.email}`} style={{ color: 'var(--accent-color)' }}>
            {BETREIBER.email}
          </a>
        </p>
        <p style={zeile}>Telefon: {BETREIBER.telefon}</p>
        <p style={{ marginTop: '12px' }}>
          Anfragen zu deinem Konto, zur Abrechnung oder zum Datenschutz
          beantworten wir über diese E-Mail-Adresse.
        </p>
      </Abschnitt>

      <Abschnitt titel="Registereintrag und Steuern">
        <p style={zeile}>Handelsregister-Nummer: {BETREIBER.handelsregister}</p>
        <p style={zeile}>Mehrwertsteuer-Nummer: {BETREIBER.mwstNummer}</p>
      </Abschnitt>

      <Abschnitt titel="Haftung für Inhalte">
        <p>
          Die Inhalte dieses Dienstes werden mit Sorgfalt erstellt. Für die
          Richtigkeit, Vollständigkeit und Aktualität der von der künstlichen
          Intelligenz erzeugten Regelauskünfte, Deck-Analysen und
          Combo-Vorschläge wird keine Gewähr übernommen. Diese Auskünfte sind
          eine Hilfestellung und keine offizielle Regelauslegung. Verbindlich
          sind allein die jeweils gültigen offiziellen Regeltexte und die
          Entscheidungen eines Judges vor Ort.
        </p>
      </Abschnitt>

      <Abschnitt titel="Haftung für Links">
        <p>
          Dieser Dienst verweist auf externe Websites, auf deren Inhalte wir
          keinen Einfluss haben. Für diese fremden Inhalte ist stets der
          jeweilige Anbieter verantwortlich.
        </p>
      </Abschnitt>

      <Abschnitt titel="Rechte an Magic: The Gathering">
        <p>
          Grana ist ein unabhängiges Werkzeug und steht in keiner Verbindung zu
          Wizards of the Coast LLC. Magic: The Gathering, alle Kartennamen,
          Kartentexte, Illustrationen und zugehörigen Marken sind Eigentum von
          Wizards of the Coast LLC, einer Tochtergesellschaft von Hasbro, Inc.
          Kartendaten und Kartenbilder stammen von Scryfall. Die Darstellung
          erfolgt im Rahmen der Fan-Content-Richtlinie von Wizards of the Coast.
        </p>
      </Abschnitt>

      <Abschnitt titel="Urheberrecht">
        <p>
          Die von uns erstellten Inhalte und Werke auf diesen Seiten unterliegen
          dem Urheberrecht. Beiträge Dritter sind als solche gekennzeichnet.
        </p>
      </Abschnitt>
    </RechtsSeite>
  );
}

export default Impressum;
