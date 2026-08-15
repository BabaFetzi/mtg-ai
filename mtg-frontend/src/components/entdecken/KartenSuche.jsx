import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Icons from '../../utils/Icons';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';
import { Dice5 } from 'lucide-react';
import { formatEuro } from '../../utils/format';
import { useMeldung } from '../layout/Meldungen';

const TAGS_POOL = [
  'Sol Ring', 'Mana Crypt', 'Jeweled Lotus', 'Ragavan', 'Sheoldred',
  'Demonic Tutor', 'Rhystic Study', 'Lightning Bolt', 'Black Lotus',
  'Great Henge', 'Fabled Passage', 'Brainstorm', 'Path to Exile',
  'Counterspell', 'Doubling Season', 'Teferi, Time Raveler',
  'Boseiju, Who Endures', 'Orcish Bowmasters', 'Esper Sentinel', 'Lotus Petal'
];

function KartenSuche({ currentUser }) {
  const { melde, bestaetige } = useMeldung();
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
  // Standard ist die normale Ausführung -- sie ist die häufigere, und eine
  // fälschlich als Foil geführte Karte verfälscht den Sammlungswert nach oben.
  const [istFoil, setIstFoil] = useState(false);
  // Sprache der physischen Karte. Leer heisst "nicht angegeben" und wird auch
  // so gespeichert -- Englisch zu unterstellen wäre eine erfundene Angabe.
  const [sprache, setSprache] = useState("");
  const [loadedImages, setLoadedImages] = useState({});
  const [popularTags, setPopularTags] = useState([]);
  const [nichtGefunden, setNichtGefunden] = useState(null);

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
    setKarte(null); setLaedt(true); setNichtGefunden(null);
    try {
      const res = await fetch(`/api/suche/${encodeURIComponent(searchTerm)}?benutzername=${currentUser}`)
      if (!res.ok) {
        setNichtGefunden({ hinweis: "Der Server ist gerade nicht erreichbar. Bitte versuche es erneut.", vorschlaege: [] });
        setLaedt(false);
        return;
      }
      const data = await res.json()
      if (data.error) {
        // Kein Popup mehr: Hinweis und Vorschläge bleiben auf der Seite stehen,
        // damit man direkt darauf klicken kann.
        setNichtGefunden({ hinweis: data.hinweis || "", vorschlaege: data.vorschlaege || [] });
      } else {
        setKarte(data); setSelectedPrintIndex(0); setSuche(data.name);
      }
    } catch {
      setNichtGefunden({ hinweis: "Die Suche ist fehlgeschlagen. Bitte prüfe deine Verbindung.", vorschlaege: [] });
    }
    setLaedt(false);
  }

  const speichereKarte = async (zielAlbum, zeigeAlert = true) => {
    const actP = karte?.prints?.[selectedPrintIndex];
    if(!actP) return melde.fehler("Fehler beim Speichern der Karte.");
    // Preis der gewählten Edition, falls echt; sonst bester Marktpreis der Karte.
    const speicherPreis = (actP.preis && actP.preis !== "N/A" && parseFloat(actP.preis) > 0)
      ? String(actP.preis)
      : (karte.marktwert || "0.00");
    try {
      const res = await fetch(`/api/sammlung/hinzufuegen`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ benutzername: currentUser, karten_name: karte.name, album_name: zielAlbum, bild_url: actP.bild_url || "", preis: speicherPreis, foil: istFoil, sprache })
      });
      const data = await res.json();
      if (data && data.erfolg) { 
        if(zeigeAlert) melde.erfolg(`Gespeichert in "${zielAlbum}"!`); 
        loadAlbums();
      } 
    } catch { melde.fehler("Fehler."); }
  }

  const handleSichernKlick = () => {
    const finalAlbumName = albumName.trim();
    if(!finalAlbumName) return melde.fehler("Bitte Albumnamen eingeben.");
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

      {!karte && !laedt && nichtGefunden && (
        <div className="content-card" style={{ maxWidth: '640px', margin: '30px auto 0 auto', padding: '26px', textAlign: 'left' }}>
          <h4 style={{ margin: '0 0 8px 0', fontSize: '1.1rem' }}>Karte nicht gefunden</h4>
          {nichtGefunden.hinweis && (
            <p style={{ margin: 0, fontSize: '0.92rem', lineHeight: 1.55 }}>{nichtGefunden.hinweis}</p>
          )}
          {nichtGefunden.vorschlaege?.length > 0 && (
            <div style={{ marginTop: '18px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 600 }}>Meintest du:</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '10px' }}>
                {nichtGefunden.vorschlaege.map(v => (
                  <button
                    key={v}
                    className="secondary-btn"
                    onClick={() => { setSuche(v); triggerSearch(v); }}
                    style={{ padding: '7px 14px', fontSize: '0.88rem', borderRadius: '16px', width: 'auto' }}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

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
                      melde.fehler("Zufallskarte konnte nicht geladen werden.");
                      setLaedt(false);
                    }
                  } catch (e) {
                    console.error("Failed to fetch random card", e);
                    melde.fehler("Netzwerkfehler beim Laden einer Zufallskarte.");
                    setLaedt(false);
                  }
                }}
                className="primary-btn"
                style={{
                  padding: '8px 18px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
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
            <div className="bento-item" style={{ textAlign: 'left', padding: '18px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <h4 style={{ margin: '0', fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-main)' }}>
                <Icons.Sparkles style={{ color: '#C4923E' }} /> Synergie-Finder
              </h4>
              <p style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: '1.5' }}>
                Suche nach einer beliebigen Karte und klicke auf "Synergien & Combos analysieren", um spielentscheidende Wechselwirkungen zu entdecken.
              </p>
            </div>

            <div className="bento-item" style={{ textAlign: 'left', padding: '18px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <h4 style={{ margin: '0', fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-main)' }}>
                <Icons.Cart style={{ color: '#0071E3' }} /> Cardmarket-Preise
              </h4>
              <p style={{ margin: 0, fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: '1.5' }}>
                Erhalte Echtzeit-Preise direkt aus dem europäischen MTG-Sekundärmarkt und kaufe Karten mit nur einem Klick.
              </p>
            </div>

            <div className="bento-item" style={{ textAlign: 'left', padding: '18px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
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
                        className={`print-thumb ${i === selectedPrintIndex ? 'active' : ''}`}
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
              
              {/* Marktwert & Cardmarket-Link */}
              <div style={{
                background: 'var(--btn-secondary)',
                border: '1px solid var(--border-color)',
                padding: '16px 20px',
                borderRadius: '14px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '20px',
                marginBottom: '30px',
                flexWrap: 'wrap'
              }}>
                <div>
                  <div style={{display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px'}}>
                    <span style={{fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.05em'}}>Marktwert</span>
                    <span style={{
                      background: 'var(--bg-card)',
                      color: 'var(--price-color)',
                      fontSize: '0.68rem',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '12px',
                      textTransform: 'uppercase'
                    }}>Best Price</span>
                  </div>
                  {/* Preis der gewählten Edition, wenn sie einen echten Preis hat;
                      sonst der beste Marktpreis über alle Editionen (marktwert).
                      Verhindert 0.00 €, wenn der erste/gewählte Print (z.B. eine
                      Secret-Lair-Promo) bei Scryfall keinen EUR-Preis hat. */}
                  <p style={{fontSize: '1.8rem', fontWeight: 700, margin: 0, color: 'var(--price-color)', letterSpacing: '-0.02em'}}>{formatEuro((actPrint?.preis && parseFloat(actPrint.preis) > 0) ? actPrint.preis : karte?.marktwert)}</p>
                </div>

                <a
                  href={getCardmarketUrl(karte?.name)}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={trackCardmarketClick}
                  className="market-btn"
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

                    {/* Die Ausführung bestimmt den Preis: Foils sind ein
                        Vielfaches wert. Ohne diese Angabe wurde jede Karte als
                        normal bewertet -- und über den früheren Fall-through in
                        der Preisauswahl konnte umgekehrt eine normale Karte den
                        Foil-Preis bekommen. */}
                    <label style={{display: 'flex', alignItems: 'center', gap: '10px', marginTop: '12px', cursor: 'pointer', fontSize: '0.92rem', color: 'var(--text-muted)'}}>
                      <input
                        type="checkbox"
                        checked={istFoil}
                        onChange={e => setIstFoil(e.target.checked)}
                        style={{width: '18px', height: '18px', cursor: 'pointer'}}
                      />
                      <span>Foil-Ausführung {istFoil && <strong style={{color: 'var(--accent-color)'}}>✦</strong>}</span>
                    </label>

                    {/* Magic-Karten erscheinen in elf Sprachen. Wer eine
                        deutsche Sammlung führt, muss sie beim Tauschen und
                        Verkaufen von einer englischen unterscheiden können. */}
                    <label style={{display: 'flex', alignItems: 'center', gap: '10px', marginTop: '12px', fontSize: '0.92rem', color: 'var(--text-muted)'}}>
                      <span>Sprache</span>
                      <select
                        value={sprache}
                        onChange={e => setSprache(e.target.value)}
                        style={{padding: '8px 12px', borderRadius: '8px', background: 'var(--input-bg)', border: '1px solid var(--border-color)', color: 'var(--text-main)', width: 'auto'}}
                      >
                        <option value="">Keine Angabe</option>
                        <option value="de">Deutsch</option>
                        <option value="en">Englisch</option>
                        <option value="fr">Französisch</option>
                        <option value="it">Italienisch</option>
                        <option value="es">Spanisch</option>
                        <option value="pt">Portugiesisch</option>
                        <option value="ja">Japanisch</option>
                        <option value="ko">Koreanisch</option>
                        <option value="ru">Russisch</option>
                        <option value="zhs">Chinesisch (vereinfacht)</option>
                        <option value="zht">Chinesisch (traditionell)</option>
                        <option value="ph">Phyrexianisch</option>
                      </select>
                    </label>

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
