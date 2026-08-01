import { useState } from 'react';

function AuthScreen({ onLoginSuccess }) {
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    const endpoint = isRegister ? "/api/register" : "/api/login";
    const payload = isRegister
      ? { benutzername: username, passwort: password, email }
      : { benutzername: username, passwort: password };
    try {
      const res = await fetch(endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.erfolg) {
        if (isRegister) { setMessage("Konto erstellt. Bitte einloggen."); setIsRegister(false); setPassword(""); }
        else { onLoginSuccess(data.benutzername, data.access_token, data.rolle, data.refresh_token); }
      } else { setMessage(data.error); }
    } catch { setMessage("Serverfehler."); }
  };

  return (
    <div style={{display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: 'var(--bg-main)'}}>
      <div className="content-card" style={{maxWidth: '450px', width: '100%', textAlign: 'center', padding: '60px'}}>
        <h2 style={{fontSize: '2.5rem'}}>Grana</h2>
        <p style={{marginBottom: '40px'}}>{isRegister ? "Erstelle dein Konto." : "Melde dich bei Grana an."}</p>
        {message && <p style={{color: '#FF3B30'}}>{message}</p>}
        <form onSubmit={handleSubmit} style={{display: 'flex', flexDirection: 'column', gap: '20px'}}>
          <input type="text" placeholder="Benutzername" value={username} onChange={(e) => setUsername(e.target.value)} />
          {isRegister && (
            <input type="email" placeholder="E-Mail-Adresse" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          )}
          <input type="password" placeholder="Passwort" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button type="submit" className="primary-btn" style={{marginTop: '10px', width: '100%'}}>Weiter</button>
        </form>
        <p style={{marginTop: '40px', fontSize: '0.95rem'}}><span onClick={() => { setIsRegister(!isRegister); setMessage(""); }} style={{cursor: 'pointer', color: 'var(--text-muted)', fontWeight: 600}}>{isRegister ? "Bereits registriert? Anmelden" : "Konto erstellen"}</span></p>
      </div>
    </div>
  );
}

export default AuthScreen;
