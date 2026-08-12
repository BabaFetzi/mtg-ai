import RechtsSeite, { Abschnitt } from './RechtsSeite';
import { BETREIBER } from './betreiber';

/**
 * Allgemeine Geschäftsbedingungen inklusive Widerrufsbelehrung.
 *
 * Der Widerruf ist der Punkt, an dem Abo-Angebote am häufigsten scheitern:
 * Verbraucherinnen und Verbraucher aus der EU haben 14 Tage Widerrufsrecht.
 * Bei digitalen Diensten erlischt es vorzeitig nur, wenn ausdrücklich
 * zugestimmt und darüber belehrt wurde -- deshalb steht das hier explizit.
 */
function AGB() {
  const li = { marginBottom: '8px' };

  return (
    <RechtsSeite
      titel="Allgemeine Geschäftsbedingungen"
      untertitel="Was du von Grana erwarten kannst — und was wir von dir erwarten."
    >
      <Abschnitt nummer="1." titel="Geltungsbereich und Anbieter">
        <p>
          Diese Bedingungen gelten für die Nutzung von Grana, angeboten von
          {' '}{BETREIBER.name}, {BETREIBER.strasse}, {BETREIBER.plz}{' '}
          {BETREIBER.ort}, {BETREIBER.land}. Mit der Registrierung erkennst du
          sie an.
        </p>
      </Abschnitt>

      <Abschnitt nummer="2." titel="Leistungsbeschreibung">
        <p>
          Grana ist ein Werkzeug zur Verwaltung einer Magic-Sammlung und zum
          Deckbau. Es umfasst Kartensuche, Sammlungsverwaltung, Deck-Editor,
          Formatprüfung sowie KI-gestützte Funktionen (Regel-Judge,
          Deck-Analyse, Combo-Suche, Kartenerkennung).
        </p>
        <p style={{ marginTop: '12px' }}>
          <strong>Kostenlose Nutzung:</strong> Kartensuche, Sammlungsverwaltung
          und bis zu drei Decks.<br />
          <strong>Grana Pro:</strong> unbegrenzte Decks sowie die
          KI-Funktionen im vollen Umfang.
        </p>
      </Abschnitt>

      <Abschnitt nummer="3." titel="Registrierung und Konto">
        <p>
          Für die Nutzung ist ein Konto erforderlich. Deine Zugangsdaten sind
          vertraulich zu behandeln. Pro Person ist ein Konto zulässig. Du bist
          dafür verantwortlich, dass deine Angaben zutreffen und deine
          E-Mail-Adresse erreichbar bleibt — sie ist der einzige Weg, dein
          Passwort zurückzusetzen.
        </p>
      </Abschnitt>

      <Abschnitt nummer="4." titel="Preise, Abrechnung und Laufzeit">
        <p>
          Der aktuelle Preis für Grana Pro wird vor dem Abschluss deutlich
          angezeigt. Die Abrechnung erfolgt über Stripe im Voraus für den
          jeweiligen Abrechnungszeitraum. Das Abo verlängert sich automatisch um
          denselben Zeitraum, solange du nicht kündigst.
        </p>
        <p style={{ marginTop: '12px' }}>
          Du kannst jederzeit zum Ende des laufenden Abrechnungszeitraums
          kündigen — in deinem Konto unter „Grana Pro". Bis zum Ende des
          bezahlten Zeitraums bleiben die Pro-Funktionen verfügbar; danach wird
          das Konto auf die kostenlose Nutzung zurückgestuft. Bereits gezahlte
          Beträge für einen laufenden Zeitraum werden nicht anteilig erstattet,
          soweit nicht zwingendes Recht etwas anderes vorsieht.
        </p>
        <p style={{ marginTop: '12px' }}>
          Schlägt eine Zahlung fehl, kann der Zugang zu den Pro-Funktionen bis
          zum Ausgleich ausgesetzt werden. Deine Sammlung und deine Decks
          bleiben davon unberührt.
        </p>
      </Abschnitt>

      <Abschnitt nummer="5." titel="Widerrufsrecht für Verbraucher">
        <p>
          Verbraucherinnen und Verbraucher mit Wohnsitz in der EU haben das
          Recht, binnen vierzehn Tagen ohne Angabe von Gründen zu widerrufen.
          Die Frist beginnt mit dem Vertragsschluss. Für den Widerruf genügt
          eine eindeutige Erklärung per E-Mail an{' '}
          <a href={`mailto:${BETREIBER.email}`} style={{ color: 'var(--accent-color)' }}>
            {BETREIBER.email}
          </a>.
        </p>
        <p style={{ marginTop: '12px' }}>
          <strong>Vorzeitiges Erlöschen:</strong> Das Widerrufsrecht erlischt
          vor Ablauf der Frist nur dann, wenn du beim Abschluss ausdrücklich
          verlangst, dass wir sofort mit der Leistung beginnen, und zugleich
          bestätigst, dass du dadurch dein Widerrufsrecht verlierst. Ohne diese
          ausdrückliche Zustimmung bleibt es dir vollständig erhalten.
        </p>
        <p style={{ marginTop: '12px' }}>
          Bei einem wirksamen Widerruf erstatten wir bereits erhaltene Zahlungen
          unverzüglich, spätestens binnen vierzehn Tagen, über dasselbe
          Zahlungsmittel.
        </p>
      </Abschnitt>

      <Abschnitt nummer="6." titel="Deine Pflichten">
        <ul style={{ paddingLeft: '20px' }}>
          <li style={li}>Keine automatisierten Massenabfragen und kein Umgehen technischer Beschränkungen.</li>
          <li style={li}>Keine Weitergabe deines Zugangs an Dritte.</li>
          <li style={li}>Keine Nutzung, die den Betrieb beeinträchtigt oder gegen geltendes Recht verstösst.</li>
          <li style={li}>Keine Inhalte hochladen, an denen dir die Rechte fehlen.</li>
        </ul>
        <p style={{ marginTop: '12px' }}>
          Bei erheblichen oder wiederholten Verstössen können wir den Zugang
          sperren. Vor einer dauerhaften Sperre weisen wir dich, soweit möglich,
          zunächst auf den Verstoss hin.
        </p>
      </Abschnitt>

      <Abschnitt nummer="7." titel="Verfügbarkeit">
        <p>
          Wir bemühen uns um einen durchgehenden Betrieb, schulden aber keine
          bestimmte Verfügbarkeit. Wartungsarbeiten und Störungen bei
          Vorleistern (insbesondere Scryfall, Google und Stripe) können zu
          Unterbrechungen führen. Längere geplante Arbeiten kündigen wir an.
        </p>
      </Abschnitt>

      <Abschnitt nummer="8." titel="KI-Auskünfte sind keine Regelauskunft">
        <p>
          Die KI-gestützten Funktionen liefern Hilfestellungen, keine
          verbindliche Regelauslegung. Sie können falsch liegen. Verbindlich
          sind allein die offiziellen Regeltexte von Wizards of the Coast und
          die Entscheidung eines Judges vor Ort. Auch angezeigte Marktwerte sind
          unverbindliche Richtwerte auf Basis der Daten von Scryfall und keine
          Kauf- oder Verkaufsempfehlung.
        </p>
      </Abschnitt>

      <Abschnitt nummer="9." titel="Deine Inhalte und Datensicherung">
        <p>
          Deine Sammlung und deine Decklisten gehören dir. Du kannst deine
          Sammlung jederzeit als CSV-Datei exportieren. Wir erstellen
          Sicherungskopien, empfehlen dir aber, wichtige Listen zusätzlich
          selbst zu sichern.
        </p>
      </Abschnitt>

      <Abschnitt nummer="10." titel="Haftung">
        <p>
          Wir haften unbeschränkt bei Vorsatz und grober Fahrlässigkeit sowie
          bei der Verletzung von Leben, Körper und Gesundheit. Bei einfacher
          Fahrlässigkeit haften wir nur für die Verletzung wesentlicher
          Vertragspflichten und begrenzt auf den vertragstypischen,
          vorhersehbaren Schaden. Eine weitergehende Haftung ist ausgeschlossen.
          Zwingende gesetzliche Ansprüche bleiben unberührt.
        </p>
      </Abschnitt>

      <Abschnitt nummer="11." titel="Änderungen dieser Bedingungen">
        <p>
          Wir können diese Bedingungen ändern, etwa bei neuen Funktionen oder
          geänderter Rechtslage. Über wesentliche Änderungen informieren wir
          dich mindestens 30 Tage vorher per E-Mail. Widersprichst du nicht bis
          zum Wirksamwerden, gelten sie als angenommen; darauf weisen wir in der
          Mitteilung gesondert hin. Andernfalls kannst du zum Zeitpunkt des
          Wirksamwerdens kündigen.
        </p>
      </Abschnitt>

      <Abschnitt nummer="12." titel="Konto löschen">
        <p>
          Du kannst dein Konto jederzeit löschen lassen. Schreib uns dazu an{' '}
          <a href={`mailto:${BETREIBER.email}`} style={{ color: 'var(--accent-color)' }}>
            {BETREIBER.email}
          </a>. Mit der Löschung enden ein laufendes Abo und der Zugriff auf
          deine Inhalte. Exportiere vorher, was du behalten möchtest.
        </p>
      </Abschnitt>

      <Abschnitt nummer="13." titel="Anwendbares Recht und Gerichtsstand">
        <p>
          Es gilt Schweizer Recht unter Ausschluss des UN-Kaufrechts.
          Gerichtsstand ist {BETREIBER.ort}, soweit nicht ein zwingender
          gesetzlicher Gerichtsstand besteht. Verbraucherinnen und Verbraucher
          können sich stets auch an die Gerichte an ihrem Wohnsitz wenden, und
          die zwingenden Verbraucherschutzvorschriften ihres Wohnsitzstaates
          bleiben unberührt.
        </p>
      </Abschnitt>

      <Abschnitt nummer="14." titel="Marken Dritter">
        <p>
          Grana steht in keiner Verbindung zu Wizards of the Coast LLC. Magic:
          The Gathering und alle zugehörigen Marken sind Eigentum von Wizards of
          the Coast LLC.
        </p>
      </Abschnitt>
    </RechtsSeite>
  );
}

export default AGB;
