import { useState } from 'react';
import PremiumOverlay from '../layout/PremiumOverlay';
import { getScryfallImage } from '../../utils/scryfallHelpers';
import { Infinity } from 'lucide-react';

function DeckAnalysis({ analyse, deckWert, userRole, onShowPremiumModal }) {
  const [hoveredCard, setHoveredCard] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  if (!analyse) {
    return <p style={{ textAlign: 'center', color: 'var(--text-muted)' }}>Keine Analyse verfügbar.</p>;
  }

  // --- 1. SVG RADAR CHART MATHEMATICS ---
  const categories = [
    { key: 'card_draw', label: 'Card Draw' },
    { key: 'removal', label: 'Removal' },
    { key: 'ramp', label: 'Ramp' },
    { key: 'protection', label: 'Protection' },
    { key: 'winconditions', label: 'Siegbedingungen' }
  ];

  const center = 150;
  const maxVal = 10;
  const radius = 100;

  // Compute (x, y) coordinates for a given index and score
  const getCoordinates = (index, value) => {
    const angle = (Math.PI * 2 / categories.length) * index - Math.PI / 2;
    const r = (value / maxVal) * radius;
    const x = center + r * Math.cos(angle);
    const y = center + r * Math.sin(angle);
    return { x, y };
  };

  // Get score data or fallback
  const getScore = (key) => {
    if (analyse.schwaechen && analyse.schwaechen[key]) {
      return Math.min(10, Math.max(1, parseInt(analyse.schwaechen[key].score) || 5));
    }
    return 5;
  };

  const getExplanation = (key) => {
    if (analyse.schwaechen && analyse.schwaechen[key]) {
      return analyse.schwaechen[key].text || "Kein Kommentar.";
    }
    return "Keine Daten.";
  };

  // Generate SVG polygon points for the score area
  const points = categories.map((cat, i) => {
    const score = getScore(cat.key);
    const coords = getCoordinates(i, score);
    return `${coords.x},${coords.y}`;
  }).join(' ');

  // Outer pentagon grid lines (e.g. at levels 2, 4, 6, 8, 10)
  const gridLevels = [2, 4, 6, 8, 10];
  const gridPolygons = gridLevels.map(level => {
    return categories.map((_, i) => {
      const coords = getCoordinates(i, level);
      return `${coords.x},${coords.y}`;
    }).join(' ');
  });

  // Label coordinates (placed slightly further out than grid level 10)
  const labelCoords = categories.map((_, i) => getCoordinates(i, 12));

  // --- 2. POWER LEVEL GAUGE ---
  const powerLevel = Math.min(10, Math.max(1, parseInt(analyse.power_level) || 5));
  // Map 1-10 to angle for gauge pointer (-90 to +90 degrees)
  const gaugeAngle = -90 + (powerLevel - 1) * 20;

  // --- 3. HOVER CARD HANDLERS ---
  const handleMouseMove = (e) => {
    setMousePos({ x: e.clientX + 15, y: e.clientY + 15 });
  };

  const getPowerLevelLabel = (lvl) => {
    if (lvl <= 3) return "Casual / Precon (1-3)";
    if (lvl <= 6) return "Optimized Casual (4-6)";
    if (lvl <= 8) return "High Power (7-8)";
    return "cEDH / Tournament (9-10)";
  };

  return (
    <div style={{ position: 'relative', marginTop: '20px' }}>
      {userRole !== 'premium' && <PremiumOverlay onShowPremiumModal={onShowPremiumModal} />}

      {/* Main Grid: Radar Chart + Power Level Gauge */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '40px',
        marginBottom: '40px'
      }}>
        {/* Radar Chart Card */}
        <div className="content-card" style={{ padding: '30px', margin: 0, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <h4 style={{ margin: '0 0 20px 0', width: '100%', fontSize: '1.2rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Deck-Schwächen (Radar Chart)</h4>
          <svg width="300" height="300" style={{ overflow: 'visible' }}>
            {/* Grid Levels */}
            {gridPolygons.map((pts, idx) => (
              <polygon
                key={idx}
                points={pts}
                fill="none"
                stroke="var(--border-color)"
                strokeWidth="1"
              />
            ))}
            {/* Spider lines (center to vertices) */}
            {categories.map((_, i) => {
              const coords = getCoordinates(i, maxVal);
              return (
                <line
                  key={i}
                  x1={center}
                  y1={center}
                  x2={coords.x}
                  y2={coords.y}
                  stroke="var(--border-color)"
                  strokeWidth="1.5"
                />
              );
            })}
            {/* Filled score area */}
            <polygon
              points={points}
              fill="rgba(0, 113, 227, 0.25)"
              stroke="#0071E3"
              strokeWidth="2.5"
            />
            {/* Category labels */}
            {categories.map((cat, i) => {
              const coords = labelCoords[i];
              let textAnchor = "middle";
              if (i === 1) textAnchor = "start";
              if (i === 2) textAnchor = "start";
              if (i === 3) textAnchor = "end";
              if (i === 4) textAnchor = "end";

              return (
                <text
                  key={cat.key}
                  x={coords.x}
                  y={coords.y}
                  textAnchor={textAnchor}
                  fill="var(--text-main)"
                  fontSize="12"
                  fontWeight="600"
                >
                  {cat.label} ({getScore(cat.key)})
                </text>
              );
            })}
          </svg>
        </div>

        {/* Power Level Gauge Card */}
        <div className="content-card" style={{ padding: '30px', margin: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
          <h4 style={{ margin: '0 0 20px 0', width: '100%', fontSize: '1.2rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Geschätztes Power-Level</h4>
          
          <div style={{ position: 'relative', width: '220px', height: '120px', overflow: 'hidden', marginTop: '20px' }}>
            {/* Semi-circular gauge */}
            <svg width="220" height="220" style={{ transform: 'rotate(180deg)' }}>
              {/* Background Arc */}
              <path
                d="M 20,110 A 90,90 0 0,1 200,110"
                fill="none"
                stroke="var(--border-color)"
                strokeWidth="20"
                strokeLinecap="round"
              />
              {/* Colored Gauge Arc */}
              <path
                d="M 20,110 A 90,90 0 0,1 200,110"
                fill="none"
                stroke="url(#gaugeGradient)"
                strokeWidth="20"
                strokeLinecap="round"
              />
              <defs>
                <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#30D158" />
                  <stop offset="50%" stopColor="#FFD60A" />
                  <stop offset="100%" stopColor="#FF453A" />
                </linearGradient>
              </defs>
            </svg>

            {/* Needle */}
            <div style={{
              position: 'absolute',
              bottom: 0,
              left: '50%',
              width: '4px',
              height: '85px',
              background: 'var(--text-main)',
              transformOrigin: 'bottom center',
              transform: `translateX(-50%) rotate(${gaugeAngle}deg)`,
              transition: 'transform 1s cubic-bezier(0.18, 0.89, 0.32, 1.28)',
              borderRadius: '2px'
            }}>
              {/* Center point pin */}
              <div style={{
                position: 'absolute',
                bottom: '-6px',
                left: '-6px',
                width: '16px',
                height: '16px',
                background: 'var(--text-main)',
                borderRadius: '50%'
              }}></div>
            </div>
          </div>

          <div style={{ textAlign: 'center', marginTop: '20px' }}>
            <span style={{ fontSize: '3rem', fontWeight: 700, color: 'var(--text-main)' }}>{powerLevel}</span>
            <span style={{ fontSize: '1.5rem', color: 'var(--text-muted)' }}>/10</span>
            <p style={{ fontWeight: 600, marginTop: '8px', color: 'var(--text-main)' }}>
              {getPowerLevelLabel(powerLevel)}
            </p>
          </div>
        </div>
      </div>

      {/* Categories Explanations & Strategy */}
      <div className="content-card" style={{ padding: '35px', marginBottom: '30px' }}>
        <h4 style={{ fontSize: '1.4rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px', marginBottom: '20px' }}>
          Strategische Auswertung
        </h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {categories.map(cat => {
            const score = getScore(cat.key);
            const text = getExplanation(cat.key);
            return (
              <div key={cat.key} style={{ display: 'flex', gap: '15px', alignItems: 'flex-start' }}>
                <span style={{
                  background: score >= 7 ? 'rgba(48, 209, 88, 0.12)' : (score >= 5 ? 'rgba(255, 214, 10, 0.12)' : 'rgba(255, 69, 58, 0.12)'),
                  color: score >= 7 ? '#30D158' : (score >= 5 ? '#FFD60A' : '#FF453A'),
                  fontWeight: 'bold',
                  padding: '4px 12px',
                  borderRadius: '8px',
                  fontSize: '1rem',
                  minWidth: '35px',
                  textAlign: 'center'
                }}>
                  {score}
                </span>
                <div>
                  <strong style={{ display: 'block', fontSize: '1.05rem', color: 'var(--text-main)' }}>{cat.label}</strong>
                  <p style={{ margin: '4px 0 0 0', fontSize: '0.95rem', color: 'var(--text-muted)' }}>{text}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Detected Combos & Infinites */}
      {analyse.combos && analyse.combos.length > 0 && (
        <div id="analysis-combos" className="content-card" style={{ padding: '35px', marginBottom: '30px' }}>
          <h4 style={{ fontSize: '1.4rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px', marginBottom: '20px' }}>
            Combo-Finder
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
            {analyse.combos.map((combo, idx) => (
              <div key={idx} style={{
                background: 'var(--btn-secondary)',
                padding: '20px',
                borderRadius: '12px',
                border: '1px solid var(--border-color)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '15px'
              }}>
                <div>
                  <strong style={{ fontSize: '1.1rem', color: 'var(--text-main)', display: 'block', marginBottom: '6px' }}>
                    {Array.isArray(combo.karten) ? combo.karten.join(' + ') : combo.karten}
                  </strong>
                  <span style={{ fontSize: '0.95rem', color: 'var(--text-muted)' }}>{combo.erklaerung}</span>
                </div>
                {combo.typ && (
                  <span style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    background: 'var(--accent-color)',
                    color: 'var(--accent-text)',
                    padding: '4px 12px',
                    borderRadius: '8px',
                    fontSize: '0.82rem',
                    fontWeight: 700,
                    textTransform: 'uppercase'
                  }}>
                    <Infinity size={14} /> {combo.typ}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Suggested Upgrades Table (Rein / Raus) */}
      {analyse.verbesserungen && analyse.verbesserungen.length > 0 && (
        <div className="content-card" style={{ padding: '35px' }}>
          <h4 style={{ fontSize: '1.4rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px', marginBottom: '25px' }}>
            Empfohlene Upgrades
          </h4>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                <th style={{ padding: '12px 15px', color: 'var(--text-muted)', fontSize: '0.9rem', textTransform: 'uppercase' }}>Hinzufügen (+ Rein)</th>
                <th style={{ padding: '12px 15px', color: 'var(--text-muted)', fontSize: '0.9rem', textTransform: 'uppercase' }}>Entfernen (- Raus)</th>
                <th style={{ padding: '12px 15px', color: 'var(--text-muted)', fontSize: '0.9rem', textTransform: 'uppercase' }}>Grund / Synergie</th>
              </tr>
            </thead>
            <tbody>
              {analyse.verbesserungen.map((verb, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid rgba(0,0,0,0.05)' }}>
                  <td style={{ padding: '15px' }}>
                    <span
                      onMouseEnter={(e) => { setHoveredCard(verb.rein); handleMouseMove(e); }}
                      onMouseMove={handleMouseMove}
                      onMouseLeave={() => setHoveredCard(null)}
                      style={{
                        fontWeight: 600,
                        color: '#30D158',
                        cursor: 'pointer',
                        textDecoration: 'underline dotted'
                      }}
                    >
                      {verb.rein}
                    </span>
                  </td>
                  <td style={{ padding: '15px' }}>
                    {verb.raus ? (
                      <span
                        onMouseEnter={(e) => { setHoveredCard(verb.raus); handleMouseMove(e); }}
                        onMouseMove={handleMouseMove}
                        onMouseLeave={() => setHoveredCard(null)}
                        style={{
                          fontWeight: 600,
                          color: 'var(--danger-color)',
                          cursor: 'pointer',
                          textDecoration: 'underline dotted'
                        }}
                      >
                        {verb.raus}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>Beliebige Karte</span>
                    )}
                  </td>
                  <td style={{ padding: '15px', color: 'var(--text-muted)', fontSize: '0.95rem' }}>
                    {verb.grund}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Floating Image Preview on Hover */}
      {hoveredCard && (
        <div style={{
          position: 'fixed',
          left: mousePos.x,
          top: mousePos.y,
          zIndex: 99999,
          pointerEvents: 'none',
          boxShadow: '0 12px 40px rgba(0,0,0,0.5)',
          borderRadius: '14px',
          overflow: 'hidden',
          width: '200px',
          height: '280px',
          background: '#1C1C1E',
          border: '1px solid #38383A'
        }}>
          <img
            src={getScryfallImage(hoveredCard)}
            alt={hoveredCard}
            style={{ width: '100%', height: '100%', display: 'block', objectFit: 'cover' }}
            onError={(e) => { e.target.style.display = 'none'; }}
          />
        </div>
      )}
    </div>
  );
}

export default DeckAnalysis;
