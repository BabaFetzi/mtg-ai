import React, { useState, useEffect, useRef } from 'react';
import { ChevronRight, Check, Copy, Video, CameraOff, Layers, Sparkles, Target, Bot } from 'lucide-react';

function PlayfieldView({ currentUser, userRole, onShowPremiumModal }) {
  const [sessionId] = useState(() => Math.random().toString(36).substring(2, 9));
  const [isConnected, setIsConnected] = useState(false);
  const [streamUrl, setStreamUrl] = useState(null);
  const [cards, setCards] = useState([]);
  const [aiAdvice, setAiAdvice] = useState('');
  const [infoMessage, setInfoMessage] = useState('Warte auf Verbindung...');
  const [copied, setCopied] = useState(false);

  // Decks for offline local matching
  const [userDecks, setUserDecks] = useState([]);
  const [selectedDeckId, setSelectedDeckId] = useState('');

  // Game state counters
  const [playerLife, setPlayerLife] = useState(40);
  const [playerPoison, setPlayerPoison] = useState(0);
  const [commanderTax, setCommanderTax] = useState(0);
  const [opponentLife, setOpponentLife] = useState(40);
  const [opponentPoison, setOpponentPoison] = useState(0);

  // Turn Phase Tracker
  const phases = ['Untap', 'Upkeep', 'Draw', 'Main 1', 'Combat', 'Main 2', 'End'];
  const [currentPhaseIdx, setCurrentPhaseIdx] = useState(0);

  const socketRef = useRef(null);
  const prevStreamUrlRef = useRef(null);

  // Fetch user's decks
  useEffect(() => {
    if (currentUser) {
      console.log(`PlayfieldView: Fetching decks for ${currentUser}`);
      fetch(`/api/decks/${currentUser}`)
        .then((res) => res.json())
        .then((data) => {
          if (Array.isArray(data)) {
            setUserDecks(data);
          }
        })
        .catch((err) => console.error('Failed to fetch user decks:', err));
    }
  }, [currentUser]);

  // Sync deck list to backend whenever WebSocket is connected or deck selection changes
  useEffect(() => {
    if (isConnected && socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      if (!selectedDeckId) {
        console.log("WebSocket: Syncing Demo Modus cards to backend...");
        socketRef.current.send(
          JSON.stringify({
            type: 'sync_deck',
            deck_liste: "1 Godo, Bandit Warlord\n1 Helm of the Host\n1 Sol Ring\n1 Black Lotus\n1 Mountain"
          })
        );
      } else {
        const deck = userDecks.find((d) => String(d.id) === String(selectedDeckId));
        if (deck) {
          console.log(`WebSocket: Syncing deck ${deck.name} to backend...`);
          socketRef.current.send(
            JSON.stringify({
              type: 'sync_deck',
              deck_liste: deck.liste
            })
          );
        }
      }
    }
  }, [isConnected, selectedDeckId, userDecks]);

  const handleDeckChange = (e) => {
    const deckId = e.target.value;
    setSelectedDeckId(deckId);
    
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      if (!deckId) {
        console.log("WebSocket: Sending sync_deck for Demo Modus");
        socketRef.current.send(
          JSON.stringify({
            type: 'sync_deck',
            deck_liste: "1 Godo, Bandit Warlord\n1 Helm of the Host\n1 Sol Ring\n1 Black Lotus\n1 Mountain"
          })
        );
      } else {
        const deck = userDecks.find((d) => String(d.id) === String(deckId));
        if (deck) {
          console.log(`WebSocket: Sending sync_deck for ${deck.name}`);
          socketRef.current.send(
            JSON.stringify({
              type: 'sync_deck',
              deck_liste: deck.liste
            })
          );
        }
      }
    }
  };

  // Dynamic mobile URL
  const mobileUrl = `${window.location.origin}/playfield/camera/${sessionId}`;

  // Copy link to clipboard
  const handleCopyLink = () => {
    navigator.clipboard.writeText(mobileUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Connect to WebSocket
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsPort = (window.location.port === '5173' || window.location.port === '5175') ? '8001' : (window.location.port ? window.location.port : '');
    const host = wsPort ? `${window.location.hostname}:${wsPort}` : window.location.hostname;
    const wsUrl = `${protocol}//${host}/api/vision/stream/${sessionId}?role=display`;
    console.log(`Connecting to WebSocket: ${wsUrl}`);
    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      setIsConnected(true);
      setInfoMessage('Verbunden. Warte auf Kamera...');
    };

    socket.onmessage = async (event) => {
      if (event.data instanceof Blob) {
        // Binary data: Render incoming camera JPEG frame
        const url = URL.createObjectURL(event.data);
        setStreamUrl((prevUrl) => {
          if (prevUrl) {
            URL.revokeObjectURL(prevUrl);
          }
          return url;
        });
        setInfoMessage('Kamera-Stream aktiv');
      } else {
        // Text data
        try {
          const message = JSON.parse(event.data);
          if (message.type === 'board_state') {
            setCards(message.cards || []);
            if (message.advice) {
              setAiAdvice(message.advice);
            }
          } else if (message.type === 'info') {
            setInfoMessage(message.message);
          }
        } catch (err) {
          console.error('Failed to parse WebSocket text message:', err);
        }
      }
    };

    socket.onerror = (err) => {
      console.error('WebSocket error:', err);
      setInfoMessage('Verbindungsfehler.');
    };

    socket.onclose = () => {
      setIsConnected(false);
      setInfoMessage('Verbindung getrennt. Versuche erneut zu verbinden...');
    };

    return () => {
      if (socket) {
        socket.close();
      }
      if (streamUrl) {
        URL.revokeObjectURL(streamUrl);
      }
    };
  }, [sessionId]);

  // Clean up any remaining blob URLs
  useEffect(() => {
    return () => {
      if (streamUrl) {
        URL.revokeObjectURL(streamUrl);
      }
    };
  }, [streamUrl]);

  // Toggle card tapped state locally
  const toggleTapped = (cardId) => {
    setCards((prevCards) =>
      prevCards.map((c) => (c.id === cardId ? { ...c, tapped: !c.tapped } : c))
    );
  };

  // Next Phase
  const handleNextPhase = () => {
    setCurrentPhaseIdx((prev) => (prev + 1) % phases.length);
  };

  // AI strategic recommendations based on board state
  const getAIRecommendations = () => {
    const recommendations = [];
    const names = cards.map((c) => c.name.toLowerCase());

    if (names.includes('godo, bandit warlord') && names.includes('helm of the host')) {
      recommendations.push({
        type: 'danger',
        title: '⚠️ Unendliche Kampfphasen Combo!',
        text: 'Godo + Helm of the Host auf dem Spielfeld detektiert. Rüste Godo mit Helm of the Host aus. Beim Angreifen erzeugt der Helm eine Godo-Kopie mit Eile, die eine zusätzliche Kampfphase generiert. Wiederhole dies unendlich oft.'
      });
    }

    if (names.includes('black lotus')) {
      recommendations.push({
        type: 'info',
        title: '💡 Black Lotus Mana-Burst',
        text: 'Black Lotus kann geopfert werden, um 3 Mana einer beliebigen Farbe zu erzeugen. Nutze diesen massiven Tempovorteil direkt in deiner ersten Hauptphase für spielentscheidende Zaubersprüche.'
      });
    }

    if (names.includes('sol ring')) {
      recommendations.push({
        type: 'tip',
        title: '⚡ Sol Ring Mana-Vorteil',
        text: 'Sol Ring erzeugt 2 farblose Mana. Stelle sicher, dass du das Mana optimal nutzt, um deine Commander-Kosten auszugleichen oder wichtige Artefakte auszuspielen.'
      });
    }

    // Dynamic advice if cards are tapped
    const tappedCount = cards.filter((c) => c.tapped).length;
    if (tappedCount > 0) {
      recommendations.push({
        type: 'tip',
        title: '🛡️ Defensiver Hinweis',
        text: `Du hast ${tappedCount} getappte Karte(n). Achte auf potenzielle Gegenangriffe deines Gegners, da dir weniger Block-Möglichkeiten zur Verfügung stehen.`
      });
    }

    if (recommendations.length === 0) {
      recommendations.push({
        type: 'welcome',
        title: '🔮 Spielfeld Analyse',
        text: 'Verbinde dein Smartphone als Kamera, um das physische Spielfeld zu scannen. Unsere Echtzeit-Bilderkennung liest deine Karten ein und gibt dir strategische Empfehlungen.'
      });
    }

    return recommendations;
  };

  // 3D Tilt Card Hover Effect
  const handleMouseMove = (e) => {
    const card = e.currentTarget;
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    const xc = rect.width / 2;
    const yc = rect.height / 2;
    
    const angleX = (yc - y) / 4;
    const angleY = (x - xc) / 4;
    
    card.style.transform = `perspective(600px) rotateX(${angleX}deg) rotateY(${angleY}deg) scale(1.08) ${
      card.dataset.tapped === 'true' ? 'rotate(90deg)' : ''
    }`;
  };

  const handleMouseLeave = (e) => {
    const card = e.currentTarget;
    card.style.transform = `perspective(600px) rotateX(0deg) rotateY(0deg) scale(1) ${
      card.dataset.tapped === 'true' ? 'rotate(90deg)' : ''
    }`;
  };

  return (
    <div style={{ maxWidth: '1600px', margin: '0 auto', padding: '30px 20px', boxSizing: 'border-box' }}>
      {/* 1. Header & Live Indicator */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '15px' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '2rem', letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ display: 'inline-block', width: '12px', height: '12px', borderRadius: '50%', background: isConnected ? '#30D158' : '#FF453A', boxShadow: isConnected ? '0 0 10px #30D158' : 'none' }}></span>
            Live Playfield
          </h2>
          <p style={{ margin: '4px 0 0 0', color: 'var(--text-muted)', fontSize: '0.95rem' }}>{infoMessage}</p>
        </div>

        {/* Phase Tracker */}
        <div style={{ display: 'flex', alignItems: 'center', background: 'var(--btn-secondary)', borderRadius: '16px', padding: '6px 12px', border: '1px solid var(--border-color)', gap: '10px', overflowX: 'auto', maxWidth: '100%' }}>
          {phases.map((phase, idx) => (
            <div
              key={phase}
              style={{
                padding: '6px 12px',
                borderRadius: '8px',
                fontSize: '0.85rem',
                fontWeight: idx === currentPhaseIdx ? '700' : '400',
                background: idx === currentPhaseIdx ? 'var(--accent-color)' : 'transparent',
                color: idx === currentPhaseIdx ? 'var(--accent-text)' : 'var(--text-muted)',
                transition: 'all 0.2s',
                whiteSpace: 'nowrap'
              }}
            >
              {phase}
            </div>
          ))}
          <button
            onClick={handleNextPhase}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-main)',
              display: 'flex',
              alignItems: 'center',
              padding: '6px'
            }}
            title="Nächste Phase"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {/* 2. Main Grid Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 2fr 1fr', gap: '24px' }}>
        
        {/* Left Column: Stream Link, QR Code & Camera Stream */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Connection Helper Panel */}
          <div className="content-card" style={{ margin: 0, padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 600 }}>Mobile Kamera verbinden</h3>
            <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
              Scanne den QR-Code oder kopiere den Link, um dein Smartphone als kabellose Kamera zu verwenden.
            </p>
            
            {window.location.hostname === 'localhost' && (
              <div style={{ background: 'rgba(255, 159, 10, 0.12)', border: '1px solid rgba(255, 159, 10, 0.3)', color: '#FF9F0A', padding: '10px 12px', borderRadius: '8px', fontSize: '0.8rem', lineHeight: 1.3 }}>
                <strong>⚠️ Localhost-Verbindungshinweis:</strong><br />
                Da du das Dashboard über <code>localhost</code> geöffnet hast, wird dein Smartphone unter dieser Adresse keine Verbindung herstellen können. Rufe das Dashboard stattdessen über die IP-Adresse deines PCs (z.B. <code>http://192.168.x.x:5175/playfield</code>) auf, damit der QR-Code funktioniert.
              </div>
            )}
            
            {/* QR Code generator using free qrserver api */}
            <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0' }}>
              <div style={{ background: '#FFF', padding: '10px', borderRadius: '12px', display: 'inline-block', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(mobileUrl)}`}
                  alt="QR Code für Mobile Camera"
                  style={{ display: 'block', width: '150px', height: '150px' }}
                />
              </div>
            </div>

            {/* Offline Deck Selector */}
            {userDecks.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Offline-Deck wählen:</label>
                <select
                  value={selectedDeckId}
                  onChange={handleDeckChange}
                  style={{
                    padding: '10px 12px',
                    fontSize: '0.9rem',
                    borderRadius: '10px',
                    background: 'var(--btn-secondary)',
                    border: '1px solid var(--border-color)',
                    color: 'var(--text-main)',
                    outline: 'none',
                    cursor: 'pointer'
                  }}
                >
                  <option value="">-- Demo-Modus (Standardkarten) --</option>
                  {userDecks.map((deck) => (
                    <option key={deck.id} value={deck.id}>
                      {deck.name} ({deck.format || 'Commander'})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Input field with Copy link */}
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                readOnly
                value={mobileUrl}
                style={{
                  flexGrow: 1,
                  padding: '10px 12px',
                  fontSize: '0.85rem',
                  borderRadius: '10px',
                  background: 'var(--btn-secondary)',
                  border: '1px solid var(--border-color)',
                  color: 'var(--text-main)',
                  outline: 'none'
                }}
              />
              <button
                className="secondary-btn"
                onClick={handleCopyLink}
                style={{ padding: '0 16px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                {copied ? <Check size={16} /> : <Copy size={16} />}
              </button>
            </div>
          </div>

          {/* Camera Feed Ingestion */}
          <div className="content-card" style={{ margin: 0, padding: '20px', flexGrow: 1, display: 'flex', flexDirection: 'column', gap: '12px', minHeight: '300px' }}>
            <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Video size={18} />
              Kamera-Feed
            </h3>
            <div style={{ flexGrow: 1, background: '#000', borderRadius: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', position: 'relative' }}>
              {streamUrl ? (
                <div style={{ position: 'relative', width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <img
                    src={streamUrl}
                    alt="Live Camera Feed"
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                  />
                  {/* SVG Overlay for bounding boxes */}
                  <svg 
                    viewBox="0 0 100 100" 
                    preserveAspectRatio="none"
                    style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 5 }}
                  >
                    {cards.map((card) => {
                      if (!card.box) return null;
                      const pointsStr = card.box.map(pt => `${pt[0]},${pt[1]}`).join(' ');
                      return (
                        <g key={card.id}>
                          <polygon
                            points={pointsStr}
                            style={{
                              fill: 'rgba(48, 209, 88, 0.12)',
                              stroke: '#30D158',
                              strokeWidth: 0.8,
                              vectorEffect: 'non-scaling-stroke'
                            }}
                          />
                          <text
                            x={card.box[0][0]}
                            y={Math.max(3, card.box[0][1] - 2)}
                            fill="#30D158"
                            style={{
                              fontSize: '2.5px',
                              fontWeight: 'bold',
                              fontFamily: 'sans-serif',
                              textShadow: '0 0 1.5px #000'
                            }}
                          >
                            Erkannt: {card.name}
                          </text>
                        </g>
                      );
                    })}
                  </svg>
                </div>
              ) : (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', padding: '20px' }}>
                  <CameraOff size={32} style={{ marginBottom: '10px', opacity: 0.5 }} />
                  <div>Kein Live-Bild empfangen.</div>
                  <div style={{ fontSize: '0.8rem', opacity: 0.7, marginTop: '4px' }}>Öffne den Link auf deinem Smartphone.</div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Center Column: Digital Card Playfield Grid */}
        <div className="content-card" style={{ margin: 0, padding: '24px', display: 'flex', flexDirection: 'column', minHeight: '600px' }}>
          <h3 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Layers size={20} />
            Digitales Spielfeld
          </h3>
          
          {/* Virtual Grid Board representation */}
          <div style={{
            flexGrow: 1,
            position: 'relative',
            background: 'var(--btn-secondary)',
            border: '2px dashed var(--border-color)',
            borderRadius: '20px',
            overflow: 'hidden',
            backgroundImage: 'radial-gradient(var(--border-color) 1px, transparent 1px)',
            backgroundSize: '24px 24px'
          }}>
            
            {/* Cards Layer */}
            {cards.length > 0 ? (
              cards.map((card) => (
                <div
                  key={card.id}
                  onClick={() => toggleTapped(card.id)}
                  onMouseMove={handleMouseMove}
                  onMouseLeave={handleMouseLeave}
                  data-tapped={card.tapped}
                  style={{
                    position: 'absolute',
                    left: `${card.x}%`,
                    top: `${card.y}%`,
                    transform: `translate(-50%, -50%) ${card.tapped ? 'rotate(90deg)' : ''}`,
                    width: '100px',
                    height: '140px',
                    borderRadius: '6px',
                    boxShadow: '0 8px 16px rgba(0,0,0,0.3)',
                    cursor: 'pointer',
                    transition: 'transform 0.2s ease, left 0.5s ease, top 0.5s ease',
                    zIndex: 10,
                    userSelect: 'none',
                    backgroundColor: '#1C0F0F'
                  }}
                  title={`${card.name} (${card.tapped ? 'Getappt' : 'Enttappt'})`}
                >
                  <img
                    src={card.image_url}
                    alt={card.name}
                    style={{ width: '100%', height: '100%', borderRadius: '6px', objectFit: 'cover' }}
                    draggable="false"
                  />
                  {/* Indicator for tapped */}
                  {card.tapped && (
                    <div style={{
                      position: 'absolute',
                      bottom: '4px',
                      right: '4px',
                      background: 'rgba(255, 69, 58, 0.95)',
                      color: '#FFF',
                      fontSize: '9px',
                      fontWeight: 'bold',
                      padding: '2px 4px',
                      borderRadius: '4px',
                      transform: 'rotate(-90deg)',
                      transformOrigin: 'bottom right'
                    }}>
                      TAP
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                textAlign: 'center',
                color: 'var(--text-muted)',
                pointerEvents: 'none'
              }}>
                <Sparkles size={40} style={{ opacity: 0.3, marginBottom: '10px' }} />
                <div style={{ fontSize: '1.05rem', fontWeight: 600 }}>Spielfeld ist leer</div>
                <div style={{ fontSize: '0.85rem', opacity: 0.7, marginTop: '4px' }}>Erkannte Karten werden hier live projiziert.</div>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Game State Trackers & AI Recommendations */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Game State Trackers */}
          <div className="content-card" style={{ margin: 0, padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Target size={18} />
              Spielstand
            </h3>
            
            {/* Player Counters */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <h4 style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Dein Status</h4>
              
              {/* Life counter */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--btn-secondary)', borderRadius: '12px', padding: '10px 16px' }}>
                <span style={{ fontSize: '0.95rem', fontWeight: 500 }}>Lebenspunkte</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <button onClick={() => setPlayerLife(l => Math.max(0, l - 1))} style={{ width: '28px', height: '28px', borderRadius: '50%', border: 'none', background: 'var(--bg-main)', color: 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}>-</button>
                  <span style={{ fontSize: '1.4rem', fontWeight: 700, minWidth: '30px', textAlign: 'center' }}>{playerLife}</span>
                  <button onClick={() => setPlayerLife(l => l + 1)} style={{ width: '28px', height: '28px', borderRadius: '50%', border: 'none', background: 'var(--bg-main)', color: 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}>+</button>
                </div>
              </div>

              {/* Poison counter */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--btn-secondary)', borderRadius: '12px', padding: '10px 16px' }}>
                <span style={{ fontSize: '0.95rem', fontWeight: 500 }}>Giftmarken</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <button onClick={() => setPlayerPoison(p => Math.max(0, p - 1))} style={{ width: '28px', height: '28px', borderRadius: '50%', border: 'none', background: 'var(--bg-main)', color: 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}>-</button>
                  <span style={{ fontSize: '1.2rem', fontWeight: 700, minWidth: '30px', textAlign: 'center', color: '#30B058' }}>{playerPoison}</span>
                  <button onClick={() => setPlayerPoison(p => p + 1)} style={{ width: '28px', height: '28px', borderRadius: '50%', border: 'none', background: 'var(--bg-main)', color: 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}>+</button>
                </div>
              </div>

              {/* Commander Tax counter */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--btn-secondary)', borderRadius: '12px', padding: '10px 16px' }}>
                <span style={{ fontSize: '0.95rem', fontWeight: 500 }}>Commander Tax</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <button onClick={() => setCommanderTax(t => Math.max(0, t - 2))} style={{ width: '28px', height: '28px', borderRadius: '50%', border: 'none', background: 'var(--bg-main)', color: 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}>-</button>
                  <span style={{ fontSize: '1.2rem', fontWeight: 700, minWidth: '30px', textAlign: 'center', color: '#9B5DE5' }}>{commanderTax}</span>
                  <button onClick={() => setCommanderTax(t => t + 2)} style={{ width: '28px', height: '28px', borderRadius: '50%', border: 'none', background: 'var(--bg-main)', color: 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}>+</button>
                </div>
              </div>
            </div>

            <hr style={{ border: 'none', borderBottom: '1px solid var(--border-color)', margin: '4px 0' }} />

            {/* Opponent Counters */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <h4 style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Gegner Status</h4>
              
              {/* Opponent Life counter */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--btn-secondary)', borderRadius: '12px', padding: '10px 16px' }}>
                <span style={{ fontSize: '0.95rem', fontWeight: 500 }}>Lebenspunkte</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <button onClick={() => setOpponentLife(l => Math.max(0, l - 1))} style={{ width: '28px', height: '28px', borderRadius: '50%', border: 'none', background: 'var(--bg-main)', color: 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}>-</button>
                  <span style={{ fontSize: '1.4rem', fontWeight: 700, minWidth: '30px', textAlign: 'center' }}>{opponentLife}</span>
                  <button onClick={() => setOpponentLife(l => l + 1)} style={{ width: '28px', height: '28px', borderRadius: '50%', border: 'none', background: 'var(--bg-main)', color: 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}>+</button>
                </div>
              </div>

              {/* Opponent Poison counter */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--btn-secondary)', borderRadius: '12px', padding: '10px 16px' }}>
                <span style={{ fontSize: '0.95rem', fontWeight: 500 }}>Giftmarken</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <button onClick={() => setOpponentPoison(p => Math.max(0, p - 1))} style={{ width: '28px', height: '28px', borderRadius: '50%', border: 'none', background: 'var(--bg-main)', color: 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}>-</button>
                  <span style={{ fontSize: '1.2rem', fontWeight: 700, minWidth: '30px', textAlign: 'center', color: '#30B058' }}>{opponentPoison}</span>
                  <button onClick={() => setOpponentPoison(p => p + 1)} style={{ width: '28px', height: '28px', borderRadius: '50%', border: 'none', background: 'var(--bg-main)', color: 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}>+</button>
                </div>
              </div>
            </div>
          </div>

          {/* AI Strategic Recommendations Panel */}
          <div className="content-card" style={{ margin: 0, padding: '24px', flexGrow: 1, display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
            <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Bot size={18} />
              Grana KI-Taktik
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {aiAdvice && (
                <div
                  style={{
                    padding: '16px',
                    borderRadius: '12px',
                    background: 'rgba(155, 93, 229, 0.1)',
                    borderLeft: '4px solid #9B5DE5',
                    marginBottom: '10px'
                  }}
                >
                  <h4 style={{ margin: '0 0 6px 0', fontSize: '0.95rem', fontWeight: 700, color: '#9B5DE5', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Sparkles size={14} /> Live KI Spielanalyse
                  </h4>
                  <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-main)', lineHeight: 1.4, whiteSpace: 'pre-line' }}>
                    {aiAdvice}
                  </p>
                </div>
              )}
              {getAIRecommendations().map((rec, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: '16px',
                    borderRadius: '12px',
                    background:
                      rec.type === 'danger'
                        ? 'var(--danger-bg)'
                        : rec.type === 'tip'
                        ? 'rgba(0, 113, 227, 0.08)'
                        : 'var(--btn-secondary)',
                    borderLeft: `4px solid ${
                      rec.type === 'danger'
                        ? 'var(--danger-color)'
                        : rec.type === 'tip'
                        ? '#0071E3'
                        : rec.type === 'info'
                        ? '#FAF8F5'
                        : 'var(--text-muted)'
                    }`
                  }}
                >
                  <h4 style={{ margin: '0 0 6px 0', fontSize: '0.95rem', fontWeight: 700, color: rec.type === 'danger' ? 'var(--danger-color)' : 'var(--text-main)' }}>
                    {rec.title}
                  </h4>
                  <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                    {rec.text}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

export default PlayfieldView;
