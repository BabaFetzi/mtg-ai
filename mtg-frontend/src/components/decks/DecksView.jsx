import { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Icons from '../../utils/Icons';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';
import { isPaywallResponse, handlePaywallResponse, DEFAULT_PAYWALL_MESSAGE } from '../../utils/paywall';
import PremiumOverlay from '../layout/PremiumOverlay';
import { Copy, Sparkles, Flame, CheckCircle2, AlertTriangle, Printer, RefreshCw, Infinity } from 'lucide-react';
import DeckEditor from './DeckEditor';
import DeckAnalysis from './DeckAnalysis';

// Die 8 vormals gleichwertigen Tabs zu 4 Gruppen zusammengefasst (Bearbeiten /
// Analysieren / Extras + die alleinstehende Deck-Bibliothek), damit die
// Tab-Leiste nicht mehr aus 8 nebeneinander konkurrierenden Buttons besteht.
// Die `tab`-Werte (URL-Query-Param) bleiben unverändert -- nur die visuelle
// Gruppierung ändert sich, damit bestehende Links (z.B. der focus=combos-
// Sprung von der Deckliste zu Analyse & Stats) unangetastet bleiben.
const TAB_GROUPS = [
  { id: 'overview', label: 'Deck-Bibliothek', tabs: [
      { tab: 'overview', label: 'Deck-Bibliothek' },
    ] },
  { id: 'edit', label: 'Bearbeiten', tabs: [
      { tab: 'visual', label: 'Deckliste' },
      { tab: 'editor', label: 'Text-Editor' },
    ] },
  { id: 'analyze', label: 'Analysieren', tabs: [
      { tab: 'stats', label: 'Analyse & Stats' },
      { tab: 'tuning', label: 'Tuning' },
      { tab: 'compare', label: 'Vergleich' },
    ] },
  { id: 'extras', label: 'Extras', tabs: [
      { tab: 'roast', label: 'Deck-Roast' },
      { tab: 'proxy', label: 'Proxy-Druck' },
    ] },
];

function DecksView({ currentUser, userRole, onShowPremiumModal }) {
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
  const [cmcFilter, setCmcFilter] = useState("all");
  const [copyStatus, setCopyStatus] = useState("");

  // Preview-Position bewusst per ref direkt am DOM gesetzt, NICHT über State:
  // ein setState pro mousemove würde die komplette DecksView bei jeder
  // Mausbewegung neu rendern (Hover-Animation ruckelt).
  const previewRef = useRef(null);
  const lastMousePos = useRef({ x: 0, y: 0 });

  // Callback-Ref statt Inline-Style: positioniert die Preview beim Mount an
  // der zuletzt bekannten Mausposition, ohne den ref im Render zu lesen.
  const setPreviewRef = (node) => {
    previewRef.current = node;
    if (node) {
      node.style.left = `${lastMousePos.current.x}px`;
      node.style.top = `${lastMousePos.current.y}px`;
    }
  };

  const handleMouseMove = (e) => {
    const cardWidth = 240;
    const cardHeight = 340;
    const x = e.clientX + cardWidth + 25 > window.innerWidth
      ? e.clientX - cardWidth - 15
      : e.clientX + 15;
    const y = e.clientY + cardHeight + 25 > window.innerHeight
      ? e.clientY - cardHeight - 15
      : e.clientY + 15;
    lastMousePos.current = { x, y };
    if (previewRef.current) {
      previewRef.current.style.left = `${x}px`;
      previewRef.current.style.top = `${y}px`;
    }
  };

  const [laedt, setLaedt] = useState(false);
  const [analyse, setAnalyse] = useState(null);
  const [stats, setStats] = useState(null);
  const [roastData, setRoastData] = useState(null);
  const [roastLoading, setRoastLoading] = useState(false);
  const [compareDeckId, setCompareDeckId] = useState("");
  const [deckWert, setDeckWert] = useState(null);
  const [quickSearch, setQuickSearch] = useState("");
  const [loadedImages, setLoadedImages] = useState({});
  const [quickResult, setQuickResult] = useState(null);
  const [selectedFormat, setSelectedFormat] = useState("commander");
  const [validation, setValidation] = useState(null);
  const [newDeckFormat, setNewDeckFormat] = useState("commander");

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
        body: JSON.stringify({ benutzername: currentUser, deck_name: newDeckName, deck_liste: importListe, format: newDeckFormat }) 
      });
      
      if (res.status === 403) {
        onShowPremiumModal();
        return;
      }
      
      const data = await res.json();
      if (data && data.erfolg) {
        setNewDeckName(""); setImportListe(""); setNewDeckFormat("commander");
        const resList = await fetch(`/api/decks/${currentUser}`); 
        const dataList = await resList.json();
        if(Array.isArray(dataList)) {
          setDecks(dataList);
          const created = dataList.find(d => d.name === newDeckName) || dataList[dataList.length - 1];
          if (created) {
            navigate(`/decks?tab=editor&deckId=${created.id}`);
          }
        }
      } else {
        alert(data.error || "Fehler beim Erstellen des Decks.");
      }
    } catch {
      alert("Fehler beim Erstellen des Decks.");
    }
  };

  const kloneTemplateDeck = async (templateName, templateListe) => {
    try {
      const res = await fetch(`/api/decks/erstellen`, { 
        method: "POST", 
        headers: {"Content-Type": "application/json"}, 
        body: JSON.stringify({ benutzername: currentUser, deck_name: templateName, deck_liste: templateListe }) 
      });
      
      if (res.status === 403) {
        onShowPremiumModal();
        return;
      }
      
      const data = await res.json();
      if (data && data.erfolg) {
        const resList = await fetch(`/api/decks/${currentUser}`); 
        const dataList = await resList.json();
        if(Array.isArray(dataList)) {
          setDecks(dataList);
          const created = dataList.find(d => d.name === templateName) || dataList[dataList.length - 1];
          if (created) {
            navigate(`/decks?tab=editor&deckId=${created.id}`);
          }
        }
      } else {
        alert(data.error || "Fehler beim Klonen des Decks.");
      }
    } catch (e) {
      console.error(e);
      alert("Fehler beim Klonen des Decks.");
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

  const addCardFromTuning = async (cardName) => {
    if (!selectedDeck) return;
    try {
      const res = await fetch(`/api/deck/add-card`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deck_id: selectedDeck.id, card_name: cardName, benutzername: currentUser })
      });
      const data = await res.json();
      if (data && data.erfolg) {
        setSelectedDeck({ ...selectedDeck, liste: data.deck_liste });
        ladeDecks();
        alert(`"${cardName}" zum Deck hinzugefügt!`);
      } else {
        alert(data.error || "Fehler beim Hinzufügen.");
      }
    } catch {
      alert("Fehlgeschlagen.");
    }
  };

  const removeCardFromTuning = async (cardName) => {
    if (!selectedDeck) return;
    try {
      const res = await fetch(`/api/deck/remove-card`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deck_id: selectedDeck.id, card_name: cardName, benutzername: currentUser })
      });
      const data = await res.json();
      if (data && data.erfolg) {
        setSelectedDeck({ ...selectedDeck, liste: data.deck_liste });
        ladeDecks();
        alert(`"${cardName}" aus dem Deck entfernt.`);
      } else {
        alert(data.error || "Fehler beim Entfernen.");
      }
    } catch {
      alert("Fehlgeschlagen.");
    }
  };

  const formatDeckForArena = (liste) => {
    if (!liste) return "";
    return liste.split('\n')
      .map(line => {
        const clean = line.trim();
        if (!clean) return "";
        if (clean.startsWith('//') || clean.startsWith('#')) return "";
        const match = clean.match(/^(\d+)[xX]?\s+(.+)$/);
        if (match) {
          return `${match[1]} ${match[2].trim()}`;
        }
        return `1 ${clean}`;
      })
      .filter(line => line !== "")
      .join('\n');
  };

  const exportDeckText = () => {
    if (!selectedDeck || !selectedDeck.liste) return;
    const text = formatDeckForArena(selectedDeck.liste);
    navigator.clipboard.writeText(text)
      .then(() => {
        setCopyStatus("Kopiert!");
        setTimeout(() => setCopyStatus(""), 2000);
      })
      .catch((err) => {
        console.error("Clipboard copy failed:", err);
        alert("Kopieren fehlgeschlagen. Hier ist die Liste:\n\n" + text);
      });
  };

  const holeRoast = async () => {
    if (!selectedDeck || !selectedDeck.liste) return;
    setRoastLoading(true);
    try {
      const res = await fetch('/api/deck/roast', {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          deck_liste: selectedDeck.liste,
          benutzername: currentUser,
          format: selectedFormat
        })
      });
      const data = await res.json();
      if (isPaywallResponse(data)) {
        handlePaywallResponse(data, onShowPremiumModal);
        setRoastData(null);
        return;
      }
      setRoastData(data);
    } catch (e) {
      console.error(e);
      alert("Roast-Generierung fehlgeschlagen.");
    } finally {
      setRoastLoading(false);
    }
  };

  const handleQuickSearch = async () => {
    if(!quickSearch) return;
    try {
      const res = await fetch(`/api/suche/${encodeURIComponent(quickSearch)}?benutzername=${currentUser}`);
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

  // Normalisiert die /api/deck/analyse-Antwort, BEVOR sie in den `analyse`-State
  // wandert: `analyse.error` wird an anderer Stelle direkt als lesbarer Text
  // angezeigt (siehe "KI nicht erreichbar." unten) -- die rohe Paywall-Antwort
  // {error: "paywall", message: "..."} würde dort sonst wörtlich "paywall"
  // anzeigen statt einer verständlichen Meldung. Normalerweise wird dieser
  // Fetch nur bei userRole === 'premium' überhaupt ausgelöst; die Paywall kann
  // hier also nur bei einer veralteten/rassigen Rollenangabe auftreten -- dann
  // öffnet sich zusätzlich das Upgrade-Modal.
  const applyAnalyseResponse = (data) => {
    if (isPaywallResponse(data)) {
      handlePaywallResponse(data, onShowPremiumModal);
      setAnalyse({ error: data.message || DEFAULT_PAYWALL_MESSAGE });
      return;
    }
    setAnalyse(data);
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
      .then(applyAnalyseResponse)
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
      if (!res.ok) {
        throw new Error(`Server antwortete mit Status ${res.status}`);
      }
      const data = await res.json();
      if(data && Array.isArray(data.karten)) {
        setVisualDeck(data.karten);
      } else {
        throw new Error("Ungültiges Datenformat erhalten.");
      }
    } catch (err) {
      console.error("Fehler beim Visualisieren des Decks:", err);
      alert("Fehler beim Laden der Bilder: " + err.message);
    }
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
          setSelectedFormat(match.format || "commander");
          setVisualDeck(null);
          setStats(null);
          setAnalyse(null);
          setDeckWert(null);
          setRoastData(null);
          setCompareDeckId("");
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
      if (currentTab === 'visual' && userRole === 'premium' && !analyse && !laedt) {
        fetch(`/api/deck/analyse`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ deck_liste: selectedDeck.liste, benutzername: currentUser, format: selectedFormat })
        })
        .then(res => res.json())
        .then(applyAnalyseResponse)
        .catch((err) => console.error("Error loading combos in background", err));
      }
    } else if (currentTab === 'stats' || currentTab === 'tuning') {
      ladeStatsUndAnalyse();
    }
  }, [currentTab, selectedDeck, selectedFormat, userRole]);

  useEffect(() => {
    if (currentTab === 'stats' && focusParam === 'combos') {
      const timer = setTimeout(() => {
        const el = document.getElementById('analysis-combos');
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.style.boxShadow = '0 0 20px rgba(196, 146, 62, 0.6)';
          setTimeout(() => {
            el.style.boxShadow = '';
          }, 2000);
        }
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [currentTab, focusParam, laedt, analyse]);

  const findCombosForCard = (cardName) => {
    if (!analyse || !Array.isArray(analyse.combos)) return [];
    const cleanName = (name) => (name || "").toLowerCase().trim();
    const searchName = cleanName(cardName);
    return analyse.combos.filter(combo => {
      if (Array.isArray(combo.karten)) {
        return combo.karten.some(k => cleanName(k) === searchName);
      }
      return false;
    });
  };

  const renderGruppierteKarten = () => {
    if(!visualDeck || !Array.isArray(visualDeck) || visualDeck.length === 0) return <p style={{textAlign: 'center', color: 'var(--text-muted)'}}>Keine Karten gefunden. Bitte prüfe die Namen im Editor.</p>;
    
    const grouped = { 
      Unbekannt: [], 
      Commander: [], 
      Kreaturen: [], 
      Planeswalker: [],
      Artefakte: [], 
      "Spontanzauber & Hexereien": [], 
      Verzauberungen: [], 
      Länder: [],
      Sonstige: []
    };
    
    visualDeck.forEach(k => {
       if(!k) return;
       const t = (k.type || "").toLowerCase();
       const isNotFound = k.type === "Unbekannt" || !k.image || (k.name && k.name.includes("(Nicht gefunden)"));
       
       if(isNotFound) grouped.Unbekannt.push(k);
       else if(t.includes('legendary creature') && grouped.Commander.length === 0) grouped.Commander.push(k);
       else if(t.includes('creature')) grouped.Kreaturen.push(k);
       else if(t.includes('planeswalker')) grouped.Planeswalker.push(k);
       else if(t.includes('artifact')) grouped.Artefakte.push(k);
       else if(t.includes('instant') || t.includes('sorcery')) grouped["Spontanzauber & Hexereien"].push(k);
       else if(t.includes('enchantment')) grouped.Verzauberungen.push(k);
       else if(t.includes('land')) grouped.Länder.push(k);
       else grouped.Sonstige.push(k);
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
                <span>{gruppe}</span>
                <span style={{fontSize: '0.9rem', color: 'var(--text-muted)', background: 'var(--bg-main)', padding: '4px 10px', borderRadius: '20px'}}>
                  {karten.reduce((acc, k) => acc + (k.count || 1), 0)} Karten
                </span>
              </h4>
              
              <div style={{display: 'flex', flexDirection: 'column'}}>
                {karten.map((k, idx) => {
                  if(!k) return null;
                  const isUnbekannt = gruppe === 'Unbekannt' || (k.name && k.name.includes("(Nicht gefunden)"));
                  const isLast = idx === karten.length - 1;
                  const cmcVal = typeof k.cmc === 'number' ? k.cmc : parseFloat(k.cmc) || 0;
                  const cmcDisplay = Number.isInteger(cmcVal) ? cmcVal : cmcVal.toFixed(1);
                  const priceVal = parseFloat(k.price);
                  const priceDisplay = isNaN(priceVal) ? '0.00' : priceVal.toFixed(2);
                  return (
                    <div
                      key={k.name || idx}
                      className="decklist-row-item"
                      onMouseEnter={(e) => { setHoveredCard(k); handleMouseMove(e); e.currentTarget.style.background = 'var(--btn-secondary)'; }}
                      onMouseMove={handleMouseMove}
                      onMouseLeave={(e) => { setHoveredCard(null); e.currentTarget.style.background = 'transparent'; }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '3px 10px',
                        minHeight: '30px',
                        lineHeight: '1.2',
                        boxSizing: 'border-box',
                        borderRadius: isUnbekannt ? '6px' : 0,
                        cursor: 'pointer',
                        transition: 'background 0.15s ease',
                        background: 'transparent',
                        border: isUnbekannt ? '1px dashed var(--danger-color)' : 'none',
                        borderBottom: isUnbekannt ? '1px dashed var(--danger-color)' : (isLast ? 'none' : '1px solid var(--border-color)')
                      }}
                    >
                      <div style={{display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0, overflow: 'hidden'}}>
                        <span style={{
                          fontWeight: 700,
                          color: isUnbekannt ? 'var(--danger-color)' : 'var(--accent-color)',
                          fontSize: '0.8rem',
                          minWidth: '22px',
                          flexShrink: 0
                        }}>
                          {k.count || 1}x
                        </span>
                        <span style={{
                          fontWeight: 500,
                          fontSize: '0.88rem',
                          color: isUnbekannt ? 'var(--danger-color)' : 'var(--text-main)',
                          textDecoration: isUnbekannt ? 'line-through' : 'none',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap'
                        }}>
                          {k.name}
                        </span>
                        {findCombosForCard(k.name).length > 0 && (
                          <span
                            title="Combo-Teil! Klicke hier, um die Combo-Erklärung zu sehen."
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(`/decks?tab=stats&deckId=${selectedDeck.id}&focus=combos`);
                            }}
                            style={{
                              flexShrink: 0,
                              background: 'rgba(196, 146, 62, 0.15)',
                              border: '1px solid rgba(196, 146, 62, 0.4)',
                              color: '#C4923E',
                              fontSize: '0.68rem',
                              padding: '1px 6px',
                              borderRadius: '10px',
                              fontWeight: 700,
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '3px',
                              cursor: 'pointer'
                            }}
                          >
                            <Infinity size={10} /> Combo
                          </span>
                        )}
                      </div>

                      <div style={{display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0}}>
                        {isUnbekannt && (
                          <span style={{
                            color: 'var(--danger-color)',
                            fontSize: '0.72rem',
                            background: 'rgba(255, 69, 58, 0.1)',
                            padding: '1px 6px',
                            borderRadius: '10px',
                            fontWeight: 600
                          }}>
                            Nicht erkannt
                          </span>
                        )}
                        <span style={{
                          fontSize: '0.72rem',
                          color: 'var(--text-muted)',
                          minWidth: '110px',
                          maxWidth: '110px',
                          textAlign: 'right',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap'
                        }}>
                          {k.type || "Karte"}
                        </span>
                        {!isUnbekannt && (
                          <>
                            <span
                              title="Manawert (CMC)"
                              style={{
                                fontSize: '0.72rem',
                                fontWeight: 600,
                                color: 'var(--text-muted)',
                                background: 'var(--btn-secondary)',
                                borderRadius: '4px',
                                padding: '1px 6px',
                                minWidth: '18px',
                                textAlign: 'center',
                                fontVariantNumeric: 'tabular-nums'
                              }}
                            >
                              {cmcDisplay}
                            </span>
                            <span style={{
                              fontSize: '0.82rem',
                              fontWeight: 600,
                              color: 'var(--price-color)',
                              minWidth: '58px',
                              textAlign: 'right',
                              fontVariantNumeric: 'tabular-nums'
                            }}>
                              {priceDisplay} €
                            </span>
                          </>
                        )}
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

      {/* TABS SEGMENTED CONTROL -- zweireihig: Gruppen oben, Untertabs der
          aktiven Gruppe direkt darunter (immer sichtbar, kein Hover/Klick
          zum Aufdecken nötig). */}
      {(() => {
        const activeGroup = TAB_GROUPS.find(g => g.tabs.some(t => t.tab === currentTab)) || TAB_GROUPS[0];
        const hasSubTabs = activeGroup.tabs.length > 1;
        return (
          <>
            <div className="segmented-control" style={{marginBottom: hasSubTabs ? '10px' : '40px', display: 'flex', justifyContent: 'center', flexWrap: 'wrap', gap: '5px'}}>
              {TAB_GROUPS.map(group => (
                <button
                  key={group.id}
                  className={`segment-btn ${activeGroup.id === group.id ? 'active' : ''}`}
                  onClick={() => {
                    if (activeGroup.id === group.id) return;
                    const defaultTab = group.tabs[0].tab;
                    navigate(`/decks?tab=${defaultTab}${deckId ? `&deckId=${deckId}` : ''}`);
                  }}
                >
                  {group.label}
                </button>
              ))}
            </div>
            {hasSubTabs && (
              <div className="segmented-control" style={{marginBottom: '40px', display: 'flex', justifyContent: 'center', flexWrap: 'wrap', gap: '5px', padding: '4px', background: 'transparent', border: 'none', boxShadow: 'none'}}>
                {activeGroup.tabs.map(({ tab, label }) => (
                  <button
                    key={tab}
                    className={`segment-btn ${currentTab === tab ? 'active' : ''}`}
                    style={{padding: '7px 18px', fontSize: '0.85rem'}}
                    onClick={() => navigate(`/decks?tab=${tab}${deckId ? `&deckId=${deckId}` : ''}`)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </>
        );
      })()}

      {/* ACTIVE DECK BAR */}
      {selectedDeck && currentTab !== 'overview' && (
        <div style={{display: 'flex', alignItems: 'center', gap: '15px', background: 'var(--btn-secondary)', padding: '15px 25px', borderRadius: '16px', marginBottom: '30px', flexWrap: 'wrap', border: '1px solid var(--border-color)'}}>
          <span style={{fontWeight: 600, color: 'var(--text-muted)'}}>Aktives Deck:</span>
          <span style={{fontWeight: 700, fontSize: '1.1rem'}}>{selectedDeck.name}</span>

          <span style={{fontWeight: 600, color: 'var(--text-muted)', marginLeft: '10px'}}>Format:</span>
          <select
            value={selectedFormat}
            onChange={async (e) => {
              const newFormat = e.target.value;
              setSelectedFormat(newFormat);
              if (selectedDeck) {
                try {
                  await fetch(`/api/decks/update`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ deck_id: selectedDeck.id, format: newFormat, benutzername: currentUser })
                  });
                  ladeDecks();
                } catch (err) {
                  console.error("Fehler beim Aktualisieren des Formats:", err);
                }
              }
            }}
            style={{padding: '6px 12px', fontSize: '0.9rem', width: 'auto', borderRadius: '8px', background: 'var(--bg-card)', border: '1px solid var(--border-color)', cursor: 'pointer', color: 'var(--text-main)', fontWeight: 600}}
          >
            <option value="commander">Commander / EDH</option>
            <option value="standard">Standard</option>
            <option value="modern">Modern</option>
            <option value="pioneer">Pioneer</option>
            <option value="legacy">Legacy</option>
            <option value="vintage">Vintage</option>
          </select>

          <button
            onClick={exportDeckText}
            style={{
              padding: '6px 12px',
              fontSize: '0.9rem',
              borderRadius: '8px',
              background: copyStatus ? 'rgba(48, 209, 88, 0.15)' : 'var(--bg-card)',
              border: copyStatus ? '1px solid rgba(48, 209, 88, 0.4)' : '1px solid var(--border-color)',
              color: copyStatus ? '#30D158' : 'var(--text-main)',
              cursor: 'pointer',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'all 0.2s ease',
              marginLeft: '10px'
            }}
          >
            {copyStatus ? <CheckCircle2 size={14} /> : <Copy size={14} />}
            {copyStatus ? "Kopiert!" : "Arena-Format kopieren"}
          </button>
          
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
            <div style={{display: 'flex', gap: '15px', marginBottom: '15px', flexWrap: 'wrap'}}>
              <input 
                ref={createInputRef}
                placeholder="Deckname..." 
                value={newDeckName} 
                onChange={e => setNewDeckName(e.target.value)} 
                style={{flexGrow: 1, background: 'var(--input-bg)'}} 
              />
              <select
                value={newDeckFormat}
                onChange={e => setNewDeckFormat(e.target.value)}
                style={{padding: '10px 14px', borderRadius: '8px', background: 'var(--bg-main)', border: '1px solid var(--border-color)', color: 'var(--text-main)', width: 'auto'}}
              >
                <option value="commander">Commander / EDH</option>
                <option value="standard">Standard</option>
                <option value="modern">Modern</option>
                <option value="pioneer">Pioneer</option>
                <option value="legacy">Legacy</option>
                <option value="vintage">Vintage</option>
              </select>
            </div>
            <textarea placeholder="Optional: Kopiere hier direkt eine komplette Deckliste hinein..." value={importListe} onChange={e => setImportListe(e.target.value)} style={{height: '100px', background: 'var(--input-bg)', marginBottom: '15px'}} />
            <button className="primary-btn" onClick={erstelleDeck}>Deck anlegen</button>
          </div>

          <h3 style={{marginBottom: '20px', fontSize: '1.8rem'}}>Meine Decks</h3>
          {decks.length === 0 ? (
            <div className="bento-grid" style={{ marginTop: '20px' }}>
              <div className="bento-item" style={{ minHeight: '220px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <h4 style={{ fontSize: '1.25rem', marginBottom: '8px' }}>Neues Deck</h4>
                  <p style={{ fontSize: '0.9rem', margin: 0, color: 'var(--text-muted)' }}>Erstelle ein leeres Deck und füge manuell oder per KI-Tuning Karten hinzu.</p>
                </div>
                <button className="primary-btn" onClick={() => createInputRef.current?.focus()} style={{ marginTop: '15px' }}>
                  Jetzt erstellen
                </button>
              </div>

              <div className="bento-item" style={{ minHeight: '220px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <h4 style={{ fontSize: '1.25rem', marginBottom: '8px' }}>CSV / Text importieren</h4>
                  <p style={{ fontSize: '0.9rem', margin: 0, color: 'var(--text-muted)' }}>Kopiere eine Kartenliste direkt aus anderen Tools oben in das Textfeld.</p>
                </div>
                <button className="secondary-btn" onClick={() => document.querySelector('textarea')?.focus()} style={{ marginTop: '15px' }}>
                  Liste eintragen
                </button>
              </div>

              <div className="bento-item" style={{ minHeight: '220px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <h4 style={{ fontSize: '1.25rem', marginBottom: '8px' }}>Godo Warlord Vorlage</h4>
                  <p style={{ fontSize: '0.9rem', margin: 0, color: 'var(--text-muted)' }}>Klone das legendäre Mono-Red Burn & Combo Commander Deck Template.</p>
                </div>
                <button 
                  className="secondary-btn" 
                  onClick={() => kloneTemplateDeck("Godo Commander Starter", "1 Godo, Bandit Warlord\n1 Helm of the Host\n1 Sol Ring\n1 Commander's Sphere\n1 Command Tower\n35 Mountain")} 
                  style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center', marginTop: '15px' }}
                >
                  <Copy size={16} /> Vorlage klonen
                </button>
              </div>
            </div>
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
          <p style={{color: 'var(--text-muted)', marginBottom: '40px'}}>Bitte wähle ein Deck aus der Deck-Bibliothek aus oder wähle eins aus der Liste unten:</p>
          
          {decks.length === 0 ? (
            <div className="bento-grid" style={{ marginTop: '20px', textAlign: 'left' }}>
              <div className="bento-item" style={{ minHeight: '220px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <h4 style={{ fontSize: '1.25rem', marginBottom: '8px' }}>Neues Deck</h4>
                  <p style={{ fontSize: '0.9rem', margin: 0, color: 'var(--text-muted)' }}>Erstelle ein leeres Deck und füge manuell oder per KI-Tuning Karten hinzu.</p>
                </div>
                <button className="primary-btn" onClick={() => navigate('/decks?tab=overview')} style={{ marginTop: '15px' }}>
                  Jetzt erstellen
                </button>
              </div>

              <div className="bento-item" style={{ minHeight: '220px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <h4 style={{ fontSize: '1.25rem', marginBottom: '8px' }}>CSV / Text importieren</h4>
                  <p style={{ fontSize: '0.9rem', margin: 0, color: 'var(--text-muted)' }}>Importiere eine Kartenliste direkt aus anderen Tools oder CSV.</p>
                </div>
                <button className="secondary-btn" onClick={() => navigate('/decks?tab=overview')} style={{ marginTop: '15px' }}>
                  Zur Importseite
                </button>
              </div>

              <div className="bento-item" style={{ minHeight: '220px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <h4 style={{ fontSize: '1.25rem', marginBottom: '8px' }}>Godo Warlord Vorlage</h4>
                  <p style={{ fontSize: '0.9rem', margin: 0, color: 'var(--text-muted)' }}>Klone das legendäre Mono-Red Burn & Combo Commander Deck Template.</p>
                </div>
                <button 
                  className="secondary-btn" 
                  onClick={() => kloneTemplateDeck("Godo Commander Starter", "1 Godo, Bandit Warlord\n1 Helm of the Host\n1 Sol Ring\n1 Commander's Sphere\n1 Command Tower\n35 Mountain")} 
                  style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center', marginTop: '15px' }}
                >
                  <Copy size={16} /> Vorlage klonen
                </button>
              </div>
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
                  const activeCmcDataset = cmcFilter === "creatures" 
                    ? (stats.cmc_creatures || {}) 
                    : cmcFilter === "noncreatures" 
                      ? (stats.cmc_noncreatures || {}) 
                      : (stats.cmc || {});
                  const counts = Object.values(activeCmcDataset).map(v => parseInt(v) || 0);
                  const maxCmcCount = counts.length > 0 ? Math.max(...counts, 1) : 1;
                  
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
                        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '15px'}}>
                          <h4 style={{color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.08em', margin: 0}}>
                            Manakurve
                          </h4>
                          <div className="segmented-control" style={{margin: 0, padding: '4px', gap: '4px', display: 'flex', background: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: '10px'}}>
                            <button 
                              className={`segment-btn ${cmcFilter === 'all' ? 'active' : ''}`} 
                              onClick={() => setCmcFilter('all')}
                              style={{padding: '6px 12px', fontSize: '0.85rem', minHeight: 'auto'}}
                            >
                              Alle Zauber
                            </button>
                            <button 
                              className={`segment-btn ${cmcFilter === 'creatures' ? 'active' : ''}`} 
                              onClick={() => setCmcFilter('creatures')}
                              style={{padding: '6px 12px', fontSize: '0.85rem', minHeight: 'auto'}}
                            >
                              Kreaturen
                            </button>
                            <button 
                              className={`segment-btn ${cmcFilter === 'noncreatures' ? 'active' : ''}`} 
                              onClick={() => setCmcFilter('noncreatures')}
                              style={{padding: '6px 12px', fontSize: '0.85rem', minHeight: 'auto'}}
                            >
                              Nicht-Kreaturen
                            </button>
                          </div>
                        </div>
                        <div style={{display: 'flex', alignItems: 'flex-end', justifyContent: 'space-around', height: '200px', padding: '0 10px'}}>
                          {Object.keys(stats?.cmc || {}).sort((a,b) => parseInt(a)-parseInt(b)).map(cmc => {
                             const val = activeCmcDataset[cmc] || 0;
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
                    <span>{validation.legal ? <CheckCircle2 size={32} style={{ color: '#30D158' }} /> : <AlertTriangle size={32} style={{ color: '#FF453A' }} />}</span>
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
                  onShowPremiumModal={onShowPremiumModal}
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

      {selectedDeck && currentTab === "tuning" && (
        <div className="content-card" style={{padding: '40px', position: 'relative', animation: 'fadeIn 0.6s ease'}}>
          {userRole !== 'premium' && <PremiumOverlay onShowPremiumModal={onShowPremiumModal} />}
          
          <h3 style={{fontSize: '2.2rem', marginBottom: '10px'}}>Smart-Tuning: DeckTrim & Mana-Base</h3>
          <p style={{color: 'var(--text-muted)', marginBottom: '40px'}}>Nimm direkte Optimierungen an deinem Deck vor. Vorschläge basieren auf Synergiewerten und deiner Manakurve.</p>
          
          {laedt ? (
            <div style={{textAlign: 'center', padding: '60px'}}><div className="spinner"></div><p style={{marginTop: '20px'}}>Erstelle Optimierungsvorschläge...</p></div>
          ) : (
            <>
              {/* Mana-Tune Section */}
              <div style={{marginBottom: '50px'}}>
                <h4 style={{fontSize: '1.4rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px', marginBottom: '20px'}}>ManaTune: Landempfehlungen</h4>
                {stats && stats.colors ? (
                  <div>
                    <p style={{marginBottom: '20px'}}>Verteilung farbiger Symbole in deinen Nicht-Land-Karten und empfohlene Standardländer:</p>
                    <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '20px'}}>
                      {Object.entries(stats.colors).map(([color, count]) => {
                        if (color === 'C' && count === 0) return null;
                        const nameMap = { W: 'Ebene (Plains)', U: 'Insel (Island)', B: 'Sumpf (Swamp)', R: 'Gebirge (Mountain)', G: 'Wald (Forest)', C: 'Farblos (Colorless)' };
                        const colorMapHex = { W: '#F9F6F0', U: '#0E68AB', B: '#1A1A1A', R: '#D32F2F', G: '#2E7D32', C: '#757575' };
                        const totalSymbols = Object.values(stats.colors).reduce((a, b) => a + b, 0);
                        const ratio = totalSymbols > 0 ? (count / totalSymbols) * 100 : 0;
                        const recommendedLands = selectedFormat === 'commander' ? 37 : 24;
                        const recommendedCount = Math.round((ratio / 100) * recommendedLands);

                        return (
                          <div key={color} style={{background: 'var(--btn-secondary)', padding: '20px', borderRadius: '14px', border: '1px solid var(--border-color)', textAlign: 'center'}}>
                            <div style={{display: 'inline-block', width: '24px', height: '24px', borderRadius: '50%', background: colorMapHex[color], border: '1px solid #ccc', marginBottom: '10px'}} />
                            <strong style={{display: 'block', fontSize: '1.05rem', marginBottom: '5px'}}>{nameMap[color]}</strong>
                            <div style={{fontSize: '0.9rem', color: 'var(--text-muted)'}}>Symbole: {count} ({ratio.toFixed(0)}%)</div>
                            <div style={{marginTop: '10px', fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-main)'}}>Empfohlen: ~{recommendedCount}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <p style={{color: 'var(--text-muted)'}}>Keine Farbstrukturdaten vorhanden.</p>
                )}
              </div>

              {/* DeckTrim Section (Cuts & Adds) */}
              <div>
                <h4 style={{fontSize: '1.4rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px', marginBottom: '20px'}}>DeckTrim: Karten hinzufügen / entfernen</h4>
                {analyse && analyse.verbesserungen && analyse.verbesserungen.length > 0 ? (
                  <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                        <th style={{ padding: '12px 15px', color: 'var(--text-muted)', fontSize: '0.9rem', textTransform: 'uppercase' }}>Hinzufügen (+ Rein)</th>
                        <th style={{ padding: '12px 15px', color: 'var(--text-muted)', fontSize: '0.9rem', textTransform: 'uppercase' }}>Entfernen (- Raus)</th>
                        <th style={{ padding: '12px 15px', color: 'var(--text-muted)', fontSize: '0.9rem', textTransform: 'uppercase' }}>Grund / Synergie</th>
                        <th style={{ padding: '12px 15px', color: 'var(--text-muted)', fontSize: '0.9rem', textTransform: 'uppercase', textAlign: 'right' }}>Aktion</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analyse.verbesserungen.map((verb, idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid var(--border-color)' }}>
                          <td style={{ padding: '15px' }}>
                            <span 
                              onMouseEnter={(e) => { setHoveredCard({name: verb.rein}); handleMouseMove(e); }}
                              onMouseMove={handleMouseMove}
                              onMouseLeave={() => setHoveredCard(null)}
                              style={{fontWeight: 600, color: '#30D158', cursor: 'pointer', textDecoration: 'underline dotted'}}
                            >
                              {verb.rein}
                            </span>
                          </td>
                          <td style={{ padding: '15px' }}>
                            {verb.raus ? (
                              <span 
                                onMouseEnter={(e) => { setHoveredCard({name: verb.raus}); handleMouseMove(e); }}
                                onMouseMove={handleMouseMove}
                                onMouseLeave={() => setHoveredCard(null)}
                                style={{fontWeight: 600, color: 'var(--danger-color)', cursor: 'pointer', textDecoration: 'underline dotted'}}
                              >
                                {verb.raus}
                              </span>
                            ) : (
                              <span style={{color: 'var(--text-muted)', fontStyle: 'italic'}}>Beliebige Karte</span>
                            )}
                          </td>
                          <td style={{ padding: '15px', color: 'var(--text-muted)', fontSize: '0.95rem', maxWidth: '350px' }}>
                            {verb.grund}
                          </td>
                          <td style={{ padding: '15px', textAlign: 'right' }}>
                            <div style={{display: 'flex', gap: '8px', justifyContent: 'flex-end'}}>
                              <button 
                                className="primary-btn" 
                                style={{padding: '8px 14px', fontSize: '0.85rem', background: '#30D158', color: 'white'}}
                                onClick={() => addCardFromTuning(verb.rein)}
                              >
                                + Rein
                              </button>
                              {verb.raus && (
                                <button 
                                  className="secondary-btn" 
                                  style={{padding: '8px 14px', fontSize: '0.85rem', background: 'var(--danger-bg)', color: 'var(--danger-color)'}}
                                  onClick={() => removeCardFromTuning(verb.raus)}
                                >
                                  - Raus
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p style={{color: 'var(--text-muted)'}}>Keine Tuning-Empfehlungen vorhanden. Klicke im Reiter "Analyse & Stats" auf Auswerten.</p>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {selectedDeck && currentTab === "compare" && (
        <div className="content-card" style={{padding: '40px', animation: 'fadeIn 0.6s ease'}}>
          <h3 style={{fontSize: '2.2rem', marginBottom: '10px'}}>Deck-Vergleich (Diff)</h3>
          <p style={{color: 'var(--text-muted)', marginBottom: '30px'}}>Vergleiche dein aktives Deck direkt mit einem deiner anderen Decks, um Unterschiede in CMC, Farben und Kartenliste zu sehen.</p>
          
          <div style={{display: 'flex', alignItems: 'center', gap: '15px', background: 'var(--btn-secondary)', padding: '20px 25px', borderRadius: '16px', marginBottom: '40px', border: '1px solid var(--border-color)'}}>
            <span style={{fontWeight: 600, color: 'var(--text-muted)'}}>Vergleichen mit:</span>
            <select
              value={compareDeckId}
              onChange={e => setCompareDeckId(e.target.value)}
              style={{padding: '10px 18px', borderRadius: '10px', background: 'var(--bg-card)', border: '1px solid var(--border-color)', width: 'auto', cursor: 'pointer', fontWeight: 600, color: 'var(--text-main)'}}
            >
              <option value="">-- Deck auswählen --</option>
              {decks.filter(d => String(d.id) !== String(selectedDeck.id)).map(d => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>

          {(() => {
            const compDeck = decks.find(d => String(d.id) === String(compareDeckId));
            if (!compDeck) return <p style={{textAlign: 'center', color: 'var(--text-muted)', padding: '40px 0'}}>Wähle oben ein Deck aus, um den Vergleich zu starten.</p>;
            
            const parseDecklistLocal = (liste) => {
              const res = {};
              if (!liste) return res;
              liste.split('\n').forEach(line => {
                const clean = line.trim();
                if (!clean) return;
                const m = clean.match(/^(\d+)[xX]?\s+(.+)$/);
                if (m) {
                  const count = parseInt(m[1]);
                  const name = m[2].trim();
                  res[name] = (res[name] || 0) + count;
                } else {
                  res[clean] = (res[clean] || 0) + 1;
                }
              });
              return res;
            };

            const mapA = parseDecklistLocal(selectedDeck.liste);
            const mapB = parseDecklistLocal(compDeck.liste);

            const diffA = [];
            const diffB = [];
            const shared = [];

            Object.keys(mapA).forEach(card => {
              const countA = mapA[card];
              const countB = mapB[card] || 0;
              if (countB === 0) {
                diffA.push({ name: card, count: countA });
              } else if (countA > countB) {
                diffA.push({ name: card, count: countA - countB });
                shared.push({ name: card, count: countB });
              } else {
                shared.push({ name: card, count: countA });
              }
            });

            Object.keys(mapB).forEach(card => {
              const countB = mapB[card];
              const countA = mapA[card] || 0;
              if (countA === 0) {
                diffB.push({ name: card, count: countB });
              } else if (countB > countA) {
                diffB.push({ name: card, count: countB - countA });
              }
            });

            return (
              <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '30px'}}>
                <div style={{background: 'rgba(255, 69, 58, 0.05)', border: '1px solid rgba(255, 69, 58, 0.2)', padding: '30px', borderRadius: '18px'}}>
                  <h4 style={{fontSize: '1.25rem', color: 'var(--danger-color)', display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px', borderBottom: '1px solid rgba(255, 69, 58, 0.1)', paddingBottom: '10px'}}>
                    <span>- Nur in "{selectedDeck.name}" ({diffA.reduce((sum, item) => sum + item.count, 0)})</span>
                  </h4>
                  {diffA.length === 0 ? <p style={{color: 'var(--text-muted)', fontStyle: 'italic'}}>Keine abweichenden Karten.</p> : (
                    <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
                      {diffA.map((item, idx) => (
                        <div key={idx} style={{display: 'flex', justifyContent: 'space-between', padding: '6px 12px', background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)'}}>
                          <span 
                            onMouseEnter={(e) => { setHoveredCard({name: item.name}); handleMouseMove(e); }}
                            onMouseMove={handleMouseMove}
                            onMouseLeave={() => setHoveredCard(null)}
                            style={{fontWeight: 600, cursor: 'pointer', textDecoration: 'underline dotted'}}
                          >
                            {item.name}
                          </span>
                          <strong style={{color: 'var(--danger-color)'}}>{item.count}x</strong>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div style={{background: 'rgba(48, 209, 88, 0.05)', border: '1px solid rgba(48, 209, 88, 0.2)', padding: '30px', borderRadius: '18px'}}>
                  <h4 style={{fontSize: '1.25rem', color: '#30D158', display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px', borderBottom: '1px solid rgba(48, 209, 88, 0.1)', paddingBottom: '10px'}}>
                    <span>+ Nur in "{compDeck.name}" ({diffB.reduce((sum, item) => sum + item.count, 0)})</span>
                  </h4>
                  {diffB.length === 0 ? <p style={{color: 'var(--text-muted)', fontStyle: 'italic'}}>Keine abweichenden Karten.</p> : (
                    <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
                      {diffB.map((item, idx) => (
                        <div key={idx} style={{display: 'flex', justifyContent: 'space-between', padding: '6px 12px', background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)'}}>
                          <span 
                            onMouseEnter={(e) => { setHoveredCard({name: item.name}); handleMouseMove(e); }}
                            onMouseMove={handleMouseMove}
                            onMouseLeave={() => setHoveredCard(null)}
                            style={{fontWeight: 600, cursor: 'pointer', textDecoration: 'underline dotted'}}
                          >
                            {item.name}
                          </span>
                          <strong style={{color: '#30D158'}}>+{item.count}x</strong>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </div>
      )}

      {selectedDeck && currentTab === "roast" && (
        <div className="content-card" style={{padding: '40px', position: 'relative', animation: 'fadeIn 0.6s ease'}}>
          {userRole !== 'premium' && <PremiumOverlay onShowPremiumModal={onShowPremiumModal} />}
          
          <div style={{textAlign: 'center', maxWidth: '650px', margin: '0 auto'}}>
            <div style={{color: '#C4923E', display: 'flex', justifyContent: 'center', marginBottom: '15px'}}><Flame size={64} /></div>
            <h3 style={{fontSize: '2.5rem', marginBottom: '10px'}}>Deck-Roast & Kritik</h3>
            <p style={{color: 'var(--text-muted)', marginBottom: '35px'}}>Lass dein Deck von unserem Stresstest-Algorithmus analysieren. Nichts für schwache Nerven!</p>

            {roastLoading ? (
              <div style={{padding: '40px 0'}}>
                <div className="spinner"></div>
                <p style={{marginTop: '20px', color: 'var(--text-muted)', fontStyle: 'italic'}}>Analysiere Deck-Schwächen und typische Spielfehler...</p>
              </div>
            ) : roastData ? (
              <div style={{textAlign: 'left'}}>
                <div style={{
                  background: 'linear-gradient(135deg, rgba(255, 149, 0, 0.08) 0%, rgba(255, 59, 48, 0.08) 100%)',
                  border: '2px solid #FF9500',
                  borderRadius: '24px',
                  padding: '35px',
                  marginBottom: '35px',
                  boxShadow: '0 8px 30px var(--shadow-color)',
                  position: 'relative'
                }}>
                  <div style={{
                    position: 'absolute',
                    top: '-15px',
                    left: '25px',
                    background: 'linear-gradient(135deg, #FF9500, #FF3B30)',
                    color: 'white',
                    fontSize: '0.8rem',
                    fontWeight: 700,
                    padding: '4px 14px',
                    borderRadius: '12px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em'
                  }}>
                    Urteil: {roastData.verdict || "Autsch."}
                  </div>
                  
                  <p style={{
                    fontSize: '1.1rem',
                    color: 'var(--text-main)',
                    lineHeight: '1.6',
                    fontStyle: 'italic',
                    whiteSpace: 'pre-line',
                    margin: 0
                  }}>
                    "{roastData.roast}"
                  </p>
                </div>

                <div style={{
                  background: 'var(--btn-secondary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '16px',
                  padding: '24px',
                  marginBottom: '40px'
                }}>
                  <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px'}}>
                    <strong style={{color: 'var(--text-main)'}}>Salzigkeits-Faktor (Salt Score)</strong>
                    <strong style={{color: '#FF3B30', fontSize: '1.25rem'}}>{roastData.salt_score || 50}%</strong>
                  </div>
                  <div style={{width: '100%', height: '12px', background: 'var(--border-color)', borderRadius: '6px', overflow: 'hidden'}}>
                    <div style={{
                      width: `${roastData.salt_score || 50}%`,
                      height: '100%',
                      background: 'linear-gradient(90deg, #FF9500, #FF3B30)',
                      borderRadius: '6px',
                      transition: 'width 1s cubic-bezier(0.1, 0.8, 0.2, 1)'
                    }} />
                  </div>
                  <p style={{fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '8px', margin: '8px 0 0 0'}}>
                    Je höher dieser Wert, desto genervter reagieren deine Gegner auf deine Kartenwahlen.
                  </p>
                </div>

                <div style={{textAlign: 'center'}}>
                  <button 
                    className="primary-btn" 
                    onClick={holeRoast}
                    style={{
                      background: 'linear-gradient(135deg, #C4923E 0%, #9E7127 100%)',
                      color: 'white',
                      border: 'none',
                      boxShadow: '0 8px 24px rgba(196, 146, 62, 0.2)',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '8px'
                    }}
                  >
                    <RefreshCw size={18} /> Deck-Roast wiederholen
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <button 
                  className="primary-btn" 
                  onClick={holeRoast}
                  style={{
                    background: 'linear-gradient(135deg, #C4923E 0%, #9E7127 100%)',
                    color: 'white',
                    border: 'none',
                    padding: '16px 36px',
                    fontSize: '1.1rem',
                    fontWeight: 700,
                    borderRadius: '980px',
                    boxShadow: '0 8px 24px rgba(196, 146, 62, 0.2)',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}
                >
                  <Flame size={18} /> Deck-Roast starten
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {selectedDeck && currentTab === "proxy" && (
        <div className="content-card" style={{padding: '40px'}}>
          {userRole !== 'premium' ? (
            <div style={{ textAlign: 'center', padding: '40px 20px' }}>
              <div style={{ color: 'var(--text-muted)', marginBottom: '20px', display: 'flex', justifyContent: 'center' }}><Printer size={48} /></div>
              <h3 style={{ fontSize: '1.8rem', marginBottom: '10px' }}>Proxy-Druck ist ein Pro-Feature</h3>
              <p style={{ color: 'var(--text-muted)', maxWidth: '500px', margin: '0 auto 25px auto', fontSize: '1.05rem' }}>
                Schalte Grana Pro frei, um deine Decks im exakten Turnier-A4-Format (63x88mm) zum Testen auszudrucken.
              </p>
              <button 
                className="primary-btn" 
                onClick={onShowPremiumModal} 
                style={{ 
                  background: 'linear-gradient(135deg, #0071E3 0%, #0077ED 100%)', 
                  color: 'white', 
                  border: 'none',
                  borderRadius: '980px',
                  padding: '12px 28px',
                  fontSize: '1rem',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Jetzt Grana Pro freischalten
              </button>
            </div>
          ) : (
            <>
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
                              className={`proxy-print-img fade-in-img ${loadedImages[k?.image] ? 'loaded' : ''}`} 
                              onLoad={() => setLoadedImages(prev => ({ ...prev, [k?.image]: true }))}
                              style={{width: '100%', borderRadius: '4.75% / 3.5%'}} 
                              loading="lazy"
                              onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(k?.name, k?.type); }}
                            />
                          ))}
                      </div>
                    </div>
                )
              )}
            </>
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
                  className={`playtest-card fade-in-img ${loadedImages[k?.image] ? 'loaded' : ''}`} 
                  onLoad={() => setLoadedImages(prev => ({ ...prev, [k?.image]: true }))}
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
        <div ref={setPreviewRef} style={{
          position: 'fixed',
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
            className={`fade-in-img ${loadedImages[hoveredCard.image] ? 'loaded' : ''}`}
            onLoad={() => setLoadedImages(prev => ({ ...prev, [hoveredCard.image]: true }))}
            style={{ width: '100%', height: '100%', display: 'block', objectFit: 'cover' }}
            onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(hoveredCard.name, hoveredCard.type); }}
          />
        </div>
      )}
    </div>
  );
}

export default DecksView;
