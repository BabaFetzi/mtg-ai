import { useNavigate } from 'react-router-dom';
import { Key } from 'lucide-react';

function PremiumOverlay({ onShowPremiumModal }) {
  const navigate = useNavigate();

  return (
    <div 
      onClick={(e) => {
        e.stopPropagation();
        if (onShowPremiumModal) {
          onShowPremiumModal();
        } else {
          navigate('/premium');
        }
      }}
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
          background: 'linear-gradient(135deg, #C4923E, #9E7127)',
          width: '50px',
          height: '50px',
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 0 15px rgba(196, 146, 62, 0.3)',
          marginBottom: '6px'
        }}>
          <Key size={22} style={{ color: '#FFFFFF' }} />
        </div>
        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, color: '#FFFFFF' }}>Premium Feature</h3>
        <p style={{ color: '#E5E5EA', fontSize: '0.85rem', margin: 0, lineHeight: '1.4' }}>
          Inhalt verborgen. Klicke hier, um das vollständige Analyse-Dossier freizuschalten.
        </p>
      </div>
    </div>
  );
}

export default PremiumOverlay;
