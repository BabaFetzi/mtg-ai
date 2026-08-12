import { useState } from 'react';

// Drei Zustände statt eines Umschalters: neben Anmelden und Registrieren gibt
// es jetzt "Passwort vergessen". Ohne diesen Weg verlor jeder, der sein
// Passwort vergisst, seine gesamte Sammlung.
const MODUS = { ANMELDEN: 'anmelden', REGISTRIEREN: 'registrieren', VERGESSEN: 'vergessen' };

function AuthScreen({ onLoginSuccess }) {
  const [modus, setModus] = useState(MODUS.ANMELDEN);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  // Hinweise, die KEIN Fehler sind (z. B. "Mail ist unterwegs"), brauchen eine
  // eigene Darstellung -- sonst steht eine Erfolgsmeldung in Rot da.
  const [erfolgsText, setErfolgsText] = useState("");
  // Sofortige Rückmeldung, dass die Anfrage läuft -- ohne diese wirkte die
  // Seite bei langsamer Antwort, als würde nichts passieren.
  const [busy, setBusy] = useState(false);

  const wechsleZu = (neu) => {
    setModus(neu);
    setMessage("");
    setErfolgsText("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (busy) return;

    const endpoint =
      modus === MODUS.REGISTRIEREN ? "/api/register"
      : modus === MODUS.VERGESSEN ? "/api/passwort/vergessen"
      : "/api/login";

    const payload =
      modus === MODUS.REGISTRIEREN ? { benutzername: username, passwort: password, email }
      : modus === MODUS.VERGESSEN ? { kennung: username || email }
      : { benutzername: username, passwort: password };

    setBusy(true);
    setMessage("");
    setErfolgsText("");
    try {
      const res = await fetch(endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json().catch(() => ({}));
      if (data.erfolg) {
        if (modus === MODUS.REGISTRIEREN) {
          setErfolgsText("Konto erstellt. Bitte melde dich an.");
          setModus(MODUS.ANMELDEN);
          setPassword("");
        } else if (modus === MODUS.VERGESSEN) {
          // Der Hinweis kommt bewusst vom Server und sagt NICHT, ob es das
          // Konto gibt -- sonst liessen sich damit gültige Konten ermitteln.
          setErfolgsText(data.hinweis || "Falls ein Konto existiert, ist die E-Mail unterwegs.");
        } else {
          onLoginSuccess(data.benutzername, data.access_token, data.rolle, data.refresh_token);
        }
      } else {
        setMessage(data.error || data.detail || "Anmeldung fehlgeschlagen. Bitte versuche es erneut.");
      }
    } catch {
      setMessage("Der Server ist nicht erreichbar. Bitte prüfe deine Verbindung und versuche es erneut.");
    } finally {
      setBusy(false);
    }
  };

  const titel =
    modus === MODUS.REGISTRIEREN ? "Erstelle dein Konto."
    : modus === MODUS.VERGESSEN ? "Passwort zurücksetzen."
    : "Melde dich bei Grana an.";

  const knopfText = busy
    ? (modus === MODUS.REGISTRIEREN ? "Konto wird erstellt…"
       : modus === MODUS.VERGESSEN ? "Wird gesendet…" : "Wird geprüft…")
    : (modus === MODUS.VERGESSEN ? "Link anfordern" : "Weiter");

  return (
    <div style={{display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: 'var(--bg-main)', padding: '20px'}}>
      <div className="content-card" style={{maxWidth: '450px', width: '100%', textAlign: 'center', padding: 'clamp(28px, 7vw, 60px)'}}>
        <h2 style={{fontSize: 'clamp(1.9rem, 7vw, 2.5rem)'}}>Grana</h2>
        <p style={{marginBottom: '32px'}}>{titel}</p>

        {modus === MODUS.VERGESSEN && !erfolgsText && (
          <p style={{color: 'var(--text-muted)', fontSize: '0.92rem', marginBottom: '24px', lineHeight: 1.55}}>
            Gib deinen Benutzernamen oder deine E-Mail-Adresse ein. Wir schicken
            dir einen Link, mit dem du ein neues Passwort vergeben kannst.
          </p>
        )}

        {message && (
          <p role="alert" style={{
            color: 'var(--danger-color)', background: 'var(--danger-bg)',
            border: '1px solid var(--danger-color)', borderRadius: '10px',
            padding: '12px 16px', fontSize: '0.92rem', lineHeight: 1.5, marginBottom: '20px'
          }}>{message}</p>
        )}

        {erfolgsText && (
          <p role="status" style={{
            color: 'var(--text-main)', background: 'var(--btn-secondary)',
            border: '1px solid var(--border-color)', borderRadius: '10px',
            padding: '12px 16px', fontSize: '0.92rem', lineHeight: 1.5, marginBottom: '20px'
          }}>{erfolgsText}</p>
        )}

        <form onSubmit={handleSubmit} style={{display: 'flex', flexDirection: 'column', gap: '20px'}}>
          <input
            type="text"
            placeholder={modus === MODUS.VERGESSEN ? "Benutzername oder E-Mail" : "Benutzername"}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
          {modus === MODUS.REGISTRIEREN && (
            <input type="email" placeholder="E-Mail-Adresse" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          )}
          {modus !== MODUS.VERGESSEN && (
            <input type="password" placeholder="Passwort" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={modus === MODUS.REGISTRIEREN ? "new-password" : "current-password"} />
          )}
          <button type="submit" className="primary-btn" disabled={busy} style={{marginTop: '10px', width: '100%', opacity: busy ? 0.7 : 1, cursor: busy ? 'progress' : 'pointer'}}>
            {knopfText}
          </button>
        </form>

        <div style={{marginTop: '32px', display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '0.95rem'}}>
          {modus === MODUS.ANMELDEN && (
            <>
              <button type="button" onClick={() => wechsleZu(MODUS.VERGESSEN)} className="link-button">
                Passwort vergessen?
              </button>
              <button type="button" onClick={() => wechsleZu(MODUS.REGISTRIEREN)} className="link-button">
                Konto erstellen
              </button>
            </>
          )}
          {modus !== MODUS.ANMELDEN && (
            <button type="button" onClick={() => wechsleZu(MODUS.ANMELDEN)} className="link-button">
              Zurück zur Anmeldung
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default AuthScreen;
