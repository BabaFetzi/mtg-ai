import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Icons from '../../utils/Icons';
import { bereiche } from './navigation';

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

function GranaLogo() {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="var(--accent-color)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 2.2c.5 0 .8.3 1 .7 3.3.5 5.8 3.4 5.8 7.1 0 4-3.4 7.2-7.8 7.2S4.2 14 4.2 10c0-3.7 2.5-6.6 5.8-7.1.2-.4.5-.7 1-.7z" />
      <path d="M9.5 3.2L10.5 1.5h3l1 1.7" />
      <polygon points="12,7.5 14.2,10.2 12,12.9 9.8,10.2" fill="#C4923E" stroke="none" />
      <circle cx="12" cy="5.2" r="1" fill="var(--accent-color)" stroke="none" />
      <circle cx="16" cy="7.8" r="1" fill="var(--accent-color)" stroke="none" />
      <circle cx="14.8" cy="12.5" r="1" fill="var(--accent-color)" stroke="none" />
      <circle cx="9.2" cy="12.5" r="1" fill="var(--accent-color)" stroke="none" />
      <circle cx="8" cy="7.8" r="1" fill="var(--accent-color)" stroke="none" />
    </svg>
  );
}

/** Farbwelt-Auswahl -- in beiden Menüs dieselbe. */
function Farbwahl({ activeTheme, setActiveTheme }) {
  return (
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
  );
}

function AppleHeader({ currentUser, setCurrentUser, isDarkMode, setIsDarkMode, setIsJudgeOpen, activeTheme, setActiveTheme }) {
  const navigate = useNavigate();
  const [hoveredNav, setHoveredNav] = useState(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [kontoOffen, setKontoOffen] = useState(false);
  const [handyOffen, setHandyOffen] = useState(false);
  const timeoutRef = useRef(null);
  const kontoRef = useRef(null);

  const NAV = bereiche();

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

  const geheZu = (pfad) => {
    setIsMenuOpen(false);
    setHoveredNav(null);
    setHandyOffen(false);
    setKontoOffen(false);
    navigate(pfad);
  };

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

  // Solange die Handy-Navigation offen ist, soll die Seite darunter nicht
  // mitscrollen -- sonst verliert man beim Zumachen die Stelle.
  useEffect(() => {
    if (!handyOffen) return undefined;
    const vorher = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const beiTaste = (e) => { if (e.key === 'Escape') setHandyOffen(false); };
    window.addEventListener('keydown', beiTaste);
    return () => {
      document.body.style.overflow = vorher;
      window.removeEventListener('keydown', beiTaste);
    };
  }, [handyOffen]);

  return (
    <nav
      className={`apple-nav-container ${isMenuOpen ? 'menu-open' : ''}${handyOffen ? ' handy-offen' : ''}`}
      onMouseLeave={handleMouseLeave}
    >
      <ul className="apple-nav-list">
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter(null)} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ marginLeft: '10px', display: 'flex' }}><GranaLogo /></span>
          <span className="apple-nav-link" style={{fontWeight: 600, fontSize: '1rem', opacity: 1, paddingLeft: 0}}>Grana</span>
        </li>
        {NAV.map((b) => (
          <li key={b.id} className="apple-nav-item" onMouseEnter={() => handleMouseEnter(b.id)}>
            <span className="apple-nav-link" onClick={() => geheZu(b.pfad)}>{b.label}</span>
          </li>
        ))}
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter(null)}>
          <span className="apple-nav-link" onClick={() => geheZu('/premium')} style={{fontWeight: 700, color: 'var(--price-color)'}}>Grana Pro Upgrade</span>
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
                  <Farbwahl activeTheme={activeTheme} setActiveTheme={setActiveTheme} />
                </div>

                <div className="konto-gruppe">
                  <button type="button" className="konto-eintrag" onClick={() => geheZu('/konto')}>
                    Konto und Daten
                  </button>
                  <button type="button" className="konto-eintrag" onClick={() => geheZu('/premium')}>
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

      {/* Handy-Leiste: auf schmalen Bildschirmen lief die obige Liste aus dem
          Bild -- "Grana Pro Upgrade" und das Konto standen ausserhalb des
          sichtbaren Bereichs und waren gar nicht erreichbar. */}
      <div className="handy-leiste">
        <button type="button" className="handy-marke" onClick={() => geheZu('/')}>
          <GranaLogo />
          <span>Grana</span>
        </button>
        <button
          type="button"
          className="handy-schalter"
          onClick={() => setHandyOffen((offen) => !offen)}
          aria-expanded={handyOffen}
          aria-controls="handy-navigation"
          aria-label={handyOffen ? 'Menü schliessen' : 'Menü öffnen'}
        >
          <span className={`handy-striche${handyOffen ? ' offen' : ''}`} aria-hidden="true">
            <i /><i /><i />
          </span>
        </button>
      </div>

      {handyOffen && (
        <div id="handy-navigation" className="handy-navigation">
          <button type="button" className="handy-pro" onClick={() => geheZu('/premium')}>
            Grana Pro Upgrade
          </button>

          {NAV.map((b) => (
            <section key={b.id} className="handy-bereich">
              <button type="button" className="handy-bereich-titel" onClick={() => geheZu(b.pfad)}>
                {b.label}
              </button>
              {b.gruppen.map((g) => (
                <div key={g.titel} className="handy-gruppe">
                  <span className="konto-titel">{g.titel}</span>
                  {g.links.map((l) => (l.extern ? (
                    <a
                      key={l.label}
                      className="handy-link"
                      href={l.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={() => setHandyOffen(false)}
                    >
                      {l.label} <Icons.ExternalLink />
                    </a>
                  ) : (
                    <button key={l.label} type="button" className="handy-link" onClick={() => geheZu(l.pfad)}>
                      {l.label}
                    </button>
                  )))}
                </div>
              ))}
            </section>
          ))}

          <section className="handy-bereich">
            <span className="handy-bereich-titel als-text">{currentUser}</span>
            <div className="handy-gruppe">
              <span className="konto-titel">Darstellung</span>
              <button type="button" className="handy-link" onClick={() => setIsDarkMode(!isDarkMode)}>
                {isDarkMode ? 'Helles Design' : 'Dunkles Design'}
              </button>
            </div>
            <div className="handy-gruppe">
              <span className="konto-titel">Farbwelt</span>
              <Farbwahl activeTheme={activeTheme} setActiveTheme={setActiveTheme} />
            </div>
            <div className="handy-gruppe">
              <button type="button" className="handy-link" onClick={() => geheZu('/konto')}>
                Konto und Daten
              </button>
              <button type="button" className="handy-link" onClick={() => geheZu('/premium')}>
                Abonnement verwalten
              </button>
              <button
                type="button"
                className="handy-link"
                onClick={() => { setHandyOffen(false); setCurrentUser(null); }}
              >
                Abmelden
              </button>
            </div>
          </section>
        </div>
      )}

      <div className={`global-mega-menu ${isMenuOpen && hoveredNav ? 'open' : ''}`}>
        <div className="mega-menu-inner">
          {NAV.map((b) => (
            <div key={b.id} className={`mega-content-panel ${hoveredNav === b.id ? 'active' : ''}`}>
              {b.gruppen.map((g) => (
                <div key={g.titel} className="dropdown-column">
                  <h4>{g.titel}</h4>
                  {g.links.map((l) => (l.extern ? (
                    <a
                      key={l.label}
                      href={l.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{display: 'flex', alignItems: 'center', gap: '8px'}}
                    >
                      {l.label} <Icons.ExternalLink />
                    </a>
                  ) : (
                    <a key={l.label} onClick={() => geheZu(l.pfad)}>{l.label}</a>
                  )))}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </nav>
  );
}

export default AppleHeader;
