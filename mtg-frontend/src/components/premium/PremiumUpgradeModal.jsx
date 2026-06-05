import { useNavigate } from 'react-router-dom';
import { Sparkles, Infinity, MessageSquare, Lock, X } from 'lucide-react';

function PremiumUpgradeModal({ isOpen, onClose }) {
  const navigate = useNavigate();

  if (!isOpen) return null;

  return (
    <div 
      className="modal-overlay" 
      onClick={onClose}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 999999,
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
          onClick={onClose}
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
            fontSize: '1rem',
            transition: 'all 0.2s ease'
          }}
          onMouseEnter={(e) => e.currentTarget.style.filter = 'brightness(1.2)'}
          onMouseLeave={(e) => e.currentTarget.style.filter = 'brightness(1)'}
        >
          <X size={18} />
        </button>

        {/* Premium Gold Icon Header */}
        <div style={{
          background: 'linear-gradient(135deg, #C4923E, #9E7127)',
          width: '70px',
          height: '70px',
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 0 20px rgba(196, 146, 62, 0.4)',
          marginBottom: '20px',
          color: '#FFFFFF'
        }}>
          <Lock size={32} />
        </div>

        {/* Heading */}
        <h2 style={{ fontSize: '2rem', fontWeight: 800, margin: '0 0 10px 0', letterSpacing: '-0.02em', color: 'var(--text-main)' }}>
          Schalte Grana Pro frei.
        </h2>
        
        <p style={{ fontSize: '1.05rem', color: 'var(--text-muted)', marginBottom: '30px', maxWidth: '440px', lineHeight: '1.5' }}>
          Erstelle unbegrenzte Decks und nutze unsere Smart-Analysen und den Rules Judge, um deine Gewinnrate zu maximieren!
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
            <span style={{ color: '#C4923E', display: 'flex', alignItems: 'center' }}><Infinity size={20} /></span>
            <div>
              <strong style={{ display: 'block', fontSize: '0.95rem', color: 'var(--text-main)' }}>Unbegrenzte Decks</strong>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Erstelle beliebig viele Decks ohne Einschränkungen.</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <span style={{ color: '#C4923E', display: 'flex', alignItems: 'center' }}><Sparkles size={20} /></span>
            <div>
              <strong style={{ display: 'block', fontSize: '0.95rem', color: 'var(--text-main)' }}>Stärken & Schwächen-Analyse</strong>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Erfahre präzise Scores für Card Draw, Removal, Ramp und Wincons.</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <span style={{ color: '#C4923E', display: 'flex', alignItems: 'center' }}><MessageSquare size={20} /></span>
            <div>
              <strong style={{ display: 'block', fontSize: '0.95rem', color: 'var(--text-main)' }}>24/7 Rules Judge Chat</strong>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Kläre knifflige Regelfragen sofort mit unserem Smart Rules Judge.</span>
            </div>
          </div>
        </div>

        {/* CTA Button */}
        <button 
          className="primary-btn" 
          onClick={() => {
            onClose();
            navigate('/premium');
          }}
          style={{
            width: '100%',
            padding: '16px',
            fontSize: '1.1rem',
            fontWeight: 700,
            borderRadius: '14px',
            justifyContent: 'center',
            boxShadow: '0 8px 24px rgba(196, 146, 62, 0.35)',
            background: 'linear-gradient(135deg, #C4923E 0%, #9E7127 100%)',
            color: 'white',
            border: 'none',
            cursor: 'pointer',
            transition: 'all 0.2s ease'
          }}
          onMouseEnter={(e) => e.currentTarget.style.filter = 'brightness(1.1)'}
          onMouseLeave={(e) => e.currentTarget.style.filter = 'brightness(1)'}
        >
          Pro-Mitgliedschaft abschließen (4,99 €/Monat)
        </button>
        
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '12px' }}>
          Jederzeit kündbar · Pro-Vorteile sofort aktiv
        </span>
      </div>
    </div>
  );
}

export default PremiumUpgradeModal;
