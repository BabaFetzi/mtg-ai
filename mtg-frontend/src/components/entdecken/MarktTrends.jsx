import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getFallbackCardImage, getScryfallImage } from '../../utils/scryfallHelpers';
import { TrendingUp, TrendingDown, Activity, Award, Flame, Search } from 'lucide-react';

const winnersLosersPool = [
  { name: "Orcish Bowmasters", price: "38.20 €", change: "+12.4%", up: true, set: "LTR" },
  { name: "Sheoldred, the Apocalypse", price: "68.00 €", change: "+8.1%", up: true, set: "DMU" },
  { name: "The One Ring", price: "82.50 €", change: "+15.2%", up: true, set: "LTR" },
  { name: "Mana Crypt", price: "162.00 €", change: "-4.2%", up: false, set: "2XM" },
  { name: "Ledger Shredder", price: "12.40 €", change: "-5.3%", up: false, set: "SNC" },
  { name: "Boseiju, Who Endures", price: "34.80 €", change: "+6.8%", up: true, set: "NEO" },
  { name: "Ragavan, Nimble Pilferer", price: "35.00 €", change: "-2.1%", up: false, set: "MH2" },
  { name: "Mox Amber", price: "24.50 €", change: "+9.3%", up: true, set: "DOM" },
  { name: "Grief", price: "18.20 €", change: "-12.5%", up: false, set: "MH2" },
  { name: "Phyrexian Tower", price: "28.00 €", change: "+11.1%", up: true, set: "MH3" }
];

const insiderTips = [
  {
    card: "Boseiju, Who Endures",
    set: "NEO",
    title: "Sichere Bank: Utility-Lands",
    desc: "Boseiju wird in fast jedem Deck gespielt, das Grün enthält. Aufgrund der extremen Vielseitigkeit als unaufhaltbarer Removal-Effekt auf einem Land bleibt diese Karte langfristig wertstabil und ist ein solider Kauf."
  },
  {
    card: "Mox Amber",
    set: "DOM",
    title: "Hype-Fokus: Legendäre Decks",
    desc: "Mit dem ständigen Zuwachs neuer legendärer Commander steigt die Relevanz von Mox Amber kontinuierlich. Wenn du günstige Kopien findest, lohnt sich der Einstieg, da die Nachfrage stetig wächst."
  },
  {
    card: "Otawara, Soaring City",
    set: "NEO",
    title: "Geheimtipp: Blaues Utility-Land",
    desc: "Ähnlich wie Boseiju bietet Otawara einen extrem flexiblen Bounce-Effekt, der nicht gecountert werden kann. Eine unverzichtbare Karte für jedes blaue Deck in Commander und Modern."
  }
];

function MarktTrends({ currentUser }) {
  const navigate = useNavigate();
  const [trendingCards, setTrendingCards] = useState([]);
  const [loadingTrends, setLoadingTrends] = useState(false);
  const [isPersonalized, setIsPersonalized] = useState(false);
  const [winnersLosers, setWinnersLosers] = useState([]);
  const [insiderTip, setInsiderTip] = useState(null);

  useEffect(() => {
    const loadTrends = async () => {
      setLoadingTrends(true);
      try {
          const res = await fetch(`/api/trends?benutzername=${currentUser || ""}`);
          const data = await res.json();
          if (data && data.erfolg && Array.isArray(data.data)) {
              setTrendingCards(data.data);
              setIsPersonalized(!!data.personalized);
          }
      } catch (e) {
          console.error("Error loading trends:", e);
      }
      setLoadingTrends(false);
    };
    loadTrends();

    // Winners/Losers und Insider-Tipp bei Mount durchmischen
    const shuffledWL = [...winnersLosersPool].sort(() => 0.5 - Math.random()).slice(0, 4);
    setWinnersLosers(shuffledWL);

    const randomTip = insiderTips[Math.floor(Math.random() * insiderTips.length)];
    setInsiderTip(randomTip);
  }, [currentUser]);

  const clickTrendingCard = (cardName) => {
      navigate(`/?view=search&q=${encodeURIComponent(cardName)}`);
  };

  return (
    <div style={{ animation: 'slideUp 0.4s ease' }}>
        <div className="search-hero" style={{ paddingTop: '0', marginBottom: '20px' }}>
            <h2>Markt-Trends.</h2>
            <p>Die aktuell gefragtesten Karten im Format und umfassende Handelsanalysen.</p>
        </div>

        {/* TOP TRENDING CARDS BLOCK */}
        <div className="content-card" style={{ marginBottom: '30px', padding: '30px', borderRadius: '24px' }}>
            <h3 style={{ marginBottom: '20px', fontSize: '1.6rem', fontWeight: 600 }}>
                {isPersonalized ? "Deine personalisierten Trends" : "Top Staples der Woche (Newest Set Fallback)"}
            </h3>
            {loadingTrends ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '50px' }}>
                <div className="spinner"></div>
              </div>
            ) : (
                <div className="trending-grid">
                    {(trendingCards || []).map(c => (
                        <div key={c?.id || Math.random()} className="trending-item" onClick={() => clickTrendingCard(c?.name)} style={{ position: 'relative' }}>
                            <img 
                              src={c?.image_uris?.normal || getFallbackCardImage(c?.name, "Staple")} 
                              alt={c?.name || "Karte"} 
                              loading="lazy"
                              onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(c?.name, "Staple"); }}
                            />
                            {c?.album_name && (
                              <div style={{
                                position: 'absolute',
                                top: '10px',
                                left: '10px',
                                background: 'rgba(0,0,0,0.7)',
                                color: 'white',
                                padding: '4px 10px',
                                borderRadius: '12px',
                                fontSize: '0.75rem',
                                fontWeight: 600,
                                backdropFilter: 'blur(4px)'
                              }}>
                                Album: {c.album_name}
                              </div>
                            )}
                            <div className="trending-overlay">
                                <Search size={20} style={{ marginBottom: '6px' }} />
                                <span>In Suche öffnen</span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>

        {/* BENTO GRID OF ADDITIONAL MARKET WIDGETS */}
        <div className="bento-grid" style={{ marginTop: '0' }}>
            {/* WIDGET 1: Market Winners & Losers (Wide) */}
            <div className="bento-item bento-col-2">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
                  <Activity size={20} style={{ color: 'var(--accent-color)' }} />
                  <h3 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 600 }}>Marktbewegungen (Gewinner & Verlierer)</h3>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {winnersLosers.map((w, idx) => (
                    <div 
                      key={idx} 
                      onClick={() => clickTrendingCard(w.name)}
                      style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between', 
                        alignItems: 'center', 
                        cursor: 'pointer',
                        padding: '10px 14px', 
                        borderRadius: '12px',
                        background: 'var(--btn-secondary)',
                        border: '1px solid var(--border-color)',
                        transition: 'transform 0.2s',
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.transform = 'translateX(4px)'}
                      onMouseLeave={(e) => e.currentTarget.style.transform = 'translateX(0)'}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span style={{ fontSize: '0.75rem', fontWeight: 'bold', color: 'var(--text-muted)', background: 'var(--border-color)', padding: '2px 6px', borderRadius: '4px' }}>
                          {w.set}
                        </span>
                        <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>{w.name}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                        <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>{w.price}</span>
                        <span style={{ 
                          color: w.up ? 'var(--price-color)' : 'var(--danger-color)',
                          background: w.up ? 'rgba(48, 209, 88, 0.1)' : 'rgba(255, 59, 48, 0.1)',
                          padding: '4px 10px',
                          borderRadius: '8px',
                          fontWeight: 600,
                          fontSize: '0.85rem',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}>
                          {w.up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                          {w.change}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* WIDGET 2: Market Activity Stats */}
            <div className="bento-item">
              <div>
                <h3 style={{ fontSize: '1.3rem', marginBottom: '25px', fontWeight: 600 }}>Live-Handelsaktivität</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>Globale Deals</span>
                    <span style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>12.480 / Tag</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>Aktivste Edition</span>
                    <span style={{ fontSize: '1.1rem', fontWeight: 'bold', color: 'var(--accent-color)' }}>MH3 (Modern Horizons)</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>Ø-Kartenpreis</span>
                    <span style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>4,92 €</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>Markttendenz</span>
                    <span style={{ 
                      fontSize: '0.9rem', 
                      fontWeight: 600, 
                      color: 'var(--price-color)',
                      background: 'rgba(48, 209, 88, 0.1)',
                      padding: '4px 10px',
                      borderRadius: '8px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px'
                    }}>
                      <TrendingUp size={14} /> Bullisch ↗
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* WIDGET 3: Insider Collector Tip */}
            {insiderTip && (
              <div className="bento-item" style={{ border: '1px solid #C4923E', background: 'linear-gradient(180deg, var(--bg-card) 0%, rgba(196, 146, 62, 0.04) 100%)' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '15px' }}>
                    <Award size={20} style={{ color: '#C4923E' }} />
                    <span style={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#C4923E', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Insider-Tipp
                    </span>
                  </div>
                  <h4 style={{ fontSize: '1.15rem', margin: '0 0 8px 0', fontWeight: 600 }}>{insiderTip.title}</h4>
                  <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: '1.6', margin: '0 0 15px 0' }}>
                    {insiderTip.desc}
                  </p>
                </div>
                <button 
                  onClick={() => clickTrendingCard(insiderTip.card)}
                  className="primary-btn" 
                  style={{ 
                    background: 'linear-gradient(135deg, #C4923E 0%, #9E7127 100%)', 
                    border: 'none',
                    borderRadius: '12px',
                    padding: '10px',
                    fontSize: '0.9rem',
                    fontWeight: 600,
                    width: '100%',
                    color: 'white',
                    cursor: 'pointer'
                  }}
                >
                  {insiderTip.card} analysieren
                </button>
              </div>
            )}

            {/* WIDGET 4: Top Traded Sets */}
            <div className="bento-item bento-col-2">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '25px' }}>
                  <Flame size={20} style={{ color: '#FF9500' }} />
                  <h3 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 600 }}>Set-Beliebtheit im Handel (Volumen)</h3>
                </div>
                
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem', marginBottom: '6px', fontWeight: 500 }}>
                      <span>Modern Horizons 3 (MH3)</span>
                      <span>38% Anteil</span>
                    </div>
                    <div style={{ width: '100%', height: '8px', background: 'var(--btn-secondary)', borderRadius: '4px', overflow: 'hidden' }}>
                      <div style={{ width: '38%', height: '100%', background: 'var(--accent-color)', borderRadius: '4px' }}></div>
                    </div>
                  </div>

                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem', marginBottom: '6px', fontWeight: 500 }}>
                      <span>The Lord of the Rings (LTR)</span>
                      <span>22% Anteil</span>
                    </div>
                    <div style={{ width: '100%', height: '8px', background: 'var(--btn-secondary)', borderRadius: '4px', overflow: 'hidden' }}>
                      <div style={{ width: '22%', height: '100%', background: '#30D158', borderRadius: '4px' }}></div>
                    </div>
                  </div>

                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem', marginBottom: '6px', fontWeight: 500 }}>
                      <span>Outlaws of Thunder Junction (OTJ)</span>
                      <span>15% Anteil</span>
                    </div>
                    <div style={{ width: '100%', height: '8px', background: 'var(--btn-secondary)', borderRadius: '4px', overflow: 'hidden' }}>
                      <div style={{ width: '15%', height: '100%', background: '#FF9500', borderRadius: '4px' }}></div>
                    </div>
                  </div>

                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem', marginBottom: '6px', fontWeight: 500 }}>
                      <span>Bloomburrow (BLB)</span>
                      <span>12% Anteil</span>
                    </div>
                    <div style={{ width: '100%', height: '8px', background: 'var(--btn-secondary)', borderRadius: '4px', overflow: 'hidden' }}>
                      <div style={{ width: '12%', height: '100%', background: '#AF52DE', borderRadius: '4px' }}></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
        </div>
    </div>
  );
}

export default MarktTrends;
