import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Icons from '../../utils/Icons';

function AppleHeader({ currentUser, setCurrentUser, isDarkMode, setIsDarkMode, setIsJudgeOpen }) {
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
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter(null)}>
          <span className="apple-nav-link" style={{fontWeight: 600, fontSize: '1rem', opacity: 1}}>MTG Pro</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter('suche')}>
          <span className="apple-nav-link" onClick={() => {navigate('/'); setIsMenuOpen(false); setHoveredNav(null);}}>Suche & KI</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter('sammlung')}>
          <span className="apple-nav-link" onClick={() => {navigate('/sammlung?tab=alben'); setIsMenuOpen(false); setHoveredNav(null);}}>Sammlung</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter('decks')}>
          <span className="apple-nav-link" onClick={() => {navigate('/decks'); setIsMenuOpen(false); setHoveredNav(null);}}>Decks</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter(null)}>
          <span className="apple-nav-link" onClick={() => {navigate('/premium'); setIsMenuOpen(false); setHoveredNav(null);}} style={{fontWeight: 700, color: 'var(--price-color)'}}>MTG Pro Upgrade</span>
        </li>
        <li className="apple-nav-item" style={{marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '15px'}} onMouseEnter={() => handleMouseEnter(null)}>
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
                   <h4>KI-Assistent</h4>
                   <a onClick={() => {navigate('/?view=synergy'); setIsMenuOpen(false); setHoveredNav(null);}}>Synergie-Analyse</a>
                   <a onClick={() => {navigate('/?view=judge'); setIsMenuOpen(false); setHoveredNav(null);}}>MTG Regel-Judge</a>
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
                   <a onClick={() => {navigate('/sammlung?tab=import'); setIsMenuOpen(false); setHoveredNav(null);}}>Massen-Import (CSV)</a>
                   <a onClick={() => {navigate('/sammlung?tab=export'); setIsMenuOpen(false); setHoveredNav(null);}}>Sammlung exportieren</a>
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
