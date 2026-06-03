import { useNavigate } from 'react-router-dom';

function PremiumPage({ currentUser, userRole, setUserRole }) {
  const navigate = useNavigate();
  return (
    <div className="apple-main-container">
      <div style={{maxWidth: '850px', margin: '0 auto', animation: 'fadeIn 0.6s ease', paddingTop: '40px'}}>
        <div className="content-card" style={{
          background: 'linear-gradient(135deg, #1C1C1E 0%, #000000 100%)',
          color: '#FFFFFF',
          border: '1px solid #38383A',
          padding: '50px',
          borderRadius: '30px',
          boxShadow: '0 20px 50px rgba(0,0,0,0.4)',
          textAlign: 'center',
          position: 'relative',
          overflow: 'hidden'
        }}>
          <div style={{
            position: 'absolute',
            top: '-150px',
            right: '-150px',
            width: '350px',
            height: '350px',
            background: 'radial-gradient(circle, rgba(0,113,227,0.15) 0%, transparent 70%)',
            pointerEvents: 'none'
          }}></div>
          
          <span style={{
            background: 'linear-gradient(135deg, #0071E3, #30D158)',
            color: 'white',
            fontSize: '0.85rem',
            fontWeight: 700,
            padding: '6px 16px',
            borderRadius: '980px',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            display: 'inline-block',
            marginBottom: '25px'
          }}>MTG Pro Subscription</span>
          
          <h2 style={{color: 'white', fontSize: '3.5rem', letterSpacing: '-0.04em', marginBottom: '15px'}}>Optimiere dein MTG-Erlebnis.</h2>
          <p style={{color: '#98989D', fontSize: '1.2rem', maxWidth: '600px', margin: '0 auto 40px auto'}}>
            Schalte fortgeschrittene KI-Analysen, Combo-Scanner und die Expertise eines virtuellen Level 3 Judges frei.
          </p>
          
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '25px',
            textAlign: 'left',
            marginBottom: '50px',
            maxWidth: '650px',
            margin: '0 auto 50px auto'
          }}>
            {[
              { title: "KI-Judge Regelprüfung", desc: "Erhalte sofortige Antworten auf komplexe MTG-Regelfragen auf L3-Judge-Niveau." },
              { title: "KI-Synergie & Combo Scanner", desc: "Entdecke versteckte Kartenkombinationen und Synergien in deiner Sammlung oder deinen Decks." },
              { title: "KI-Deck-Analyse", desc: "Detaillierte Strategieberichte, Stärken- und Schwächenprofile für deine erstellten Decks." },
              { title: "Unbegrenzter Support & Caching", desc: "Priorisierte Scryfall-Preise und nahtloser Live-Portfoliowert ohne API-Wartezeiten." }
            ].map((feat, idx) => (
              <div key={idx} style={{display: 'flex', gap: '15px', alignItems: 'flex-start'}}>
                <span style={{color: '#30D158', fontSize: '1.4rem', fontWeight: 'bold'}}>✓</span>
                <div>
                  <h4 style={{color: 'white', fontSize: '1.05rem', margin: '0 0 5px 0'}}>{feat.title}</h4>
                  <p style={{color: '#86868B', fontSize: '0.9rem', margin: 0}}>{feat.desc}</p>
                </div>
              </div>
            ))}
          </div>
          
          <div style={{
            background: 'rgba(255,255,255,0.04)',
            borderRadius: '20px',
            padding: '30px',
            maxWidth: '450px',
            margin: '0 auto',
            border: '1px solid rgba(255,255,255,0.08)'
          }}>
            {userRole === 'premium' ? (
              <div>
                <h3 style={{color: '#30D158', fontSize: '1.8rem', marginBottom: '10px'}}>✓ Premium Aktiv</h3>
                <p style={{color: '#98989D', margin: 0}}>Vielen Dank für deine Unterstützung! Du hast vollen Zugriff auf alle KI-Features.</p>
                <button 
                  className="secondary-btn" 
                  onClick={async () => {
                    if (window.confirm("Möchtest du dein Test-Abonnement zu Testzwecken beenden? (Downgrade)")) {
                      const res = await fetch('/api/user/update-role', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ benutzername: currentUser, rolle: 'free' })
                      });
                      if (res.ok) {
                        alert("Abo beendet (Rolle zurückgesetzt auf 'free').");
                        setUserRole("free");
                      }
                    }
                  }}
                  style={{marginTop: '20px', background: 'rgba(255,255,255,0.1)', color: 'white'}}
                >
                  Als Entwickler downgraden (Testen)
                </button>
              </div>
            ) : (
              <div>
                <div style={{marginBottom: '20px'}}>
                  <span style={{fontSize: '2.5rem', fontWeight: 700, color: 'white'}}>4,99 €</span>
                  <span style={{color: '#98989D'}}> / Monat</span>
                </div>
                <button 
                  className="primary-btn" 
                  onClick={async () => {
                    try {
                      const res = await fetch('/api/checkout/create-session', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ benutzername: currentUser, host_url: window.location.origin })
                      });
                      const data = await res.json();
                      if (data && data.url) {
                        if (data.simulated) {
                          alert("Stripe ist nicht konfiguriert. Wir leiten dich zur simulierten Upgrade-Seite weiter.");
                        }
                        window.location.href = data.url;
                      } else {
                        alert("Fehler beim Erstellen der Stripe-Session.");
                      }
                    } catch {
                      alert("Verbindungsfehler zum Backend.");
                    }
                  }}
                  style={{
                    width: '100%',
                    background: 'linear-gradient(135deg, #0071E3, #0077ED)',
                    border: 'none',
                    padding: '16px 32px',
                    fontSize: '1.1rem',
                    fontWeight: 600,
                    color: 'white'
                  }}
                >
                  Jetzt abonnieren
                </button>
                <p style={{color: '#86868B', fontSize: '0.8rem', marginTop: '15px', marginBottom: 0}}>
                  Monatlich kündbar. Sichere Abrechnung über Stripe.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default PremiumPage;
