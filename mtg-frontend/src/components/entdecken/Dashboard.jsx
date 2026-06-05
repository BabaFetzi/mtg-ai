import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getScryfallImage, getFallbackCardImage } from '../../utils/scryfallHelpers';
import SkeletonLoader from '../layout/SkeletonLoader';
import { Plus, Package, BookOpen, Swords, RefreshCw } from 'lucide-react';

// Pools für Preissprünge und Staples zur Rotation
const spikesPool = [
  { name: 'Jeweled Lotus', price: '74.50 €', change: '+15.6%', up: true },
  { name: 'Orcish Bowmasters', price: '38.20 €', change: '+12.4%', up: true },
  { name: 'Sheoldred, the Apocalypse', price: '68.00 €', change: '+8.1%', up: true },
  { name: 'Mana Crypt', price: '162.00 €', change: '-4.2%', up: false },
  { name: 'Black Lotus', price: '15000.00 €', change: '+25.0%', up: true },
  { name: 'Ragavan, Nimble Pilferer', price: '35.00 €', change: '+5.2%', up: true },
  { name: 'Time Walk', price: '4000.00 €', change: '+18.3%', up: true },
  { name: 'Ledger Shredder', price: '12.40 €', change: '-5.3%', up: false },
  { name: 'Mox Diamond', price: '550.00 €', change: '+10.5%', up: true },
  { name: 'Gaea\'s Cradle', price: '850.00 €', change: '+14.2%', up: true }
];

const staplesPool = [
  { name: 'Sol Ring', type: 'Artifact' },
  { name: 'Arcane Signet', type: 'Artifact' },
  { name: 'Command Tower', type: 'Land' },
  { name: 'Cyclonic Rift', type: 'Instant' },
  { name: 'Demonic Tutor', type: 'Sorcery' },
  { name: 'Rhystic Study', type: 'Enchantment' },
  { name: 'Swords to Plowshares', type: 'Instant' },
  { name: 'Lightning Bolt', type: 'Instant' },
  { name: 'Brainstorm', type: 'Instant' },
  { name: 'Birds of Paradise', type: 'Creature' }
];

const combos = [
  {
    name: "Godo + Helm of the Host",
    badge: "Infinite Combats",
    card1: "Godo, Bandit Warlord",
    card2: "Helm of the Host",
    type1: "Creature",
    type2: "Artifact",
    desc: "Wenn Godo ins Spiel kommt, sucht er nach Helm of the Host und legt es an. Helm erzeugt in jedem Kampfsegment eine Eile-Kopie von Godo, die wiederum eine zusätzliche Kampfphase auslöst. Das Ergebnis: Unendlich viele Kampfphasen!"
  },
  {
    name: "Sanguine Bond + Exquisite Blood",
    badge: "Infinite Life Drain",
    card1: "Sanguine Bond",
    card2: "Exquisite Blood",
    type1: "Enchantment",
    type2: "Enchantment",
    desc: "Sobald ein Gegner Lebenspunkte verliert oder du Lebenspunkte erhältst, startet diese verheerende Endlosschleife: Sanguine Bond lässt den Gegner Lebenspunkte verlieren, wenn du Leben erhältst, und Exquisite Blood gibt dir Leben, wenn der Gegner Leben verliert."
  },
  {
    name: "Kiki-Jiki + Deceiver Exarch",
    badge: "Infinite Hasty Tokens",
    card1: "Kiki-Jiki, Mirror Breaker",
    card2: "Deceiver Exarch",
    type1: "Creature",
    type2: "Creature",
    desc: "Tappe Kiki-Jiki, um eine Kopie von Deceiver Exarch mit Eile zu erzeugen. Der neue Exarch kommt ins Spiel und enttappt Kiki-Jiki. Wiederhole dies beliebig oft für eine Armee von unendlich vielen eilig angreifenden Kreaturen!"
  },
  {
    name: "Thassa's Oracle + Demonic Consultation",
    badge: "Instant Win Combo",
    card1: "Thassa's Oracle",
    card2: "Demonic Consultation",
    type1: "Creature",
    type2: "Instant",
    desc: "Spiele Thassa's Oracle und reagiere auf den Auslöser, indem du Demonic Consultation spielst. Nenne eine Karte, die nicht im Deck ist, um deine gesamte Bibliothek ins Exil zu schicken. Der Oracle-Effekt gewinnt dir sofort das Spiel!"
  },
  {
    name: "Painter's Servant + Grindstone",
    badge: "Infinite Library Mill",
    card1: "Painter's Servant",
    card2: "Grindstone",
    type1: "Creature",
    type2: "Artifact",
    desc: "Painter's Servant macht alle Karten im Spiel und in Bibliotheken zu einer Farbe deiner Wahl. Aktiviere Grindstone, um die obersten zwei Karten des Gegners zu millen. Da sie dieselbe Farbe haben, wiederholt Grindstone den effekt, bis die gesamte Bibliothek gemillt ist."
  }
];

export default function Dashboard({ currentUser }) {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loadingStats, setLoadingStats] = useState(true);
  const [loadedImages, setLoadedImages] = useState({});
  const [spikes, setSpikes] = useState([]);
  const [staples, setStaples] = useState([]);

  // Synergie des Tages Rotation per Datum initialisieren
  const getDailyComboIndex = () => {
    const now = new Date();
    const start = new Date(now.getFullYear(), 0, 0);
    const diff = now - start;
    const oneDay = 1000 * 60 * 60 * 24;
    const day = Math.floor(diff / oneDay);
    return day % combos.length;
  };
  const [comboIndex, setComboIndex] = useState(getDailyComboIndex());

  useEffect(() => {
    fetch('/api/dashboard/stats')
      .then((res) => res.json())
      .then((data) => {
        setStats(data);
        setLoadingStats(false);
      })
      .catch((err) => {
        console.error('Error fetching dashboard stats:', err);
        setLoadingStats(false);
      });

    // Spikes und Staples bei Mount durchmischen
    const shuffledSpikes = [...spikesPool].sort(() => 0.5 - Math.random()).slice(0, 4);
    const shuffledStaples = [...staplesPool].sort(() => 0.5 - Math.random()).slice(0, 4);
    setSpikes(shuffledSpikes);
    setStaples(shuffledStaples);
  }, []);

  const handleImageLoad = (id) => {
    setLoadedImages((prev) => ({ ...prev, [id]: true }));
  };

  const handleCardClick = (cardName) => {
    navigate(`/?view=search&q=${encodeURIComponent(cardName)}`);
  };

  const handleRerollCombo = () => {
    let nextIdx;
    do {
      nextIdx = Math.floor(Math.random() * combos.length);
    } while (nextIdx === comboIndex && combos.length > 1);
    setComboIndex(nextIdx);
  };

  return (
    <div style={{ animation: 'slideUp 0.4s ease' }}>
      <div className="search-hero" style={{ paddingTop: '0', marginBottom: '20px' }}>
        <h2>Willkommen im Multiversum.</h2>
        <p>Deine Kommandozentrale für Decks, Synergien und Markt-Trends.</p>
      </div>

      <div className="bento-grid">
        {/* WIDGET 1: Synergy of the Day (Wide) */}
        <div className="bento-item bento-col-2" style={{ minHeight: '320px' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <h3 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 600 }}>Synergie des Tages</h3>
                <button 
                  onClick={handleRerollCombo}
                  title="Andere Synergie würfeln"
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
                  <RefreshCw size={14} className="rotation-icon" />
                </button>
              </div>
              <span className="combo-badge" style={{ display: 'flex', alignItems: 'center', gap: '6px', margin: 0, background: 'rgba(255, 59, 48, 0.08)', color: 'var(--danger-color)', border: '1px solid rgba(255, 59, 48, 0.2)', padding: '4px 10px', borderRadius: '20px', fontSize: '0.85rem', fontWeight: 500 }}>
                <Swords size={14} /> {combos[comboIndex].badge}
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '30px', alignItems: 'center' }}>
              <div className="combo-images-container" style={{ padding: 0, margin: 0, justifyContent: 'center' }}>
                <img
                  src={getScryfallImage(combos[comboIndex].card1)}
                  alt={combos[comboIndex].card1}
                  className={`combo-card-img fade-in-img ${loadedImages[combos[comboIndex].card1] ? 'loaded' : ''}`}
                  onLoad={() => handleImageLoad(combos[comboIndex].card1)}
                  onError={(e) => {
                    e.target.onerror = null;
                    e.target.src = getFallbackCardImage(combos[comboIndex].card1, combos[comboIndex].type1);
                  }}
                  onClick={() => handleCardClick(combos[comboIndex].card1)}
                  style={{ cursor: 'pointer', width: '140px', marginRight: '-50px' }}
                />
                <img
                  src={getScryfallImage(combos[comboIndex].card2)}
                  alt={combos[comboIndex].card2}
                  className={`combo-card-img fade-in-img ${loadedImages[combos[comboIndex].card2] ? 'loaded' : ''}`}
                  onLoad={() => handleImageLoad(combos[comboIndex].card2)}
                  onError={(e) => {
                    e.target.onerror = null;
                    e.target.src = getFallbackCardImage(combos[comboIndex].card2, combos[comboIndex].type2);
                  }}
                  onClick={() => handleCardClick(combos[comboIndex].card2)}
                  style={{ cursor: 'pointer', width: '140px' }}
                />
              </div>

              <div>
                <h4 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>{combos[comboIndex].name}</h4>
                <p style={{ fontSize: '0.95rem', margin: 0, color: 'var(--text-muted)', lineHeight: '1.6' }} dangerouslySetInnerHTML={{ __html: combos[comboIndex].desc.replace(new RegExp(`(${combos[comboIndex].card1}|${combos[comboIndex].card2})`, 'g'), '<strong>$1</strong>') }}>
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* WIDGET 2: Schnellzugriff */}
        <div className="bento-item">
          <div>
            <h3 style={{ fontSize: '1.3rem', marginBottom: '20px' }}>Schnellzugriff</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <button
                className="secondary-btn"
                onClick={() => navigate('/decks')}
                style={{ display: 'flex', alignItems: 'center', gap: '10px', justifyContent: 'flex-start', padding: '14px 20px', borderRadius: '14px', width: '100%', textAlign: 'left' }}
              >
                <Plus size={18} style={{ color: 'var(--text-muted)' }} /> Neues Deck erstellen
              </button>
              <button
                className="secondary-btn"
                onClick={() => navigate('/sammlung')}
                style={{ display: 'flex', alignItems: 'center', gap: '10px', justifyContent: 'flex-start', padding: '14px 20px', borderRadius: '14px', width: '100%', textAlign: 'left' }}
              >
                <Package size={18} style={{ color: 'var(--text-muted)' }} /> Sammlung verwalten / Import
              </button>
              <button
                className="secondary-btn"
                onClick={() => navigate('/?view=rulebook')}
                style={{ display: 'flex', alignItems: 'center', gap: '10px', justifyContent: 'flex-start', padding: '14px 20px', borderRadius: '14px', width: '100%', textAlign: 'left' }}
              >
                <BookOpen size={18} style={{ color: 'var(--text-muted)' }} /> Offizielles Regelbuch
              </button>
            </div>
          </div>
        </div>

        {/* WIDGET 3: Platform Activity Stats */}
        <div className="bento-item">
          <div>
            <h3 style={{ fontSize: '1.3rem', marginBottom: '25px' }}>Plattform-Aktivität</h3>
            {loadingStats ? (
              <SkeletonLoader type="text" count={3} />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Erstellte Decks</span>
                  <span style={{ fontSize: '1.4rem', fontWeight: 'bold' }}>{stats?.total_decks ?? 0}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Karten in Sammlungen</span>
                  <span style={{ fontSize: '1.4rem', fontWeight: 'bold' }}>{stats?.total_collection_cards ?? 0}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Suchanfragen & Analysen</span>
                  <span style={{ fontSize: '1.4rem', fontWeight: 'bold', color: '#0071E3' }}>{stats?.query_count ?? 1420}</span>
                </div>
              </div>
            )}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '20px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '8px', height: '8px', background: '#30D158', borderRadius: '50%', display: 'inline-block' }}></span>
            Daten live synchronisiert
          </div>
        </div>

        {/* WIDGET 4: Market Spikes */}
        <div className="bento-item">
          <div>
            <h3 style={{ fontSize: '1.3rem', marginBottom: '20px' }}>Heutige Preissprünge</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {spikes.map((s, idx) => (
                <div
                  key={idx}
                  onClick={() => handleCardClick(s.name)}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', padding: '6px 0', borderBottom: idx < spikes.length - 1 ? '1px solid var(--border-color)' : 'none' }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>{s.name}</div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{s.price}</div>
                  </div>
                  <span style={{
                    color: s.up ? 'var(--price-color)' : 'var(--danger-color)',
                    background: s.up ? 'rgba(48, 209, 88, 0.1)' : 'rgba(255, 59, 48, 0.1)',
                    padding: '4px 10px',
                    borderRadius: '8px',
                    fontWeight: 600,
                    fontSize: '0.85rem'
                  }}>
                    {s.change}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* WIDGET 5: Commander Staples */}
        <div className="bento-item">
          <div>
            <h3 style={{ fontSize: '1.3rem', marginBottom: '20px' }}>Top Commander Staples</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              {staples.map((st, idx) => {
                const imgId = `staple_${idx}`;
                return (
                  <div
                    key={idx}
                    className="deck-card-wrapper"
                    onClick={() => handleCardClick(st.name)}
                    style={{ cursor: 'pointer', textAlign: 'center', background: 'var(--btn-secondary)', borderRadius: '16px', padding: '12px', border: '1px solid var(--border-color)' }}
                  >
                    <img
                      src={getScryfallImage(st.name)}
                      alt={st.name}
                      className={`fade-in-img ${loadedImages[imgId] ? 'loaded' : ''}`}
                      onLoad={() => handleImageLoad(imgId)}
                      onError={(e) => {
                        e.target.onerror = null;
                        e.target.src = getFallbackCardImage(st.name, st.type);
                      }}
                      style={{ width: '100%', borderRadius: '4px', marginBottom: '8px' }}
                    />
                    <div style={{ fontSize: '0.85rem', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{st.name}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
