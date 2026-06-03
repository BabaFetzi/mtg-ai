import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';

function MarktTrends() {
  const navigate = useNavigate();
  const [trendingCards, setTrendingCards] = useState([]);
  const [loadingTrends, setLoadingTrends] = useState(false);

  useEffect(() => {
    const loadTrends = async () => {
      setLoadingTrends(true);
      const identifiers = [
          {name: "The One Ring"}, {name: "Sheoldred, the Apocalypse"},
          {name: "Dockside Extortionist"}, {name: "Rhystic Study"},
          {name: "Smothering Tithe"}, {name: "Cyclonic Rift"},
          {name: "Mana Crypt"}, {name: "Fierce Guardianship"}
      ];
      try {
          const res = await fetch("https://api.scryfall.com/cards/collection", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ identifiers })
          });
          const data = await res.json();
          if(data && Array.isArray(data.data)) setTrendingCards(data.data);
      } catch (e) {}
      setLoadingTrends(false);
    };
    loadTrends();
  }, []);

  const clickTrendingCard = (cardName) => {
      navigate(`/?view=search&q=${encodeURIComponent(cardName)}`);
  }

  return (
    <div>
        <div className="search-hero" style={{paddingTop: '0'}}>
            <h2>Markt-Trends.</h2>
            <p>Die aktuell gefragtesten Karten im Format.</p>
        </div>
        <div className="content-card">
            <h3 style={{marginBottom: '20px', fontSize: '1.8rem'}}>Top Staples der Woche</h3>
            {loadingTrends ? <div className="spinner"></div> : (
                <div className="trending-grid">
                    {(trendingCards || []).map(c => (
                        <div key={c?.id || Math.random()} className="trending-item" onClick={() => clickTrendingCard(c?.name)}>
                            <img 
                              src={c?.image_uris?.normal || getFallbackCardImage(c?.name, "Staple")} 
                              alt={c?.name || "Karte"} 
                              loading="lazy"
                              onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(c?.name, "Staple"); }}
                            />
                            <div className="trending-overlay">
                                <span>In Suche öffnen</span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    </div>
  );
}

export default MarktTrends;
