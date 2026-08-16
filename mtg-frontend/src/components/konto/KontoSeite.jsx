import { useState } from 'react';
import { useMeldung } from '../layout/Meldungen';

/**
 * Konto und Daten.
 *
 * Zwei Rechte, die jede Seite mit echten Kunden anbieten muss und die es hier
 * bisher gar nicht gab:
 *   * Auskunft und Mitnahme der eigenen Daten (Artikel 15 und 20 DSGVO)
 *   * Löschung des Kontos (Artikel 17)
 *
 * Das Löschen verlangt Passwort UND ein getipptes Wort. Ein Knopf allein wäre
 * für einen Vorgang, der eine über Jahre gepflegte Sammlung vernichtet, zu
 * wenig.
 */

const BESTAETIGUNGSWORT = 'LÖSCHEN';

function KontoSeite({ currentUser, onAbgemeldet }) {
  const { melde, bestaetige } = useMeldung();
  const [laedtExport, setLaedtExport] = useState(false);
  const [loeschbereich, setLoeschbereich] = useState(false);
  const [passwort, setPasswort] = useState('');
  const [bestaetigung, setBestaetigung] = useState('');
  const [loescht, setLoescht] = useState(false);

  const exportieren = async () => {
    setLaedtExport(true);
    try {
      const res = await fetch('/api/konto/export');
      if (!res.ok) {
        melde.fehler('Der Export konnte nicht erstellt werden.');
        return;
      }
      // Als Datei speichern, ohne den Umweg über einen neuen Tab -- die
      // Antwort trägt bereits einen Dateinamen.
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `grana-daten-${currentUser}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      melde.erfolg('Deine Daten wurden heruntergeladen.');
    } catch {
      melde.fehler('Keine Verbindung zum Server.');
    } finally {
      setLaedtExport(false);
    }
  };

  const loeschen = async () => {
    if (bestaetigung.trim().toUpperCase() !== BESTAETIGUNGSWORT) {
      melde.fehler(`Bitte ${BESTAETIGUNGSWORT} eintippen, um die Löschung zu bestätigen.`);
      return;
    }
    if (!passwort) {
      melde.fehler('Bitte gib dein Passwort ein.');
      return;
    }

    const ok = await bestaetige({
      titel: 'Konto endgültig löschen?',
      text: 'Sammlung, Decks und Konto werden unwiderruflich gelöscht. Ein laufendes '
        + 'Abonnement wird beendet; bereits bezahlte Restlaufzeit verfällt.',
      bestaetigenText: 'Ja, alles löschen',
      gefaehrlich: true,
    });
    if (!ok) return;

    setLoescht(true);
    try {
      const res = await fetch('/api/konto/loeschen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passwort, bestaetigung }),
      });
      const daten = await res.json().catch(() => null);

      if (res.status === 403) {
        melde.fehler('Das Passwort stimmt nicht.');
        return;
      }
      if (!res.ok || !daten?.erfolg) {
        melde.fehler(daten?.detail || 'Das Konto konnte nicht gelöscht werden.');
        return;
      }

      if (daten.abo_hinweis && !daten.abo_beendet) melde.info(daten.abo_hinweis);
      melde.erfolg('Dein Konto und alle Daten wurden gelöscht.');
      if (onAbgemeldet) onAbgemeldet();
    } catch {
      melde.fehler('Keine Verbindung zum Server. Es wurde nichts gelöscht.');
    } finally {
      setLoescht(false);
    }
  };

  return (
    <div className="apple-main-container">
      <h2 style={{ fontSize: 'clamp(1.5rem, 3vw, 1.9rem)', marginBottom: '24px' }}>
        Konto und Daten
      </h2>

      <div className="content-card" style={{ marginBottom: '24px' }}>
        <h3 style={{ fontSize: '1.25rem' }}>Deine Daten mitnehmen</h3>
        <p>
          Du bekommst alles, was zu deinem Konto gespeichert ist, als JSON-Datei:
          Kontodaten, Sammlung, Decks und die Nutzung der KI-Funktionen. Nicht
          enthalten sind Passwort-Hash und Sicherheits-Token — sie sagen nichts
          über dich aus und wären in fremder Hand ein Risiko.
        </p>
        <button
          className="secondary-btn"
          onClick={exportieren}
          disabled={laedtExport}
          style={{ display: 'inline-flex', alignItems: 'center', gap: '10px' }}
        >
          {laedtExport && <span className="spinner" style={{ width: '14px', height: '14px', borderWidth: '2px', margin: 0 }} />}
          {laedtExport ? 'Wird erstellt...' : 'Daten herunterladen'}
        </button>
      </div>

      <div className="content-card" style={{ borderColor: 'var(--danger-color)' }}>
        <h3 style={{ fontSize: '1.25rem', color: 'var(--danger-color)' }}>Konto löschen</h3>
        <p>
          Sammlung, Decks und Konto werden unwiderruflich gelöscht. Ein laufendes
          Abonnement wird dabei beendet; bereits bezahlte Restlaufzeit verfällt.
          Lade dir vorher deine Daten herunter, wenn du sie behalten möchtest.
        </p>

        {!loeschbereich ? (
          <button className="gefahr-btn" onClick={() => setLoeschbereich(true)}>
            Konto löschen
          </button>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxWidth: '28rem' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Dein Passwort</span>
              <input
                type="password"
                value={passwort}
                onChange={(e) => setPasswort(e.target.value)}
                autoComplete="current-password"
                style={{ background: 'var(--input-bg)' }}
              />
            </label>

            <label style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                Tippe {BESTAETIGUNGSWORT}, um zu bestätigen
              </span>
              <input
                value={bestaetigung}
                onChange={(e) => setBestaetigung(e.target.value)}
                style={{ background: 'var(--input-bg)' }}
              />
            </label>

            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <button
                className="gefahr-btn"
                onClick={loeschen}
                disabled={loescht}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '10px' }}
              >
                {loescht && <span className="spinner" style={{ width: '14px', height: '14px', borderWidth: '2px', margin: 0 }} />}
                {loescht ? 'Wird gelöscht...' : 'Endgültig löschen'}
              </button>
              <button
                className="secondary-btn"
                onClick={() => { setLoeschbereich(false); setPasswort(''); setBestaetigung(''); }}
                disabled={loescht}
              >
                Abbrechen
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default KontoSeite;
