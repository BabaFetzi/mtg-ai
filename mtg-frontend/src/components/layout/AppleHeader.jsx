import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Icons from '../../utils/Icons';
import { FEATURES } from '../../config';

// Die sechs Farbkreise standen dauerhaft neben den Seitenlinks und sahen aus
// wie Bedienelemente für die Seite, auf der man gerade ist. Sie sind eine
// Einstellung -- und Einstellungen gehören unter den Namen.
const FARBWELTEN = [
  { id: 'default', color: 'transparent', symbol: '', label: 'Standard' },
  { id: 'plains', color: '#FAF8F5', symbol: 'https://svgs.scryfall.io/card-symbols/W.svg', label: 'Ebene' },
  { id: 'island', color: '#070F18', symbol: 'https://svgs.scryfall.io/card-symbols/U.svg', label: 'Insel' },
  { id: 'swamp', color: '#060608', symbol: 'https://svgs.scryfall.io/card-symbols/B.svg', label: 'Sumpf' },
  { id: 'mountain', color: '#0E0707', symbol: 'https://svgs.scryfall.io/card-symbols/R.svg', label: 'Gebirge' },
  { id: 'forest', color: '#050A06', symbol: 'https://svgs.scryfall.io/card-symbols/G.svg', label: 'Wald' },
];

function AppleHeader({ currentUser, setCurrentUser, isDarkMode, setIsDarkMode, setIsJudgeOpen, activeTheme, setActiveTheme }) {
  const navigate = useNavigate();
  const [hoveredNav, setHoveredNav] = useState(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [kontoOffen, setKontoOffen] = useState(false);
  const timeoutRef = useRef(null);
  const kontoRef = useRef(null);

  // Klick daneben und Escape schliessen das Konto-Menü -- sonst bleibt es
  // offen stehen, während man schon wieder auf der Seite arbeitet.
  useEffect(() => {
    if (!kontoOffen) return undefined;
    const beiKlick = (e) => {
      if (kontoRef.current && !kontoRef.current.contains(e.target)) setKontoOffen(false);
    };
    const beiTaste = (e) => { if (e.key === 'Escape') setKontoOffen(false); };
    document.addEventListener('mousedown', beiKlick);
    window.addEventListener('keydown', beiTaste);
    return () => {
      document.removeEventListener('mousedown', beiKlick);
      window.removeEventListener('keydown', beiTaste);
    };
  }, [kontoOffen]);

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
        <li className="apple-nav-item" style={{marginLeft: 'auto'}} onMouseEnter={() => handleMouseEnter(null)}>
          <div className="konto-menu" ref={kontoRef}>
            <button
              type="button"
              className="konto-knopf"
              onClick={() => setKontoOffen((offen) => !offen)}
              aria-expanded={kontoOffen}
              aria-haspopup="true"
            >
              <span className="konto-kuerzel" aria-hidden="true">
                {(currentUser || '?').charAt(0).toUpperCase()}
              </span>
              <span className="konto-name">{currentUser}</span>
              <span className="konto-pfeil" aria-hidden="true">▾</span>
            </button>

            {kontoOffen && (
              <div className="konto-klappe">
                <p className="konto-kopf">Angemeldet als <strong>{currentUser}</strong></p>

                <div className="konto-gruppe">
                  <span className="konto-titel">Darstellung</span>
                  <button
                    type="button"
                    className="konto-eintrag"
                    onClick={() => setIsDarkMode(!isDarkMode)}
                  >
                    {isDarkMode ? <Icons.Sun /> : <Icons.Moon />}
                    {isDarkMode ? 'Helles Design' : 'Dunkles Design'}
                  </button>
                </div>

                <div className="konto-gruppe">
                  <span className="konto-titel">Farbwelt</span>
                  <div className="konto-farben">
                    {FARBWELTEN.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        className={`konto-farbe${activeTheme === t.id ? ' aktiv' : ''}`}
                        onClick={() => setActiveTheme(t.id)}
                        aria-pressed={activeTheme === t.id}
                        title={t.label}
                      >
                        {t.symbol
                          ? <img src={t.symbol} alt="" style={{ background: t.color }} />
                          : <span className="konto-farbe-standard" aria-hidden="true">S</span>}
                        <span className="konto-farbe-name">{t.label}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="konto-gruppe">
                  <button
                    type="button"
                    className="konto-eintrag"
                    onClick={() => { setKontoOffen(false); navigate('/premium'); }}
                  >
                    Abonnement verwalten
                  </button>
                  <button
                    type="button"
                    className="konto-eintrag"
                    onClick={() => { setKontoOffen(false); setCurrentUser(null); }}
                  >
                    Abmelden
                  </button>
                </div>
              </div>
            )}
          </div>
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
                    {FEATURES.livePlayfield && (
                        <a onClick={() => {navigate('/playfield'); setIsMenuOpen(false); setHoveredNav(null);}}>Spielfeld (Live Playfield)</a>
                    )}
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
