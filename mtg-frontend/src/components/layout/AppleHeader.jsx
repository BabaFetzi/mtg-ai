import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Icons from '../../utils/Icons';

function AppleHeader({ currentUser, setCurrentUser, isDarkMode, setIsDarkMode, setIsJudgeOpen, activeTheme, setActiveTheme }) {
  const navigate = useNavigate();
  const [hoveredNav, setHoveredNav] = useState(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const timeoutRef = useRef(null);

  const handleMouseEnter = (navItem) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    if (navItem) {
      setHoveredNav(navItem);
      setIsMenuOpen(true);
    } else {
      setIsMenuOpen(false);
      setHoveredNav(null);
    }
  };

  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => {
      setIsMenuOpen(false);
      setHoveredNav(null);
    }, 250); 
  };

  return (
    <nav className={`apple-nav-container ${isMenuOpen ? 'menu-open' : ''}`} onMouseLeave={handleMouseLeave}>
      <ul className="apple-nav-list">
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter(null)} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="var(--accent-color)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ marginLeft: '10px' }}>
            <path d="M12 2.2c.5 0 .8.3 1 .7 3.3.5 5.8 3.4 5.8 7.1 0 4-3.4 7.2-7.8 7.2S4.2 14 4.2 10c0-3.7 2.5-6.6 5.8-7.1.2-.4.5-.7 1-.7z" />
            <path d="M9.5 3.2L10.5 1.5h3l1 1.7" />
            <polygon points="12,7.5 14.2,10.2 12,12.9 9.8,10.2" fill="#C4923E" stroke="none" />
            <circle cx="12" cy="5.2" r="1" fill="var(--accent-color)" stroke="none" />
            <circle cx="16" cy="7.8" r="1" fill="var(--accent-color)" stroke="none" />
            <circle cx="14.8" cy="12.5" r="1" fill="var(--accent-color)" stroke="none" />
            <circle cx="9.2" cy="12.5" r="1" fill="var(--accent-color)" stroke="none" />
            <circle cx="8" cy="7.8" r="1" fill="var(--accent-color)" stroke="none" />
          </svg>
          <span className="apple-nav-link" style={{fontWeight: 600, fontSize: '1rem', opacity: 1, paddingLeft: 0}}>Grana</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter('suche')}>
          <span className="apple-nav-link" onClick={() => {navigate('/'); setIsMenuOpen(false); setHoveredNav(null);}}>Suche & Analyse</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter('sammlung')}>
          <span className="apple-nav-link" onClick={() => {navigate('/sammlung?tab=alben'); setIsMenuOpen(false); setHoveredNav(null);}}>Sammlung</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter('decks')}>
          <span className="apple-nav-link" onClick={() => {navigate('/decks'); setIsMenuOpen(false); setHoveredNav(null);}}>Decks</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter(null)}>
          <span className="apple-nav-link" onClick={() => {navigate('/premium'); setIsMenuOpen(false); setHoveredNav(null);}} style={{fontWeight: 700, color: 'var(--price-color)'}}>Grana Pro Upgrade</span>
        </li>
        <li className="apple-nav-item" style={{marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '15px'}} onMouseEnter={() => handleMouseEnter(null)}>
          {/* WUBRG theme circles */}
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginRight: '5px' }}>
            {[
              { id: 'plains', color: '#FAF8F5', symbol: 'https://svgs.scryfall.io/card-symbols/W.svg', label: 'Plains' },
              { id: 'island', color: '#070F18', symbol: 'https://svgs.scryfall.io/card-symbols/U.svg', label: 'Island' },
              { id: 'swamp', color: '#060608', symbol: 'https://svgs.scryfall.io/card-symbols/B.svg', label: 'Swamp' },
              { id: 'mountain', color: '#0E0707', symbol: 'https://svgs.scryfall.io/card-symbols/R.svg', label: 'Mountain' },
              { id: 'forest', color: '#050A06', symbol: 'https://svgs.scryfall.io/card-symbols/G.svg', label: 'Forest' },
              { id: 'default', color: 'transparent', symbol: '', label: 'Standard' }
            ].map(t => (
              <button
                key={t.id}
                type="button"
                onClick={() => setActiveTheme(t.id)}
                style={{
                  width: '18px',
                  height: '18px',
                  borderRadius: '50%',
                  background: t.id === 'default' ? 'var(--text-muted)' : t.color,
                  border: activeTheme === t.id ? '2px solid var(--accent-color)' : '1px solid var(--border-color)',
                  cursor: 'pointer',
                  padding: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  transition: 'all 0.15s ease',
                  transform: activeTheme === t.id ? 'scale(1.15)' : 'scale(1)',
                  boxShadow: activeTheme === t.id ? '0 0 5px var(--accent-color)' : 'none',
                  opacity: activeTheme === t.id ? 1 : 0.65
                }}
                title={`Theme: ${t.label}`}
              >
                {t.symbol ? (
                  <img src={t.symbol} alt="" style={{ width: '12px', height: '12px' }} />
                ) : (
                  <span style={{ fontSize: '7px', fontWeight: 'bold', color: 'var(--bg-card)', lineHeight: 1 }}>D</span>
                )}
              </button>
            ))}
          </div>

          <button className="theme-toggle" onClick={() => setIsDarkMode(!isDarkMode)} title="Theme wechseln">
            {isDarkMode ? <Icons.Sun /> : <Icons.Moon />}
          </button>
          <span className="apple-nav-link" style={{color: 'var(--text-muted)'}}>{currentUser}</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter(null)}>
          <span className="apple-nav-link" onClick={() => setCurrentUser(null)}>Abmelden</span>
        </li>
      </ul>

      <div className={`global-mega-menu ${isMenuOpen && hoveredNav ? 'open' : ''}`}>
        <div className="mega-menu-inner">
           <div className={`mega-content-panel ${hoveredNav === 'suche' ? 'active' : ''}`}>
               <div className="dropdown-column">
                   <h4>Entdecken</h4>
                   <a onClick={() => {navigate('/?view=search'); setIsMenuOpen(false); setHoveredNav(null);}}>Kartensuche</a>
                   <a onClick={() => {navigate('/?view=trends'); setIsMenuOpen(false); setHoveredNav(null);}}>Beliebte Karten (Trends)</a>
                   <a href="https://www.cardmarket.com/de/Magic" target="_blank" rel="noopener noreferrer" style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
                     Marktplatz (Cardmarket) <Icons.ExternalLink />
                   </a>
               </div>
               <div className="dropdown-column">
                   <h4>Regeln & Analyse</h4>
                   <a onClick={() => {navigate('/?view=synergy'); setIsMenuOpen(false); setHoveredNav(null);}}>Synergie-Analyse</a>
                   <a onClick={() => {navigate('/?view=judge'); setIsMenuOpen(false); setHoveredNav(null);}}>MTG Rules Judge</a>
                   <a onClick={() => {navigate('/?view=rulebook'); setIsMenuOpen(false); setHoveredNav(null);}}>Offizielles Regelbuch</a>
               </div>
           </div>

           <div className={`mega-content-panel ${hoveredNav === 'sammlung' ? 'active' : ''}`}>
               <div className="dropdown-column">
                   <h4>Portfolio</h4>
                   <a onClick={() => {navigate('/sammlung?tab=alben'); setIsMenuOpen(false); setHoveredNav(null);}}>Alben Übersicht</a>
                   <a onClick={() => {navigate('/sammlung?tab=alben'); setIsMenuOpen(false); setHoveredNav(null);}}>Neues Album anlegen</a>
                   <a onClick={() => {navigate('/sammlung?tab=dashboard'); setIsMenuOpen(false); setHoveredNav(null);}}>Marktwert & Finanzen</a>
               </div>
               <div className="dropdown-column">
                   <h4>Organisation</h4>
                    <a onClick={() => {navigate('/sammlung?tab=wishlist'); setIsMenuOpen(false); setHoveredNav(null);}}>Wunschliste (Wishlist)</a>
                    <a onClick={() => {navigate('/sammlung?tab=import'); setIsMenuOpen(false); setHoveredNav(null);}}>In- und Export (CSV)</a>
               </div>
           </div>

            <div className={`mega-content-panel ${hoveredNav === 'decks' ? 'active' : ''}`}>
                <div className="dropdown-column">
                    <h4>Deck-Management</h4>
                    <a onClick={() => {navigate('/decks?tab=overview'); setIsMenuOpen(false); setHoveredNav(null);}}>Deck-Center</a>
                    <a onClick={() => {navigate('/decks?tab=overview&focus=create'); setIsMenuOpen(false); setHoveredNav(null);}}>Neues Deck erstellen</a>
                </div>
                <div className="dropdown-column">
                    <h4>Analyse & Tools</h4>
                    <a onClick={() => {navigate('/decks?tab=visual'); setIsMenuOpen(false); setHoveredNav(null);}}>Deckliste & Starthand</a>
                    <a onClick={() => {navigate('/decks?tab=stats'); setIsMenuOpen(false); setHoveredNav(null);}}>Stats & Analyse</a>
                </div>
                <div className="dropdown-column">
                    <h4>Export</h4>
                    <a onClick={() => {navigate('/decks?tab=proxy'); setIsMenuOpen(false); setHoveredNav(null);}}>Proxy-Druck (PDF)</a>
                </div>
            </div>
        </div>
      </div>
    </nav>
  );
}

export default AppleHeader;
