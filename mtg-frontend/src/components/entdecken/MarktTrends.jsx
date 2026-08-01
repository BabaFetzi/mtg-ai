import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';
import { Search } from 'lucide-react';

function MarktTrends({ currentUser }) {
  const navigate = useNavigate();
  const [trendingCards, setTrendingCards] = useState([]);
  const [loadingTrends, setLoadingTrends] = useState(false);

  useEffect(() => {
    const loadTrends = async () => {
      setLoadingTrends(true);
      try {
          const res = await fetch(`/api/trends`);
          const data = await res.json();
          if (data && data.erfolg && Array.isArray(data.data)) {
              setTrendingCards(data.data);
          }
      } catch (e) {
          console.error("Error loading trends:", e);
      }
      setLoadingTrends(false);
    };
    loadTrends();
  }, []);

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
                Gefragte Karten des neuesten Sets
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
                            <div className="trending-overlay">
                                <Search size={20} style={{ marginBottom: '6px' }} />
                                <span>In Suche öffnen</span>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <p style={{ color: 'var(--text-muted)', margin: 0 }}>
                    Aktuell sind keine Trend-Daten verfügbar. Bitte versuche es später erneut.
                </p>
            )}
        </div>
    </div>
  );
}

export default MarktTrends;
