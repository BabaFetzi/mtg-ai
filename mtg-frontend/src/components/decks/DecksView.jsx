import { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Icons from '../../utils/Icons';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';
import PremiumOverlay from '../layout/PremiumOverlay';
import DeckEditor from './DeckEditor';
import DeckAnalysis from './DeckAnalysis';

function DecksView({ currentUser, userRole }) {
  const location = useLocation();
  const navigate = useNavigate();
  const searchParams = new URLSearchParams(location.search);
  const currentTab = searchParams.get('tab') || 'overview';
  const deckId = searchParams.get('deckId');
  const focusParam = searchParams.get('focus');

  const [decks, setDecks] = useState([]);
  const [selectedDeck, setSelectedDeck] = useState(null);
  
  const [newDeckName, setNewDeckName] = useState("");
  const [importListe, setImportListe] = useState("");
  const [visualDeck, setVisualDeck] = useState(null);
  const [playtest, setPlaytest] = useState(null);
  const [hoveredCard, setHoveredCard] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  const handleMouseMove = (e) => {
    const cardWidth = 240;
    const cardHeight = 340;
    const x = e.clientX + cardWidth + 25 > window.innerWidth 
      ? e.clientX - cardWidth - 15 
      : e.clientX + 15;
    const y = e.clientY + cardHeight + 25 > window.innerHeight 
      ? e.clientY - cardHeight - 15 
      : e.clientY + 15;
    setMousePos({ x, y });
  };

  const [laedt, setLaedt] = useState(false);
  const [analyse, setAnalyse] = useState(null);
  const [stats, setStats] = useState(null);
  const [deckWert, setDeckWert] = useState(null);
  const [quickSearch, setQuickSearch] = useState("");
  const [quickResult, setQuickResult] = useState(null);
  const [selectedFormat, setSelectedFormat] = useState("commander");
  const [validation, setValidation] = useState(null);

  const createInputRef = useRef(null);

  const ladeDecks = async () => {
    try { 
      const res = await fetch(`/api/decks/${currentUser}`); 
      const data = await res.json();
      if(Array.isArray(data)) setDecks(data); else setDecks([]);
    } catch { setDecks([]); }
  };

  const erstelleDeck = async () => {
    if(!newDeckName) return;
    try {
      const res = await fetch(`/api/decks/erstellen`, { 
        method: "POST", 
        headers: {"Content-Type": "application/json"}, 
        body: JSON.stringify({ benutzername: currentUser, deck_name: newDeckName, deck_liste: importListe }) 
      });
      const data = await res.json();
      if (data && data.erfolg) {
        setNewDeckName(""); setImportListe(""); 
        const resList = await fetch(`/api/decks/${currentUser}`); 
        const dataList = await resList.json();
        if(Array.isArray(dataList)) {
          setDecks(dataList);
          const created = dataList.find(d => d.name === newDeckName) || dataList[dataList.length - 1];
          if (created) {
            navigate(`/decks?tab=editor&deckId=${created.id}`);
          }
        }
      }
    } catch {
      alert("Fehler beim Erstellen des Decks.");
    }
  };

  const speichereListe = async () => {
    if(!selectedDeck) return;
    try {
      const res = await fetch(`/api/decks/update`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ deck_id: selectedDeck.id, deck_liste: selectedDeck.liste }) });
      const data = await res.json();
      if(data && data.erfolg) {
        alert("Deck gespeichert.");
        ladeDecks();
      }
    } catch {
      alert("Fehler beim Speichern.");
    }
  };

  const loescheDeck = async (id, name) => {
    const finalName = name || selectedDeck?.name || "Dieses Deck";
    if(!window.confirm(`Möchtest du das Deck "${finalName}" wirklich löschen?`)) return;
    try {
      const res = await fetch(`/api/decks/loeschen`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deck_id: id, benutzername: currentUser })
      });
      const data = await res.json();
      if (data && data.erfolg) {
        alert(`Deck "${finalName}" wurde gelöscht.`);
        navigate('/decks?tab=overview');
        ladeDecks();
      }
    } catch {
      alert("Fehler beim Löschen des Decks.");
    }
  };

  const handleQuickSearch = async () => {
    if(!quickSearch) return;
    try {
      const res = await fetch(`/api/suche/${quickSearch}?benutzername=${currentUser}`);
      const data = await res.json();
      if(!data.error) setQuickResult(data); else alert("Nicht gefunden.");
    } catch {
      alert("Fehlgeschlagen.");
    }
  };

  const addCardToTextarea = () => {
    if(!quickResult || !selectedDeck) return;
    const aktuelleListe = selectedDeck.liste ? selectedDeck.liste + "\n" : "";
    setSelectedDeck({ ...selectedDeck, liste: aktuelleListe + `1x ${quickResult.name}` });
    setQuickSearch(""); setQuickResult(null);
    setVisualDeck(null); setStats(null); setAnalyse(null); setDeckWert(null);
  };

  const ladeStatsUndAnalyse = async () => {
    if (!selectedDeck || !selectedDeck.liste || !selectedDeck.liste.trim()) {
        return;
    }
    setLaedt(true);
    
    let p1;
    if (userRole === 'premium') {
      p1 = fetch(`/api/deck/analyse`, { 
        method: "POST", 
        headers: {"Content-Type": "application/json"}, 
        body: JSON.stringify({ deck_liste: selectedDeck.liste, benutzername: currentUser, format: selectedFormat }) 
      })
      .then(res => res.json())
      .then(data => setAnalyse(data))
      .catch(() => setAnalyse({error: "KI nicht erreichbar."}));
    } else {
      setAnalyse({
        strategie: "Upgrade auf Premium, um die strategische Analyse dieses Decks freizuschalten.",
        staerken: ["Pro-Feature"],
        schwaechen: ["Pro-Feature"],
        commander: "Commander-Analyse gesperrt",
        combos: []
      });
      p1 = Promise.resolve();
    }

    const p2 = fetch(`/api/deck/wert`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ deck_liste: selectedDeck.liste }) })
        .then(res => res.json()).then(data => setDeckWert(data)).catch(() => {});

    const p3 = fetch(`/api/deck/stats`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ deck_liste: selectedDeck.liste }) })
        .then(res => res.json()).then(data => setStats(data)).catch(() => {});

    const p4 = fetch(`/api/deck/validate`, { 
        method: "POST", 
        headers: {"Content-Type": "application/json"}, 
        body: JSON.stringify({ deck_liste: selectedDeck.liste, format: selectedFormat }) 
      })
      .then(res => res.json())
      .then(data => setValidation(data))
      .catch(() => {});

    await Promise.all([p1, p2, p3, p4]);
    setLaedt(false);
  };

  const ladeVisuelleAnsicht = async (mode) => {
    if (!selectedDeck || !selectedDeck.liste || !selectedDeck.liste.trim()) {
        return;
    }
    setLaedt(true);
    try {
      const res = await fetch(`/api/deck/visualize`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ deck_liste: selectedDeck.liste }) });
      const data = await res.json();
      if(data && Array.isArray(data.karten)) setVisualDeck(data.karten);
    } catch { alert("Fehler beim Laden der Bilder."); }
    setLaedt(false);
  };

  const startPlaytest = () => {
    if(!visualDeck || !Array.isArray(visualDeck) || visualDeck.length === 0) {
        alert("Dein Deck konnte nicht visualisiert werden.");
        return;
    }
    let deckArray = [];
    visualDeck.forEach(k => { if(k && k.name && !k.name.includes("(Nicht gefunden)")) { for(let i=0; i<(k.count||1); i++) deckArray.push(k); }});
    for (let i = deckArray.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [deckArray[i], deckArray[j]] = [deckArray[j], deckArray[i]];
    }
    setPlaytest({ hand: deckArray.slice(0, 7), library: deckArray.slice(7), mulligans: 0 });
  };

  const doMulligan = () => {
    let deckArray = [];
    visualDeck.forEach(k => { if(k && k.name && !k.name.includes("(Nicht gefunden)")) { for(let i=0; i<(k.count||1); i++) deckArray.push(k); }});
    for (let i = deckArray.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [deckArray[i], deckArray[j]] = [deckArray[j], deckArray[i]];
    }
    const nextMulligans = playtest.mulligans + 1;
    const drawCount = Math.max(0, 7 - nextMulligans);
    setPlaytest({ hand: deckArray.slice(0, drawCount), library: deckArray.slice(drawCount), mulligans: nextMulligans });
  };

  const drawCard = () => {
    if(!playtest || !playtest.library || playtest.library.length === 0) return;
    const newHand = [...playtest.hand, playtest.library[0]];
    const newLibrary = playtest.library.slice(1);
    setPlaytest({ hand: newHand, library: newLibrary, mulligans: playtest.mulligans });
  };

  const holeAlleProxyKarten = () => {
    if(!visualDeck) return [];
    const proxyCards = [];
    visualDeck.forEach(k => {
        if(k && k.name && !k.name.includes("(Nicht gefunden)")) {
            const count = k.count || 1;
            for(let i=0; i<count; i++) proxyCards.push(k);
        }
    });
    return proxyCards;
  };

  useEffect(() => { ladeDecks(); }, [currentUser]);

  useEffect(() => {
    if (deckId && decks.length > 0) {
      const match = decks.find(d => String(d.id) === String(deckId));
      if (match) {
        if (!selectedDeck || String(selectedDeck.id) !== String(match.id)) {
          setSelectedDeck(match);
          setVisualDeck(null);
          setStats(null);
          setAnalyse(null);
          setDeckWert(null);
        }
      } else {
        setSelectedDeck(null);
      }
    } else {
      setSelectedDeck(null);
    }
  }, [deckId, decks]);

  useEffect(() => {
    if (currentTab === 'overview' && focusParam === 'create') {
      if (createInputRef.current) {
        createInputRef.current.focus();
        createInputRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [currentTab, focusParam, decks]);

  useEffect(() => {
    if (!selectedDeck) return;
    if (currentTab === 'visual' || currentTab === 'proxy') {
      if (!visualDeck && !laedt) {
        ladeVisuelleAnsicht(currentTab);
      }
    } else if (currentTab === 'stats') {
      ladeStatsUndAnalyse();
    }
  }, [currentTab, selectedDeck, selectedFormat]);

  const renderGruppierteKarten = () => {
    if(!visualDeck || !Array.isArray(visualDeck) || visualDeck.length === 0) return <p style={{textAlign: 'center', color: 'var(--text-muted)'}}>Keine Karten gefunden. Bitte prüfe die Namen im Editor.</p>;
    
    const grouped = { 
      Unbekannt: [], 
      Kommander: [], 
      Kreaturen: [], 
      Planeswalker: [],
      Artefakte: [], 
      Hexereien_Spontanzauber: [], 
      Verzauberungen: [], 
      Länder: [],
      Andere: []
    };
    
    visualDeck.forEach(k => {
       if(!k) return;
       const t = (k.type || "").toLowerCase();
       const isNotFound = k.type === "Unbekannt" || !k.image || (k.name && k.name.includes("(Nicht gefunden)"));
       
       if(isNotFound) grouped.Unbekannt.push(k);
       else if(t.includes('legendary creature') && grouped.Kommander.length === 0) grouped.Kommander.push(k);
       else if(t.includes('creature')) grouped.Kreaturen.push(k);
       else if(t.includes('planeswalker')) grouped.Planeswalker.push(k);
       else if(t.includes('artifact')) grouped.Artefakte.push(k);
       else if(t.includes('instant') || t.includes('sorcery')) grouped.Hexereien_Spontanzauber.push(k);
       else if(t.includes('enchantment')) grouped.Verzauberungen.push(k);
       else if(t.includes('land')) grouped.Länder.push(k);
       else grouped.Andere.push(k);
    });

    return (
      <div style={{display: 'flex', flexDirection: 'column', gap: '30px'}}>
        {Object.entries(grouped).map(([gruppe, karten]) => {
          if(!karten || karten.length === 0) return null;
          return (
            <div key={gruppe} style={{
              background: 'var(--bg-card)', 
              borderRadius: '16px', 
              padding: '25px', 
              border: '1px solid var(--border-color)',
              boxSizing: 'border-box'
            }}>
              <h4 style={{
                margin: '0 0 15px 0', 
                fontSize: '1.2rem', 
                fontWeight: 600, 
                color: gruppe === 'Unbekannt' ? 'var(--danger-color)' : 'var(--text-main)',
                borderBottom: '1px solid var(--border-color)',
                paddingBottom: '10px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <span>{gruppe.replace('_', ' & ')}</span>
                <span style={{fontSize: '0.9rem', color: 'var(--text-muted)', background: 'var(--bg-main)', padding: '4px 10px', borderRadius: '20px'}}>
                  {karten.reduce((acc, k) => acc + (k.count || 1), 0)} Karten
                </span>
              </h4>
              
              <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
                {karten.map((k, idx) => {
                  if(!k) return null;
                  const isUnbekannt = gruppe === 'Unbekannt' || (k.name && k.name.includes("(Nicht gefunden)"));
                  return (
                    <div 
                      key={k.name || idx} 
                      className="decklist-row-item"
                      onMouseEnter={(e) => { setHoveredCard(k); handleMouseMove(e); }}
                      onMouseMove={handleMouseMove}
                      onMouseLeave={() => setHoveredCard(null)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '10px 15px',
                        borderRadius: '8px',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease',
                        background: 'var(--bg-main)',
                        border: isUnbekannt ? '1px dashed var(--danger-color)' : '1px solid transparent'
                      }}
                    >
                      <div style={{display: 'flex', alignItems: 'center', gap: '12px'}}>
                        <span style={{
                          fontWeight: 700, 
                          color: isUnbekannt ? 'var(--danger-color)' : 'var(--accent-color)', 
                          fontSize: '1rem',
                          minWidth: '28px'
                        }}>
                          {k.count || 1}x
                        </span>
                        <span style={{
                          fontWeight: 500, 
                          fontSize: '1.05rem', 
                          color: isUnbekannt ? 'var(--danger-color)' : 'var(--text-main)',
                          textDecoration: isUnbekannt ? 'line-through' : 'none'
                        }}>
                          {k.name}
                        </span>
                      </div>
                      
                      <div style={{display: 'flex', alignItems: 'center', gap: '10px'}}>
                        {isUnbekannt && (
                          <span style={{
                            color: 'var(--danger-color)', 
                            fontSize: '0.8rem', 
                            background: 'rgba(255, 69, 58, 0.1)', 
                            padding: '3px 8px', 
                            borderRadius: '12px',
                            fontWeight: 600
                          }}>
                            Nicht erkannt
                          </span>
                        )}
                        <span style={{
                          fontSize: '0.85rem', 
                          color: 'var(--text-muted)'
                        }}>
                          {k.type || "Karte"}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="apple-main-container">
      <h2>Deck-Management & Tools.</h2>
      <p style={{marginBottom: '40px', fontSize: '1.2rem', color: 'var(--text-muted)'}}>Erstelle, editiere und analysiere deine Decks mit KI-Unterstützung.</p>

      {/* TABS SEGMENTED CONTROL */}
      <div className="segmented-control" style={{marginBottom: '40px', display: 'flex', justifyContent: 'center'}}>
        <button className={`segment-btn ${currentTab === 'overview' ? 'active' : ''}`} onClick={() => navigate(`/decks?tab=overview${deckId ? `&deckId=${deckId}` : ''}`)}>Deck-Center</button>
        <button className={`segment-btn ${currentTab === 'editor' ? 'active' : ''}`} onClick={() => navigate(`/decks?tab=editor${deckId ? `&deckId=${deckId}` : ''}`)}>Text-Editor</button>
        <button className={`segment-btn ${currentTab === 'visual' ? 'active' : ''}`} onClick={() => navigate(`/decks?tab=visual${deckId ? `&deckId=${deckId}` : ''}`)}>Deckliste</button>
        <button className={`segment-btn ${currentTab === 'stats' ? 'active' : ''}`} onClick={() => navigate(`/decks?tab=stats${deckId ? `&deckId=${deckId}` : ''}`)}>Analyse & Stats</button>
        <button className={`segment-btn ${currentTab === 'proxy' ? 'active' : ''}`} onClick={() => navigate(`/decks?tab=proxy${deckId ? `&deckId=${deckId}` : ''}`)}>Proxy-Druck</button>
      </div>

      {/* ACTIVE DECK BAR */}
      {selectedDeck && currentTab !== 'overview' && (
        <div style={{display: 'flex', alignItems: 'center', gap: '15px', background: 'var(--btn-secondary)', padding: '15px 25px', borderRadius: '16px', marginBottom: '30px', flexWrap: 'wrap', border: '1px solid var(--border-color)'}}>
          <span style={{fontWeight: 600, color: 'var(--text-muted)'}}>Aktives Deck:</span>
          <span style={{fontWeight: 700, fontSize: '1.1rem'}}>{selectedDeck.name}</span>
          
          <div style={{marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '15px', flexWrap: 'wrap'}}>
            <span style={{fontSize: '0.9rem', color: 'var(--text-muted)'}}>Deck wechseln:</span>
            <select
              value={deckId || ""}
              onChange={(e) => navigate(`/decks?tab=${currentTab}&deckId=${e.target.value}`)}
              style={{padding: '8px 12px', fontSize: '0.9rem', width: 'auto', borderRadius: '8px', background: 'var(--bg-card)', border: '1px solid var(--border-color)', cursor: 'pointer', color: 'var(--text-main)'}}
            >
              {decks.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
            <button
              className="danger-btn-subtle"
              onClick={() => loescheDeck(selectedDeck.id, selectedDeck.name)}
              style={{padding: '8px 16px', borderRadius: '8px', fontSize: '0.9rem'}}
            >
              Deck löschen
            </button>
            <button
              className="secondary-btn"
              onClick={() => navigate(`/decks?tab=overview`)}
              style={{padding: '8px 16px', borderRadius: '8px', fontSize: '0.9rem', background: 'var(--bg-card)'}}
            >
              ← Zurück zur Übersicht
            </button>
          </div>
        </div>
      )}

      {/* TABS OVERVIEW CONTENT */}
      {currentTab === 'overview' && (
        <>
          <div className="content-card" style={{marginBottom: '50px', padding: '30px'}}>
            <h4 style={{marginBottom: '15px'}}>Neues Deck erstellen</h4>
            <div style={{display: 'flex', gap: '15px', marginBottom: '15px'}}>
              <input 
                ref={createInputRef}
                placeholder="Deckname..." 
                value={newDeckName} 
                onChange={e => setNewDeckName(e.target.value)} 
                style={{background: 'var(--input-bg)'}} 
              />
            </div>
            <textarea placeholder="Optional: Kopiere hier direkt eine komplette Deckliste hinein..." value={importListe} onChange={e => setImportListe(e.target.value)} style={{height: '100px', background: 'var(--input-bg)', marginBottom: '15px'}} />
            <button className="primary-btn" onClick={erstelleDeck}>Deck anlegen</button>
          </div>

          <h3 style={{marginBottom: '20px', fontSize: '1.8rem'}}>Meine Decks</h3>
          {decks.length === 0 ? (
            <p style={{color: 'var(--text-muted)'}}>Keine Decks gefunden. Erstelle dein erstes Deck oben!</p>
          ) : (
            <div className="gallery-grid" style={{gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))'}}>
              {(decks || []).map((d, idx) => {
                if(!d) return null;
                const isCurrentActive = String(d.id) === String(deckId);
                return (
                <div 
                  key={d.id || idx} 
                  className="gallery-item" 
                  style={{
                    cursor: 'pointer', 
                    padding: '35px', 
                    display: 'flex', 
                    flexDirection: 'column', 
                    justifyContent: 'center', 
                    minHeight: '130px',
                    borderColor: isCurrentActive ? 'var(--accent-color)' : 'var(--border-color)',
                    borderWidth: isCurrentActive ? '2.2px' : '1px',
                    background: isCurrentActive ? 'var(--btn-secondary)' : 'var(--bg-card)'
                  }}
                >
                  <button className="gallery-remove-btn" onClick={(e) => { e.stopPropagation(); loescheDeck(d.id, d.name); }}>✕</button>
                  <div onClick={() => navigate(`/decks?tab=editor&deckId=${d.id}`)}>
                    <h3 style={{fontSize: '1.5rem', marginBottom: '10px'}}>{d.name}</h3>
                    <p style={{margin: 0, fontSize: '0.9rem', color: 'var(--text-muted)'}}>
                      {isCurrentActive ? "Aktiviert • Editor öffnen" : "Öffnen & Bearbeiten"}
                    </p>
                  </div>
                </div>
              )})}
            </div>
          )}
        </>
      )}

      {/* OTHER TABS: NO DECK SELECTED SELECTOR */}
      {currentTab !== 'overview' && !selectedDeck && (
        <div className="content-card" style={{padding: '50px', textAlign: 'center'}}>
          <h3 style={{fontSize: '1.8rem', marginBottom: '15px'}}>Kein Deck ausgewählt</h3>
          <p style={{color: 'var(--text-muted)', marginBottom: '40px'}}>Bitte wähle ein Deck aus dem Deck-Center aus oder wähle eins aus der Liste unten:</p>
          
          {decks.length === 0 ? (
            <div>
              <p style={{color: 'var(--text-muted)', marginBottom: '20px'}}>Du hast noch keine Decks erstellt.</p>
              <button className="primary-btn" onClick={() => navigate('/decks?tab=overview')}>Neues Deck erstellen</button>
            </div>
          ) : (
            <div className="gallery-grid" style={{gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))'}}>
              {decks.map((d, idx) => (
                <div 
                  key={d.id || idx} 
                  className="gallery-item" 
                  onClick={() => navigate(`/decks?tab=${currentTab}&deckId=${d.id}`)}
                  style={{cursor: 'pointer', padding: '35px', display: 'flex', flexDirection: 'column', justifyContent: 'center', minHeight: '130px'}}
                >
                  <h3 style={{fontSize: '1.5rem', marginBottom: '10px'}}>{d.name}</h3>
                  <p style={{margin: 0, fontSize: '0.9rem', color: 'var(--text-muted)'}}>Auswählen</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TEXT EDITOR TAB CONTENT */}
      {selectedDeck && currentTab === "editor" && (
        <DeckEditor 
          selectedDeck={selectedDeck} 
          currentUser={currentUser} 
          ladeDecks={ladeDecks} 
        />
      )}

      {/* VISUELLE ANSICHT TAB CONTENT */}
      {selectedDeck && currentTab === "visual" && (
        <div className="content-card" style={{padding: '40px'}}>
          {laedt ? <div className="spinner"></div> : (
            <>
              {(!visualDeck || visualDeck.length === 0) ? (
                 <p style={{textAlign: 'center', color: 'var(--text-muted)'}}>Keine Karten gefunden. Hast du Namen im Editor eingegeben?</p>
              ) : (
                <>
                  <div style={{textAlign: 'right', marginBottom: '20px'}}>
                    <button className="primary-btn" style={{padding: '16px 30px', fontSize: '1.1rem'}} onClick={startPlaytest}>
                       <Icons.Sparkles /> Starthand Simulator starten
                    </button>
                  </div>
                  {renderGruppierteKarten()}
                </>
              )}
            </>
          )}
        </div>
      )}

      {/* STATISTIKEN TAB CONTENT */}
      {selectedDeck && currentTab === "stats" && (
        <div className="content-card" style={{padding: '40px', animation: 'fadeIn 0.6s ease'}}>
          {laedt ? <div style={{textAlign: 'center', padding: '60px'}}><div className="spinner"></div><p style={{marginTop: '20px'}}>Deck wird analysiert...</p></div> : (
            <>
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '40px', flexWrap: 'wrap', gap: '20px'}}>
                <h3 style={{margin: 0, fontSize: '2.2rem'}}>Deck-Statistiken & Regelcheck</h3>
                
                <div style={{display: 'flex', alignItems: 'center', gap: '15px'}}>
                  <span style={{fontWeight: 600, color: 'var(--text-muted)'}}>Format validieren:</span>
                  <select 
                    value={selectedFormat} 
                    onChange={e => setSelectedFormat(e.target.value)} 
                    style={{padding: '10px 18px', borderRadius: '10px', background: 'var(--btn-secondary)', border: '1px solid var(--border-color)', width: 'auto', cursor: 'pointer', fontWeight: 600, color: 'var(--text-main)'}}
                  >
                    <option value="commander">Commander / EDH</option>
                    <option value="standard">Standard</option>
                    <option value="modern">Modern</option>
                    <option value="pioneer">Pioneer</option>
                    <option value="legacy">Legacy</option>
                    <option value="vintage">Vintage</option>
                  </select>
                </div>
              </div>

              {/* === ZUSAMMENFASSUNG INFO-BOXEN === */}
              {(() => {
                const totalSpells = stats ? Object.values(stats.cmc || {}).reduce((a, b) => a + b, 0) : 0;
                const avgCmc = stats && stats.cmc ? (() => {
                  let sum = 0; let count = 0;
                  Object.entries(stats.cmc).forEach(([cmc, cnt]) => { sum += parseInt(cmc) * cnt; count += cnt; });
                  return count > 0 ? (sum / count).toFixed(2) : '0.00';
                })() : '0.00';
                
                return (
                  <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '20px', marginBottom: '40px'}}>
                    <div style={{background: 'rgba(97, 218, 251, 0.08)', border: '1px solid rgba(97, 218, 251, 0.2)', borderRadius: '16px', padding: '20px', textAlign: 'center'}}>
                      <div style={{fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px'}}>Zaubersprüche</div>
                      <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--text-main)'}}>{totalSpells}</div>
                    </div>
                    <div style={{background: 'rgba(50, 215, 75, 0.08)', border: '1px solid rgba(50, 215, 75, 0.2)', borderRadius: '16px', padding: '20px', textAlign: 'center'}}>
                      <div style={{fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px'}}>Ø Manakosten</div>
                      <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--text-main)'}}>
                        <img src="https://svgs.scryfall.io/card-symbols/S.svg" alt="" style={{width: '20px', height: '20px', verticalAlign: 'middle', marginRight: '6px', opacity: 0.7}} />
                        {avgCmc}
                      </div>
                    </div>
                    {deckWert && (
                      <div style={{background: 'rgba(255, 214, 10, 0.08)', border: '1px solid rgba(255, 214, 10, 0.2)', borderRadius: '16px', padding: '20px', textAlign: 'center'}}>
                        <div style={{fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px'}}>Deckwert</div>
                        <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--text-main)'}}>{deckWert.gesamt_wert} €</div>
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* === MANAKURVE === */}
              {stats && stats.cmc && Object.keys(stats.cmc).length > 0 ? (
                (() => {
                  const maxCmcCount = Math.max(...Object.values(stats.cmc).map(v => parseInt(v) || 0), 1);
                  const colorNameMap = {
                    "W": {name: "Weiß", svg: "https://svgs.scryfall.io/card-symbols/W.svg"},
                    "U": {name: "Blau", svg: "https://svgs.scryfall.io/card-symbols/U.svg"},
                    "B": {name: "Schwarz", svg: "https://svgs.scryfall.io/card-symbols/B.svg"},
                    "R": {name: "Rot", svg: "https://svgs.scryfall.io/card-symbols/R.svg"},
                    "G": {name: "Grün", svg: "https://svgs.scryfall.io/card-symbols/G.svg"},
                    "C": {name: "Farblos", svg: "https://svgs.scryfall.io/card-symbols/C.svg"}
                  };
                  const totalColorCards = Object.values(stats.colors || {}).reduce((a, b) => a + b, 0);
                  
                  return (
                    <div style={{display: 'flex', flexDirection: 'column', gap: '40px', marginBottom: '50px'}}>
                      
                      {/* MANAKURVE */}
                      <div style={{background: 'rgba(0, 0, 0, 0.15)', border: '1px solid var(--border-color)', borderRadius: '20px', padding: '30px'}}>
                        <h4 style={{color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 20px 0'}}>
                          Manakurve
                        </h4>
                        <div style={{display: 'flex', alignItems: 'flex-end', justifyContent: 'space-around', height: '200px', padding: '0 10px'}}>
                          {Object.keys(stats?.cmc || {}).sort((a,b) => parseInt(a)-parseInt(b)).map(cmc => {
                             const val = stats.cmc[cmc] || 0;
                             const pct = (val / maxCmcCount) * 75;
                             const cmcNum = parseInt(cmc);
                             const manaSymbolUrl = cmcNum <= 20 ? `https://svgs.scryfall.io/card-symbols/${cmcNum}.svg` : null;
                             return (
                               <div key={cmc} style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', flex: 1, height: '100%', justifyContent: 'flex-end'}}>
                                 <span style={{fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-main)'}}>{val}</span>
                                 <div style={{
                                   width: '32px', 
                                   height: `${pct}%`, 
                                   minHeight: val > 0 ? '6px' : '0px',
                                   background: 'linear-gradient(180deg, #61dafb 0%, #2b95d6 100%)',
                                   borderRadius: '6px 6px 2px 2px',
                                   boxShadow: '0 0 12px rgba(97, 218, 251, 0.3)',
                                   transition: 'height 0.6s cubic-bezier(0.16, 1, 0.3, 1)'
                                 }}></div>
                                 {manaSymbolUrl ? (
                                   <img src={manaSymbolUrl} alt={`Kosten ${cmc}`} title={`Manakosten ${cmc}`} style={{width: '24px', height: '24px'}} />
                                 ) : (
                                   <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 600}}>{cmc}+</span>
                                 )}
                               </div>
                             );
                          })}
                        </div>
                      </div>

                      {/* FARBVERTEILUNG */}
                      <div style={{background: 'rgba(0, 0, 0, 0.15)', border: '1px solid var(--border-color)', borderRadius: '20px', padding: '30px'}}>
                        <h4 style={{color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 25px 0'}}>
                          Farbverteilung
                        </h4>
                        <div style={{display: 'flex', flexWrap: 'wrap', gap: '20px', justifyContent: 'center'}}>
                          {Object.keys(stats?.colors || {}).filter(c => stats.colors[c] > 0).map(c => {
                             const colorInfo = colorNameMap[c] || {name: c, svg: null};
                             const count = stats.colors[c];
                             const percentage = totalColorCards > 0 ? ((count / totalColorCards) * 100).toFixed(0) : 0;
                             return (
                               <div key={c} style={{
                                 display: 'flex', 
                                 alignItems: 'center', 
                                 gap: '14px',
                                 background: 'rgba(255, 255, 255, 0.04)',
                                 border: '1px solid var(--border-color)',
                                 borderRadius: '14px',
                                 padding: '16px 24px',
                                 minWidth: '160px',
                                 transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                                 cursor: 'default'
                               }}>
                                 {colorInfo.svg && (
                                   <img src={colorInfo.svg} alt={colorInfo.name} style={{width: '36px', height: '36px', flexShrink: 0}} />
                                 )}
                                 <div style={{display: 'flex', flexDirection: 'column', gap: '2px'}}>
                                   <span style={{fontWeight: 700, fontSize: '1.1rem', color: 'var(--text-main)'}}>{colorInfo.name}</span>
                                   <span style={{fontSize: '0.85rem', color: 'var(--text-muted)'}}>{count} Karten · {percentage}%</span>
                                 </div>
                               </div>
                             );
                          })}
                        </div>
                      </div>
                    </div>
                  );
                })()
              ) : (
                  <p style={{color: 'var(--text-muted)', marginBottom: '40px'}}>Keine Statistiken verfügbar. Ist das Deck leer?</p>
              )}

              {validation && (
                <div style={{
                  background: validation.legal ? 'rgba(48, 209, 88, 0.08)' : 'rgba(255, 69, 58, 0.08)',
                  border: `1px solid ${validation.legal ? '#30D158' : '#FF453A'}`,
                  borderRadius: '20px',
                  padding: '30px',
                  marginBottom: '50px'
                }}>
                  <div style={{display: 'flex', alignItems: 'center', gap: '15px', marginBottom: '20px'}}>
                    <span style={{fontSize: '2rem'}}>{validation.legal ? "✅" : "⚠️"}</span>
                    <div>
                      <h4 style={{margin: 0, fontSize: '1.4rem', color: 'var(--text-main)'}}>
                        {validation.legal ? "Deck ist Regelkonform (Legal)" : "Regelverstöße gefunden (Illegal)"}
                      </h4>
                      <p style={{margin: 0, fontSize: '0.95rem', color: 'var(--text-muted)'}}>
                        Format: <span style={{textTransform: 'capitalize', fontWeight: 600, color: 'var(--text-main)'}}>{validation.details?.format}</span> | Karten im Deck: <strong style={{color: 'var(--text-main)'}}>{validation.details?.total_cards}</strong>
                      </p>
                    </div>
                  </div>
                  
                  {validation.errors && validation.errors.length > 0 && (
                    <div style={{marginBottom: '20px'}}>
                      <h5 style={{color: '#FF453A', fontSize: '1.05rem', margin: '0 0 10px 0', fontWeight: 600}}>Fehler:</h5>
                      <ul style={{margin: 0, paddingLeft: '20px', color: 'var(--text-main)', fontSize: '0.95rem', lineHeight: '1.6'}}>
                        {validation.errors.map((err, i) => <li key={i} style={{marginBottom: '6px'}}>{err}</li>)}
                      </ul>
                    </div>
                  )}

                  {validation.warnings && validation.warnings.length > 0 && (
                    <div>
                      <h5 style={{color: '#FF9500', fontSize: '1.05rem', margin: '0 0 10px 0', fontWeight: 600}}>Hinweise:</h5>
                      <ul style={{margin: 0, paddingLeft: '20px', color: 'var(--text-main)', fontSize: '0.95rem', lineHeight: '1.6'}}>
                        {validation.warnings.map((warn, i) => <li key={i} style={{marginBottom: '6px'}}>{warn}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {analyse && !analyse.error && analyse.strategie && (
                <DeckAnalysis 
                  analyse={analyse} 
                  deckWert={deckWert} 
                  userRole={userRole} 
                />
              )}

              {analyse && analyse.error && (
                  <div style={{background: 'var(--danger-bg)', color: 'var(--danger-color)', padding: '20px', borderRadius: '12px', textAlign: 'center'}}>
                      {analyse.error}
                  </div>
              )}

              {deckWert && (
                <div style={{marginTop: '50px', paddingTop: '30px', borderTop: '1px solid var(--border-color)', textAlign: 'right'}}>
                  <span style={{fontSize: '0.95rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginRight: '15px', letterSpacing: '0.05em'}}>Geschätzter Marktwert</span>
                  <span style={{color: 'var(--price-color)', fontWeight: 600, fontSize: '2.5rem', letterSpacing: '-0.04em'}}>{deckWert?.gesamt_wert || "0.00"} €</span>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {selectedDeck && currentTab === "proxy" && (
        <div className="content-card" style={{padding: '40px'}}>
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px'}}>
             <div>
               <h3 style={{fontSize: '2rem', margin: 0}}>Proxy-Druck (PDF)</h3>
               <p style={{margin: '5px 0 0 0', color: 'var(--text-muted)'}}>Drucke diese Seite im A4-Format (ohne Ränder). Die Karten haben exakte Turnier-Maße (63x88mm).</p>
             </div>
             {visualDeck && visualDeck.length > 0 && (
                  <button className="primary-btn" onClick={() => window.print()}><Icons.ExternalLink /> Jetzt Drucken</button>
             )}
          </div>
          
          {laedt ? <div className="spinner"></div> : (
            (!visualDeck || visualDeck.length === 0) ? (
               <p style={{textAlign: 'center', color: 'var(--text-muted)'}}>Keine Karten zum Drucken gefunden. Füge zuerst Karten in den Editor ein.</p>
            ) : (
                <div className="proxy-print-area">
                  <div className="proxy-preview-grid">
                      {holeAlleProxyKarten().map((k, i) => (
                        <img 
                          key={i} 
                          src={k?.image || getFallbackCardImage(k?.name, k?.type)} 
                          alt={k?.name} 
                          className="proxy-print-img" 
                          style={{width: '100%', borderRadius: '4.75% / 3.5%'}} 
                          loading="lazy"
                          onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(k?.name, k?.type); }}
                        />
                      ))}
                  </div>
                </div>
            )
          )}
        </div>
      )}

      {/* ERWEITERTER STARTHAND SIMULATOR MODAL */}
      {playtest && (
        <div className="modal-overlay" onClick={() => setPlaytest(null)}>
          <div className="modal-content" style={{maxWidth: '1200px', background: 'var(--bg-main)'}} onClick={e => e.stopPropagation()}>
            <button className="close-btn" onClick={() => setPlaytest(null)}>✕</button>
            
            <h2 style={{marginBottom: '5px', fontSize: '2.5rem', textAlign: 'center'}}>Starthand Simulator</h2>
            <p style={{textAlign: 'center', color: 'var(--text-muted)', marginBottom: '40px'}}>
               Karten in der Bibliothek: <strong style={{color: 'var(--text-main)'}}>{(playtest.library || []).length}</strong> | Genommene Mulligans: <strong style={{color: 'var(--danger-color)'}}>{playtest.mulligans}</strong>
            </p>

            <div className="playtest-hand-container">
              {(playtest.hand || []).map((k, i) => (
                <img 
                  key={i} 
                  src={k?.image || getFallbackCardImage(k?.name, k?.type)} 
                  alt={k?.name || "Unbekannt"} 
                  className="playtest-card" 
                  style={{zIndex: i}} 
                  loading="lazy"
                  onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(k?.name, k?.type); }}
                />
              ))}
              {(!playtest.hand || playtest.hand.length === 0) && <p style={{color: 'var(--text-muted)'}}>Keine Karten mehr in der Hand.</p>}
            </div>
            
            <div style={{textAlign: 'center', marginTop: '60px', display: 'flex', gap: '20px', justifyContent: 'center'}}>
              <button className="secondary-btn" style={{padding: '16px 30px', fontSize: '1.1rem'}} onClick={doMulligan}>Mulligan nehmen</button>
              <button className="primary-btn" style={{padding: '16px 30px', fontSize: '1.1rem'}} onClick={drawCard}>Karte ziehen</button>
            </div>
          </div>
        </div>
      )}

      {/* FLOATING HOVER CARD PREVIEW */}
      {hoveredCard && (
        <div style={{
          position: 'fixed',
          left: mousePos.x,
          top: mousePos.y,
          zIndex: 99999,
          pointerEvents: 'none',
          animation: 'fadeIn 0.1s ease-out',
          boxShadow: '0 12px 40px rgba(0,0,0,0.6)',
          borderRadius: '14px',
          overflow: 'hidden',
          width: '240px',
          height: '340px',
          background: '#1C1C1E',
          border: '1px solid #38383A'
        }}>
          <img 
            src={hoveredCard.image || getFallbackCardImage(hoveredCard.name, hoveredCard.type)} 
            alt={hoveredCard.name}
            style={{ width: '100%', height: '100%', display: 'block', objectFit: 'cover' }}
            onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(hoveredCard.name, hoveredCard.type); }}
          />
        </div>
      )}
    </div>
  );
}

export default DecksView;
