import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Icons from '../../utils/Icons';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';
import CollectionFilters from './CollectionFilters';
import CollectionGrid from './CollectionGrid';
import CSVImportExport from './CSVImportExport';

function MeineSammlung({ currentUser, userRole, setUserRole }) {
  const location = useLocation();
  const navigate = useNavigate();
  const currentTab = new URLSearchParams(location.search).get('tab') || 'alben';

  const [alben, setAlben] = useState({});
  const [newAlbumName, setNewAlbumName] = useState("");
  const [updatingPrices, setUpdatingPrices] = useState(false);
  
  const [wishlistSearch, setWishlistSearch] = useState("");
  const [isWishlistAdding, setIsWishlistAdding] = useState(false);

  const [filteredKarten, setFilteredKarten] = useState([]);
  const [loadingFilters, setLoadingFilters] = useState(false);
  const [activeFilters, setActiveFilters] = useState({});
  const [selectedAlbum, setSelectedAlbum] = useState(null);

  const ladeSammlung = async () => {
    try {
      const res = await fetch(`/api/sammlung/${currentUser}`);
      if (res.ok) {
        const data = await res.json();
        if(data && data.erfolg && data.alben) {
          const cleanedAlben = {};
          for (const [albumName, karten] of Object.entries(data.alben)) {
              if(Array.isArray(karten)) {
                  cleanedAlben[albumName] = karten.filter(k => k && k.name !== "__PLACEHOLDER__").map(k => ({
                      ...k,
                      livePreis: k.livePreis || k.preis || "0.00"
                  }));
              }
          }
          setAlben(cleanedAlben);
        }
      }
    } catch {}
  }

  const ladeGefilterteSammlung = async (filters, albumFilter = selectedAlbum) => {
    setLoadingFilters(true);
    try {
      const queryParams = new URLSearchParams();
      if (filters.farbe) queryParams.append("farbe", filters.farbe);
      if (filters.seltenheit) queryParams.append("seltenheit", filters.seltenheit);
      if (filters.edition) queryParams.append("edition", filters.edition);
      if (filters.manakosten_min !== undefined) queryParams.append("manakosten_min", filters.manakosten_min);
      if (filters.manakosten_max !== undefined) queryParams.append("manakosten_max", filters.manakosten_max);
      if (filters.typ) queryParams.append("typ", filters.typ);
      if (filters.suche) queryParams.append("suche", filters.suche);
      if (albumFilter) queryParams.append("album", albumFilter);

      const res = await fetch(`/api/sammlung/${currentUser}/filter?${queryParams.toString()}`);
      if (res.ok) {
        const data = await res.json();
        if (data && data.erfolg) {
          setFilteredKarten(data.karten || []);
        }
      }
    } catch (e) {
      console.error("Error loading filtered collection:", e);
    }
    setLoadingFilters(false);
  };

  const erstelleLeeresAlbum = async () => {
    if(!newAlbumName.trim()) return;
    const albumName = newAlbumName.trim();
    try {
      await fetch(`/api/sammlung/hinzufuegen`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ benutzername: currentUser, karten_name: "__PLACEHOLDER__", album_name: albumName, bild_url: "", preis: "0.00" }) });
      setNewAlbumName("");
      setSelectedAlbum(albumName);
      ladeSammlung();
      ladeGefilterteSammlung(activeFilters, albumName);
    } catch {}
  }

  const loescheKarte = async (karten_id) => {
    await fetch(`/api/sammlung/loeschen`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ karten_id }) });
    ladeSammlung();
    ladeGefilterteSammlung(activeFilters, selectedAlbum);
  }

  const deleteAlbum = async (albumName) => {
    try {
      await fetch(`/api/sammlung/album_loeschen`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ benutzername: currentUser, album_name: albumName })
      });
      if (selectedAlbum === albumName) {
        setSelectedAlbum(null);
      }
      ladeSammlung();
      ladeGefilterteSammlung(activeFilters, selectedAlbum === albumName ? null : selectedAlbum);
    } catch {}
  };

  useEffect(() => {
    ladeSammlung();
  }, []);

  useEffect(() => {
    ladeGefilterteSammlung(activeFilters, selectedAlbum);
  }, [selectedAlbum]);

  const wishlistKarten = Array.isArray(alben["Wunschliste"]) ? alben["Wunschliste"] : [];
  const portfolioAlben = { ...alben };
  delete portfolioAlben["Wunschliste"];

  const getPriceVal = (k) => {
      if(!k) return 0;
      return parseFloat(String(k.livePreis || k.preis || "0").replace(',', '.')) || 0;
  }
  
  const berechneAlbumWert = (karten) => {
      if(!karten || !Array.isArray(karten)) return "0.00";
      return karten.reduce((summe, karte) => summe + getPriceVal(karte), 0).toFixed(2);
  }
  
  const totalPortfolioWert = Object.values(portfolioAlben).reduce((acc, karten) => {
      if(!Array.isArray(karten)) return acc;
      return acc + parseFloat(berechneAlbumWert(karten))
  }, 0).toFixed(2);
  
  const totalWishlistWert = berechneAlbumWert(wishlistKarten);

  const getAllCardsFlat = () => {
    const all = [];
    Object.entries(portfolioAlben).forEach(([albumName, karten]) => {
      if(Array.isArray(karten)) {
          karten.forEach(k => { if(k) all.push({...k, albumName}) });
      }
    });
    return all;
  };

  const sortiereKarten = (karten, methode) => {
    if(!karten || !Array.isArray(karten)) return [];
    const arr = [...karten].filter(k => k != null);
    if(methode === "priceDesc") return arr.sort((a,b) => getPriceVal(b) - getPriceVal(a));
    if(methode === "priceAsc") return arr.sort((a,b) => getPriceVal(a) - getPriceVal(b));
    if(methode === "az") return arr.sort((a,b) => (a?.name || "").localeCompare(b?.name || ""));
    return arr; 
  };

  const addToWishlist = async () => {
    if(!wishlistSearch) return;
    setIsWishlistAdding(true);
    try {
        const res = await fetch(`/api/suche/${wishlistSearch}?benutzername=${currentUser}`);
        const data = await res.json();
        if(data && data.error) {
            alert("Karte nicht gefunden. Bitte Namen prüfen.");
        } else if (data && Array.isArray(data.prints) && data.prints.length > 0) {
            const actP = data.prints[0];
            await fetch(`/api/sammlung/hinzufuegen`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ benutzername: currentUser, karten_name: data.name, album_name: "Wunschliste", bild_url: actP?.bild_url || "", preis: actP?.preis && actP.preis !== "N/A" ? String(actP.preis) : "0.00" })
            });
            setWishlistSearch("");
            ladeSammlung();
        } else {
            alert("Fehler: API hat keine Druck-Versionen für diese Karte geliefert.");
        }
    } catch(e) { alert("Verbindungsfehler."); }
    setIsWishlistAdding(false);
  }

  const handleFilterChange = (filters) => {
    setActiveFilters(filters);
    ladeGefilterteSammlung(filters, selectedAlbum);
  };

  return (
    <div className="apple-main-container">
      <h2>Portfolio & Alben.</h2>
      <p style={{marginBottom: '40px', fontSize: '1.2rem'}}>Verwalte deine Sammlung, Werte und Einkaufslisten.</p>

      <div className="segmented-control">
        <button className={`segment-btn ${currentTab === 'alben' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=alben')}>Alben & Verwaltung</button>
        <button className={`segment-btn ${currentTab === 'dashboard' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=dashboard')}>Finanz-Dashboard</button>
        <button className={`segment-btn ${currentTab === 'wishlist' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=wishlist')}>Wunschliste</button>
        <button className={`segment-btn ${currentTab === 'import' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=import')}>Massen-Import</button>
        <button className={`segment-btn ${currentTab === 'export' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=export')}>Export</button>
      </div>
      
      {currentTab === 'alben' && (
        <>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '35px',
            gap: '20px',
            flexWrap: 'wrap'
          }}>
            <div style={{display: 'flex', gap: '15px', maxWidth: '500px', background: 'var(--bg-card)', padding: '15px 25px', borderRadius: '16px', border: '1px solid var(--border-color)', boxShadow: '0 4px 15px var(--shadow-color)', flexGrow: 1}}>
              <input placeholder="Neues Albumname..." value={newAlbumName} onChange={e => setNewAlbumName(e.target.value)} style={{background: 'var(--input-bg)', border: 'none', padding: '10px 14px'}} />
              <button className="primary-btn" onClick={erstelleLeeresAlbum} style={{padding: '10px 20px'}}>Erstellen</button>
            </div>
            
            <div style={{background: 'var(--bg-card)', padding: '15px 25px', borderRadius: '16px', border: '1px solid var(--border-color)', boxShadow: '0 4px 15px var(--shadow-color)', textAlign: 'right'}}>
              <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginRight: '15px', letterSpacing: '0.05em'}}>Gesamtwert</span>
              <span style={{color: 'var(--price-color)', fontWeight: 600, fontSize: '1.6rem'}}>{totalPortfolioWert} €</span>
            </div>
          </div>

          {/* Album-Selector */}
          <div style={{
            display: 'flex',
            gap: '12px',
            marginBottom: '30px',
            flexWrap: 'wrap',
            alignItems: 'center',
            background: 'var(--bg-card)',
            padding: '15px 25px',
            borderRadius: '16px',
            border: '1px solid var(--border-color)',
            boxShadow: '0 4px 15px var(--shadow-color)'
          }}>
            <span style={{ fontSize: '0.95rem', color: 'var(--text-muted)', fontWeight: 600 }}>Album:</span>
            <button 
              type="button"
              className={`segment-btn ${selectedAlbum === null ? 'active' : ''}`}
              onClick={() => setSelectedAlbum(null)}
              style={{
                borderRadius: '20px',
                padding: '8px 18px',
                fontSize: '0.88rem',
                border: '1px solid var(--border-color)',
                background: selectedAlbum === null ? 'var(--accent-color)' : 'transparent',
                color: selectedAlbum === null ? 'white' : 'var(--text-main)',
                cursor: 'pointer',
                transition: 'all 0.2s',
                fontWeight: 500
              }}
            >
              Alle Alben
            </button>
            {Object.keys(portfolioAlben).map(name => (
              <button 
                key={name}
                type="button"
                className={`segment-btn ${selectedAlbum === name ? 'active' : ''}`}
                onClick={() => setSelectedAlbum(name)}
                style={{
                  borderRadius: '20px',
                  padding: '8px 18px',
                  fontSize: '0.88rem',
                  border: '1px solid var(--border-color)',
                  background: selectedAlbum === name ? 'var(--accent-color)' : 'transparent',
                  color: selectedAlbum === name ? 'white' : 'var(--text-main)',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  fontWeight: 500
                }}
              >
                {name}
                <span
                  onClick={(e) => {
                    e.stopPropagation();
                    if(confirm(`Möchtest du das Album "${name}" und alle darin enthaltenen Karten wirklich löschen?`)) {
                      deleteAlbum(name);
                    }
                  }}
                  style={{
                    background: selectedAlbum === name ? 'rgba(255,255,255,0.2)' : 'rgba(255,59,48,0.1)',
                    color: selectedAlbum === name ? 'white' : 'var(--danger-color)',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 'bold',
                    transition: 'all 0.2s'
                  }}
                  title="Album löschen"
                >
                  ✕
                </span>
              </button>
            ))}
          </div>

          {/* Collection Filters Panel */}
          <CollectionFilters currentUser={currentUser} onFilterChange={handleFilterChange} />

          {/* Collection Grid / List Display */}
          <div className="content-card" style={{ padding: '30px' }}>
            {loadingFilters ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <div className="spinner"></div>
                <p style={{ marginTop: '15px', color: 'var(--text-muted)' }}>Sammlung wird gefiltert...</p>
              </div>
            ) : (
              <CollectionGrid
                karten={filteredKarten}
                updatingPrices={updatingPrices}
                loescheKarte={loescheKarte}
              />
            )}
          </div>
        </>
      )}

      {currentTab === 'dashboard' && (
        <div className="dashboard-grid">
           <div>
              <div className="content-card" style={{padding: '40px'}}>
                <h3 style={{fontSize: '1.2rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '10px'}}>Gesamter Marktwert (Ohne Wunschliste)</h3>
                <h1 style={{fontSize: '4.5rem', margin: '0 0 30px 0', color: 'var(--text-main)', letterSpacing: '-0.04em'}}>{totalPortfolioWert} €</h1>
                
                <h4 style={{marginBottom: '15px', color: 'var(--text-muted)'}}>Wertverteilung nach Alben</h4>
                {Object.entries(portfolioAlben).map(([name, karten]) => {
                   const val = parseFloat(berechneAlbumWert(karten));
                   if(val === 0) return null;
                   const total = parseFloat(totalPortfolioWert) || 1; 
                   const pct = Math.round((val / total) * 100) || 0;
                   return (
                     <div key={name} style={{marginBottom: '15px'}}>
                        <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '5px', fontSize: '0.95rem'}}>
                          <span style={{fontWeight: 600}}>{name}</span>
                          <span>{val.toFixed(2)} € ({pct}%)</span>
                        </div>
                        <div style={{width: '100%', height: '8px', background: 'var(--btn-secondary)', borderRadius: '4px', overflow: 'hidden'}}>
                          <div style={{width: `${pct}%`, height: '100%', background: 'var(--accent-color)'}}></div>
                        </div>
                     </div>
                   )
                })}
              </div>
           </div>

           <div>
              <div className="content-card" style={{padding: '30px'}}>
                <h3 style={{marginBottom: '20px', fontSize: '1.5rem'}}>Top 10 Wertvollste Karten</h3>
                <div style={{display: 'flex', flexDirection: 'column'}}>
                  {getAllCardsFlat()
                    .sort((a,b) => getPriceVal(b) - getPriceVal(a))
                    .slice(0, 10)
                    .map((k, i) => (
                    <div key={i} className="top-card-item">
                      <span style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--text-muted)', width: '30px' }}>#{i+1}</span>
                      <img 
                        src={k?.bild_url || getFallbackCardImage(k?.name, "Portfolio")} 
                        alt={k?.name || "Unbekannt"} 
                        className="top-card-img" 
                        loading="lazy"
                        onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(k?.name, "Portfolio"); }}
                      />
                      <div style={{ flexGrow: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: '1.05rem', color: 'var(--text-main)' }}>{k?.name}</div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>In: {k?.albumName}</div>
                      </div>
                      <div style={{ fontWeight: 600, fontSize: '1.1rem', color: 'var(--price-color)' }}>{k?.livePreis || k?.preis || "0.00"} €</div>
                    </div>
                  ))}
                  {getAllCardsFlat().length === 0 && <p>Keine Karten im Portfolio.</p>}
                </div>
              </div>
           </div>
        </div>
      )}

      {currentTab === 'wishlist' && (
        <div className="content-card" style={{padding: '40px'}}>
           <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '20px', marginBottom: '30px', flexWrap: 'wrap', gap: '20px'}}>
              <div>
                 <h3 style={{margin: 0, fontSize: '2rem'}}>Meine Wunschliste</h3>
                 <p style={{margin: '5px 0 0 0'}}>Diese Karten sind von deinem Finanz-Dashboard ausgeschlossen.</p>
              </div>
              <div style={{textAlign: 'right'}}>
                 <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginRight: '15px', letterSpacing: '0.05em'}}>Benötigtes Budget</span>
                 <span style={{color: 'var(--accent-color)', fontWeight: 600, fontSize: '1.6rem'}}>{totalWishlistWert} €</span>
              </div>
           </div>

           <div style={{display: 'flex', gap: '15px', maxWidth: '600px', marginBottom: '40px', background: 'var(--bg-main)', padding: '15px', borderRadius: '16px'}}>
              <input 
                 placeholder="Kartenname eingeben (z.B. The One Ring)..." 
                 value={wishlistSearch} 
                 onChange={e => setWishlistSearch(e.target.value)} 
                 onKeyDown={(e) => e.key === 'Enter' && addToWishlist()}
                 style={{background: 'var(--input-bg)', border: '1px solid var(--border-color)'}} 
              />
              <button className="primary-btn" onClick={addToWishlist}>{isWishlistAdding ? "Sucht..." : "Hinzufügen"}</button>
           </div>

           {wishlistKarten.length === 0 ? (
             <p style={{color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '40px 0'}}>Deine Wunschliste ist leer.</p>
           ) : (
             <div className="gallery-grid" style={{marginTop: 0}}>
               {sortiereKarten(wishlistKarten, "priceDesc").map((karte, idx) => {
                 if(!karte) return null;
                 return (
                 <div key={karte?.id || idx} className="gallery-item">
                   <button className="gallery-remove-btn" onClick={() => loescheKarte(karte.id)}>✕</button>
                    <img 
                      src={karte?.bild_url || getFallbackCardImage(karte?.name, "Karte")} 
                      alt={karte?.name || "Unbekannt"} 
                      className="gallery-img" 
                      loading="lazy"
                      onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(karte?.name, "Karte"); }}
                    />
                   <span style={{fontWeight: 600, fontSize: '0.95rem', display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginBottom: '5px'}} title={karte?.name}>{karte?.name}</span>
                   <span className="gallery-price-tag" style={{color: 'var(--text-main)', background: 'var(--bg-main)'}}>{karte?.livePreis || karte?.preis || "0.00"} €</span>
                 </div>
               )})}
             </div>
           )}
        </div>
      )}

      {(currentTab === 'import' || currentTab === 'export') && (
        <CSVImportExport currentUser={currentUser} ladeSammlung={ladeSammlung} />
      )}
    </div>
  );
}

export default MeineSammlung;
