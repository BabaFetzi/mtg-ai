import { useState, useEffect } from 'react';
import Icons from '../../utils/Icons';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';
import { useMeldung } from '../layout/Meldungen';
import AuflagenWahl from './AuflagenWahl';

function DeckEditor({ selectedDeck, currentUser, ladeDecks }) {
  const { melde, bestaetige } = useMeldung();
  // Karte, für die gerade eine Auflage gewählt wird (null = kein Dialog offen).
  const [auflagenKarte, setAuflagenKarte] = useState(null);
  const [activeView, setActiveView] = useState("visual"); // "visual" | "text"
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  // Ehrliche Rückmeldung statt eines blossen "Keine Karten gefunden".
  const [suchHinweis, setSuchHinweis] = useState("");
  const [vorschlaege, setVorschlaege] = useState([]);
  const [dragActive, setDragActive] = useState(false);
  
  // Local list parsed for visual editor
  const [deckCards, setDeckCards] = useState([]);
  const [textList, setTextList] = useState(selectedDeck?.liste || "");

  // Fetch / parse cards inside the deck
  useEffect(() => {
    if (selectedDeck?.liste) {
      setTextList(selectedDeck.liste);
      parseDecklist(selectedDeck.liste);
    } else {
      setDeckCards([]);
      setTextList("");
    }
  }, [selectedDeck]);

  const parseDecklist = async (listText) => {
    if (!listText.trim()) {
      setDeckCards([]);
      return;
    }
    // Fetch visual representation from API
    try {
      const res = await fetch(`/api/deck/visualize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deck_liste: listText })
      });
      if (res.ok) {
        const data = await res.json();
        if (data && Array.isArray(data.karten)) {
          setDeckCards(data.karten);
        }
      }
    } catch (e) {
      console.error("Error parsing decklist:", e);
    }
  };

  // Kartensuche über das eigene Backend.
  //
  // Vorher ging diese Anfrage DIREKT aus dem Browser an Scryfall. Damit umging
  // sie die serverseitige Drossel und den Cache (bei vielen Nutzern ein
  // Rate-Limit-Risiko) und verhielt sich anders als die normale Kartensuche.
  const triggerSearch = async (q) => {
    if (!q.trim()) return;
    setSearching(true);
    setSuchHinweis("");
    setVorschlaege([]);
    try {
      const res = await fetch(`/api/karten/suchen?q=${encodeURIComponent(q)}`);
      const data = await res.json().catch(() => ({}));
      setSearchResults(Array.isArray(data.karten) ? data.karten : []);
      if (data.hinweis) setSuchHinweis(data.hinweis);
      if (Array.isArray(data.vorschlaege)) setVorschlaege(data.vorschlaege);
    } catch (e) {
      setSearchResults([]);
      setSuchHinweis("Verbindungsfehler bei der Kartensuche.");
    }
    setSearching(false);
  };

  // 1. Text Editor Save
  const handleTextSave = async () => {
    try {
      const res = await fetch(`/api/decks/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deck_id: selectedDeck.id, deck_liste: textList })
      });
      const data = await res.json();
      if (data && data.erfolg) {
        melde.erfolg("Deck gespeichert.");
        ladeDecks();
        parseDecklist(textList);
      }
    } catch {
      melde.fehler("Fehler beim Speichern.");
    }
  };

  // Ein Aufruf für alle drei Änderungen am Deck (hinzufügen, entfernen,
  // Auflage wechseln). Vorher stand derselbe Ablauf zweimal da -- und der
  // Fehlerfall wurde in beiden Fassungen nur auf die Konsole geschrieben, wo
  // ihn kein Nutzer sieht.
  const aendereDeck = async (pfad, nutzlast, fehlertext) => {
    try {
      const res = await fetch(pfad, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deck_id: selectedDeck.id, ...nutzlast })
      });
      const data = await res.json().catch(() => ({}));
      if (data && data.erfolg) {
        ladeDecks();
        setTextList(data.deck_liste);
        parseDecklist(data.deck_liste);
        return true;
      }
      melde.fehler(data?.error || fehlertext);
    } catch {
      melde.fehler(fehlertext);
    }
    return false;
  };

  // 2. Add card to deck list (Updates the deck in db & UI)
  //
  // `auflage` ist optional. Ohne sie wird die vorhandene Zeile hochgezählt,
  // gleich aus welchem Set -- mit ihr genau diese Auflage.
  const addCard = (cardName, auflage) =>
    aendereDeck("/api/deck/add-card",
      { card_name: cardName, set: auflage?.set || null,
        sammlernummer: auflage?.sammlernummer || null },
      "Die Karte konnte nicht hinzugefügt werden.");

  // 3. Remove card from deck list
  const removeCard = (cardName, auflage) =>
    aendereDeck("/api/deck/remove-card",
      { card_name: cardName, set: auflage?.set || null,
        sammlernummer: auflage?.sammlernummer || null },
      "Die Karte konnte nicht entfernt werden.");

  // 3b. Auflage einer Karte im Deck festlegen oder wieder aufheben.
  const setzeAuflage = async (karte, auflage) => {
    const erfolg = await aendereDeck("/api/deck/auflage", {
      card_name: karte.name,
      alt_set: karte.set || null,
      alt_sammlernummer: karte.sammlernummer || null,
      set: auflage?.set || null,
      sammlernummer: auflage?.sammlernummer || null,
    }, "Die Auflage konnte nicht geändert werden.");
    if (erfolg) {
      melde.erfolg(auflage
        ? `${karte.name}: Auflage ${(auflage.set || '').toUpperCase()} übernommen.`
        : `${karte.name}: Festlegung der Auflage aufgehoben.`);
    }
    setAuflagenKarte(null);
  };

  // 4. Drag and Drop handlers
  const handleDragStart = (e, cardName) => {
    e.dataTransfer.setData("cardName", cardName);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragActive(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setDragActive(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    const cardName = e.dataTransfer.getData("cardName");
    if (cardName) {
      addCard(cardName);
    }
  };

  // 5. Total Cards Count
  const totalCardsCount = deckCards.reduce((acc, c) => acc + (c.count || 1), 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Editor Header / View Switcher */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: 'var(--bg-card)',
        padding: '15px 30px',
        borderRadius: '16px',
        border: '1px solid var(--border-color)'
      }}>
        <div>
          <span style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>Editor-Modus: </span>
          <strong style={{ fontSize: '1.1rem', color: 'var(--text-main)' }}>{activeView === "visual" ? "Visueller Drag & Drop" : "Klassischer Text-Editor"}</strong>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={() => setActiveView("visual")}
            className={activeView === "visual" ? "primary-btn" : "secondary-btn"}
            style={{ padding: '8px 18px', fontSize: '0.88rem', borderRadius: '8px' }}
          >
            D&D Editor
          </button>
          <button
            onClick={() => setActiveView("text")}
            className={activeView === "text" ? "primary-btn" : "secondary-btn"}
            style={{ padding: '8px 18px', fontSize: '0.88rem', borderRadius: '8px' }}
          >
            Text Editor
          </button>
        </div>
      </div>

      {/* Main split containers */}
      {activeView === "text" ? (
        /* RAW TEXT AREA VIEW */
        <div className="split-editor-text">
          <div>
            <textarea
              className="deck-textarea"
              value={textList}
              onChange={e => setTextList(e.target.value)}
              placeholder="z.B.&#10;1 Sol Ring&#10;4 Lightning Bolt&#10;1 Arcane Signet..."
              style={{ padding: '25px', borderRadius: '20px', minHeight: '450px' }}
            />
            <div style={{ marginTop: '25px', display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
              <button className="primary-btn" onClick={handleTextSave}>Speichern</button>
              <button className="secondary-btn" onClick={() => {
                navigator.clipboard.writeText(textList);
                melde.erfolg("Deckliste in Zwischenablage kopiert!");
              }}>Kopieren (Arena Export)</button>
            </div>
          </div>

          <div className="content-card" style={{ margin: 0, padding: '30px', background: 'var(--btn-secondary)' }}>
            <h4 style={{ fontSize: '1.2rem', marginBottom: '15px' }}>Hilfe & Syntax</h4>
            <p style={{ fontSize: '0.92rem', lineHeight: '1.5', color: 'var(--text-muted)' }}>
              Trage einfach die Kartenzeilen ein. Jede Zeile sollte dem Format entsprechen:<br />
              <code style={{ background: 'var(--bg-card)', padding: '2px 6px', borderRadius: '4px', display: 'inline-block', marginTop: '5px' }}>[Anzahl]x [Kartenname]</code>
              <br /><br />
              Beispiel:<br />
              <code style={{ background: 'var(--bg-card)', padding: '4px 8px', borderRadius: '4px', display: 'inline-block', whiteSpace: 'pre' }}>
                {"1x Sol Ring\n4x Lightning Bolt\n1x Krenko, Mob Boss"}
              </code>
              <br /><br />
              Willst du eine <strong>bestimmte Auflage</strong> festhalten, schreibe Set-Kürzel
              und Sammlernummer dahinter — dieselbe Schreibweise wie bei Moxfield, Arena und MTGO:<br />
              <code style={{ background: 'var(--bg-card)', padding: '4px 8px', borderRadius: '4px', display: 'inline-block', whiteSpace: 'pre', marginTop: '5px' }}>
                {"4x Lightning Bolt (2XM) 123"}
              </code>
              <br />
              Bequemer geht es im D&amp;D-Editor: dort steht unter jeder Karte ein Knopf mit
              der Auflage, der alle Versionen zeigt und die aus deiner Sammlung markiert.
            </p>
          </div>
        </div>
      ) : (
        /* VISUAL DRAG & DROP VIEW */
        <div className="split-editor-visual">
          
          {/* LEFT: CARD SEARCH PANEL */}
          <div className="content-card" style={{ margin: 0, padding: '25px', display: 'flex', flexDirection: 'column', gap: '20px', maxHeight: '750px', overflowY: 'auto' }}>
            <h4 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600 }}>Karten-Datenbank</h4>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>Suche eine Karte und ziehe sie per Drag & Drop in dein Deck, oder klicke auf das "+"-Symbol.</p>
            
            <div style={{ display: 'flex', gap: '10px' }}>
              <input
                type="text"
                placeholder="z.B. Sol Ring..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && triggerSearch(searchQuery)}
                style={{ padding: '10px 14px', borderRadius: '8px', background: 'var(--bg-main)', fontSize: '0.95rem' }}
              />
              <button className="primary-btn" onClick={() => triggerSearch(searchQuery)} style={{ padding: '10px 18px', fontSize: '0.9rem', borderRadius: '8px' }}>
                {searching ? "..." : "Suche"}
              </button>
            </div>

            {/* Search results list */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {searching ? (
                <div style={{ textAlign: 'center', padding: '20px' }}><div className="spinner"></div></div>
              ) : (
                searchResults.map(item => (
                  <div
                    key={item.id}
                    draggable="true"
                    onDragStart={(e) => handleDragStart(e, item.name)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      background: 'var(--bg-main)',
                      padding: '10px',
                      borderRadius: '10px',
                      border: '1px solid var(--border-color)',
                      cursor: 'grab',
                      transition: 'transform 0.2s',
                      position: 'relative'
                    }}
                    className="drag-source-card"
                  >
                    {/* Bild deutlich grösser: bei 40px waren zwei ähnliche Karten
                        nicht auseinanderzuhalten. Zusätzlich vergrössert es sich
                        beim Darüberfahren (siehe .kartentreffer-bild in App.css). */}
                    <img
                      src={item.bild_url || getFallbackCardImage(item.name, item.type_line)}
                      alt={item.name}
                      className="kartentreffer-bild"
                      style={{ width: '62px', borderRadius: '3px', flexShrink: 0 }}
                      draggable="false"
                      onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(item.name, item.type_line); }}
                    />
                    <div style={{ flexGrow: 1, minWidth: 0 }}>
                      <div
                        style={{ fontWeight: 600, fontSize: '0.9rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                        title={item.printed_name && item.printed_name !== item.name ? `${item.printed_name} (${item.name})` : item.name}
                      >
                        {item.printed_name && item.printed_name !== item.name ? `${item.printed_name} (${item.name})` : item.name}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.type_line}</div>
                      {/* Die Edition unterscheidet Treffer, die sonst gleich aussehen. */}
                      {item.set && (
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                          {item.set}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => addCard(item.name)}
                      style={{
                        background: 'var(--accent-color)',
                        color: 'var(--accent-text)',
                        border: 'none',
                        borderRadius: '50%',
                        width: '26px',
                        height: '26px',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 'bold',
                        fontSize: '1rem'
                      }}
                      title="Zum Deck hinzufügen"
                    >
                      +
                    </button>
                  </div>
                ))
              )}
              {!searching && searchQuery && searchResults.length === 0 && (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.88rem', padding: '16px 0', lineHeight: 1.5 }}>
                  <div style={{ fontWeight: 600, color: 'var(--text-main)', marginBottom: '6px' }}>Keine Karten gefunden.</div>
                  {suchHinweis && <div>{suchHinweis}</div>}
                  {vorschlaege.length > 0 && (
                    <div style={{ marginTop: '12px' }}>
                      <div style={{ marginBottom: '6px' }}>Meintest du:</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {vorschlaege.map(v => (
                          <button
                            key={v}
                            type="button"
                            className="secondary-btn"
                            onClick={() => { setSearchQuery(v); triggerSearch(v); }}
                            style={{ padding: '5px 12px', fontSize: '0.82rem', borderRadius: '14px', width: 'auto' }}
                          >
                            {v}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* RIGHT: DECK ZONES & DROPAREA */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            style={{
              background: 'var(--bg-card)',
              borderRadius: '24px',
              padding: '30px',
              border: dragActive ? '2px dashed #0071E3' : '1px solid var(--border-color)',
              minHeight: '550px',
              display: 'flex',
              flexDirection: 'column',
              gap: '20px',
              boxShadow: '0 8px 30px var(--shadow-color)'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '15px' }}>
              <h3 style={{ margin: 0, fontSize: '1.5rem' }}>Mein Deck ({totalCardsCount} Karten)</h3>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', background: 'var(--bg-main)', padding: '5px 12px', borderRadius: '20px', fontWeight: 600 }}>
                Dropzone Active
              </span>
            </div>

            {/* Deck Content visual lists */}
            {deckCards.length === 0 ? (
              <div style={{
                flexGrow: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-muted)',
                fontSize: '1.1rem',
                fontStyle: 'italic',
                padding: '80px 0'
              }}>
                Ziehe Karten hierher oder klicke links auf "+", um dein Deck zu bauen.
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: '20px' }}>
                {deckCards.map((card, idx) => (
                  <div
                    // Dieselbe Karte kann in zwei Auflagen im Deck stehen --
                    // der Name allein wäre dann kein eindeutiger Schlüssel und
                    // React würde die beiden Kacheln vermischen.
                    key={`${card.name}|${card.set || ''}|${card.sammlernummer || ''}|${idx}`}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      position: 'relative'
                    }}
                  >
                    {/* Floating remove/add buttons on hover */}
                    <div style={{
                      position: 'absolute',
                      top: '-10px',
                      zIndex: 10,
                      display: 'flex',
                      gap: '4px'
                    }}>
                      <button
                        onClick={() => removeCard(card.name, card)}
                        style={{
                          background: 'var(--danger-color)',
                          color: 'white',
                          border: 'none',
                          borderRadius: '50%',
                          width: '22px',
                          height: '22px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 'bold',
                          boxShadow: '0 2px 5px rgba(0,0,0,0.2)'
                        }}
                        title="Verringern"
                      >
                        -
                      </button>
                      <span style={{
                        background: 'var(--accent-color)',
                        color: 'white',
                        padding: '2px 8px',
                        borderRadius: '10px',
                        fontSize: '0.78rem',
                        fontWeight: 'bold',
                        boxShadow: '0 2px 5px rgba(0,0,0,0.2)'
                      }}>
                        {card.count || 1}
                      </span>
                      <button
                        onClick={() => addCard(card.name, card)}
                        style={{
                          background: '#30D158',
                          color: 'white',
                          border: 'none',
                          borderRadius: '50%',
                          width: '22px',
                          height: '22px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 'bold',
                          boxShadow: '0 2px 5px rgba(0,0,0,0.2)'
                        }}
                        title="Erhöhen"
                      >
                        +
                      </button>
                    </div>

                    {/* Card Image */}
                    <img
                      src={card.image || getFallbackCardImage(card.name, card.type)}
                      alt={card.name}
                      style={{
                        width: '100%',
                        borderRadius: '4.75% / 3.5%',
                        boxShadow: '0 4px 10px rgba(0,0,0,0.15)',
                        border: '1px solid var(--border-color)',
                        display: 'block'
                      }}
                      onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(card.name, card.type); }}
                    />
                    
                    {/* Card Title */}
                    <span style={{
                      fontWeight: 600,
                      fontSize: '0.8rem',
                      textAlign: 'center',
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                      marginTop: '8px',
                      color: 'var(--text-main)'
                    }} title={card.name}>
                      {card.name}
                    </span>

                    {/* Auflage: sichtbar und in einem Klick änderbar. Steht sie
                        nicht fest, sagt der Knopf genau das -- sonst sähe der
                        Standarddruck aus wie eine Wahl des Nutzers. */}
                    <button
                      type="button"
                      onClick={() => setAuflagenKarte(card)}
                      title={card.auflage_gewuenscht && !card.auflage_gefunden
                        ? 'Diese Auflage liess sich nicht abrufen -- angezeigt wird der Standarddruck.'
                        : 'Auflage wählen'}
                      style={{
                        marginTop: '5px',
                        padding: '3px 9px',
                        fontSize: '0.7rem',
                        borderRadius: '10px',
                        cursor: 'pointer',
                        width: 'auto',
                        maxWidth: '100%',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        background: 'var(--bg-main)',
                        color: card.auflage_gewuenscht && !card.auflage_gefunden
                          ? '#FF9F0A' : 'var(--text-muted)',
                        border: `1px solid ${card.set ? 'var(--accent-color)' : 'var(--border-color)'}`,
                      }}
                    >
                      {card.set
                        ? `${(card.set || '').toUpperCase()}${card.sammlernummer ? ` · ${card.sammlernummer}` : ''}`
                        : 'Auflage wählen'}
                      {card.auflage_gewuenscht && !card.auflage_gefunden ? ' ⚠' : ''}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {auflagenKarte && (
        <AuflagenWahl
          key={`${auflagenKarte.name}|${auflagenKarte.set || ''}`}
          kartenName={auflagenKarte.name}
          aktuell={auflagenKarte}
          onWaehlen={(auflage) => setzeAuflage(auflagenKarte, auflage)}
          onSchliessen={() => setAuflagenKarte(null)}
        />
      )}
    </div>
  );
}

export default DeckEditor;
