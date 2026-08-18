import { Component } from 'react';

/**
 * Fängt Fehler aus der Darstellung ab, damit aus einem kaputten Bauteil keine
 * leere Seite wird.
 *
 * Warum das nötig ist: React entfernt bei einem unbehandelten Fehler den
 * KOMPLETTEN Baum. Für den Nutzer heisst das nicht "eine Funktion streikt",
 * sondern "die Webseite ist weiss". Kein Hinweis, kein Weg zurück, nichts zum
 * Melden -- und im schlimmsten Fall mitten in einer laufenden Partie.
 *
 * Ein einziger Fehler in einer Nebensache (eine Karte ohne Preis, ein
 * unerwartetes Feld in einer Antwort) reicht dafür aus.
 *
 * Bewusst eine Klasse: componentDidCatch gibt es nur hier: React bietet dafür
 * keinen Hook an.
 */
export default class Fehlergrenze extends Component {
  constructor(props) {
    super(props);
    this.state = { fehler: null };
  }

  static getDerivedStateFromError(fehler) {
    return { fehler };
  }

  componentDidCatch(fehler, info) {
    // In die Konsole, damit der Fehler beim Nachstellen auffindbar bleibt.
    console.error('Unbehandelter Fehler in der Darstellung:', fehler, info);

    // An die Überwachung, falls eingerichtet. Ohne das merkt niemand, dass
    // Nutzer auf eine kaputte Ansicht laufen -- sie melden sich meistens
    // nicht, sie gehen.
    if (window.Sentry?.captureException) {
      try {
        window.Sentry.captureException(fehler);
      } catch {
        /* Eine kaputte Überwachung darf die Fehlerseite nicht auch noch stören. */
      }
    }
  }

  neuLaden = () => {
    window.location.reload();
  };

  zurueckZumStart = () => {
    window.location.href = '/';
  };

  render() {
    if (!this.state.fehler) return this.props.children;

    return (
      <div
        role="alert"
        style={{
          minHeight: '60vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '16px',
          padding: '40px 20px',
          textAlign: 'center',
          color: 'var(--text-main)',
        }}
      >
        <h1 style={{ fontSize: 'clamp(1.3rem, 4vw, 1.8rem)', margin: 0 }}>
          Hier ist etwas schiefgelaufen
        </h1>
        <p style={{ color: 'var(--text-muted)', maxWidth: '34rem', lineHeight: 1.6, margin: 0 }}>
          Deine Daten sind nicht betroffen — nur die Anzeige dieses Bereichs
          konnte nicht geladen werden.
        </p>
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', justifyContent: 'center' }}>
          <button onClick={this.neuLaden} className="btn-primary">
            Seite neu laden
          </button>
          <button onClick={this.zurueckZumStart} className="btn-secondary">
            Zur Startseite
          </button>
        </div>
      </div>
    );
  }
}
