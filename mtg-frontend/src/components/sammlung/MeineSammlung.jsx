import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Icons from '../../utils/Icons';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';
import { FolderPlus, FileSpreadsheet, Heart, RefreshCw, Plus } from 'lucide-react';
import CollectionFilters from './CollectionFilters';
import CollectionGrid from './CollectionGrid';
import CSVImportExport from './CSVImportExport';
import { formatEuro } from '../../utils/format';
import { useMeldung } from '../layout/Meldungen';

function MeineSammlung({ currentUser, userRole, setUserRole, onShowPremiumModal }) {
  const { melde, bestaetige } = useMeldung();
  const location = useLocation();
  const navigate = useNavigate();
  const currentTab = new URLSearchParams(location.search).get('tab') || 'alben';

  const [alben, setAlben] = useState({});
  const [newAlbumName, setNewAlbumName] = useState("");
  const [updatingPrices, setUpdatingPrices] = useState(false);
  
  const [wishlistSearch, setWishlistSearch] = useState("");
  const [isWishlistAdding, setIsWishlistAdding] = useState(false);

  // Karte direkt in den gerade geöffneten Ordner suchen & hinzufügen.
  const [albumCardSearch, setAlbumCardSearch] = useState("");
  const [isAlbumAdding, setIsAlbumAdding] = useState(false);

  const [filteredKarten, setFilteredKarten] = useState([]);
  const [loadingFilters, setLoadingFilters] = useState(false);
  const [activeFilters, setActiveFilters] = useState({});
  
  // Selected album: null means "Alle Alben" overview grid
  const [selectedAlbum, setSelectedAlbum] = useState(null);
  // Track which album context menu is open
  const [openMenuAlbum, setOpenMenuAlbum] = useState(null);
  // Track which album is selected for destruction modal
  const [albumToDelete, setAlbumToDelete] = useState(null);

  // Redirect legacy /export tab to consolidated /import (In- und Export)
  useEffect(() => {
    if (currentTab === 'export') {
      navigate('/sammlung?tab=import', { replace: true });
    }
  }, [currentTab, navigate]);

  // Click-away listener for context menus
  useEffect(() => {
    const closeMenus = () => setOpenMenuAlbum(null);
    window.addEventListener('click', closeMenus);
    return () => window.removeEventListener('click', closeMenus);
  }, []);

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
    } catch (e) {
      console.error(e);
    }
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

  const handleRefreshPrices = async () => {
    if (userRole !== 'premium') {
      if (onShowPremiumModal) onShowPremiumModal();
      else melde.fehler("Dieses Feature steht nur Premium-Mitgliedern zur Verfügung. Bitte upgrade deine Rolle!");
      return;
    }
    setUpdatingPrices(true);
    try {
      const res = await fetch(`/api/sammlung/${currentUser}/refresh-prices`, {
        method: "POST"
      });
      if (res.ok) {
        await ladeSammlung();
        await ladeGefilterteSammlung(activeFilters, selectedAlbum);
        melde.erfolg("Preise wurden erfolgreich aktualisiert!");
      } else {
        melde.fehler("Fehler beim Aktualisieren der Preise.");
      }
    } catch (e) {
      console.error("Error refreshing prices:", e);
      melde.fehler("Fehler beim Aktualisieren der Preise.");
    } finally {
      setUpdatingPrices(false);
    }
  };

  const erstelleLeeresAlbum = async () => {
    if(!newAlbumName.trim()) return;
    const albumName = newAlbumName.trim();
    try {
      await fetch(`/api/sammlung/hinzufuegen`, { 
        method: "POST", 
        headers: { "Content-Type": "application/json" }, 
        body: JSON.stringify({ benutzername: currentUser, karten_name: "__PLACEHOLDER__", album_name: albumName, bild_url: "", preis: "0.00" }) 
      });
      setNewAlbumName("");
      setSelectedAlbum(albumName);
      ladeSammlung();
      ladeGefilterteSammlung(activeFilters, albumName);
    } catch (e) {
      console.error(e);
    }
  }

  const loescheKarte = async (karten_id) => {
    await fetch(`/api/sammlung/loeschen`, { 
      method: "POST", 
      headers: { "Content-Type": "application/json" }, 
      body: JSON.stringify({ karten_id }) 
    });
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
    } catch (e) {
      console.error(e);
    }
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
        const res = await fetch(`/api/suche/${encodeURIComponent(wishlistSearch)}?benutzername=${currentUser}`);
        const data = await res.json();
        if(data && data.error) {
            melde.fehler("Karte nicht gefunden. Bitte Namen prüfen.");
        } else if (data && Array.isArray(data.prints) && data.prints.length > 0) {
            const actP = data.prints[0];
            // Bester Marktpreis als Fallback, falls der erste Print keinen echten Preis hat.
            const wunschPreis = (actP?.preis && actP.preis !== "N/A" && parseFloat(actP.preis) > 0)
              ? String(actP.preis)
              : (data.marktwert || "0.00");
            await fetch(`/api/sammlung/hinzufuegen`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ benutzername: currentUser, karten_name: data.name, album_name: "Wunschliste", bild_url: actP?.bild_url || "", preis: wunschPreis })
            });
            setWishlistSearch("");
            ladeSammlung();
        } else {
            melde.fehler("Fehler: API hat keine Druck-Versionen für diese Karte geliefert.");
        }
    } catch(e) { melde.fehler("Verbindungsfehler."); }
    setIsWishlistAdding(false);
  }

  const handleFilterChange = (filters) => {
    setActiveFilters(filters);
    ladeGefilterteSammlung(filters, selectedAlbum);
  };

  // Sucht eine Karte über Scryfall und legt sie im aktuell geöffneten Ordner ab.
  // Nutzt denselben erprobten Flow wie die Wunschliste, nur mit dem Zielalbum.
  const addCardToAlbum = async () => {
    if (!albumCardSearch.trim() || !selectedAlbum) return;
    setIsAlbumAdding(true);
    try {
      const res = await fetch(`/api/suche/${encodeURIComponent(albumCardSearch.trim())}?benutzername=${currentUser}`);
      const data = await res.json();
      if (data && data.error) {
        melde.fehler("Karte nicht gefunden. Bitte Namen prüfen.");
      } else if (data && Array.isArray(data.prints) && data.prints.length > 0) {
        const actP = data.prints[0];
        const preis = (actP?.preis && actP.preis !== "N/A" && parseFloat(actP.preis) > 0)
          ? String(actP.preis)
          : (data.marktwert || "0.00");
        await fetch(`/api/sammlung/hinzufuegen`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ benutzername: currentUser, karten_name: data.name, album_name: selectedAlbum, bild_url: actP?.bild_url || "", preis })
        });
        setAlbumCardSearch("");
        await ladeSammlung();
        await ladeGefilterteSammlung(activeFilters, selectedAlbum);
      } else {
        melde.fehler("Fehler: Es wurden keine Druck-Versionen für diese Karte geliefert.");
      }
    } catch (e) {
      melde.fehler("Verbindungsfehler.");
    }
    setIsAlbumAdding(false);
  };

  return (
    <div className="apple-main-container">
      <h2>Sammlung & Inventar.</h2>
      <p style={{marginBottom: '40px', fontSize: '1.2rem'}}>Verwalte deine Magic: The Gathering Ordner, Finanzen und Exporte.</p>

      <div className="segmented-control">
        <button className={`segment-btn ${currentTab === 'alben' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=alben')}>Ordner & Verwaltung</button>
        <button className={`segment-btn ${currentTab === 'dashboard' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=dashboard')}>Finanz-Dashboard</button>
        <button className={`segment-btn ${currentTab === 'wishlist' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=wishlist')}>Wunschliste</button>
        <button className={`segment-btn ${currentTab === 'import' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=import')}>In- und Export</button>
      </div>
      
      {currentTab === 'alben' && (
        <>
          {/* Overview Controls when selectedAlbum is null */}
          {selectedAlbum === null ? (
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
                  <input id="new-album-input" placeholder="Neuer Ordnername..." value={newAlbumName} onChange={e => setNewAlbumName(e.target.value)} onKeyDown={e => e.key === 'Enter' && erstelleLeeresAlbum()} style={{background: 'var(--input-bg)', border: 'none', padding: '10px 14px', flexGrow: 1, borderRadius: '8px', color: 'var(--text-main)'}} />
                  <button className="primary-btn" onClick={erstelleLeeresAlbum} style={{padding: '10px 20px'}}>Erstellen</button>
                </div>
                
                <div style={{display: 'flex', gap: '20px', alignItems: 'center', background: 'var(--bg-card)', padding: '15px 25px', borderRadius: '16px', border: '1px solid var(--border-color)', boxShadow: '0 4px 15px var(--shadow-color)', flexWrap: 'wrap'}}>
                  <div style={{textAlign: 'right'}}>
                    <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginRight: '15px', letterSpacing: '0.05em', display: 'block'}}>Zentraler Gesamtwert</span>
                    <span style={{color: 'var(--price-color)', fontWeight: 700, fontSize: '1.6rem'}}>{formatEuro(totalPortfolioWert)}</span>
                  </div>
                  <button 
                    className="secondary-btn" 
                    onClick={handleRefreshPrices} 
                    disabled={updatingPrices}
                    style={{
                      padding: '10px 15px', 
                      borderRadius: '10px', 
                      fontSize: '0.82rem', 
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      background: 'rgba(255, 255, 255, 0.03)',
                      color: 'var(--text-main)',
                      border: '1px solid var(--border-color)',
                      cursor: 'pointer'
                    }}
                  >
                    {updatingPrices ? <div className="spinner" style={{width: '12px', height: '12px', borderWidth: '2px', margin: 0}}></div> : <RefreshCw size={12} />}
                    Preise aktualisieren
                  </button>
                </div>
              </div>

              {/* Album Cards Grid */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', gap: '15px', flexWrap: 'wrap' }}>
                <h3 style={{ fontSize: '1.5rem', margin: 0, fontWeight: 600 }}>Meine Ordner</h3>
                {/* Direkter Einstieg zum Hinzufügen einzelner Karten -- führt zur
                    Kartensuche, die den funktionierenden "Sichern"-Flow bietet.
                    Vorher gab es in der Sammlungs-Ansicht keinen sichtbaren Weg,
                    eine einzelne Karte hinzuzufügen. */}
                <button
                  className="primary-btn"
                  onClick={() => navigate('/?view=search')}
                  style={{ padding: '10px 18px', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Plus size={16} /> Karte hinzufügen
                </button>
              </div>
              
              {Object.keys(portfolioAlben).length === 0 ? (
                <div className="bento-grid" style={{ marginTop: '20px', marginBottom: '40px' }}>
                  <div className="bento-item" style={{ minHeight: '220px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', textAlign: 'left' }}>
                    <div>
                      <h4 style={{ fontSize: '1.25rem', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <FolderPlus size={20} style={{ color: 'var(--text-muted)' }} /> Ordner erstellen
                      </h4>
                      <p style={{ fontSize: '0.9rem', margin: 0, color: 'var(--text-muted)' }}>Erstelle einen leeren Ordner, um deine physischen Karten zu katalogisieren.</p>
                    </div>
                    <button className="primary-btn" onClick={() => document.getElementById('new-album-input')?.focus()} style={{ marginTop: '15px' }}>
                      Ordner benennen
                    </button>
                  </div>

                  <div className="bento-item" style={{ minHeight: '220px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', textAlign: 'left' }}>
                    <div>
                      <h4 style={{ fontSize: '1.25rem', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <FileSpreadsheet size={20} style={{ color: 'var(--text-muted)' }} /> Sammlung importieren
                      </h4>
                      <p style={{ fontSize: '0.9rem', margin: 0, color: 'var(--text-muted)' }}>Importiere deine bestehende Sammlung direkt per CSV-Datei oder einfachem Text.</p>
                    </div>
                    <button className="secondary-btn" onClick={() => navigate('/sammlung?tab=import')} style={{ marginTop: '15px' }}>
                      Import-Center öffnen
                    </button>
                  </div>

                  <div className="bento-item" style={{ minHeight: '220px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', textAlign: 'left' }}>
                    <div>
                      <h4 style={{ fontSize: '1.25rem', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Heart size={20} style={{ color: 'var(--text-muted)' }} /> Wunschliste füllen
                      </h4>
                      <p style={{ fontSize: '0.9rem', margin: 0, color: 'var(--text-muted)' }}>Füge Karten hinzu, nach denen du suchst, um dein benötigtes Budget zu berechnen.</p>
                    </div>
                    <button className="secondary-btn" onClick={() => navigate('/sammlung?tab=wishlist')} style={{ marginTop: '15px' }}>
                      Zur Wunschliste
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                  gap: '25px',
                  marginBottom: '40px'
                }}>
                  {Object.entries(portfolioAlben).map(([name, karten]) => {
                    const cardCount = karten.length;
                    const albumWert = berechneAlbumWert(karten);
                    // Top-Karten nach Wert sortiert, statt nur der ersten Karte im
                    // Album -- gibt einen tatsächlich aussagekräftigen Eindruck vom
                    // Inhalt ("was ist hier wertvoll?") statt eines beliebigen Covers.
                    const topKarten = [...karten]
                      .filter(Boolean)
                      .sort((a, b) => getPriceVal(b) - getPriceVal(a))
                      .slice(0, 4);
                    const isMenuOpen = openMenuAlbum === name;
                    
                    return (
                      <div 
                        key={name}
                        onClick={() => setSelectedAlbum(name)}
                        className="album-card"
                        style={{
                          background: 'var(--bg-card)',
                          border: '1px solid var(--border-color)',
                          borderRadius: '24px',
                          padding: '20px',
                          boxShadow: '0 8px 30px var(--shadow-color)',
                          cursor: 'pointer',
                          transition: 'transform 0.2s, box-shadow 0.2s',
                          position: 'relative',
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'space-between',
                          minHeight: '260px',
                          overflow: 'visible'
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-4px)'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.transform = 'none'; }}
                      >
                        {/* Context menu toggle button */}
                        <div 
                          onClick={(e) => {
                            e.stopPropagation();
                            setOpenMenuAlbum(isMenuOpen ? null : name);
                          }}
                          style={{
                            position: 'absolute',
                            top: '15px',
                            right: '15px',
                            width: '32px',
                            height: '32px',
                            borderRadius: '50%',
                            background: 'rgba(0,0,0,0.5)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: 'var(--text-main)',
                            fontSize: '1.2rem',
                            fontWeight: 'bold',
                            cursor: 'pointer',
                            zIndex: 10
                          }}
                        >
                          ⋮
                        </div>
                        
                        {/* Popover list */}
                        {isMenuOpen && (
                          <div 
                            style={{
                              position: 'absolute',
                              top: '55px',
                              right: '15px',
                              background: 'var(--bg-card)',
                              border: '1px solid var(--border-color)',
                              borderRadius: '12px',
                              boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
                              width: '130px',
                              zIndex: 20,
                              overflow: 'hidden'
                            }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button 
                              onClick={() => { setSelectedAlbum(name); setOpenMenuAlbum(null); }}
                              style={{
                                width: '100%',
                                padding: '10px 15px',
                                background: 'none',
                                border: 'none',
                                color: 'var(--text-main)',
                                textAlign: 'left',
                                cursor: 'pointer',
                                fontSize: '0.88rem'
                              }}
                            >
                              Öffnen
                            </button>
                            <button 
                              onClick={() => {
                                setAlbumToDelete(name);
                                setOpenMenuAlbum(null);
                              }}
                              style={{
                                width: '100%',
                                padding: '10px 15px',
                                background: 'none',
                                border: 'none',
                                color: '#ff453a',
                                textAlign: 'left',
                                cursor: 'pointer',
                                fontSize: '0.88rem',
                                borderTop: '1px solid var(--border-color)'
                              }}
                            >
                              Löschen
                            </button>
                          </div>
                        )}

                        {/* Gestapelte Mini-Vorschau der wertvollsten Karten im Album,
                            statt eines einzelnen, beliebig zugeschnittenen Coverbilds --
                            zeigt auf einen Blick, was in diesem Ordner steckt. */}
                        <div style={{
                          width: '100%',
                          height: '140px',
                          borderRadius: '14px',
                          marginBottom: '15px',
                          position: 'relative',
                          background: 'var(--btn-secondary)',
                          overflow: 'visible'
                        }}>
                          {topKarten.length === 0 ? (
                            <div style={{
                              position: 'absolute', inset: 0, borderRadius: '14px', overflow: 'hidden',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              color: 'var(--text-muted)', fontSize: '0.8rem', fontWeight: 600
                            }}>
                              Leer
                            </div>
                          ) : (
                            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                              {topKarten.map((k, i) => {
                                // Wertvollste Karte (i=0) mittig und obenauf; die restlichen
                                // fächern sich abwechselnd nach rechts/links auf, mit
                                // sinkendem z-index -- wie eine aufgefaecherte Kartenhand.
                                const magnitude = Math.ceil(i / 2);
                                const sign = i === 0 ? 0 : (i % 2 === 1 ? 1 : -1);
                                const offset = sign * magnitude;
                                return (
                                  <img
                                    key={k.id || i}
                                    src={k.bild_url || getFallbackCardImage(k.name, "Karte")}
                                    alt={k.name}
                                    title={k.name}
                                    style={{
                                      position: 'absolute',
                                      // Explizite Höhe (Kartenseitenverhältnis ~0.72), sonst
                                      // kollabiert das Bild auf 0px Höhe, solange es noch lädt --
                                      // das Kartenformat ist von vornherein bekannt, muss also
                                      // nicht erst vom geladenen Bild abgeleitet werden.
                                      width: '64px',
                                      height: '89px',
                                      objectFit: 'cover',
                                      background: 'var(--bg-card)',
                                      borderRadius: '6px',
                                      boxShadow: '0 8px 18px rgba(0,0,0,0.35)',
                                      border: '2px solid var(--bg-card)',
                                      transform: `translateX(${offset * 32}px) translateY(${magnitude * 5}px) rotate(${offset * 7}deg)`,
                                      zIndex: topKarten.length - i
                                    }}
                                    onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(k.name, "Karte"); }}
                                  />
                                );
                              })}
                            </div>
                          )}
                          <div style={{
                            position: 'absolute',
                            bottom: '10px',
                            left: '10px',
                            background: 'rgba(0,0,0,0.7)',
                            padding: '4px 10px',
                            borderRadius: '8px',
                            fontSize: '0.8rem',
                            color: 'white',
                            fontWeight: 600,
                            zIndex: topKarten.length + 1
                          }}>
                            {cardCount} {cardCount === 1 ? 'Karte' : 'Karten'}
                          </div>
                        </div>

                        {/* Card text */}
                        <div style={{ textAlign: 'left' }}>
                          <h4 style={{ margin: '0 0 5px 0', fontSize: '1.15rem', color: 'var(--text-main)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</h4>
                          <span style={{ fontSize: '1.25rem', color: 'var(--price-color)', fontWeight: 600 }}>{formatEuro(albumWert)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          ) : (
            /* Selected album detail view */
            <>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '15px',
                marginBottom: '30px',
                flexWrap: 'wrap'
              }}>
                <button 
                  onClick={() => setSelectedAlbum(null)}
                  className="secondary-btn"
                  style={{
                    borderRadius: '20px',
                    padding: '8px 18px',
                    fontSize: '0.88rem',
                    border: '1px solid var(--border-color)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    fontWeight: 500,
                    width: 'auto'
                  }}
                >
                  ← Alle Ordner
                </button>
                <h3 style={{ margin: 0, fontSize: '1.8rem' }}>Ordner: {selectedAlbum}</h3>
                
                {/* Options button for active album */}
                <div style={{ position: 'relative' }}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setOpenMenuAlbum(openMenuAlbum === selectedAlbum ? null : selectedAlbum);
                    }}
                    style={{
                      background: 'var(--btn-secondary)',
                      border: 'none',
                      borderRadius: '50%',
                      width: '36px',
                      height: '36px',
                      cursor: 'pointer',
                      color: 'var(--text-main)',
                      fontSize: '1.1rem',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}
                  >
                    ⋮
                  </button>
                  {openMenuAlbum === selectedAlbum && (
                    <div 
                      style={{
                        position: 'absolute',
                        top: '42px',
                        left: 0,
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border-color)',
                        borderRadius: '12px',
                        boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
                        width: '130px',
                        zIndex: 20,
                        overflow: 'hidden'
                      }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button 
                        onClick={() => {
                          setAlbumToDelete(selectedAlbum);
                          setOpenMenuAlbum(null);
                        }}
                        style={{
                          width: '100%',
                          padding: '10px 15px',
                          background: 'none',
                          border: 'none',
                          color: '#ff453a',
                          textAlign: 'left',
                          cursor: 'pointer',
                          fontSize: '0.88rem'
                        }}
                      >
                        Ordner löschen
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Karte direkt in diesen Ordner hinzufügen */}
              <div style={{
                display: 'flex', gap: '12px', maxWidth: '600px', marginBottom: '25px',
                background: 'var(--bg-card)', padding: '15px 20px', borderRadius: '16px',
                border: '1px solid var(--border-color)', boxShadow: '0 4px 15px var(--shadow-color)',
                flexWrap: 'wrap'
              }}>
                <input
                  placeholder="Karte suchen und in diesen Ordner legen (z.B. Sol Ring)..."
                  value={albumCardSearch}
                  onChange={e => setAlbumCardSearch(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addCardToAlbum()}
                  style={{ background: 'var(--input-bg)', border: '1px solid var(--border-color)', padding: '10px 14px', flexGrow: 1, minWidth: '220px', borderRadius: '8px', color: 'var(--text-main)' }}
                />
                <button className="primary-btn" onClick={addCardToAlbum} disabled={isAlbumAdding} style={{ padding: '10px 20px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {isAlbumAdding ? <div className="spinner" style={{ width: '12px', height: '12px', borderWidth: '2px', margin: 0 }}></div> : <Plus size={16} />}
                  {isAlbumAdding ? "Fügt hinzu..." : "Hinzufügen"}
                </button>
              </div>

              {/* Collection Filters Panel */}
              <CollectionFilters
                currentUser={currentUser}
                selectedAlbum={selectedAlbum}
                onFilterChange={handleFilterChange}
              />

              {/* Collection Grid */}
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
        </>
      )}

      {currentTab === 'dashboard' && (
        <div className="dashboard-grid">
           <div>
              <div className="content-card" style={{padding: '26px'}}>
                 <h3 style={{fontSize: '1.05rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '10px'}}>Gesamter Marktwert (Ohne Wunschliste)</h3>
                 <div style={{display: 'flex', alignItems: 'baseline', gap: '20px', flexWrap: 'wrap', marginBottom: '22px'}}>
                   <h1 style={{fontSize: '2.5rem', margin: 0, color: 'var(--price-color)', letterSpacing: '-0.03em'}}>{formatEuro(totalPortfolioWert)}</h1>
                   <button
                     className="secondary-btn"
                     onClick={handleRefreshPrices}
                     disabled={updatingPrices}
                     style={{
                       padding: '10px 18px',
                       borderRadius: '12px',
                       fontSize: '0.88rem',
                       fontWeight: 600,
                       display: 'flex',
                       alignItems: 'center',
                       gap: '8px',
                       background: 'var(--btn-secondary)',
                       color: 'var(--text-main)',
                       border: '1px solid var(--border-color)',
                       cursor: 'pointer'
                     }}
                   >
                     {updatingPrices ? <div className="spinner" style={{width: '14px', height: '14px', borderWidth: '2px', margin: 0}}></div> : <RefreshCw size={14} />}
                     Preise aktualisieren
                   </button>
                 </div>

                 <h4 style={{marginBottom: '15px', color: 'var(--text-muted)', fontSize: '0.95rem'}}>Wertverteilung nach Ordnern</h4>
                 {Object.entries(portfolioAlben).map(([name, karten]) => {
                    const val = parseFloat(berechneAlbumWert(karten));
                    if(val === 0) return null;
                    const total = parseFloat(totalPortfolioWert) || 1;
                    const pct = Math.round((val / total) * 100) || 0;
                    return (
                      <div key={name} style={{marginBottom: '12px'}}>
                         <div style={{display: 'flex', justifycontent: 'space-between', marginBottom: '5px', fontSize: '0.85rem'}}>
                           <span style={{fontWeight: 600}}>{name}</span>
                           <span>{formatEuro(val)} ({pct}%)</span>
                         </div>
                         <div style={{width: '100%', height: '6px', background: 'var(--btn-secondary)', borderRadius: '3px', overflow: 'hidden'}}>
                           <div style={{width: `${pct}%`, height: '100%', background: 'var(--accent-color)'}}></div>
                         </div>
                      </div>
                    )
                 })}
              </div>
           </div>

           <div>
              <div className="content-card" style={{padding: '22px'}}>
                 <h3 style={{marginBottom: '16px', fontSize: '1.3rem'}}>Top 10 Wertvollste Karten</h3>
                 <div style={{display: 'flex', flexDirection: 'column'}}>
                   {getAllCardsFlat()
                     .sort((a,b) => getPriceVal(b) - getPriceVal(a))
                     .slice(0, 10)
                     .map((k, i) => (
                     <div key={i} className="top-card-item">
                       <span style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-muted)', width: '28px' }}># {i+1}</span>
                       <img 
                         src={k?.bild_url || getFallbackCardImage(k?.name, "Portfolio")} 
                         alt={k?.name || "Unbekannt"} 
                         className="top-card-img" 
                         loading="lazy"
                         onError={(e) => { e.target.onerror = null; e.target.src = getFallbackCardImage(k?.name, "Portfolio"); }}
                       />
                       <div style={{ flexGrow: 1 }}>
                         <div style={{ fontWeight: 600, fontSize: '1.05rem', color: 'var(--text-main)' }}>
                           {k?.name}
                           {/* Foils sind ein Vielfaches wert -- die Ausführung
                               muss auf einen Blick erkennbar sein, sonst ist der
                               Sammlungswert nicht nachvollziehbar. */}
                           {k?.foil && <span title="Foil-Ausführung" style={{ marginLeft: '8px', color: 'var(--accent-color)', fontWeight: 700 }}>✦ Foil</span>}
                         </div>
                         <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>In: {k?.albumName}</div>
                       </div>
                       <div style={{ fontWeight: 600, fontSize: '1.1rem', color: 'var(--price-color)' }}>{formatEuro(k?.livePreis || k?.preis)}</div>
                     </div>
                   ))}
                   {getAllCardsFlat().length === 0 && <p>Keine Karten im Portfolio.</p>}
                 </div>
              </div>
           </div>
        </div>
      )}

      {currentTab === 'wishlist' && (
        <div className="content-card" style={{padding: '28px'}}>
           <div style={{display: 'flex', justifycontent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '18px', marginBottom: '22px', flexWrap: 'wrap', gap: '20px'}}>
              <div>
                 <h3 style={{margin: 0, fontSize: '1.7rem'}}>Meine Wunschliste</h3>
                 <p style={{margin: '5px 0 0 0'}}>Diese Karten sind von deinem Finanz-Dashboard ausgeschlossen.</p>
              </div>
              <div style={{textAlign: 'right'}}>
                 <span style={{fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginRight: '15px', letterSpacing: '0.05em'}}>Benötigtes Budget</span>
                 <span style={{color: 'var(--price-color)', fontWeight: 600, fontSize: '1.4rem'}}>{formatEuro(totalWishlistWert)}</span>
              </div>
           </div>

           <div style={{display: 'flex', gap: '15px', maxWidth: '600px', marginBottom: '28px', background: 'var(--bg-main)', padding: '15px', borderRadius: '16px'}}>
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
                   <span className="gallery-price-tag" style={{color: 'var(--text-main)', background: 'var(--bg-main)'}}>
                     {karte?.foil && <span title="Foil-Ausführung" style={{color: 'var(--accent-color)', marginRight: '4px'}}>✦</span>}
                     {formatEuro(karte?.livePreis || karte?.preis)}
                   </span>
                 </div>
               )})}
             </div>
           )}
        </div>
      )}

      {currentTab === 'import' && (
        <CSVImportExport currentUser={currentUser} ladeSammlung={ladeSammlung} />
      )}

      {/* Premium Glassmorphic Confirmation Modal */}
      {albumToDelete && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.6)',
          backdropFilter: 'blur(8px)',
          WebkitBackdropFilter: 'blur(8px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          animation: 'fade-in 0.2s'
        }}>
          <div style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border-color)',
            borderRadius: '24px',
            padding: '30px',
            maxWidth: '450px',
            width: '90%',
            textAlign: 'center',
            boxShadow: '0 20px 50px rgba(0,0,0,0.5)'
          }}>
            <div style={{ fontSize: '3rem', marginBottom: '15px' }}>⚠️</div>
            <h4 style={{ margin: '0 0 10px 0', fontSize: '1.4rem', color: 'var(--text-main)', fontWeight: 600 }}>Ordner löschen?</h4>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', lineHeight: '1.6', marginBottom: '25px' }}>
              Möchtest du den Ordner <strong>"{albumToDelete}"</strong> und alle darin enthaltenen Karten wirklich unwiderruflich löschen? Diese Aktion kann nicht rückgängig gemacht werden.
            </p>
            
            <div style={{ display: 'flex', gap: '15px' }}>
              <button 
                onClick={() => setAlbumToDelete(null)}
                className="secondary-btn"
                style={{ flex: 1, padding: '12px 20px', borderRadius: '12px', fontSize: '0.95rem', cursor: 'pointer' }}
              >
                Abbrechen
              </button>
              <button 
                onClick={async () => {
                  const toDelete = albumToDelete;
                  setAlbumToDelete(null);
                  await deleteAlbum(toDelete);
                }}
                style={{ 
                  flex: 1, 
                  padding: '12px 20px', 
                  borderRadius: '12px', 
                  fontSize: '0.95rem',
                  background: 'rgba(255, 69, 58, 0.15)',
                  color: '#ff453a',
                  border: '1px solid rgba(255, 69, 58, 0.3)',
                  cursor: 'pointer',
                  fontWeight: 600
                }}
              >
                Ordner löschen
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default MeineSammlung;
