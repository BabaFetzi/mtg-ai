import RechtsSeite, { Abschnitt } from './RechtsSeite';
import { BETREIBER } from './betreiber';

/**
 * Datenschutzerklärung.
 *
 * Deckt das revidierte Schweizer Datenschutzgesetz (revDSG) und die DSGVO ab,
 * weil der Dienst auch aus der EU nutzbar ist.
 *
 * Besonders wichtig und leicht zu übersehen: Grana gibt Nutzereingaben an
 * Google Gemini weiter (Judge-Fragen, Decklisten, Kartenfotos) und
 * protokolliert die KI-Nutzung. Beides gehört ausdrücklich hier hinein.
 */
function Datenschutz() {
  const li = { marginBottom: '8px' };

  return (
    <RechtsSeite
      titel="Datenschutzerklärung"
      untertitel="Welche Daten wir verarbeiten, wozu, und welche Rechte du hast."
    >
      <Abschnitt nummer="1." titel="Verantwortliche Stelle">
        <p>
          Verantwortlich für die Verarbeitung deiner Daten ist {BETREIBER.name},
          {' '}{BETREIBER.strasse}, {BETREIBER.plz} {BETREIBER.ort},
          {' '}{BETREIBER.land}. Du erreichst uns unter{' '}
          <a href={`mailto:${BETREIBER.email}`} style={{ color: 'var(--accent-color)' }}>
            {BETREIBER.email}
          </a>.
        </p>
      </Abschnitt>

      <Abschnitt nummer="2." titel="Welche Daten wir verarbeiten">
        <ul style={{ paddingLeft: '20px' }}>
          <li style={li}>
            <strong>Kontodaten:</strong> Benutzername, E-Mail-Adresse, ein
            kryptografischer Hash deines Passworts (niemals das Passwort selbst),
            Zeitpunkt der Registrierung und des letzten Logins.
          </li>
          <li style={li}>
            <strong>Inhalte, die du anlegst:</strong> deine Kartensammlung,
            Alben, Decklisten und Deckformate.
          </li>
          <li style={li}>
            <strong>Zahlungsdaten:</strong> Kunden- und Abonnement-Kennung von
            Stripe sowie dein Abo-Status. Kreditkartendaten sehen und speichern
            wir nicht — sie werden ausschliesslich von Stripe verarbeitet.
          </li>
          <li style={li}>
            <strong>Eingaben an die KI-Funktionen:</strong> Regelfragen an den
            Judge, Decklisten für Analyse und Combo-Suche sowie Fotos, die du
            zum Erkennen von Karten hochlädst.
          </li>
          <li style={li}>
            <strong>Technische Protokolle:</strong> Zeitpunkt, aufgerufene
            Funktion und Fehlermeldungen. Sie dienen dem Betrieb und der
            Fehlersuche.
          </li>
        </ul>
      </Abschnitt>

      <Abschnitt nummer="3." titel="Zwecke und Rechtsgrundlagen">
        <p>
          Wir verarbeiten deine Daten, um dir den Dienst bereitzustellen
          (Vertragserfüllung, Art. 6 Abs. 1 lit. b DSGVO), um den Betrieb
          sicher und stabil zu halten sowie Missbrauch zu verhindern
          (berechtigtes Interesse, Art. 6 Abs. 1 lit. f DSGVO) und um
          gesetzliche Aufbewahrungspflichten zu erfüllen (Art. 6 Abs. 1 lit. c
          DSGVO). Nach Schweizer Recht stützen wir uns auf Art. 31 revDSG.
        </p>
      </Abschnitt>

      <Abschnitt nummer="4." titel="Künstliche Intelligenz (Google Gemini)">
        <p>
          Für den Regel-Judge, die Deck-Analyse, die Combo-Suche, die
          Kartenerkennung aus Fotos und die Übersetzung von Kartentexten nutzen
          wir Modelle von Google (Gemini). Dabei wird der jeweilige Inhalt
          deiner Anfrage — also deine Regelfrage, deine Deckliste oder dein
          hochgeladenes Foto — an Google übermittelt und dort verarbeitet.
          Verarbeitung findet auch ausserhalb der Schweiz und des EWR statt.
        </p>
        <p style={{ marginTop: '12px' }}>
          <strong>Was wir dabei protokollieren:</strong> Zu jeder KI-Anfrage
          halten wir fest, welche Funktion genutzt wurde, welches Modell
          geantwortet hat, wie lange es gedauert hat und wie viele Token
          verbraucht wurden. Das dient der Kostenkontrolle und der Erkennung von
          Störungen. <strong>Der Inhalt deiner Anfragen wird dabei
          standardmässig nicht mitgespeichert.</strong>
        </p>
        <p style={{ marginTop: '12px' }}>
          Gib in Regelfragen und Deckbeschreibungen bitte keine Angaben ein, die
          Rückschlüsse auf dich oder andere Personen zulassen — für die
          Beantwortung sind sie nicht nötig.
        </p>
      </Abschnitt>

      <Abschnitt nummer="5." titel="Weitergabe an Dritte">
        <ul style={{ paddingLeft: '20px' }}>
          <li style={li}>
            <strong>Stripe</strong> (Zahlungsabwicklung): verarbeitet deine
            Zahlungsdaten eigenverantwortlich. Es gilt zusätzlich die
            Datenschutzerklärung von Stripe.
          </li>
          <li style={li}>
            <strong>Google</strong> (KI-Funktionen): siehe Abschnitt 4.
          </li>
          <li style={li}>
            <strong>Scryfall</strong> (Kartendaten und Kartenbilder): Beim
            Anzeigen von Karten werden Daten von Scryfall abgerufen. Ein Teil
            dieser Abrufe erfolgt über unseren Server, sodass deine
            IP-Adresse dabei nicht an Scryfall gelangt.
          </li>
          <li style={li}>
            <strong>{BETREIBER.hostingAnbieter}</strong> (Hosting): betreibt die
            Server, auf denen dieser Dienst läuft.
          </li>
        </ul>
        <p style={{ marginTop: '12px' }}>
          Darüber hinaus geben wir deine Daten nicht weiter und verkaufen sie
          nicht.
        </p>
      </Abschnitt>

      <Abschnitt nummer="6." titel="Cookies und lokale Speicherung">
        <p>
          Wir setzen keine Werbe- oder Analyse-Cookies ein. Für die Anmeldung
          und deine Einstellungen (etwa das gewählte Farbschema) speichern wir
          Angaben technisch notwendig im Browser. Ohne sie funktioniert die
          Anmeldung nicht. Eine Einwilligung ist dafür nicht erforderlich.
        </p>
      </Abschnitt>

      <Abschnitt nummer="7." titel="Speicherdauer">
        <p>
          Kontodaten und deine Inhalte speichern wir, solange dein Konto besteht.
          Nach einer Löschung entfernen wir sie innerhalb von 30 Tagen aus dem
          laufenden Betrieb; aus Sicherungskopien verschwinden sie spätestens
          nach 90 Tagen. Rechnungsbezogene Daten bewahren wir so lange auf, wie
          es die gesetzlichen Aufbewahrungsfristen verlangen (in der Schweiz in
          der Regel zehn Jahre).
        </p>
      </Abschnitt>

      <Abschnitt nummer="8." titel="Deine Rechte">
        <p>
          Du hast das Recht auf Auskunft über die zu dir gespeicherten Daten,
          auf Berichtigung, auf Löschung, auf Einschränkung der Verarbeitung, auf
          Datenübertragbarkeit sowie auf Widerspruch gegen bestimmte
          Verarbeitungen. Eine erteilte Einwilligung kannst du jederzeit mit
          Wirkung für die Zukunft widerrufen.
        </p>
        <p style={{ marginTop: '12px' }}>
          Zwei dieser Rechte kannst du sofort selbst ausüben, ohne uns zu
          schreiben: Unter <strong>Konto und Daten</strong> (im Menü unter deinem
          Benutzernamen) lädst du alle zu dir gespeicherten Daten als
          JSON-Datei herunter und löschst dort auch dein Konto samt allen
          Inhalten.
        </p>
        <p style={{ marginTop: '12px' }}>
          Für alles Weitere schreib uns an{' '}
          <a href={`mailto:${BETREIBER.email}`} style={{ color: 'var(--accent-color)' }}>
            {BETREIBER.email}
          </a>. Du kannst dich ausserdem bei einer Aufsichtsbehörde beschweren —
          in der Schweiz beim Eidgenössischen Datenschutz- und
          Öffentlichkeitsbeauftragten (EDÖB), in der EU bei der für deinen
          Wohnsitz zuständigen Datenschutzbehörde.
        </p>
      </Abschnitt>

      <Abschnitt nummer="9." titel="Sicherheit">
        <p>
          Die Verbindung zu diesem Dienst ist verschlüsselt. Passwörter werden
          ausschliesslich als bcrypt-Hash gespeichert und sind für uns nicht
          lesbar. Der Zugriff auf die Datenbank ist auf die für den Betrieb
          notwendigen Personen beschränkt.
        </p>
      </Abschnitt>

      <Abschnitt nummer="10." titel="Änderungen">
        <p>
          Wir passen diese Erklärung an, wenn sich der Dienst oder die
          Rechtslage ändert. Bei wesentlichen Änderungen informieren wir dich
          vorab per E-Mail oder mit einem Hinweis im Dienst.
        </p>
      </Abschnitt>
    </RechtsSeite>
  );
}

export default Datenschutz;
