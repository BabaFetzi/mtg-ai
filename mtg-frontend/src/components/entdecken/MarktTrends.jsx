import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';
import { Search } from 'lucide-react';

function MarktTrends({ currentUser }) {
  const navigate = useNavigate();
  const [trendingCards, setTrendingCards] = useState([]);
  const [loadingTrends, setLoadingTrends] = useState(false);
  const [isPersonalized, setIsPersonalized] = useState(false);

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
  }, [currentUser]);

  const clickTrendingCard = (cardName) => {
      navigate(`/?view=search&q=${encodeURIComponent(cardName)}`);
  };

  return (
    <div style={{ animation: 'slideUp 0.4s ease' }}>
        <div className="search-hero" style={{ paddingTop: '0', marginBottom: '20px' }}>
            <h2>Markt-Trends.</h2>
            <p>Die aktuell gefragtesten Karten – live von Scryfall.</p>
        </div>

        {/* TOP TRENDING CARDS BLOCK (echte Daten aus /api/trends) */}
        <div className="content-card" style={{ marginBottom: '30px', padding: '30px', borderRadius: '24px' }}>
            <h3 style={{ marginBottom: '20px', fontSize: '1.6rem', fontWeight: 600 }}>
                {isPersonalized ? "Deine personalisierten Trends" : "Top Staples der Woche (Newest Set Fallback)"}
            </h3>
            {loadingTrends ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '50px' }}>
                <div className="spinner"></div>
              </div>
            ) : (trendingCards && trendingCards.length > 0) ? (
                <div className="trending-grid">
                    {trendingCards.map(c => (
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
            ) : (
                <p style={{ color: 'var(--text-muted)', margin: 0 }}>
                    Aktuell sind keine Trend-Daten verfügbar. Lege Karten in deiner Sammlung an, um personalisierte Trends zu sehen.
                </p>
            )}
        </div>
    </div>
  );
}

export default MarktTrends;
