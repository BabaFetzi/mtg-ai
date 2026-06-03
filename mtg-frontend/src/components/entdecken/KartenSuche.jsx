import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Icons from '../../utils/Icons';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';

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

  const loadAlbums = () => {
    fetch(`/api/sammlung/${currentUser}`).then(res => res.json()).then(data => {
        if(data && data.erfolg && data.alben) {
          const keys = Object.keys(data.alben);
          setExistingAlben(keys);
          if(keys.length > 0) { setAlbumMode("select"); setAlbumName(keys[0]); } else { setAlbumMode("new"); }
        }
    }).catch(e => console.log(e));
  };

  useEffect(() => { loadAlbums(); }, [currentUser]);

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
      const res = await fetch(`/api/suche/${searchTerm}?benutzername=${currentUser}`)
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

      {karte && actPrint && (
        <div className="content-card">
          <div className="result-layout">
            <div className="card-image-wrapper">
              <img 
                src={actPrint.bild_url || getFallbackCardImage(karte?.name, karte?.typ)} 
                alt={karte?.name || "Unbekannt"} 
                className="main-card-img" 
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
                <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: '12px'}}>Deutsche Übersetzung (KI)</span>
                <p style={{color: 'var(--text-main)', fontSize: '1.15rem', margin: 0, fontStyle: 'italic'}}>{karte?.text_de}</p>
              </div>
              
              <div style={{display: 'flex', alignItems: 'center', gap: '25px', marginBottom: '40px', flexWrap: 'wrap'}}>
                <div>
                  <span style={{fontSize: '0.95rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, display: 'block'}}>Marktwert</span>
                  <p className="price-display">{actPrint?.preis || "0.00"} €</p>
                </div>
                <a href={getCardmarketUrl(karte?.name)} target="_blank" rel="noopener noreferrer" className="market-btn" style={{marginTop: '15px'}}>
                   <Icons.Cart /> Auf Cardmarket kaufen
                </a>
              </div>
              
              <div style={{borderTop: '1px solid var(--border-color)', paddingTop: '30px'}}>
                <button id="synergy-btn" className="secondary-btn" style={{marginBottom: '30px', width: '100%', padding: '18px', fontSize: '1.1rem'}} onClick={navigateToSynergy}>
                   <Icons.Sparkles /> KI-Synergien analysieren
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
