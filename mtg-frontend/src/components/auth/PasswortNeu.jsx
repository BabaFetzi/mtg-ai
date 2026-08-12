import { useState } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';

const MIN_LAENGE = 8;

/**
 * Zielseite des Links aus der Passwort-Mail (/passwort-neu?token=…).
 *
 * Muss ohne Anmeldung erreichbar sein -- wer hier landet, kommt ja gerade
 * NICHT in sein Konto.
 */
function PasswortNeu() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get('token') || '';

  const [passwort, setPasswort] = useState('');
  const [wiederholung, setWiederholung] = useState('');
  const [fehler, setFehler] = useState('');
  const [fertig, setFertig] = useState(false);
  const [busy, setBusy] = useState(false);

  const absenden = async (e) => {
    e.preventDefault();
    if (busy) return;

    // Vor dem Netzaufruf prüfen, damit die Rückmeldung sofort kommt.
    if (passwort.length < MIN_LAENGE) {
      setFehler(`Das Passwort muss mindestens ${MIN_LAENGE} Zeichen lang sein.`);
      return;
    }
    if (passwort !== wiederholung) {
      setFehler('Die beiden Eingaben stimmen nicht überein.');
      return;
    }

    setBusy(true);
    setFehler('');
    try {
      const res = await fetch('/api/passwort/zuruecksetzen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, neues_passwort: passwort }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.erfolg) {
        setFertig(true);
        setTimeout(() => navigate('/'), 2500);
      } else {
        setFehler(data.detail || 'Der Link ist nicht mehr gültig. Fordere bitte einen neuen an.');
      }
    } catch {
      setFehler('Der Server ist nicht erreichbar. Bitte versuche es erneut.');
    } finally {
      setBusy(false);
    }
  };

  const rahmen = {
    display: 'flex', justifyContent: 'center', alignItems: 'center',
    minHeight: '100vh', background: 'var(--bg-main)', padding: '20px',
  };
  const karte = {
    maxWidth: '450px', width: '100%', textAlign: 'center',
    padding: 'clamp(28px, 7vw, 60px)',
  };

  // Ohne Token ist die Seite sinnlos -- das gleich sagen, statt ein Formular
  // anzubieten, das garantiert scheitert.
  if (!token) {
    return (
      <div style={rahmen}>
        <div className="content-card" style={karte}>
          <h2 style={{ fontSize: 'clamp(1.6rem, 6vw, 2rem)' }}>Link unvollständig</h2>
          <p style={{ color: 'var(--text-muted)', marginTop: '16px', lineHeight: 1.55 }}>
            In der Adresse fehlt der Bestätigungscode. Öffne den Link aus der
            E-Mail bitte direkt, ohne ihn abzutippen.
          </p>
          <Link to="/" style={{ display: 'inline-block', marginTop: '24px', color: 'var(--accent-color)' }}>
            Zurück zur Anmeldung
          </Link>
        </div>
      </div>
    );
  }

  if (fertig) {
    return (
      <div style={rahmen}>
        <div className="content-card" style={karte}>
          <h2 style={{ fontSize: 'clamp(1.6rem, 6vw, 2rem)' }}>Passwort geändert</h2>
          <p role="status" style={{ color: 'var(--text-muted)', marginTop: '16px', lineHeight: 1.55 }}>
            Du kannst dich jetzt mit deinem neuen Passwort anmelden. Wir leiten
            dich gleich weiter.
          </p>
          <Link to="/" style={{ display: 'inline-block', marginTop: '24px', color: 'var(--accent-color)' }}>
            Jetzt anmelden
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div style={rahmen}>
      <div className="content-card" style={karte}>
        <h2 style={{ fontSize: 'clamp(1.9rem, 7vw, 2.5rem)' }}>Neues Passwort</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: '28px', lineHeight: 1.55 }}>
          Vergib ein neues Passwort für dein Konto. Mindestens {MIN_LAENGE} Zeichen.
        </p>

        {fehler && (
          <p role="alert" style={{
            color: 'var(--danger-color)', background: 'var(--danger-bg)',
            border: '1px solid var(--danger-color)', borderRadius: '10px',
            padding: '12px 16px', fontSize: '0.92rem', lineHeight: 1.5, marginBottom: '20px',
          }}>{fehler}</p>
        )}

        <form onSubmit={absenden} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <input
            type="password" placeholder="Neues Passwort" value={passwort}
            onChange={(e) => setPasswort(e.target.value)}
            autoComplete="new-password" aria-label="Neues Passwort"
          />
          <input
            type="password" placeholder="Neues Passwort wiederholen" value={wiederholung}
            onChange={(e) => setWiederholung(e.target.value)}
            autoComplete="new-password" aria-label="Neues Passwort wiederholen"
          />
          <button type="submit" className="primary-btn" disabled={busy}
            style={{ marginTop: '10px', width: '100%', opacity: busy ? 0.7 : 1, cursor: busy ? 'progress' : 'pointer' }}>
            {busy ? 'Wird gespeichert…' : 'Passwort speichern'}
          </button>
        </form>
      </div>
    </div>
  );
}

export default PasswortNeu;
