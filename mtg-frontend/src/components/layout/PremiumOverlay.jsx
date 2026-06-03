import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

function PremiumOverlay() {
  const navigate = useNavigate();
  const [showModal, setShowModal] = useState(false);

  return (
    <>
      {/* Blurred overlay wrapper */}
      <div 
        onClick={() => setShowModal(true)}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.25)',
          backdropFilter: 'blur(10px) saturate(140%)',
          WebkitBackdropFilter: 'blur(10px) saturate(140%)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          borderRadius: '24px',
          zIndex: 90,
          padding: '20px',
          textAlign: 'center',
          cursor: 'pointer',
          transition: 'all 0.3s ease'
        }}
      >
        <div style={{
          background: 'rgba(28, 28, 30, 0.85)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          padding: '25px 35px',
          borderRadius: '20px',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.5)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
          transform: 'scale(1)',
          transition: 'transform 0.2s ease',
          maxWidth: '320px'
        }}
        onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.05)'}
        onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
        >
          <div style={{
            fontSize: '1.8rem',
            background: 'linear-gradient(135deg, #FFD60A, #FF9500)',
            width: '50px',
            height: '50px',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 0 15px rgba(255, 214, 10, 0.4)'
          }}>
            🔑
          </div>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, color: '#FFFFFF' }}>Premium Feature</h3>
          <p style={{ color: '#E5E5EA', fontSize: '0.85rem', margin: 0, lineHeight: '1.4' }}>
            Inhalt verborgen. Klicke hier, um das vollständige Analyse-Dossier freizuschalten.
          </p>
        </div>
      </div>

      {/* Interactive Upsell Modal */}
      {showModal && (
        <div 
          className="modal-overlay" 
          onClick={() => setShowModal(false)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.85)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 100000,
            animation: 'fadeIn 0.2s ease-out'
          }}
        >
          <div 
            className="modal-content"
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: '24px',
              padding: '40px',
              maxWidth: '550px',
              width: '90%',
              boxShadow: '0 30px 60px rgba(0, 0, 0, 0.4)',
              position: 'relative',
              textAlign: 'center',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center'
            }}
          >
            {/* Close Button */}
            <button 
              onClick={() => setShowModal(false)}
              style={{
                position: 'absolute',
                top: '20px',
                right: '20px',
                background: 'var(--btn-secondary)',
                border: 'none',
                color: 'var(--text-main)',
                width: '36px',
                height: '36px',
                borderRadius: '50%',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 'bold',
                fontSize: '1rem'
              }}
            >
              ✕
            </button>

            {/* Icon */}
            <div style={{
              fontSize: '3rem',
              marginBottom: '20px',
              animation: 'bounce 2s infinite'
            }}>
              🚀
            </div>

            {/* Heading */}
            <h2 style={{ fontSize: '2rem', fontWeight: 800, margin: '0 0 10px 0', letterSpacing: '-0.02em' }}>
              Schalte MTG Pro frei.
            </h2>
            
            <p style={{ fontSize: '1.05rem', color: 'var(--text-muted)', marginBottom: '30px', maxWidth: '440px' }}>
              Dein Deck hat ungenutztes Potenzial! Entfessle die volle Power mit KI-gestützten Spielstärke-Analysen und Deck-Optimierungen.
            </p>

            {/* Highlights List */}
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '15px',
              width: '100%',
              textAlign: 'left',
              background: 'var(--btn-secondary)',
              padding: '24px',
              borderRadius: '16px',
              marginBottom: '30px',
              boxSizing: 'border-box',
              border: '1px solid var(--border-color)'
            }}>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                <span style={{ fontSize: '1.2rem' }}>💡</span>
                <div>
                  <strong style={{ display: 'block', fontSize: '0.95rem', color: 'var(--text-main)' }}>KI-Schwächen & Radar Chart</strong>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Erfahre präzise Scores für Card Draw, Removal, Ramp und Wincons.</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                <span style={{ fontSize: '1.2rem' }}>♾️</span>
                <div>
                  <strong style={{ display: 'block', fontSize: '0.95rem', color: 'var(--text-main)' }}>Interaktiver Combo-Finder</strong>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Entdecke versteckte unendliche Combos in deiner Deckliste.</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                <span style={{ fontSize: '1.2rem' }}>💬</span>
                <div>
                  <strong style={{ display: 'block', fontSize: '0.95rem', color: 'var(--text-main)' }}>24/7 MTG Rules Judge Chat</strong>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Kläre knifflige Regelfragen sofort mit unserem KI-Schiedsrichter.</span>
                </div>
              </div>
            </div>

            {/* CTA Button */}
            <button 
              className="primary-btn" 
              onClick={() => {
                setShowModal(false);
                navigate('/premium');
              }}
              style={{
                width: '100%',
                padding: '16px',
                fontSize: '1.1rem',
                fontWeight: 700,
                borderRadius: '14px',
                justifyContent: 'center',
                boxShadow: '0 8px 24px rgba(0, 113, 227, 0.35)',
                background: 'linear-gradient(135deg, #0071E3 0%, #0077ED 100%)'
              }}
            >
              Jetzt Upgraden für 5.99€/Monat
            </button>
            
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '12px' }}>
              Jederzeit kündbar · 7 Tage Geld-zurück-Garantie
            </span>
          </div>
        </div>
      )}
    </>
  );
}

export default PremiumOverlay;
