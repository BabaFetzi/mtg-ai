import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Icons from '../../utils/Icons';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';
import { Dice5 } from 'lucide-react';

const TAGS_POOL = [
  'Sol Ring', 'Mana Crypt', 'Jeweled Lotus', 'Ragavan', 'Sheoldred',
  'Demonic Tutor', 'Rhystic Study', 'Lightning Bolt', 'Black Lotus',
  'Great Henge', 'Fabled Passage', 'Brainstorm', 'Path to Exile',
  'Counterspell', 'Doubling Season', 'Teferi, Time Raveler',
  'Boseiju, Who Endures', 'Orcish Bowmasters', 'Esper Sentinel', 'Lotus Petal'
];

function KartenSuche({ currentUser }) {
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const initialQ = queryParams.get('q');

  const [karte, setKarte] = useState(null);
  const [suche, setSuche] = useState("");
  const [laedt, setLaedt] = useState(false);
  const [selectedPrintIndex, setSelectedPrintIndex] = useState(0);
  const [existingAlben, setExistingAlben] = useState([]);
  const [albumMode, setAlbumMode] = useState("select");
  const [albumName, setAlbumName] = useState("");
  const [loadedImages, setLoadedImages] = useState({});
  const [popularTags, setPopularTags] = useState([]);

  const loadAlbums = () => {
    fetch(`/api/sammlung/${currentUser}`).then(res => res.json()).then(data => {
        if(data && data.erfolg && data.alben) {
          const keys = Object.keys(data.alben);
          setExistingAlben(keys);
          if(keys.length > 0) { setAlbumMode("select"); setAlbumName(keys[0]); } else { setAlbumMode("new"); }
        }
    }).catch(e => console.log(e));
  };

  useEffect(() => { 
    loadAlbums(); 
    // Shuffle and pick 5 popular search tags
    const shuffled = [...TAGS_POOL].sort(() => 0.5 - Math.random()).slice(0, 5);
    setPopularTags(shuffled);
  }, [currentUser]);

  useEffect(() => {
    if (initialQ && !karte && !laedt) {
      setSuche(initialQ);
      triggerSearch(initialQ);
    }
  }, [initialQ]);

  const handleSearchSubmit = () => {
    if(!suche) return;
    triggerSearch(suche);
  }

  const triggerSearch = async (searchTerm) => {
    setKarte(null); setLaedt(true);
    try {
      const res = await fetch(`/api/suche/${encodeURIComponent(searchTerm)}?benutzername=${currentUser}`)
      if (!res.ok) { alert("Fehler bei der Serververbindung."); setLaedt(false); return; }
      const data = await res.json()
      if (data.error) alert("Karte nicht gefunden."); 
      else { setKarte(data); setSelectedPrintIndex(0); setSuche(data.name); }
    } catch { alert("Suche fehlgeschlagen."); }
    setLaedt(false);
  }

  const speichereKarte = async (zielAlbum, zeigeAlert = true) => {
    const actP = karte?.prints?.[selectedPrintIndex];
    if(!actP) return alert("Fehler beim Speichern der Karte.");
    try {
      const res = await fetch(`/api/sammlung/hinzufuegen`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ benutzername: currentUser, karten_name: karte.name, album_name: zielAlbum, bild_url: actP.bild_url || "", preis: actP.preis && actP.preis !== "N/A" ? String(actP.preis) : "0.00" })
      });
      const data = await res.json();
      if (data && data.erfolg) { 
        if(zeigeAlert) alert(`Gespeichert in "${zielAlbum}"!`); 
        loadAlbums();
      } 
    } catch { alert("Fehler."); }
  }

  const handleSichernKlick = () => {
    const finalAlbumName = albumName.trim();
    if(!finalAlbumName) return alert("Bitte Albumnamen eingeben.");
    speichereKarte(finalAlbumName, true);
  }

  const handleWunschlisteKlick = () => {
    speichereKarte("Wunschliste", true);
  }

  const navigate = useNavigate();
  const navigateToSynergy = () => {
    if(karte && karte.name) {
        navigate(`/?view=synergy&card=${encodeURIComponent(karte.name)}`);
    }
  }

  const actPrint = karte && Array.isArray(karte.prints) ? karte.prints[selectedPrintIndex] : null;
  const getCardmarketUrl = (kartenName) => `https://www.cardmarket.com/de/Magic/Products/Search?searchString=${encodeURIComponent(kartenName || "")}`;

  const trackCardmarketClick = async () => {
    try {
      fetch('/api/v1/affiliate/track', {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          card_name: karte?.name,
          set_name: actPrint?.set_name,
          price: actPrint?.preis
        })
      });
    } catch (e) {
      console.error("Tracking failed", e);
    }
  };

  return (
    <div>
      <div className="search-hero" style={{paddingTop: '0'}}>
        <h2>Intelligente Kartensuche.</h2>
        <p>Finde Versionen, deutsche Übersetzungen und aktuelle Marktdaten.</p>
        <div className="search-bar-wrapper">
            <input 
              id="main-search-input"
              value={suche} 
              onChange={(e) => setSuche(e.target.value)} 
              placeholder="Kartennamen eingeben (z.B. Sol Ring)..." 
              onKeyDown={(e) => e.key === 'Enter' && handleSearchSubmit()} 
              style={{boxShadow: '0 8px 20px var(--shadow-color)'}} 
            />
            <button className="primary-btn" onClick={handleSearchSubmit}>{laedt && !karte ? "Suche..." : "Suchen"}</button>
        </div>
      </div>

      {!karte && !laedt && (
        <div style={{ animation: 'slideUp 0.4s ease', marginTop: '40px', maxWidth: '800px', margin: '40px auto 0 auto' }}>
          {/* Häufig gesuchte Karten */}
          <div style={{ textAlign: 'center', marginBottom: '40px' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '16px', fontWeight: 600, letterSpacing: '0.05em' }}>
              Beliebte Karten
            </span>
            <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', flexWrap: 'wrap', alignItems: 'center' }}>
              {popularTags.map((name) => (
                <button
                  key={name}
                  onClick={() => { setSuche(name); triggerSearch(name); }}
                  className="secondary-btn"
                  style={{
                    padding: '8px 16px',
                    borderRadius: '20px',
                    fontSize: '0.85rem',
                    fontWeight: 500,
                    cursor: 'pointer',
                    background: 'var(--btn-secondary)',
                    border: '1px solid var(--border-color)'
                  }}
                >
                  {name}
                </button>
              ))}
              
              {/* Zufallskarte */}
              <button
                onClick={async () => {
                  setLaedt(true);
                  try {
                    const res = await fetch('https://api.scryfall.com/cards/random');
                    const data = await res.json();
                    if (data && data.name) {
                      setSuche(data.name);
                      triggerSearch(data.name);
                    } else {
                      alert("Zufallskarte konnte nicht geladen werden.");
                      setLaedt(false);
                    }
                  } catch (e) {
                    console.error("Failed to fetch random card", e);
                    alert("Netzwerkfehler beim Laden einer Zufallskarte.");
                    setLaedt(false);
                  }
                }}
                className="primary-btn"
                style={{
                  background: 'linear-gradient(135deg, #C4923E 0%, #9E7127 100%)',
                  border: 'none',
                  color: 'white',
                  padding: '8px 18px',
                  borderRadius: '20px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  boxShadow: '0 4px 12px rgba(196, 146, 62, 0.25)',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <Dice5 size={14} /> Zufällige Karte
              </button>
            </div>
          </div>

          {/* Quick Info Bento Grid */}
          <div className="bento-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '20px', marginTop: '20px' }}>
            <div className="bento-item" style={{ textAlign: 'left', padding: '25px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <h4 style={{ margin: '0', fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-main)' }}>
                <Icons.Sparkles style={{ color: '#C4923E' }} /> Synergie-Finder
              </h4>
              <p style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: '1.5' }}>
                Suche nach einer beliebigen Karte und klicke auf "Synergien & Combos analysieren", um spielentscheidende Wechselwirkungen zu entdecken.
              </p>
            </div>

            <div className="bento-item" style={{ textAlign: 'left', padding: '25px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <h4 style={{ margin: '0', fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-main)' }}>
                <Icons.Cart style={{ color: '#0071E3' }} /> Cardmarket-Preise
              </h4>
              <p style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: '1.5' }}>
                Erhalte Echtzeit-Preise direkt aus dem europäischen MTG-Sekundärmarkt und kaufe Karten mit nur einem Klick.
              </p>
            </div>

            <div className="bento-item" style={{ textAlign: 'left', padding: '25px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <h4 style={{ margin: '0', fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-main)' }}>
                <Icons.Heart style={{ color: '#FF3B30' }} /> Alben & Sammlungen
              </h4>
              <p style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: '1.5' }}>
                Ordne gefundene Karten in deine virtuellen Ordner oder die Wunschliste ein, um den Gesamtwert deiner Sammlung im Blick zu behalten.
              </p>
            </div>
          </div>
        </div>
      )}

      {karte && actPrint && (
        <div className="content-card">
          <div className="result-layout">
            <div className="card-image-wrapper">
              <img 
                src={actPrint.bild_url || getFallbackCardImage(karte?.name, karte?.typ)} 
                alt={karte?.name || "Unbekannt"} 
                className={`main-card-img fade-in-img ${loadedImages[actPrint.bild_url] ? 'loaded' : ''}`} 
                onLoad={() => setLoadedImages(prev => ({ ...prev, [actPrint.bild_url]: true }))}
                loading="lazy"
                onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(karte?.name, karte?.typ); }}
              />
              {karte.prints && karte.prints.length > 1 && (
                <div>
                  <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600}}>Alle Editionen</span>
                  <div className="prints-scroll" style={{marginTop: '10px'}}>
                    {karte.prints.map((p, i) => (
                      <img 
                        key={i} 
                        src={p?.bild_url || getFallbackCardImage(karte?.name, p?.set_name)} 
                        className={`print-thumb ${i === selectedPrintIndex ? 'active' : ''} fade-in-img ${loadedImages[p?.bild_url] ? 'loaded' : ''}`} 
                        onLoad={() => setLoadedImages(prev => ({ ...prev, [p?.bild_url]: true }))}
                        onClick={() => setSelectedPrintIndex(i)} 
                        title={p?.set_name} 
                        alt="Edition" 
                        loading="lazy"
                        onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(karte?.name, p?.set_name); }}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div>
              <div className="info-header">
                <h3>{karte?.name}</h3>
                <p>{karte?.typ} • <strong style={{color: 'var(--text-main)'}}>{actPrint?.set_name}</strong></p>
              </div>
              <div className="translation-box">
                <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: '12px'}}>Deutsche Übersetzung</span>
                <p style={{color: 'var(--text-main)', fontSize: '1.15rem', margin: 0, fontStyle: 'italic'}}>{karte?.text_de}</p>
              </div>
              
              {/* Premium Cardmarket Affiliate Box */}
              <div style={{
                background: 'rgba(255, 255, 255, 0.03)',
                backdropFilter: 'blur(12px)',
                WebkitBackdropFilter: 'blur(12px)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                padding: '24px',
                borderRadius: '24px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '20px',
                marginBottom: '40px',
                flexWrap: 'wrap',
                boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.15)',
                transition: 'all 0.3s ease'
              }}>
                <div>
                  <div style={{display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px'}}>
                    <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.05em'}}>Marktwert</span>
                    <span style={{
                      background: 'rgba(76, 217, 100, 0.15)', 
                      color: '#4cd964', 
                      fontSize: '0.7rem', 
                      fontWeight: 700, 
                      padding: '2px 8px', 
                      borderRadius: '12px',
                      textTransform: 'uppercase'
                    }}>Best Price</span>
                  </div>
                  <p style={{fontSize: '2.2rem', fontWeight: 700, margin: 0, color: 'var(--text-main)', letterSpacing: '-0.02em'}}>{actPrint?.preis || "0.00"} €</p>
                </div>
                
                <a 
                  href={getCardmarketUrl(karte?.name)} 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  onClick={trackCardmarketClick}
                  className="market-btn-premium"
                  style={{
                    background: 'linear-gradient(135deg, #C4923E 0%, #9E7127 100%)',
                    color: 'white',
                    border: 'none',
                    padding: '16px 32px',
                    borderRadius: '20px',
                    fontSize: '1.1rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    textDecoration: 'none',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '10px',
                    boxShadow: '0 4px 15px rgba(196, 146, 62, 0.2)',
                    transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-2px)';
                    e.currentTarget.style.boxShadow = '0 6px 20px rgba(196, 146, 62, 0.35)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'none';
                    e.currentTarget.style.boxShadow = '0 4px 15px rgba(196, 146, 62, 0.2)';
                  }}
                >
                   <Icons.Cart /> Auf Cardmarket kaufen
                </a>
              </div>
              
              <div style={{borderTop: '1px solid var(--border-color)', paddingTop: '30px'}}>
                <button id="synergy-btn" className="secondary-btn" style={{marginBottom: '30px', width: '100%', padding: '18px', fontSize: '1.1rem'}} onClick={navigateToSynergy}>
                   <Icons.Sparkles /> Synergien & Combos analysieren
                </button>
                
                <div style={{display: 'flex', gap: '15px', alignItems: 'center', flexWrap: 'wrap'}}>
                    <div style={{display: 'flex', gap: '15px', alignItems: 'center', background: 'var(--btn-secondary)', padding: '20px', borderRadius: '20px', flexGrow: 1}}>
                      {existingAlben && existingAlben.length > 0 && albumMode === "select" ? (
                        <select value={albumName} onChange={e => { if(e.target.value === "NEW") { setAlbumMode("new"); setAlbumName(""); } else setAlbumName(e.target.value); }} style={{padding: '14px', flexGrow: 1, border: 'none', background: 'var(--input-bg)'}}>
                          {(existingAlben || []).map(a => <option key={a} value={a}>{a}</option>)}
                          <option value="NEW">+ Neues Album erstellen...</option>
                        </select>
                      ) : (
                        <input type="text" placeholder="Neues Album benennen..." value={albumName} onChange={e => setAlbumName(e.target.value)} style={{padding: '14px', flexGrow: 1, border: 'none', background: 'var(--input-bg)'}} />
                      )}
                      <button className="primary-btn" style={{padding: '14px 35px'}} onClick={handleSichernKlick}>Sichern</button>
                    </div>

                    <button className="secondary-btn" style={{padding: '20px', height: '100%', borderRadius: '20px', border: '1px solid var(--border-color)', background: 'var(--bg-card)'}} onClick={handleWunschlisteKlick}>
                        <Icons.Heart /> Auf Wunschliste
                    </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default KartenSuche;
