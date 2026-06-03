import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { getScryfallImage, getFallbackCardImage } from '../../utils/scryfallHelpers';
import PremiumOverlay from '../layout/PremiumOverlay';

function SynergieAnsicht({ currentUser, userRole }) {
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const initialCard = queryParams.get('card');

  const [activeMode, setActiveMode] = useState('single'); 
  const [suche, setSuche] = useState("");
  const [karte, setKarte] = useState(null);
  const [combos, setCombos] = useState([]);
  const [laedt, setLaedt] = useState(false);
  
  const [userDecks, setUserDecks] = useState([]);
  const [userAlbums, setUserAlbums] = useState({});
  const [selectedTarget, setSelectedTarget] = useState("");

  const topTournamentCombos = [
    { format: "cEDH / Legacy", name: "Thassa's Oracle + Demonic Consultation", cards: ["Thassa's Oracle", "Demonic Consultation"], grund: "Exiliere deine gesamte Bibliothek für 1 schwarzes Mana und gewinne das Spiel auf der Stelle durch den ETB-Trigger von Thassa's Oracle." },
    { format: "Modern / Pioneer", name: "Kiki-Jiki, Mirror Breaker + Zealous Conscripts", cards: ["Kiki-Jiki, Mirror Breaker", "Zealous Conscripts"], grund: "Erzeuge unendlich viele Eile-Kopien von Zealous Conscripts, die bei ihrem ETB wiederum Kiki-Jiki enttappen. Infinite Damage." },
    { format: "Modern", name: "Grief + Ephemerate", cards: ["Grief", "Ephemerate"], grund: "Zerstöre die Hand deines Gegners in Zug 1 durch Evoke und sofortiges Blink-Modul, sodass die Kreatur ohne Opfer-Nachteil dauerhaft im Spiel bleibt." },
    { format: "cEDH / Vintage", name: "Underworld Breach + Brain Freeze + Lion's Eye Diamond", cards: ["Underworld Breach", "Brain Freeze", "Lion's Eye Diamond"], grund: "Mühle dein gesamtes Deck in den Friedhof und generiere nebenbei unendlich viel Storm-Count und rotes Mana." }
  ];

  useEffect(() => {
    if(initialCard && !karte && !laedt && activeMode === 'single') {
      setSuche(initialCard);
      analysiereSynergien(initialCard);
    }
  }, [initialCard, activeMode]);

  useEffect(() => {
    if (activeMode === 'decks') {
        fetch(`/api/decks/${currentUser}`).then(r => r.json()).then(data => {
            if(Array.isArray(data)) { setUserDecks(data); if(data.length > 0) setSelectedTarget(data[0].id.toString()); }
        }).catch(e => console.log(e));
    } else if (activeMode === 'albums') {
        fetch(`/api/sammlung/${currentUser}`).then(r => r.json()).then(data => {
            if(data && data.erfolg && data.alben) { setUserAlbums(data.alben); const keys = Object.keys(data.alben); if(keys.length > 0) setSelectedTarget(keys[0]); }
        }).catch(e => console.log(e));
    }
  }, [activeMode, currentUser]);

  const handleSearchSubmit = () => { if(!suche) return; analysiereSynergien(suche); }

  const analysiereSynergien = async (searchTerm) => {
    setKarte(null); setCombos([]); setLaedt(true);
    try {
      const resImg = await fetch(`/api/suche/${searchTerm}?benutzername=${currentUser}`);
      if (!resImg.ok) throw new Error();
      const dataImg = await resImg.json();
      if (!dataImg.error) setKarte(dataImg);
      const resCombos = await fetch(`/api/combos/${dataImg.name || searchTerm}?benutzername=${currentUser}`);
      const dataCombos = await resCombos.json();
      if (dataCombos.error === "paywall") {
        alert(dataCombos.message);
        setLaedt(false);
        return;
      }
      const empf = Array.isArray(dataCombos.empfehlungen) ? dataCombos.empfehlungen : [];
      const normalizedCombos = empf.map(c => ({ name: c?.name || c?.karten || c?.combo || "Unbekannte Combo", grund: c?.grund || c?.erklaerung || c?.beschreibung || "Keine Erklärung verfügbar." }));
      setCombos(normalizedCombos);
    } catch { alert("Analyse fehlgeschlagen."); }
    setLaedt(false);
  }

  const runScanner = async () => {
      if(!selectedTarget) return;
      setLaedt(true); setCombos([]);
      let listeFürKI = "";
      if (activeMode === 'decks') {
          const deck = userDecks.find(d => d.id.toString() === selectedTarget);
          if (deck) listeFürKI = deck.liste || "";
      } else if (activeMode === 'albums') {
          const kartenImAlbum = Array.isArray(userAlbums[selectedTarget]) ? userAlbums[selectedTarget] : [];
          listeFürKI = kartenImAlbum.map(k => k?.name || "").join('\n');
      }

      if(!listeFürKI.trim()) { alert("Das ausgewählte Ziel ist leer."); setLaedt(false); return; }

      try {
          const res = await fetch(`/api/scan_combos`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ karten_liste: listeFürKI, benutzername: currentUser }) });
          const data = await res.json();
          if (data && data.error) { 
              if (data.error === "paywall") {
                  alert(data.message);
              } else {
                  alert("KI Meldung: " + data.error); 
              }
              setLaedt(false); 
              return; 
          }

          let normalizedCombos = [];
          if (Array.isArray(data)) {
              normalizedCombos = data.map(c => ({ name: c?.name || c?.karten || c?.combo || "Unbekannte Combo", grund: c?.grund || c?.erklaerung || c?.beschreibung || "Keine Erklärung verfügbar." }));
          } else if (data && data.combos && Array.isArray(data.combos)) {
              normalizedCombos = data.combos.map(c => ({ name: c?.name || c?.karten || c?.combo || "Unbekannte Combo", grund: c?.grund || c?.erklaerung || c?.beschreibung || "Keine Erklärung verfügbar." }));
          }
          setCombos(normalizedCombos);
      } catch { alert("Fehler beim Scannen der Sammlung. Bitte API checken."); }
      setLaedt(false);
  };

  const parseComboCards = (comboString) => {
    if (!comboString || typeof comboString !== 'string') return [];
    let cleanedString = comboString.replace(/combo|synergy|synergie/gi, "");
    return cleanedString.split(/\+|und|and|&|,|\/|\|/i).map(s => s.trim()).filter(s => s.length > 2);
  }

  return (
    <div>
      <div className="search-hero" style={{paddingTop: '0'}}>
        <h2>Synergie-Scanner.</h2>
        <p>Lass die KI deine Decks und Alben nach verborgenen Combos durchsuchen.</p>
        
        <div className="segmented-control" style={{margin: '30px auto', display: 'flex'}}>
            <button className={`segment-btn ${activeMode === 'single' ? 'active' : ''}`} onClick={() => {setActiveMode('single'); setCombos([]); setKarte(null);}}>Einzelkarte</button>
            <button className={`segment-btn ${activeMode === 'decks' ? 'active' : ''}`} onClick={() => {setActiveMode('decks'); setCombos([]); setKarte(null);}}>Meine Decks scannen</button>
            <button className={`segment-btn ${activeMode === 'albums' ? 'active' : ''}`} onClick={() => {setActiveMode('albums'); setCombos([]); setKarte(null);}}>Alben scannen</button>
        </div>
        
        {activeMode === 'single' && (
            <div className="search-bar-wrapper">
                <input value={suche} onChange={(e) => setSuche(e.target.value)} placeholder="Kartennamen eingeben..." onKeyDown={(e) => e.key === 'Enter' && handleSearchSubmit()} style={{boxShadow: '0 8px 20px var(--shadow-color)'}} />
                <button className="primary-btn" onClick={handleSearchSubmit}>{laedt ? "Analysiere..." : "Analysieren"}</button>
            </div>
        )}
        {activeMode === 'decks' && (
            <div className="search-bar-wrapper" style={{position: 'relative', minHeight: '120px'}}>
                {userRole !== 'premium' && <PremiumOverlay />}
                <select value={selectedTarget} onChange={e => setSelectedTarget(e.target.value)} style={{boxShadow: '0 8px 20px var(--shadow-color)', background: 'var(--input-bg)', border: '1px solid var(--border-color)'}} disabled={userRole !== 'premium'}>
                    <option value="" disabled>Bitte Deck auswählen...</option>
                    {userDecks.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
                <button className="primary-btn" onClick={runScanner} disabled={userRole !== 'premium'}>{laedt ? "Scanne..." : "Scannen"}</button>
            </div>
        )}
        {activeMode === 'albums' && (
            <div className="search-bar-wrapper" style={{position: 'relative', minHeight: '120px'}}>
                {userRole !== 'premium' && <PremiumOverlay />}
                <select value={selectedTarget} onChange={e => setSelectedTarget(e.target.value)} style={{boxShadow: '0 8px 20px var(--shadow-color)', background: 'var(--input-bg)', border: '1px solid var(--border-color)'}} disabled={userRole !== 'premium'}>
                    <option value="" disabled>Bitte Album auswählen...</option>
                    {Object.keys(userAlbums || {}).map(a => <option key={a} value={a}>{a}</option>)}
                </select>
                <button className="primary-btn" onClick={runScanner} disabled={userRole !== 'premium'}>{laedt ? "Scanne..." : "Scannen"}</button>
            </div>
        )}
      </div>

      {laedt && <div style={{textAlign: 'center', marginTop: '60px'}}><div className="spinner"></div><p style={{marginTop: '20px', color: 'var(--text-muted)'}}>{activeMode === 'single' ? "KI ermittelt beste Kombinationen..." : "Durchsuche Datenbank nach verborgenen Synergien... (Das kann kurz dauern)"}</p></div>}

      {activeMode === 'single' && !karte && !laedt && (
        <div className="content-card" style={{padding: '40px'}}>
          <h3 style={{fontSize: '1.8rem', marginBottom: '30px'}}>Meta-Breaker: Top Turnier-Combos</h3>
          <div className="dashboard-grid">
            {(topTournamentCombos || []).map((combo, index) => (
              <div key={index} className="tournament-combo-card">
                <span className="combo-badge">{combo.format}</span>
                <div className="combo-images-container">
                  {(combo.cards || []).map((cardName, idx) => (
                    <img key={idx} src={getScryfallImage(cardName)} alt={cardName} className="combo-card-img" onError={(e) => e.target.style.display = 'none'} />
                  ))}
                </div>
                <h4 style={{fontSize: '1.3rem', color: 'var(--text-main)', marginBottom: '15px'}}>{combo.name}</h4>
                <p style={{margin: 0, color: 'var(--text-muted)'}}>{combo.grund}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeMode === 'single' && karte && !laedt && (
        <div className="content-card" style={{position: 'relative', minHeight: '300px'}}>
          {userRole !== 'premium' && <PremiumOverlay />}
          <div className="result-layout" style={{gridTemplateColumns: '350px 1fr'}}>
            <div className="card-image-wrapper">
              <img 
                src={karte?.prints?.[0]?.bild_url || getFallbackCardImage(karte?.name, karte?.typ)} 
                alt={karte?.name || "Unbekannt"} 
                className="main-card-img" 
                style={{maxWidth: '350px'}} 
                loading="lazy"
                onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(karte?.name, karte?.typ); }}
              />
              <h3 style={{marginTop: '20px', fontSize: '1.5rem'}}>{karte?.name}</h3>
              <p style={{margin: 0}}>{karte?.typ}</p>
            </div>
            <div>
              <h3 style={{fontSize: '2rem', marginBottom: '30px'}}>KI-Gefundene Combos</h3>
              {(!combos || combos.length === 0) ? <p>Keine spezifischen Combos gefunden.</p> : combos.map((c, i) => {
                if (!c) return null;
                const comboCardNames = parseComboCards(c.name);
                return (
                  <div key={i} className="synergy-combo-card">
                    {comboCardNames.length > 0 && (
                      <div className="combo-images-container">
                        {comboCardNames.map((cardName, idx) => (
                          <img key={idx} src={getScryfallImage(cardName)} alt={cardName} className="combo-card-img" onError={(e) => e.target.style.display = 'none'} />
                        ))}
                      </div>
                    )}
                    <h4 style={{margin: 0, color: 'var(--text-main)', fontSize: '1.3rem', marginBottom: '10px'}}>{c.name}</h4>
                    <p style={{margin: 0, fontSize: '1.05rem', color: 'var(--text-muted)'}}>{c.grund}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {(activeMode === 'decks' || activeMode === 'albums') && !laedt && combos && combos.length > 0 && (
          <div className="content-card" style={{padding: '40px'}}>
              <h3 style={{fontSize: '2rem', marginBottom: '30px'}}>Gefundene Synergien & Combos</h3>
              {combos.map((c, i) => {
                if(!c) return null;
                const comboCardNames = parseComboCards(c.name);
                return (
                  <div key={i} className="synergy-combo-card">
                    {comboCardNames.length > 0 && (
                      <div className="combo-images-container">
                        {comboCardNames.map((cardName, idx) => (
                          <img key={idx} src={getScryfallImage(cardName)} alt={cardName} className="combo-card-img" onError={(e) => e.target.style.display = 'none'} />
                        ))}
                      </div>
                    )}
                    <h4 style={{margin: 0, color: 'var(--text-main)', fontSize: '1.3rem', marginBottom: '10px'}}>{c.name}</h4>
                    <p style={{margin: 0, fontSize: '1.05rem', color: 'var(--text-muted)'}}>{c.grund}</p>
                  </div>
                );
              })}
          </div>
      )}

      {(activeMode === 'decks' || activeMode === 'albums') && !laedt && (!combos || combos.length === 0) && selectedTarget && (
          <p style={{textAlign: 'center', color: 'var(--text-muted)'}}>Klicke auf Scannen, um verborgene Combos zu finden, oder wähle ein anderes Ziel.</p>
      )}

    </div>
  );
}

export default SynergieAnsicht;
