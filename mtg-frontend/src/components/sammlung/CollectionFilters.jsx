import { useState, useEffect, useRef } from 'react';

const colorSymbols = {
  "W": "https://svgs.scryfall.io/card-symbols/W.svg",
  "U": "https://svgs.scryfall.io/card-symbols/U.svg",
  "B": "https://svgs.scryfall.io/card-symbols/B.svg",
  "R": "https://svgs.scryfall.io/card-symbols/R.svg",
  "G": "https://svgs.scryfall.io/card-symbols/G.svg",
  "C": "https://svgs.scryfall.io/card-symbols/C.svg"
};

function CollectionFilters({ currentUser, selectedAlbum, onFilterChange }) {
  const [editions, setEditions] = useState([]);
  const [search, setSearch] = useState("");
  const [selectedColor, setSelectedColor] = useState("");
  const [rarity, setRarity] = useState("");
  const [edition, setEdition] = useState("");
  const [minCmc, setMinCmc] = useState(0);
  const [maxCmc, setMaxCmc] = useState(16);
  const [cardType, setCardType] = useState("");

  useEffect(() => {
    // Fetch editions for selection
    if (currentUser) {
      const url = selectedAlbum
        ? `/api/sammlung/${currentUser}/editions?album=${encodeURIComponent(selectedAlbum)}`
        : `/api/sammlung/${currentUser}/editions`;
      fetch(url)
        .then(res => res.json())
        .then(data => {
          if (data && data.erfolg && data.editions) {
            setEditions(data.editions);
          }
        })
        .catch(err => console.error("Error loading editions:", err));
    }
  }, [currentUser, selectedAlbum]);

  // Filter nach oben melden -- entprellt.
  //
  // Vorher löste JEDER Tastendruck in der Suche und JEDE Bewegung der
  // Manawert-Slider sofort eine vollständige Server-Anfrage aus (inklusive
  // Scryfall-Auflösung der ganzen Sammlung). "Lightning Bolt" zu tippen
  // erzeugte so 14 Anfragen, von denen nur die letzte zählte -- die
  // Hauptursache für die trägen Ladezeiten in der Sammlung.
  //
  // Zusätzlich wird der Aufruf beim ersten Rendern übersprungen: die
  // Erstbefüllung übernimmt bereits die Album-Auswahl in MeineSammlung,
  // sonst lief jede Album-Öffnung doppelt.
  const istErstesRendern = useRef(true);

  useEffect(() => {
    if (istErstesRendern.current) {
      istErstesRendern.current = false;
      return;
    }
    const timer = setTimeout(() => {
      onFilterChange({
        farbe: selectedColor || undefined,
        seltenheit: rarity || undefined,
        edition: edition || undefined,
        manakosten_min: minCmc,
        manakosten_max: maxCmc,
        typ: cardType || undefined,
        suche: search.trim() || undefined
      });
    }, 350);
    return () => clearTimeout(timer);
  }, [search, selectedColor, rarity, edition, minCmc, maxCmc, cardType]);

  const handleReset = () => {
    setSearch("");
    setSelectedColor("");
    setRarity("");
    setEdition("");
    setMinCmc(0);
    setMaxCmc(16);
    setCardType("");
  };

  const handleColorClick = (color) => {
    if (selectedColor === color) {
      setSelectedColor("");
    } else {
      setSelectedColor(color);
    }
  };

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-color)',
      borderRadius: '20px',
      padding: '25px',
      marginBottom: '30px',
      boxShadow: '0 4px 15px var(--shadow-color)',
      display: 'flex',
      flexDirection: 'column',
      gap: '20px'
    }}>
      {/* First Row: Search & Color Symbols */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '20px',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        {/* Free text search */}
        <div style={{ flex: '1 1 300px' }}>
          <input
            type="text"
            placeholder="Sammlung durchsuchen (z.B. Black Lotus)..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              padding: '12px 18px',
              borderRadius: '10px',
              background: 'var(--bg-main)'
            }}
          />
        </div>

        {/* Color filters (Mana Symbols) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)', fontWeight: 600 }}>Farbe:</span>
          <div style={{ display: 'flex', gap: '8px' }}>
            {Object.entries(colorSymbols).map(([code, url]) => {
              const isActive = selectedColor === code;
              return (
                <button
                  key={code}
                  type="button"
                  onClick={() => handleColorClick(code)}
                  style={{
                    background: isActive ? 'var(--btn-secondary-hover)' : 'transparent',
                    border: isActive ? '2px solid var(--accent-color)' : '2px solid transparent',
                    borderRadius: '50%',
                    padding: '2px',
                    width: '38px',
                    height: '38px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    transition: 'all 0.2s',
                    boxShadow: isActive ? '0 0 8px rgba(0,113,227,0.3)' : 'none'
                  }}
                  title={code === 'C' ? 'Farblos' : `Farbe ${code}`}
                >
                  <img src={url} alt={code} style={{ width: '28px', height: '28px' }} />
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Second Row: Dropdowns (Rarity, Edition, Type) */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: '15px'
      }}>
        {/* Rarity select */}
        <div>
          <span style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 600, marginBottom: '6px' }}>Seltenheit</span>
          <select
            value={rarity}
            onChange={e => setRarity(e.target.value)}
            style={{ padding: '12px 15px', borderRadius: '10px', background: 'var(--bg-main)' }}
          >
            <option value="">Alle Seltenheiten</option>
            <option value="common">Common</option>
            <option value="uncommon">Uncommon</option>
            <option value="rare">Rare</option>
            <option value="mythic">Mythic</option>
          </select>
        </div>

        {/* Edition / Set select */}
        <div>
          <span style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 600, marginBottom: '6px' }}>Set (Edition)</span>
          <select
            value={edition}
            onChange={e => setEdition(e.target.value)}
            style={{ padding: '12px 15px', borderRadius: '10px', background: 'var(--bg-main)' }}
          >
            <option value="">Alle Sets / Editionen</option>
            {editions.map(ed => (
              <option key={ed.set_code} value={ed.set_code}>
                [{ed.set_code.toUpperCase()}] {ed.set_name}
              </option>
            ))}
          </select>
        </div>

        {/* Card Type select */}
        <div>
          <span style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 600, marginBottom: '6px' }}>Kartentyp</span>
          <select
            value={cardType}
            onChange={e => setCardType(e.target.value)}
            style={{ padding: '12px 15px', borderRadius: '10px', background: 'var(--bg-main)' }}
          >
            <option value="">Alle Typen</option>
            <option value="creature">Kreatur (Creature)</option>
            <option value="instant">Spontanzauber (Instant)</option>
            <option value="sorcery">Hexerei (Sorcery)</option>
            <option value="artifact">Artefakt (Artifact)</option>
            <option value="enchantment">Verzauberung (Enchantment)</option>
            <option value="planeswalker">Planeswalker</option>
            <option value="land">Land</option>
          </select>
        </div>
      </div>

      {/* Third Row: CMC Slider & Reset Button */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '30px',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderTop: '1px solid var(--border-color)',
        paddingTop: '15px'
      }}>
        {/* CMC range */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px', flex: '1 1 auto' }}>
          <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)', fontWeight: 600 }}>Manawert (CMC):</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexGrow: 1, maxWidth: '350px' }}>
            <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>{minCmc}</span>
            <input
              type="range"
              min="0"
              max="16"
              value={minCmc}
              onChange={e => setMinCmc(Math.min(parseInt(e.target.value), maxCmc))}
              style={{ padding: 0, height: '6px', background: 'var(--border-color)', cursor: 'pointer' }}
            />
            <input
              type="range"
              min="0"
              max="16"
              value={maxCmc}
              onChange={e => setMaxCmc(Math.max(parseInt(e.target.value), minCmc))}
              style={{ padding: 0, height: '6px', background: 'var(--border-color)', cursor: 'pointer' }}
            />
            <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>{maxCmc === 16 ? "16+" : maxCmc}</span>
          </div>
        </div>

        {/* Reset button */}
        <button
          type="button"
          onClick={handleReset}
          className="secondary-btn"
          style={{ padding: '10px 24px', fontSize: '0.95rem', borderRadius: '10px' }}
        >
          Filter zurücksetzen
        </button>
      </div>
    </div>
  );
}

export default CollectionFilters;
