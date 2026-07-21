import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { getScryfallImage, getFallbackCardImage } from '../../utils/scryfallHelpers';
import { isPaywallResponse, handlePaywallResponse } from '../../utils/paywall';
import PremiumOverlay from '../layout/PremiumOverlay';
import { RefreshCw, Swords, Zap, HelpCircle, FileText } from 'lucide-react';

const TOURNAMENT_COMBOS_POOL = [
  { format: "cEDH / Legacy", name: "Thassa's Oracle + Demonic Consultation", cards: ["Thassa's Oracle", "Demonic Consultation"], grund: "Exiliere deine gesamte Bibliothek für 1 schwarzes Mana und gewinne das Spiel auf der Stelle durch den ETB-Trigger von Thassa's Oracle." },
  { format: "Modern / Pioneer", name: "Kiki-Jiki + Zealous Conscripts", cards: ["Kiki-Jiki, Mirror Breaker", "Zealous Conscripts"], grund: "Erzeuge unendlich viele Eile-Kopien von Zealous Conscripts, die bei ihrem ETB wiederum Kiki-Jiki enttappen. Infinite Damage." },
  { format: "Modern", name: "Grief + Ephemerate", cards: ["Grief", "Ephemerate"], grund: "Zerstöre die Hand deines Gegners in Zug 1 durch Evoke und sofortiges Blink-Modul, sodass die Kreatur ohne Opfer-Nachteil dauerhaft im Spiel bleibt." },
  { format: "cEDH / Vintage", name: "Underworld Breach + Brain Freeze + Lion's Eye Diamond", cards: ["Underworld Breach", "Brain Freeze", "Lion's Eye Diamond"], grund: "Mühle dein gesamtes Deck in den Friedhof und generiere nebenbei unendlich viel Storm-Count und rotes Mana." },
  { format: "Legacy / Vintage", name: "Painter's Servant + Grindstone", cards: ["Painter's Servant", "Grindstone"], grund: "Macht alle Karten im Spiel und in Bibliotheken zu einer Farbe deiner Wahl. Aktiviere Grindstone, um die gesamte gegnerische Bibliothek zu millen." },
  { format: "Pioneer / Modern", name: "Heliod, Sun-Crowned + Walking Ballista", cards: ["Heliod, Sun-Crowned", "Walking Ballista"], grund: "Verleihe der Walking Ballista Lebensverknüpfung. Jeder Schaden erzeugt eine +1/+1 Marke, womit du unendlich viel Schaden schießen kannst." },
  { format: "Commander / Casual", name: "Sanguine Bond + Exquisite Blood", cards: ["Sanguine Bond", "Exquisite Blood"], grund: "Startet eine Endlosschleife, sobald ein Gegner Lebenspunkte verliert oder du Leben erhältst, und entzieht allen Gegnern das gesamte Leben." },
  { format: "Commander / cEDH", name: "Godo, Bandit Warlord + Helm of the Host", cards: ["Godo, Bandit Warlord", "Helm of the Host"], grund: "Sucht bei Eintritt den Helm, rüstet ihn aus und generiert in jeder Kampfphase eine Eile-Kopie für unendlich viele Kampfphasen." },
  { format: "Modern / Commander", name: "Devoted Druid + Swift Reconfiguration", cards: ["Devoted Druid", "Swift Reconfiguration"], grund: "Verwandelt Devoted Druid in ein Fahrzeug (keine Kreatureinschränkungen mehr). Du kannst sie unendlich oft für grünes Mana enttappen." },
  { format: "Commander / Vintage", name: "Sensei's Top + Aetherflux Reservoir + Bolas's Citadel", cards: ["Sensei's Divining Top", "Aetherflux Reservoir", "Bolas's Citadel"], grund: "Spiele Sensei's Top umsonst von oben mit Bolas's Citadel, ziehe eine Karte, spiele Top erneut. Generiert unendlich viel Leben und gewinnt." }
];

function SynergieAnsicht({ currentUser, userRole, onShowPremiumModal }) {
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const initialCard = queryParams.get('card');

  const [activeMode, setActiveMode] = useState('single'); 
  const [suche, setSuche] = useState("");
  const [karte, setKarte] = useState(null);
  const [combos, setCombos] = useState([]);
  const [laedt, setLaedt] = useState(false);
  const [hasScanned, setHasScanned] = useState(false);
  const [selectedFormat, setSelectedFormat] = useState('commander');
  
  const [userDecks, setUserDecks] = useState([]);
  const [userAlbums, setUserAlbums] = useState({});
  const [selectedTarget, setSelectedTarget] = useState("");
  const [tournamentCombos, setTournamentCombos] = useState([]);

  useEffect(() => {
    // Top Turnier-Combos auf Mount durchmischen und 4 auswählen
    const shuffled = [...TOURNAMENT_COMBOS_POOL].sort(() => 0.5 - Math.random()).slice(0, 4);
    setTournamentCombos(shuffled);
  }, []);

  const handleRerollTournamentCombos = () => {
    const shuffled = [...TOURNAMENT_COMBOS_POOL].sort(() => 0.5 - Math.random()).slice(0, 4);
    setTournamentCombos(shuffled);
  };

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

  const pollSynergyJob = (jobId) => {
    return new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        try {
          const res = await fetch(`/api/scan_combos/status/${jobId}`);
          if (res.ok) {
            const data = await res.json();
            if (data.status === 'completed') {
              clearInterval(interval);
              resolve(data.result);
            } else if (data.status === 'failed') {
              clearInterval(interval);
              reject(new Error(data.result?.error || "Job fehlgeschlagen"));
            }
          } else {
            clearInterval(interval);
            reject(new Error("Netzwerkfehler beim Prüfen des Job-Status"));
          }
        } catch (err) {
          clearInterval(interval);
          reject(err);
        }
      }, 1000);
    });
  };

  const analysiereSynergien = async (searchTerm) => {
    setKarte(null); setCombos([]); setLaedt(true); setHasScanned(false);
    try {
      const resImg = await fetch(`/api/suche/${encodeURIComponent(searchTerm)}?benutzername=${currentUser}`);
      if (!resImg.ok) throw new Error();
      const dataImg = await resImg.json();
      if (!dataImg.error) setKarte(dataImg);
      
      const resCombos = await fetch(`/api/combos/${encodeURIComponent(dataImg.name || searchTerm)}?benutzername=${currentUser}&format=${selectedFormat}`);
      const dataCombos = await resCombos.json();
      if (isPaywallResponse(dataCombos)) {
        handlePaywallResponse(dataCombos, onShowPremiumModal);
        setLaedt(false);
        return;
      }
      
      let finalData;
      if (dataCombos.status === 'processing') {
        finalData = await pollSynergyJob(dataCombos.job_id);
      } else {
        finalData = dataCombos.result;
      }
      
      const empf = Array.isArray(finalData?.empfehlungen) ? finalData.empfehlungen : [];
      const normalizedCombos = empf.map(c => ({ name: c?.name || c?.karten || c?.combo || "Unbekannte Combo", grund: c?.grund || c?.erklaerung || c?.beschreibung || "Keine Erklärung verfügbar.", cards: Array.isArray(c?.cards) ? c.cards : null }));
      setCombos(normalizedCombos);
    } catch (e) {
      console.error(e);
      alert("Analyse fehlgeschlagen.");
    }
    setHasScanned(true);
    setLaedt(false);
  }

  const runScanner = async () => {
      if(!selectedTarget) return;
      setLaedt(true); setCombos([]); setHasScanned(false);
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
          const res = await fetch(`/api/scan_combos`, { 
              method: "POST", 
              headers: {"Content-Type": "application/json"}, 
              body: JSON.stringify({ karten_liste: listeFürKI, benutzername: currentUser, format: selectedFormat }) 
          });
          const data = await res.json();
          if (data && data.error) {
              if (isPaywallResponse(data)) {
                   handlePaywallResponse(data, onShowPremiumModal);
              } else {
                   alert("KI Meldung: " + data.error);
              }
              setLaedt(false);
              return;
          }

          let finalData;
          if (data.status === 'processing') {
            finalData = await pollSynergyJob(data.job_id);
          } else {
            finalData = data;
          }

          let normalizedCombos = [];
          const normalize = c => ({ name: c?.name || c?.karten || c?.combo || "Unbekannte Combo", grund: c?.grund || c?.erklaerung || c?.beschreibung || "Keine Erklärung verfügbar.", kategorie: c?.kategorie || "combo", cards: Array.isArray(c?.cards) ? c.cards : null });
          if (Array.isArray(finalData)) {
              normalizedCombos = finalData.map(normalize);
          } else if (finalData && finalData.combos && Array.isArray(finalData.combos)) {
              normalizedCombos = finalData.combos.map(normalize);
          }
          setCombos(normalizedCombos);
      } catch (err) {
          console.error(err);
          alert("Fehler beim Scannen der Sammlung. Bitte API checken.");
      }
      setHasScanned(true);
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
        <p>Finde verborgene Combos und Wechselwirkungen in deinen Decks und Alben.</p>
        
        <div className="segmented-control" style={{margin: '30px auto 20px auto', display: 'flex'}}>
            <button className={`segment-btn ${activeMode === 'single' ? 'active' : ''}`} onClick={() => {setActiveMode('single'); setCombos([]); setKarte(null); setHasScanned(false);}}>Einzelkarte</button>
            <button className={`segment-btn ${activeMode === 'decks' ? 'active' : ''}`} onClick={() => {setActiveMode('decks'); setCombos([]); setKarte(null); setHasScanned(false);}}>Meine Decks scannen</button>
            <button className={`segment-btn ${activeMode === 'albums' ? 'active' : ''}`} onClick={() => {setActiveMode('albums'); setCombos([]); setKarte(null); setHasScanned(false);}}>Alben scannen</button>
        </div>

        {/* Format Selector Dropdown */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', marginBottom: '30px', alignItems: 'center' }}>
          <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)', fontWeight: 600 }}>Zielformat:</span>
          <select 
            value={selectedFormat} 
            onChange={e => setSelectedFormat(e.target.value)}
            style={{
              padding: '8px 16px',
              borderRadius: '10px',
              background: 'var(--input-bg)',
              border: '1px solid var(--border-color)',
              color: 'var(--text-main)',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.88rem',
              width: 'auto'
            }}
          >
            <option value="commander">Commander / cEDH</option>
            <option value="modern">Modern</option>
            <option value="standard">Standard</option>
            <option value="pioneer">Pioneer</option>
            <option value="legacy">Legacy</option>
            <option value="vintage">Vintage</option>
          </select>
        </div>
        
        {activeMode === 'single' && (
            <div className="search-bar-wrapper">
                <input value={suche} onChange={(e) => setSuche(e.target.value)} placeholder="Kartennamen eingeben..." onKeyDown={(e) => e.key === 'Enter' && handleSearchSubmit()} style={{boxShadow: '0 8px 20px var(--shadow-color)'}} />
                <button className="primary-btn" onClick={handleSearchSubmit}>{laedt ? "Analysiere..." : "Analysieren"}</button>
            </div>
        )}
        {activeMode === 'decks' && (
            <div className="search-bar-wrapper" style={{position: 'relative', minHeight: '120px'}}>
                {userRole !== 'premium' && <PremiumOverlay onShowPremiumModal={onShowPremiumModal} />}
                <select 
                  value={selectedTarget} 
                  onChange={e => {
                    const deckId = e.target.value;
                    setSelectedTarget(deckId);
                    setHasScanned(false);
                    setCombos([]);
                    const deck = userDecks.find(d => String(d.id) === String(deckId));
                    if (deck && deck.format) {
                      setSelectedFormat(deck.format);
                    }
                  }} 
                  style={{boxShadow: '0 8px 20px var(--shadow-color)', background: 'var(--input-bg)', border: '1px solid var(--border-color)'}} 
                  disabled={userRole !== 'premium'}
                >
                    <option value="" disabled>Bitte Deck auswählen...</option>
                    {userDecks.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
                <button className="primary-btn" onClick={runScanner} disabled={userRole !== 'premium'}>{laedt ? "Scanne..." : "Scannen"}</button>
            </div>
        )}
        {activeMode === 'albums' && (
            <div className="search-bar-wrapper" style={{position: 'relative', minHeight: '120px'}}>
                {userRole !== 'premium' && <PremiumOverlay onShowPremiumModal={onShowPremiumModal} />}
                <select value={selectedTarget} onChange={e => { setSelectedTarget(e.target.value); setHasScanned(false); setCombos([]); }} style={{boxShadow: '0 8px 20px var(--shadow-color)', background: 'var(--input-bg)', border: '1px solid var(--border-color)'}} disabled={userRole !== 'premium'}>
                    <option value="" disabled>Bitte Album auswählen...</option>
                    {Object.keys(userAlbums || {}).map(a => <option key={a} value={a}>{a}</option>)}
                </select>
                <button className="primary-btn" onClick={runScanner} disabled={userRole !== 'premium'}>{laedt ? "Scanne..." : "Scannen"}</button>
            </div>
        )}
      </div>

      {laedt && (
        <div style={{ marginTop: '50px' }}>
          <p style={{ textAlign: 'center', color: 'var(--text-muted)', marginBottom: '30px', fontSize: '1.1rem' }}>
            {activeMode === 'single' ? "Analysiere Einzelkartendetails & Combos..." : "Analysiere Deck/Album im Hintergrund..."}
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '800px', margin: '0 auto' }}>
            {[1, 2, 3].map(i => (
              <div key={i} style={{
                background: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid var(--border-color)',
                borderRadius: '16px',
                padding: '25px',
                position: 'relative',
                overflow: 'hidden',
                boxShadow: '0 4px 15px var(--shadow-color)',
                minHeight: '120px'
              }}>
                {/* Shimmer line */}
                <div style={{
                  position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
                  background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.05), transparent)',
                  animation: 'shimmer-sweep 1.6s infinite',
                  transform: 'skewX(-20deg)'
                }} />
                
                {/* Skeleton title */}
                <div style={{ width: '40%', height: '22px', background: 'var(--border-color)', borderRadius: '6px', marginBottom: '15px' }} />
                {/* Skeleton text lines */}
                <div style={{ width: '85%', height: '14px', background: 'var(--border-color)', opacity: 0.6, borderRadius: '4px', marginBottom: '8px' }} />
                <div style={{ width: '60%', height: '14px', background: 'var(--border-color)', opacity: 0.6, borderRadius: '4px' }} />
              </div>
            ))}
          </div>
          <style>{`
            @keyframes shimmer-sweep {
              0% { transform: translateX(-100%) skewX(-20deg); }
              100% { transform: translateX(100%) skewX(-20deg); }
            }
          `}</style>
        </div>
      )}

      {activeMode === 'single' && !karte && !laedt && (
        <>
          <div className="content-card" style={{padding: '40px', marginBottom: '30px', borderRadius: '24px'}}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
              <h3 style={{fontSize: '1.8rem', margin: 0, fontWeight: 600}}>Meta-Breaker: Top Turnier-Combos</h3>
              <button 
                onClick={handleRerollTournamentCombos}
                title="Andere Combos würfeln"
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  padding: '6px',
                  borderRadius: '50%',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = 'var(--text-main)';
                  e.currentTarget.style.background = 'var(--border-color)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = 'var(--text-muted)';
                  e.currentTarget.style.background = 'none';
                }}
              >
                <RefreshCw size={18} />
              </button>
            </div>
            <div className="dashboard-grid">
              {(tournamentCombos || []).map((combo, index) => (
                <div key={index} className="tournament-combo-card">
                  <span className="combo-badge">{combo.format}</span>
                  <div className="combo-images-container">
                    {(combo.cards || []).map((cardName, idx) => (
                      <img key={idx} src={getScryfallImage(cardName)} alt={cardName} className="combo-card-img" onError={(e) => e.target.style.display = 'none'} />
                    ))}
                  </div>
                  <h4 style={{fontSize: '1.3rem', color: 'var(--text-main)', marginBottom: '15px'}}>{combo.name}</h4>
                  <p style={{margin: 0, color: 'var(--text-muted)', fontSize: '0.92rem', lineHeight: '1.5'}}>{combo.grund}</p>
                </div>
              ))}
            </div>
          </div>

          {/* BENTO GRID WIDGETS BELOW */}
          <div className="bento-grid" style={{ marginTop: '0', marginBottom: '40px' }}>
            {/* WIDGET 1: Beliebte Combo-Karten (Quick Search) */}
            <div className="bento-item bento-col-2">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
                  <Swords size={20} style={{ color: 'var(--accent-color)' }} />
                  <h3 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 600 }}>Schnellsuche: Beliebte Combo-Karten</h3>
                </div>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.92rem', marginBottom: '20px' }}>
                  Wähle eine der folgenden Karten aus, um sofort ihre stärksten Synergien und Combos im System zu analysieren:
                </p>
                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                  {[
                    "Godo, Bandit Warlord", "Kiki-Jiki, Mirror Breaker", "Thassa's Oracle", 
                    "Sanguine Bond", "Underworld Breach", "Devoted Druid", 
                    "Walking Ballista", "Helm of the Host", "Exquisite Blood"
                  ].map((cardName) => (
                    <button
                      key={cardName}
                      onClick={() => { setSuche(cardName); analysiereSynergien(cardName); }}
                      className="secondary-btn"
                      style={{
                        padding: '8px 16px',
                        borderRadius: '20px',
                        fontSize: '0.85rem',
                        fontWeight: 500,
                        cursor: 'pointer',
                        background: 'var(--btn-secondary)',
                        border: '1px solid var(--border-color)',
                        transition: 'transform 0.1s'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.03)'}
                      onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
                    >
                      {cardName}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* WIDGET 2: Combo Categories */}
            <div className="bento-item">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
                  <Zap size={20} style={{ color: '#FF9500' }} />
                  <h3 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 600 }}>Combo-Typen</h3>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 'bold', background: 'rgba(255, 59, 48, 0.1)', color: 'var(--danger-color)', padding: '2px 8px', borderRadius: '12px', whiteSpace: 'nowrap' }}>Infinite Damage</span>
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Erzeugt unendlich viel Schaden in einem Zug.</span>
                  </div>
                  <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 'bold', background: 'rgba(0, 113, 227, 0.1)', color: 'var(--accent-color)', padding: '2px 8px', borderRadius: '12px', whiteSpace: 'nowrap' }}>Instant Win</span>
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Gewinnt das Spiel sofort durch einen speziellen Effekt.</span>
                  </div>
                  <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 'bold', background: 'rgba(48, 209, 88, 0.1)', color: 'var(--price-color)', padding: '2px 8px', borderRadius: '12px', whiteSpace: 'nowrap' }}>Infinite Mana</span>
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Generiert unbegrenzt viel Mana für deine Sprüche.</span>
                  </div>
                </div>
              </div>
            </div>

            {/* WIDGET 3: Scanner Guide */}
            <div className="bento-item bento-col-2" style={{ border: '1px solid #C4923E', background: 'linear-gradient(180deg, var(--bg-card) 0%, rgba(196, 146, 62, 0.04) 100%)' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '15px' }}>
                  <FileText size={20} style={{ color: '#C4923E' }} />
                  <span style={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#C4923E', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Scanner-Leitfaden
                  </span>
                </div>
                <h4 style={{ fontSize: '1.2rem', margin: '0 0 10px 0', fontWeight: 600 }}>Durchsuche deine Decks & Alben</h4>
                <p style={{ fontSize: '0.92rem', color: 'var(--text-muted)', lineHeight: '1.6', margin: 0 }}>
                  Wähle oben den Reiter <strong>"Meine Decks scannen"</strong> oder <strong>"Alben scannen"</strong> aus, um eine vollständige Analyse deiner Liste durchzuführen. Unser intelligenter Synergie-Finder gleicht alle deine Karten ab und deckt versteckte Interaktionen oder Combos auf, die du in deiner Sammlung übersehen hast. (Pro-Feature)
                </p>
              </div>
            </div>

            {/* WIDGET 4: Scanner Stats */}
            <div className="bento-item">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
                  <HelpCircle size={20} style={{ color: 'var(--text-muted)' }} />
                  <h3 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 600 }}>Gewusst wie?</h3>
                </div>
                <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: '1.6', margin: 0 }}>
                  Combos bestehen meist aus 2 oder 3 Karten. Wenn du den genauen Ablauf einer Combo verstehen willst, klicke einfach auf die Karte, um sie in der Detailansicht zu öffnen und den Kartentext live nachzulesen.
                </p>
              </div>
            </div>
          </div>
        </>
      )}

      {activeMode === 'single' && karte && !laedt && (
        <div className="content-card" style={{position: 'relative', minHeight: '300px'}}>
          {userRole !== 'premium' && <PremiumOverlay onShowPremiumModal={onShowPremiumModal} />}
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
              <h3>Gefundene Combos & Synergien</h3>
              {(!combos || combos.length === 0) ? <p>Keine spezifischen Combos gefunden.</p> : combos.map((c, i) => {
                if (!c) return null;
                const comboCardNames = (Array.isArray(c.cards) && c.cards.length > 0) ? c.cards : parseComboCards(c.name);
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
              {[
                { key: 'combo', titel: '✅ Fertige Combos', hinweis: 'Alle Karten hast du bereits – sofort spielbar.' },
                { key: 'fast', titel: '⚡ Fast-Combos', hinweis: 'Dir fehlt jeweils nur noch eine Karte.' },
                { key: 'synergie', titel: '🔗 Synergien', hinweis: 'Karten-Pakete, die sich gegenseitig verstärken.' },
              ].map(section => {
                const items = combos.filter(c => (c?.kategorie || 'combo') === section.key);
                if (items.length === 0) return null;
                return (
                  <div key={section.key} style={{marginBottom: '40px'}}>
                    <div style={{borderBottom: '1px solid var(--border-color)', paddingBottom: '10px', marginBottom: '20px'}}>
                      <h4 style={{fontSize: '1.5rem', margin: 0, color: 'var(--text-main)'}}>
                        {section.titel} <span style={{color: 'var(--text-muted)', fontWeight: 400, fontSize: '1rem'}}>({items.length})</span>
                      </h4>
                      <p style={{margin: '4px 0 0 0', fontSize: '0.9rem', color: 'var(--text-muted)'}}>{section.hinweis}</p>
                    </div>
                    {items.map((c, i) => {
                      if(!c) return null;
                      const comboCardNames = (Array.isArray(c.cards) && c.cards.length > 0) ? c.cards : parseComboCards(c.name);
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
                );
              })}
          </div>
      )}

      {(activeMode === 'decks' || activeMode === 'albums') && !laedt && (!combos || combos.length === 0) && selectedTarget && (
          hasScanned ? (
              <div className="content-card" style={{padding: '40px', textAlign: 'center', borderRadius: '24px', border: '1px solid var(--border-color)', background: 'var(--bg-card)'}}>
                  <div style={{ fontSize: '3rem', marginBottom: '15px' }}>🔍</div>
                  <h3 style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--text-main)', margin: '0 0 10px 0' }}>Keine Combos gefunden</h3>
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', margin: 0 }}>
                      Es wurden keine bekannten Synergien oder unendlichen Kombinationen in diesem Deck/Album gefunden.
                  </p>
              </div>
          ) : (
              <p style={{textAlign: 'center', color: 'var(--text-muted)'}}>Klicke auf Scannen, um verborgene Combos zu finden, oder wähle ein anderes Ziel.</p>
          )
      )}

    </div>
  );
}

export default SynergieAnsicht;
