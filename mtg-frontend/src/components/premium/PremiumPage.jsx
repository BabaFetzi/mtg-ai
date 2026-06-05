import { useNavigate } from 'react-router-dom';

const CheckIcon = ({ color = "#30D158", size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: '2px' }}>
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const LockIcon = ({ color = "var(--text-muted)", size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: '2px', opacity: 0.6 }}>
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
);

function PremiumPage({ currentUser, userRole, setUserRole }) {
  const navigate = useNavigate();

  return (
    <div className="apple-main-container" style={{ paddingTop: '20px' }}>
      <div style={{ maxWidth: '1000px', margin: '0 auto', animation: 'fadeIn 0.6s ease' }}>
        
        {/* Header Section */}
        <div style={{ textAlign: 'center', marginBottom: '50px' }}>
          <span style={{
            background: 'var(--btn-secondary)',
            color: 'var(--text-main)',
            border: '1px solid var(--border-color)',
            fontSize: '0.8rem',
            fontWeight: 600,
            padding: '6px 16px',
            borderRadius: '980px',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            display: 'inline-block',
            marginBottom: '15px'
          }}>
            Tarifübersicht
          </span>
          <h2 style={{ fontSize: '3rem', letterSpacing: '-0.03em', marginBottom: '15px' }}>
            Finde den passenden Tarif.
          </h2>
          <p style={{ fontSize: '1.15rem', color: 'var(--text-muted)', maxWidth: '600px', margin: '0 auto' }}>
            Erweitere deine Möglichkeiten mit fortschrittlichen KI-Analysen und unbegrenzten Tools für deine Decks.
          </p>
        </div>

        {/* Side-by-Side Pricing Cards */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '30px',
          alignItems: 'stretch',
          marginBottom: '50px'
        }}>
          
          {/* Card 1: Free Tier */}
          <div 
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: '24px',
              padding: '40px',
              boxShadow: '0 8px 30px var(--shadow-color)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              position: 'relative'
            }} 
            className="pricing-card"
          >
            <div>
              <h3 style={{ fontSize: '1.6rem', fontWeight: 600, marginBottom: '5px' }}>Free</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', minHeight: '44px', marginBottom: '20px' }}>
                Kostenloser Zugang zu grundlegenden Such- und Verwaltungsfunktionen.
              </p>
              <div style={{ marginBottom: '30px' }}>
                <span style={{ fontSize: '2.5rem', fontWeight: 700, color: 'var(--text-main)' }}>0,00 €</span>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}> / Monat</span>
              </div>

              {/* Divider */}
              <div style={{ height: '1px', background: 'var(--border-color)', marginBottom: '30px' }} />

              {/* Feature List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '40px' }}>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="var(--text-muted)" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.95rem' }}>Standard-Kartensuche & Scryfall-Preise</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="var(--text-muted)" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.95rem' }}>Bis zu 3 Decks erstellen</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="var(--text-muted)" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.95rem' }}>Sammlungsverwaltung in Alben</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', opacity: 0.6 }}>
                  <LockIcon />
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.95rem', textDecoration: 'line-through' }}>KI-Deck-Analyse & Stärken/Schwächen</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', opacity: 0.6 }}>
                  <LockIcon />
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.95rem', textDecoration: 'line-through' }}>KI-Synergie & Combo Scanner</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', opacity: 0.6 }}>
                  <LockIcon />
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.95rem', textDecoration: 'line-through' }}>24/7 Level 3 KI-Schiedsrichter Chat</span>
                </div>
              </div>
            </div>

            {/* Action Button */}
            <div style={{ marginTop: 'auto' }}>
              <button 
                className="secondary-btn" 
                style={{
                  width: '100%',
                  cursor: 'default',
                  opacity: userRole !== 'premium' ? 0.8 : 0.4,
                  pointerEvents: 'none',
                  background: 'var(--btn-secondary)',
                  border: '1px solid var(--border-color)',
                  color: 'var(--text-main)',
                  fontWeight: 600
                }}
              >
                {userRole !== 'premium' ? 'Aktueller Tarif' : 'Kostenloses Basis-Konto'}
              </button>
            </div>
          </div>

          {/* Card 2: Pro Tier */}
          <div 
            style={{
              background: 'var(--bg-card)',
              border: '2px solid #0071E3',
              borderRadius: '24px',
              padding: '40px',
              boxShadow: '0 12px 40px var(--shadow-color)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              position: 'relative'
            }} 
            className="pricing-card highlighted"
          >
            
            {/* Best Value Badge */}
            <div style={{
              position: 'absolute',
              top: '-15px',
              right: '25px',
              background: 'linear-gradient(135deg, #0071E3, #30D158)',
              color: 'white',
              fontSize: '0.75rem',
              fontWeight: 700,
              padding: '4px 14px',
              borderRadius: '20px',
              boxShadow: '0 4px 10px rgba(0, 113, 227, 0.25)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em'
            }}>
              Empfohlen
            </div>

            <div>
              <h3 style={{ fontSize: '1.6rem', fontWeight: 700, marginBottom: '5px', color: 'var(--text-main)' }}>Grana Pro</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', minHeight: '44px', marginBottom: '20px' }}>
                Voller Zugriff auf fortgeschrittene KI-Analysen, Combo-Scanner und Schiedsrichter.
              </p>
              <div style={{ marginBottom: '30px' }}>
                <span style={{ fontSize: '2.5rem', fontWeight: 700, color: 'var(--text-main)' }}>4,99 €</span>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}> / Monat</span>
              </div>

              {/* Divider */}
              <div style={{ height: '1px', background: 'var(--border-color)', marginBottom: '30px' }} />

              {/* Feature List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '40px' }}>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="#30D158" />
                  <strong style={{ color: 'var(--text-main)', fontSize: '0.95rem', fontWeight: 600 }}>Unbegrenzte Decks erstellen</strong>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="#30D158" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.95rem' }}>KI-Deck-Analyse & Stärken/Schwächen-Profil</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="#30D158" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.95rem' }}>KI-Synergie & Combo Scanner (Sammlung & Decks)</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="#30D158" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.95rem' }}>24/7 Level 3 KI-Schiedsrichter (Rules Judge Chat)</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="#30D158" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.95rem' }}>Priorisierte Abfragen & schnelleres Scryfall-Caching</span>
                </div>
              </div>
            </div>

            {/* Action Button / Premium State */}
            <div style={{ marginTop: 'auto' }}>
              {userRole === 'premium' ? (
                <div style={{ textAlign: 'center' }}>
                  <div style={{ color: '#30D158', fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '15px' }}>
                    <CheckIcon color="#30D158" size={22} /> Premium Aktiv
                  </div>
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
                    style={{
                      width: '100%',
                      background: 'var(--btn-secondary)',
                      color: 'var(--text-main)',
                      border: '1px solid var(--border-color)',
                      padding: '12px 20px',
                      fontSize: '0.95rem'
                    }}
                  >
                    Als Entwickler downgraden (Testen)
                  </button>
                </div>
              ) : (
                <div>
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
                      background: 'linear-gradient(135deg, #0071E3 0%, #0077ED 100%)',
                      border: 'none',
                      color: 'white',
                      padding: '16px 32px',
                      fontSize: '1.1rem',
                      fontWeight: 600,
                      borderRadius: '980px',
                      boxShadow: '0 8px 24px rgba(0, 113, 227, 0.25)',
                      cursor: 'pointer'
                    }}
                  >
                    Jetzt abonnieren
                  </button>
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '12px', textAlign: 'center', marginBottom: 0 }}>
                    Monatlich kündbar. Sichere Abrechnung über Stripe.
                  </p>
                </div>
              )}
            </div>
          </div>
          
        </div>
      </div>
    </div>
  );
}

export default PremiumPage;
