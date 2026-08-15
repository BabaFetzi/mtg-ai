import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import usePremiumPrice from './usePremiumPrice';
import { useMeldung } from '../layout/Meldungen';

const CheckIcon = ({ color = "var(--price-color)", size = 20 }) => (
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
  const { melde, bestaetige } = useMeldung();
  const navigate = useNavigate();
  const { preisText, loading: preisLoading } = usePremiumPrice();
  // Persistente Rückmeldung nach einer Kündigung, damit das Ergebnis eindeutig
  // sichtbar ist (statt nur eines kurzen melde.info()-Popups, das übersehen wird).
  const [cancelInfo, setCancelInfo] = useState(null); // { bis: "TT.MM.JJJJ" | null } oder "downgraded"

  return (
    <div className="apple-main-container" style={{ paddingTop: '20px' }}>
      <div style={{ maxWidth: '1000px', margin: '0 auto', animation: 'fadeIn 0.6s ease' }}>
        
        {/* Header Section */}
        <div style={{ textAlign: 'center', marginBottom: '28px' }}>
          <span style={{
            background: 'var(--btn-secondary)',
            color: 'var(--text-main)',
            border: '1px solid var(--border-color)',
            fontSize: '0.75rem',
            fontWeight: 600,
            padding: '5px 14px',
            borderRadius: '980px',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            display: 'inline-block',
            marginBottom: '12px'
          }}>
            Tarifübersicht
          </span>
          <h2 style={{ fontSize: '2.2rem', letterSpacing: '-0.02em', marginBottom: '10px' }}>
            Finde den passenden Tarif.
          </h2>
          <p style={{ fontSize: '1rem', color: 'var(--text-muted)', maxWidth: '560px', margin: '0 auto' }}>
            Erweitere deine Möglichkeiten mit fortschrittlichen KI-Analysen und unbegrenzten Tools für deine Decks.
          </p>
        </div>

        {/* Side-by-Side Pricing Cards */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: '20px',
          alignItems: 'stretch',
          marginBottom: '30px'
        }}>

          {/* Card 1: Free Tier */}
          <div
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: '18px',
              padding: '28px',
              boxShadow: '0 8px 30px var(--shadow-color)',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              position: 'relative'
            }}
            className="pricing-card"
          >
            <div>
              <h3 style={{ fontSize: '1.4rem', fontWeight: 600, marginBottom: '5px' }}>Free</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '16px' }}>
                Kostenloser Zugang zu grundlegenden Such- und Verwaltungsfunktionen.
              </p>
              <div style={{ marginBottom: '20px' }}>
                <span style={{ fontSize: '2.1rem', fontWeight: 700, color: 'var(--text-main)' }}>0,00 €</span>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}> / Monat</span>
              </div>

              {/* Divider */}
              <div style={{ height: '1px', background: 'var(--border-color)', marginBottom: '20px' }} />

              {/* Feature List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '24px' }}>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="var(--text-muted)" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.88rem' }}>Standard-Kartensuche & Scryfall-Preise</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="var(--text-muted)" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.88rem' }}>Bis zu 3 Decks erstellen</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="var(--text-muted)" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.88rem' }}>Sammlungsverwaltung in Alben</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', opacity: 0.6 }}>
                  <LockIcon />
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.88rem', textDecoration: 'line-through' }}>KI-Deck-Analyse & Stärken/Schwächen</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', opacity: 0.6 }}>
                  <LockIcon />
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.88rem', textDecoration: 'line-through' }}>KI-Synergie & Combo Scanner</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', opacity: 0.6 }}>
                  <LockIcon />
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.88rem', textDecoration: 'line-through' }}>24/7 Level 3 KI-Schiedsrichter Chat</span>
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
              border: '2px solid var(--accent-color)',
              borderRadius: '18px',
              padding: '28px',
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
              top: '-13px',
              right: '22px',
              background: 'var(--accent-color)',
              color: 'var(--accent-text)',
              fontSize: '0.7rem',
              fontWeight: 700,
              padding: '4px 12px',
              borderRadius: '20px',
              textTransform: 'uppercase',
              letterSpacing: '0.05em'
            }}>
              Empfohlen
            </div>

            <div>
              <h3 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '5px', color: 'var(--text-main)' }}>Grana Pro</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '16px' }}>
                Voller Zugriff auf fortgeschrittene KI-Analysen, Combo-Scanner und Schiedsrichter.
              </p>
              <div style={{ marginBottom: '20px' }}>
                <span style={{ fontSize: '2.1rem', fontWeight: 700, color: 'var(--text-main)' }}>
                  {preisLoading ? '…' : (preisText || 'Preis nicht verfügbar')}
                </span>
                {(preisLoading || preisText) && (
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}> / Monat</span>
                )}
              </div>

              {/* Divider */}
              <div style={{ height: '1px', background: 'var(--border-color)', marginBottom: '20px' }} />

              {/* Feature List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '24px' }}>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="var(--price-color)" />
                  <strong style={{ color: 'var(--text-main)', fontSize: '0.88rem', fontWeight: 600 }}>Unbegrenzte Decks erstellen</strong>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="var(--price-color)" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.88rem' }}>KI-Deck-Analyse & Stärken/Schwächen-Profil</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="var(--price-color)" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.88rem' }}>KI-Synergie & Combo Scanner (Sammlung & Decks)</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="var(--price-color)" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.88rem' }}>24/7 Level 3 KI-Schiedsrichter (Rules Judge Chat)</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <CheckIcon color="var(--price-color)" />
                  <span style={{ color: 'var(--text-main)', fontSize: '0.88rem' }}>Priorisierte Abfragen & schnelleres Scryfall-Caching</span>
                </div>
              </div>
            </div>

            {/* Action Button / Premium State */}
            <div style={{ marginTop: 'auto' }}>
              {userRole === 'premium' ? (
                <div style={{ textAlign: 'center' }}>
                  <div style={{ color: 'var(--price-color)', fontSize: '1.05rem', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '15px' }}>
                    <CheckIcon color="var(--price-color)" size={20} /> Premium Aktiv
                  </div>
                  {cancelInfo ? (
                    <div style={{
                      background: 'var(--btn-secondary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '12px',
                      padding: '14px 18px',
                      fontSize: '0.92rem',
                      color: 'var(--text-main)',
                      lineHeight: 1.5
                    }}>
                      ✓ Abo gekündigt.{' '}
                      {cancelInfo.bis
                        ? `Premium bleibt noch bis zum ${cancelInfo.bis} aktiv, danach wird nichts mehr abgebucht.`
                        : 'Premium bleibt bis zum Ende der bezahlten Periode aktiv, danach wird nichts mehr abgebucht.'}
                    </div>
                  ) : (
                  <button
                    className="secondary-btn"
                    onClick={async () => {
                      const sicher = await bestaetige({
                        titel: "Premium-Abo kündigen?",
                        text: "Premium bleibt bis zum Ende der bereits bezahlten Periode aktiv, danach wird nichts mehr abgebucht.",
                        bestaetigenText: "Ja, kündigen",
                        abbrechenText: "Behalten",
                        gefaehrlich: true,
                      });
                      if (!sicher) return;
                      try {
                        // Echte Self-Service-Kündigung: setzt das Stripe-Abo auf
                        // cancel_at_period_end. Das Downgrade auf 'free' erledigt
                        // der Stripe-Webhook am Periodenende automatisch.
                        const res = await fetch('/api/checkout/cancel-subscription', { method: 'POST' });
                        const data = await res.json().catch(() => ({}));

                        if (res.ok && data.erfolg) {
                          const bis = data.laeuft_bis
                            ? new Date(data.laeuft_bis * 1000).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
                            : null;
                          // Persistente, eindeutige Rückmeldung statt nur eines Popups.
                          setCancelInfo({ bis });
                          return;
                        }

                        if (res.status === 401) {
                          melde.fehler("Deine Sitzung ist abgelaufen. Bitte logge dich erneut ein und versuche es noch einmal.");
                          return;
                        }

                        if (data.kein_abo) {
                          // Premium ohne Stripe-Abo (Dev-/Admin-Upgrade): dann gibt es
                          // bei Stripe nichts zu kündigen -- Rolle direkt zurücksetzen.
                          const resRole = await fetch('/api/user/update-role', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ benutzername: currentUser, rolle: 'free' })
                          });
                          if (resRole.ok) {
                            melde.fehler("Für dieses Konto war kein Stripe-Abo hinterlegt (Test-Premium). Die Rolle wurde auf 'free' zurückgesetzt.");
                            setUserRole("free");
                          } else {
                            melde.info(data.error || "Kündigung fehlgeschlagen. Bitte kontaktiere den Support.");
                          }
                          return;
                        }

                        melde.info(data.error || "Kündigung fehlgeschlagen. Bitte versuche es später erneut oder kontaktiere den Support.");
                      } catch (err) {
                        console.error("Kündigung fehlgeschlagen:", err);
                        melde.fehler("Kündigung fehlgeschlagen (Netzwerkfehler). Bitte versuche es später erneut.");
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
                    Abo kündigen
                  </button>
                  )}
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
                            melde.fehler("Stripe ist nicht konfiguriert. Wir leiten dich zur simulierten Upgrade-Seite weiter.");
                          }
                          window.location.href = data.url;
                        } else {
                          melde.fehler("Fehler beim Erstellen der Stripe-Session.");
                        }
                      } catch {
                        melde.fehler("Verbindungsfehler zum Backend.");
                      }
                    }}
                    style={{
                      width: '100%',
                      background: 'var(--accent-color)',
                      border: 'none',
                      color: 'var(--accent-text)',
                      padding: '14px 28px',
                      fontSize: '1.05rem',
                      fontWeight: 600,
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
