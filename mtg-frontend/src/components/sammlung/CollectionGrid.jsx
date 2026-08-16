import { useState } from 'react';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';
import { formatEuro, formatZahl } from '../../utils/format';

// Sortiert und geblättert wird im Server, nicht hier.
//
// Vorher tat dieses Bauteil beides selbst: es sortierte die übergebenen Karten
// und zeigte davon 24 je Seite. Das ging nur, solange die Ansicht IMMER die
// vollständige Sammlung bekam. Seit sie seitenweise lädt, wäre es falsch --
// "Preis: Hoch → Tief" würde die teuerste der geladenen 100 nach oben stellen
// und nicht die teuerste des Ordners. Das sieht nicht falsch aus, ist es aber.
//
// Der Zähler kommt aus demselben Grund von aussen: "Karten gefunden" zählte
// die geladenen, nicht die vorhandenen.
function CollectionGrid({ karten, updatingPrices, loescheKarte,
                          sortBy = "name", onSortChange, gesamt }) {
  const [viewMode, setViewMode] = useState("grid"); // "grid" | "list"

  const renderPriceTrend = (k) => {
    // Einheitliche Feldnamen: "preis" ist der gespeicherte Wert,
    // "livePreis" der aktuelle. Frueher hiessen sie hier
    // "originalPrice"/"price" -- und nur hier.
    const pOriginal = parseFloat(String(k.preis || "0").replace(',', '.')) || 0;
    const pLive = parseFloat(String(k.livePreis || k.preis || "0").replace(',', '.')) || 0;
    
    if (pOriginal <= 0) return null;
    
    const diff = pLive - pOriginal;
    const diffPct = (diff / pOriginal) * 100;
    
    if (diff > 0.005) {
      return (
        <span style={{ 
          color: '#4cd964', 
          fontWeight: 600, 
          fontSize: '0.82rem', 
          display: 'inline-flex', 
          alignItems: 'center', 
          gap: '3px',
          background: 'rgba(76, 217, 100, 0.08)',
          padding: '2px 8px',
          borderRadius: '8px',
          marginLeft: '8px',
          verticalAlign: 'middle'
        }}>
          ▲ +{formatEuro(diff)} (+{formatZahl(diffPct, 1)}%)
        </span>
      );
    } else if (diff < -0.005) {
      return (
        <span style={{ 
          color: '#ff453a', 
          fontWeight: 600, 
          fontSize: '0.82rem', 
          display: 'inline-flex', 
          alignItems: 'center', 
          gap: '3px',
          background: 'rgba(255, 69, 58, 0.08)',
          padding: '2px 8px',
          borderRadius: '8px',
          marginLeft: '8px',
          verticalAlign: 'middle'
        }}>
          ▼ {formatEuro(diff)} ({formatZahl(diffPct, 1)}%)
        </span>
      );
    }
    return null;
  };

  // Die Karten kommen bereits sortiert und auf die geladenen Seiten begrenzt.
  const currentCards = karten;
  // Fehlt die Angabe von aussen, ist die Anzahl der übergebenen Karten die
  // ehrlichste verfügbare Aussage.
  const totalCards = typeof gesamt === 'number' ? gesamt : karten.length;

  return (
    <div>
      {/* Controls: Sorting, View Mode, Counter */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '20px',
        flexWrap: 'wrap',
        gap: '15px'
      }}>
        <div style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>
          Karten gefunden: <strong style={{ color: 'var(--text-main)' }}>{totalCards}</strong>
        </div>

        <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
          {/* Sorting */}
          <select
            aria-label="Sortierung"
            value={sortBy}
            onChange={e => onSortChange?.(e.target.value)}
            style={{
              padding: '8px 12px',
              fontSize: '0.9rem',
              width: 'auto',
              borderRadius: '8px',
              background: 'var(--btn-secondary)',
              border: 'none',
              cursor: 'pointer'
            }}
          >
            <option value="name">Alphabetisch (A-Z)</option>
            <option value="priceDesc">Preis: Hoch → Tief</option>
            <option value="priceAsc">Preis: Tief → Hoch</option>
            <option value="cmc">Manakosten (CMC)</option>
            <option value="rarity">Seltenheit</option>
          </select>

          {/* View Mode Toggle */}
          <div style={{
            display: 'flex',
            background: 'var(--btn-secondary)',
            padding: '3px',
            borderRadius: '8px',
            border: '1px solid var(--border-color)'
          }}>
            <button
              onClick={() => setViewMode("grid")}
              style={{
                background: viewMode === "grid" ? "var(--bg-card)" : "transparent",
                color: "var(--text-main)",
                border: 'none',
                padding: '6px 12px',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.85rem',
                fontWeight: 600,
                boxShadow: viewMode === "grid" ? "0 2px 4px var(--shadow-color)" : "none"
              }}
            >
              Grid
            </button>
            <button
              onClick={() => setViewMode("list")}
              style={{
                background: viewMode === "list" ? "var(--bg-card)" : "transparent",
                color: "var(--text-main)",
                border: 'none',
                padding: '6px 12px',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '0.85rem',
                fontWeight: 600,
                boxShadow: viewMode === "list" ? "0 2px 4px var(--shadow-color)" : "none"
              }}
            >
              Liste
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      {totalCards === 0 ? (
        <div style={{
          padding: '60px',
          textAlign: 'center',
          color: 'var(--text-muted)',
          fontSize: '1.1rem',
          fontStyle: 'italic',
          background: 'var(--bg-card)',
          borderRadius: '16px',
          border: '1px dashed var(--border-color)'
        }}>
          Keine Karten entsprechen den ausgewählten Filtern.
        </div>
      ) : viewMode === "grid" ? (
        /* GRID VIEW */
        <div className="gallery-grid" style={{ marginTop: 0 }}>
          {currentCards.map((karte, idx) => (
            <div key={karte.id || idx} className="gallery-item" style={{
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              minHeight: '320px'
            }}>
              <div>
                <button className="gallery-remove-btn" onClick={() => loescheKarte(karte.id)}>✕</button>
                <div style={{ overflow: 'hidden', borderRadius: '4.75% / 3.5%', position: 'relative' }}>
                  <img
                    src={karte.bild_url || getFallbackCardImage(karte.name, karte.type)}
                    alt={karte.name}
                    className="gallery-img"
                    style={{
                      transition: 'transform 0.3s ease',
                      width: '100%'
                    }}
                    loading="lazy"
                    onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(karte.name, karte.type); }}
                  />
                </div>
                <span style={{
                  fontWeight: 600,
                  fontSize: '0.95rem',
                  display: 'block',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  marginTop: '10px',
                  marginBottom: '2px'
                }} title={karte.name}>
                  {karte.name}
                </span>
                <span style={{
                  fontSize: '0.78rem',
                  color: 'var(--text-muted)',
                  display: 'block',
                  textTransform: 'uppercase',
                  fontWeight: 600
                }}>
                  {karte.set ? `[${karte.set.toUpperCase()}]` : ""} {karte.type || "Karte"}
                </span>
              </div>
              <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '5px' }}>
                <span className="gallery-price-tag" style={{ margin: 0 }}>
                  {formatEuro(karte.livePreis)}
                </span>
                {renderPriceTrend(karte)}
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* LIST VIEW */
        <div style={{
          background: 'var(--bg-card)',
          borderRadius: '16px',
          border: '1px solid var(--border-color)',
          overflow: 'hidden',
          boxShadow: '0 4px 12px var(--shadow-color)'
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ background: 'var(--btn-secondary)', borderBottom: '1px solid var(--border-color)' }}>
                <th style={{ padding: '15px 20px', fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Name</th>
                <th style={{ padding: '15px 20px', fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Typ</th>
                <th style={{ padding: '15px 20px', fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Edition</th>
                <th style={{ padding: '15px 20px', fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Rarität</th>
                <th style={{ padding: '15px 20px', fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Preis</th>
                <th style={{ padding: '15px 20px', width: '60px' }}></th>
              </tr>
            </thead>
            <tbody>
              {currentCards.map((karte, idx) => (
                <tr key={karte.id || idx} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '12px 20px', fontWeight: 600, color: 'var(--text-main)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <img
                        src={karte.bild_url || getFallbackCardImage(karte.name, karte.type)}
                        alt={karte.name}
                        style={{ width: '35px', borderRadius: '2px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}
                        onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(karte.name, karte.type); }}
                      />
                      {karte.name}
                    </div>
                  </td>
                  <td style={{ padding: '12px 20px', color: 'var(--text-muted)', fontSize: '0.95rem' }}>{karte.type || "Unbekannt"}</td>
                  <td style={{ padding: '12px 20px', color: 'var(--text-muted)', fontSize: '0.95rem' }}>
                    <span style={{ textTransform: 'uppercase', fontWeight: 600, background: 'var(--btn-secondary)', padding: '2px 6px', borderRadius: '4px', marginRight: '6px' }}>
                      {karte.set}
                    </span>
                  </td>
                  <td style={{ padding: '12px 20px', color: 'var(--text-muted)', fontSize: '0.95rem', textTransform: 'capitalize' }}>
                    {karte.rarity}
                  </td>
                  <td style={{ padding: '12px 20px', fontWeight: 600, color: 'var(--price-color)' }}>
                    {formatEuro(karte.livePreis)}
                    {renderPriceTrend(karte)}
                  </td>
                  <td style={{ padding: '12px 20px', textAlign: 'center' }}>
                    <button
                      onClick={() => loescheKarte(karte.id)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--danger-color)',
                        fontSize: '1.1rem',
                        cursor: 'pointer',
                        padding: '4px 8px'
                      }}
                      title="Karte entfernen"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Das Nachladen sitzt in der übergeordneten Ansicht ("Mehr laden").
          Hier stand früher eine zweite, eigene Blätterung über die geladenen
          Karten -- zwei Blätterungen übereinander hätten sich gegenseitig
          erklären müssen. */}
    </div>
  );
}

export default CollectionGrid;
