import { useState } from 'react';
import AuthScreen from '../auth/AuthScreen';
import { ChevronRight, Infinity, Compass, HelpCircle, Flame, RefreshCw, CheckCircle2, Copy } from 'lucide-react';

function LandingPage({ onLoginSuccess, activeTheme, setActiveTheme }) {
  const [showLoginDrawer, setShowLoginDrawer] = useState(false);

  // 3D Tilt Card Hover Effect
  const handleMouseMove = (e) => {
    const card = e.currentTarget;
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    const xc = rect.width / 2;
    const yc = rect.height / 2;
    
    const angleX = (yc - y) / 10;
    const angleY = (x - xc) / 10;
    
    card.style.transform = `perspective(1000px) rotateX(${angleX}deg) rotateY(${angleY}deg) scale(1.05)`;
    if (card.parentElement) {
      card.parentElement.style.zIndex = '10';
    }
    
    const glare = card.querySelector('.glare-overlay');
    if (glare) {
      glare.style.opacity = '0.7';
      glare.style.background = `radial-gradient(circle at ${x}px ${y}px, rgba(255,255,255,0.45) 0%, transparent 65%)`;
    }
  };

  const handleMouseLeave = (e) => {
    const card = e.currentTarget;
    card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale(1)';
    if (card.parentElement) {
      card.parentElement.style.zIndex = card.dataset.baseZindex || '2';
    }
    const glare = card.querySelector('.glare-overlay');
    if (glare) {
      glare.style.opacity = '0';
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-main)', position: 'relative', overflowX: 'hidden' }}>
      
      {/* 1. HEADER & NAVIGATION */}
      <nav style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '60px',
        background: 'var(--nav-bg)',
        backdropFilter: 'saturate(180%) blur(20px)',
        WebkitBackdropFilter: 'saturate(180%) blur(20px)',
        borderBottom: '1px solid var(--border-color)',
        zIndex: 999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '0 20px',
        boxSizing: 'border-box'
      }}>
        <div style={{ width: '100%', maxWidth: '1200px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <svg viewBox="0 0 24 24" width="34" height="34" fill="none" stroke="var(--accent-color)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2.2c.5 0 .8.3 1 .7 3.3.5 5.8 3.4 5.8 7.1 0 4-3.4 7.2-7.8 7.2S4.2 14 4.2 10c0-3.7 2.5-6.6 5.8-7.1.2-.4.5-.7 1-.7z" />
              <path d="M9.5 3.2L10.5 1.5h3l1 1.7" />
              <polygon points="12,7.5 14.2,10.2 12,12.9 9.8,10.2" fill="#C4923E" stroke="none" />
              <circle cx="12" cy="5.2" r="1" fill="var(--accent-color)" stroke="none" />
              <circle cx="16" cy="7.8" r="1" fill="var(--accent-color)" stroke="none" />
              <circle cx="14.8" cy="12.5" r="1" fill="var(--accent-color)" stroke="none" />
              <circle cx="9.2" cy="12.5" r="1" fill="var(--accent-color)" stroke="none" />
              <circle cx="8" cy="7.8" r="1" fill="var(--accent-color)" stroke="none" />
            </svg>
            <span style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--text-main)', letterSpacing: '-0.02em' }}>
              Grana
            </span>
          </div>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
            <button 
              className="secondary-btn" 
              onClick={() => setShowLoginDrawer(true)}
              style={{ padding: '8px 18px', fontSize: '0.85rem', background: 'transparent', color: 'var(--text-main)', cursor: 'pointer' }}
            >
              Anmelden
            </button>
            <button 
              className="primary-btn" 
              onClick={() => setShowLoginDrawer(true)}
              style={{ padding: '8px 20px', fontSize: '0.85rem', background: 'var(--accent-color)', color: 'var(--accent-text)', borderRadius: '20px', cursor: 'pointer' }}
            >
              Registrieren
            </button>
          </div>
        </div>
      </nav>

      {/* 2. HERO SECTION */}
      <section style={{
        maxWidth: '1200px',
        margin: '0 auto',
        padding: '120px 20px 80px 20px',
        display: 'grid',
        gridTemplateColumns: '1.2fr 0.8fr',
        gap: '60px',
        alignItems: 'center',
        boxSizing: 'border-box'
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '25px', textAlign: 'left' }}>
          <h1 style={{ fontSize: '4.2rem', fontWeight: 800, lineHeight: 1.1, letterSpacing: '-0.03em', margin: 0 }}>
            Beherrsche den Stack.<br />
            <span style={{ background: 'linear-gradient(135deg, #C4923E 0%, #B89324 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              Optimiere dein Deck.
            </span>
          </h1>
          <p style={{ fontSize: '1.25rem', color: 'var(--text-muted)', margin: 0, lineHeight: 1.6, maxWidth: '600px' }}>
            Schließe dich ambitionierten MTG-Spielern an. Analysiere deine Decks mit unserer KI-gestützten Rules-Engine, finde verborgene Combos und checke deine Deckliste auf Format-Konformität in Sekunden. Unfehlbar wie ein Pro Tour Judge.
          </p>
          <div style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', marginTop: '10px' }}>
            <button 
              className="primary-btn" 
              onClick={() => setShowLoginDrawer(true)}
              style={{ padding: '16px 32px', fontSize: '1.05rem', borderRadius: '30px', fontWeight: 600, cursor: 'pointer' }}
            >
              Jetzt kostenlos starten <ChevronRight size={18} />
            </button>
            <button 
              className="secondary-btn" 
              onClick={() => setShowLoginDrawer(true)}
              style={{ padding: '16px 32px', fontSize: '1.05rem', borderRadius: '30px', fontWeight: 600, background: 'var(--btn-secondary)', cursor: 'pointer' }}
            >
              Schiedsrichter fragen
            </button>
          </div>
        </div>

        {/* Tactile 3D-Tilt Card Previews */}
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', position: 'relative', height: '400px' }}>
          
          {/* Card 1 Wrapper (Godo) */}
          <div style={{
            position: 'absolute',
            transform: 'rotate(-8deg) translateX(-40px)',
            zIndex: 2,
            transition: 'z-index 0.1s ease'
          }}>
            <div 
              className="mtg-card-3d"
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
              data-base-zindex="2"
              style={{
                width: '240px',
                height: '335px',
                borderRadius: '4.75% / 3.5%',
                overflow: 'hidden',
                cursor: 'pointer',
                transition: 'transform 0.1s ease',
                boxShadow: '0 20px 45px rgba(0,0,0,0.5)',
                transform: 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale(1)'
              }}
            >
              <img 
                src="https://api.scryfall.com/cards/named?exact=Godo,%20Bandit%20Warlord&format=image" 
                alt="Godo, Bandit Warlord" 
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
              <div className="glare-overlay" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, pointerEvents: 'none', opacity: 0, transition: 'opacity 0.1s ease' }} />
            </div>
          </div>

          {/* Card 2 Wrapper (Helm) */}
          <div style={{
            position: 'absolute',
            transform: 'rotate(6deg) translateX(50px) translateY(20px)',
            zIndex: 3,
            transition: 'z-index 0.1s ease'
          }}>
            <div 
              className="mtg-card-3d"
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
              data-base-zindex="3"
              style={{
                width: '240px',
                height: '335px',
                borderRadius: '4.75% / 3.5%',
                overflow: 'hidden',
                cursor: 'pointer',
                transition: 'transform 0.1s ease',
                boxShadow: '0 20px 50px rgba(0,0,0,0.6)',
                transform: 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale(1)'
              }}
            >
              <img 
                src="https://api.scryfall.com/cards/named?exact=Helm%20of%20the%20Host&format=image" 
                alt="Helm of the Host" 
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
              <div className="glare-overlay" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, pointerEvents: 'none', opacity: 0, transition: 'opacity 0.1s ease' }} />
            </div>
          </div>

        </div>
      </section>

      {/* 3. Statistik-Leiste entfernt: die drei Zahlen ("142.800+ Analysierte
          Decks", "99.98% Schiedsrichter-Präzision", "1.4M+ Verifizierte
          Combos") waren frei erfunden. Auf der öffentlichen Verkaufsseite eines
          kostenpflichtigen Angebots wären das irreführende Werbeaussagen --
          insbesondere eine unbelegbare Genauigkeitsangabe zur KI. */}

      {/* 4. FEATURE SHOWCASE */}
      <section style={{
        maxWidth: '1200px',
        margin: '0 auto',
        padding: '100px 20px',
        boxSizing: 'border-box'
      }}>
        <h2 style={{ textAlign: 'center', fontSize: '2.8rem', fontWeight: 800, marginBottom: '60px', letterSpacing: '-0.03em' }}>
          Entwickelt für Spikes & Johnnies
        </h2>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '40px'
        }}>
          {/* Feature 1 */}
          <div className="content-card" style={{ padding: '40px', display: 'flex', flexDirection: 'column', gap: '20px', margin: 0 }}>
            <div style={{ color: '#C4923E', background: 'rgba(196, 146, 62, 0.1)', padding: '12px', borderRadius: '12px', width: 'fit-content' }}>
              <HelpCircle size={28} />
            </div>
            <h3 style={{ fontSize: '1.4rem', margin: 0, fontWeight: 700 }}>24/7 Live Rules Judge</h3>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.98rem', lineHeight: 1.5 }}>
              Erhalte präzise Entscheidungen bei komplexen Interaktionen (z.B. Layers, Mutate-Stacks oder Stapelauflösungen) direkt nach den offiziellen *Magic Comprehensive Rules*.
            </p>
          </div>

          {/* Feature 2 */}
          <div className="content-card" style={{ padding: '40px', display: 'flex', flexDirection: 'column', gap: '20px', margin: 0 }}>
            <div style={{ color: '#0071E3', background: 'rgba(0, 113, 227, 0.1)', padding: '12px', borderRadius: '12px', width: 'fit-content' }}>
              <Infinity size={28} />
            </div>
            <h3 style={{ fontSize: '1.4rem', margin: 0, fontWeight: 700 }}>Synergie- & Combo-Finder</h3>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.98rem', lineHeight: 1.5 }}>
              Lass deine Decks automatisch scannen. Unsere Engine deckt unendliche Mana- oder Token-Loops über die offizielle *Commander Spellbook API* im Handumdrehen auf.
            </p>
          </div>

          {/* Feature 3 */}
          <div className="content-card" style={{ padding: '40px', display: 'flex', flexDirection: 'column', gap: '20px', margin: 0 }}>
            <div style={{ color: '#30D158', background: 'rgba(48, 209, 88, 0.1)', padding: '12px', borderRadius: '12px', width: 'fit-content' }}>
              <Compass size={28} />
            </div>
            <h3 style={{ fontSize: '1.4rem', margin: 0, fontWeight: 700 }}>Manakurven-Typenfilter</h3>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.98rem', lineHeight: 1.5 }}>
              Analysiere die Verteilung deiner Zaubersprüche separat nach Kreaturen und Nicht-Kreaturen, um dein Gameplay und deine Interaktionseffizienz optimal vorzubereiten.
            </p>
          </div>
        </div>
      </section>

      {/* 5. MANA-THEME SELECTOR WIDGET */}
      <section style={{
        background: 'var(--btn-secondary)',
        borderTop: '1px solid var(--border-color)',
        borderBottom: '1px solid var(--border-color)',
        padding: '60px 20px',
        textAlign: 'center',
        boxSizing: 'border-box'
      }}>
        <div style={{ maxWidth: '600px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px', alignItems: 'center' }}>
          <h4 style={{ fontSize: '1.2rem', fontWeight: 700, margin: 0 }}>Mana-zentriertes Theming</h4>
          <p style={{ fontSize: '0.95rem', color: 'var(--text-muted)', margin: 0 }}>
            Passe die Farbpalette der Plattform an deine Lieblingsgilde oder deine Deckfarbe an. Wähle eine der fünf Manafarben:
          </p>
          <div style={{ display: 'flex', gap: '15px', flexWrap: 'wrap', justifyContent: 'center', marginTop: '10px' }}>
            {[
              { id: 'plains', color: '#FAF8F5', symbol: 'https://svgs.scryfall.io/card-symbols/W.svg', label: 'Plains (Weiß)' },
              { id: 'island', color: '#050E17', symbol: 'https://svgs.scryfall.io/card-symbols/U.svg', label: 'Island (Blau)' },
              { id: 'swamp', color: '#0A0A0C', symbol: 'https://svgs.scryfall.io/card-symbols/B.svg', label: 'Swamp (Schwarz)' },
              { id: 'mountain', color: '#140A0A', symbol: 'https://svgs.scryfall.io/card-symbols/R.svg', label: 'Mountain (Rot)' },
              { id: 'forest', color: '#081009', symbol: 'https://svgs.scryfall.io/card-symbols/G.svg', label: 'Forest (Grün)' },
              { id: 'default', color: 'var(--bg-card)', symbol: '', label: 'Default Dark/Light' }
            ].map(t => (
              <button
                key={t.id}
                type="button"
                onClick={() => setActiveTheme(t.id)}
                style={{
                  width: '44px',
                  height: '44px',
                  borderRadius: '50%',
                  background: t.id === 'default' ? 'var(--bg-card)' : t.color,
                  border: activeTheme === t.id ? '2.5px solid var(--accent-color)' : '1px solid var(--border-color)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  transition: 'all 0.2s',
                  boxShadow: activeTheme === t.id ? '0 0 10px var(--accent-color)' : 'none'
                }}
                title={t.label}
              >
                {t.symbol ? (
                  <img src={t.symbol} alt="" style={{ width: '26px', height: '26px' }} />
                ) : (
                  <span style={{ fontSize: '0.85rem', fontWeight: 'bold', color: 'var(--text-main)' }}>D</span>
                )}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* 6. FINAL CALL TO ACTION */}
      <section style={{
        maxWidth: '800px',
        margin: '0 auto',
        padding: '120px 20px',
        textAlign: 'center',
        boxSizing: 'border-box'
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '30px', alignItems: 'center' }}>
          <h2 style={{ fontSize: '3rem', fontWeight: 800, margin: 0, letterSpacing: '-0.03em' }}>
            Bist du bereit, deine Win-Rate zu maximieren?
          </h2>
          <p style={{ fontSize: '1.2rem', color: 'var(--text-muted)', margin: 0, maxWidth: '600px', lineHeight: 1.6 }}>
            Erstelle noch heute deine kostenlose Deck-Bibliothek. Importiere deine Arena-Listen oder scanne deine Ordner im Handumdrehen.
          </p>
          <button 
            className="primary-btn" 
            onClick={() => setShowLoginDrawer(true)}
            style={{ padding: '16px 36px', fontSize: '1.1rem', borderRadius: '30px', fontWeight: 700, cursor: 'pointer' }}
          >
            Jetzt kostenlos anmelden
          </button>
        </div>
      </section>

      {/* 7. SLIDE-IN FRICTIONLESS LOGIN DRAWER */}
      {showLoginDrawer && (
        <div 
          onClick={() => setShowLoginDrawer(false)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.5)',
            backdropFilter: 'blur(8px)',
            WebkitBackdropFilter: 'blur(8px)',
            zIndex: 9999,
            display: 'flex',
            justifyContent: 'flex-end'
          }}
        >
          <div 
            onClick={e => e.stopPropagation()}
            style={{
              width: '100%',
              maxWidth: '460px',
              height: '100%',
              background: 'var(--bg-card)',
              borderLeft: '1px solid var(--border-color)',
              boxShadow: '-10px 0 30px rgba(0,0,0,0.3)',
              padding: '60px 30px',
              boxSizing: 'border-box',
              position: 'relative',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center'
            }}
          >
            {/* Close button */}
            <button 
              onClick={() => setShowLoginDrawer(false)}
              style={{
                position: 'absolute',
                top: '25px',
                right: '25px',
                background: 'none',
                border: 'none',
                color: 'var(--text-muted)',
                fontSize: '1.5rem',
                cursor: 'pointer',
                fontWeight: 'bold'
              }}
            >
              ✕
            </button>

            <div>
              <AuthScreen onLoginSuccess={(username, token, role) => {
                setShowLoginDrawer(false);
                onLoginSuccess(username, token, role);
              }} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default LandingPage;
