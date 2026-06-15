import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Video, Sparkles } from 'lucide-react';

// Default card templates for simulation
const SIMULATED_TEMPLATES = [
  { name: 'Godo, Bandit Warlord', image_url: 'https://api.scryfall.com/cards/named?exact=Godo,%20Bandit%20Warlord&format=image', type: 'Creature' },
  { name: 'Helm of the Host', image_url: 'https://api.scryfall.com/cards/named?exact=Helm%20of%20the%20Host&format=image', type: 'Artifact' },
  { name: 'Sol Ring', image_url: 'https://api.scryfall.com/cards/named?exact=Sol%20Ring&format=image', type: 'Artifact' },
  { name: 'Black Lotus', image_url: 'https://api.scryfall.com/cards/named?exact=Black%20Lotus&format=image', type: 'Artifact' },
  { name: 'Colossal Dreadmaw', image_url: 'https://api.scryfall.com/cards/named?exact=Colossal%20Dreadmaw&format=image', type: 'Creature' },
  { name: 'Lightning Bolt', image_url: 'https://api.scryfall.com/cards/named?exact=Lightning%20Bolt&format=image', type: 'Instant' },
  { name: 'Mountain', image_url: 'https://api.scryfall.com/cards/named?exact=Mountain&format=image', type: 'Land' }
];

function MobileCamera() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [isConnected, setIsConnected] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [fps, setFps] = useState(3); // stream at 3 FPS by default (optimal for network stability and detection)
  const [errorMsg, setErrorMsg] = useState(null);
  const [qaWarning, setQaWarning] = useState(null);
  const [videoDevices, setVideoDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [isSecure, setIsSecure] = useState(window.isSecureContext);
  
  // Simulator state
  const [simulatedCards, setSimulatedCards] = useState([]);
  const [selectedTemplateIdx, setSelectedTemplateIdx] = useState(0);
  const [sliderX, setSliderX] = useState(50);
  const [sliderY, setSliderY] = useState(50);
  const [isTapped, setIsTapped] = useState(false);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const socketRef = useRef(null);
  const streamRef = useRef(null);
  const intervalRef = useRef(null);

  // Check for camera-API availability on mount
  useEffect(() => {
    if (!navigator.mediaDevices) {
      setErrorMsg('Die Kamera-API (navigator.mediaDevices) ist in diesem Browser oder Kontext nicht verfügbar. Dies liegt meistens an einer fehlenden HTTPS-Verschlüsselung.');
    }
  }, []);

  // Connect to WebSocket
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsPort = (window.location.port === '5173' || window.location.port === '5175') ? '8001' : (window.location.port ? window.location.port : '');
    const host = wsPort ? `${window.location.hostname}:${wsPort}` : window.location.hostname;
    const wsUrl = `${protocol}//${host}/api/vision/stream/${sessionId}?role=camera`;
    console.log(`Connecting camera to: ${wsUrl}`);
    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      setIsConnected(true);
      setErrorMsg(null);
    };

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'qa_feedback') {
          console.log('Received QA feedback:', message);
          setQaWarning(message.message);
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    socket.onclose = () => {
      setIsConnected(false);
    };

    socket.onerror = (err) => {
      console.error('Camera WebSocket error:', err);
      setErrorMsg('Verbindungsfehler zum Stream-Server.');
    };

    return () => {
      if (socket) {
        socket.close();
      }
      stopCamera();
    };
  }, [sessionId]);

  // Synchronous Wide-Angle / FOV scanner based on labels
  const scanDevicesForWideAngle = (devices) => {
    const scoredDevices = [];
    const videoInputs = devices.filter(d => d.kind === 'videoinput');
    
    for (const dev of videoInputs) {
      let score = 0;
      const label = (dev.label || '').toLowerCase();
      
      // Heuristic 1: Check label naming conventions for wide angle keywords
      if (label.includes('0.5x') || label.includes('0.5') || label.includes('0.6x') || label.includes('0.6')) {
        score += 100;
      }
      if (label.includes('ultra')) {
        score += 50;
      }
      if (label.includes('weit') || label.includes('wide')) {
        score += 30;
      }
      if (label.includes('camera 1') || label.includes('camera 3')) {
        score += 20;
      }
      if (label.includes('back') || label.includes('rear') || label.includes('rück')) {
        score += 10;
      }
      if (label.includes('front') || label.includes('vorder')) {
        score -= 100; // Ignore front-facing lenses
      }

      scoredDevices.push({
        deviceId: dev.deviceId,
        label: dev.label,
        kind: dev.kind,
        groupId: dev.groupId,
        score,
        displayName: dev.label || `Kamera (${dev.deviceId.substring(0, 5)})`
      });
    }

    // Sort by score descending (widest lens first)
    scoredDevices.sort((a, b) => b.score - a.score);
    console.log("Scored video devices for Wide Angle:", scoredDevices);
    return scoredDevices;
  };

  // Enumerate devices on mount to pre-select back camera if permission is already granted
  useEffect(() => {
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
      navigator.mediaDevices.enumerateDevices()
        .then((devices) => {
          const videoInputs = devices.filter(d => d.kind === 'videoinput');
          if (videoInputs.length > 0 && videoInputs[0].label) {
            const scored = scanDevicesForWideAngle(devices);
            setVideoDevices(scored);
            if (scored.length > 0) {
              setSelectedDeviceId(scored[0].deviceId);
            }
          }
        })
        .catch(err => console.error('Error pre-listing video devices:', err));
    }
  }, []);

  // Start Camera feed
  const startCamera = async (overrideDeviceId = null) => {
    setErrorMsg(null);
    setQaWarning(null); // Clear warnings
    
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setErrorMsg('Die Kamera-API (navigator.mediaDevices.getUserMedia) ist in diesem Browser/Kontext nicht verfügbar.');
      return;
    }

    const activeDeviceId = overrideDeviceId || selectedDeviceId;

    // We will attempt up to 4 fallback options to guarantee we get a working stream.
    
    // Attempt 1: Target device with ideal resolution
    try {
      const constraints = {
        video: {
          deviceId: activeDeviceId ? { ideal: activeDeviceId } : undefined,
          facingMode: activeDeviceId ? undefined : 'environment',
          width: { ideal: 1280 },
          height: { ideal: 720 },
          frameRate: { ideal: 15 }
        },
        audio: false
      };
      console.log("Attempt 1: opening camera with constraints:", constraints);
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      await handleSuccessfulStream(stream, overrideDeviceId);
      return;
    } catch (err) {
      console.warn("Attempt 1 failed, trying Attempt 2 (exact deviceId, no constraints)...", err);
    }

    // Attempt 2: Strict deviceId constraint with fallback
    if (activeDeviceId) {
      try {
        const constraints = {
          video: {
            deviceId: { exact: activeDeviceId }
          },
          audio: false
        };
        console.log("Attempt 2: opening camera with exact deviceId:", constraints);
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        await handleSuccessfulStream(stream, overrideDeviceId);
        return;
      } catch (err) {
        console.warn("Attempt 2 failed, trying Attempt 3 (generic environment camera)...", err);
      }
    }

    // Attempt 3: Generic environment camera
    try {
      const constraints = {
        video: { facingMode: 'environment' },
        audio: false
      };
      console.log("Attempt 3: opening generic environment camera:", constraints);
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      await handleSuccessfulStream(stream, overrideDeviceId);
      return;
    } catch (err) {
      console.warn("Attempt 3 failed, trying Attempt 4 (any video source)...", err);
    }

    // Attempt 4: Any camera
    try {
      const constraints = {
        video: true,
        audio: false
      };
      console.log("Attempt 4: opening any camera (video: true):", constraints);
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      await handleSuccessfulStream(stream, overrideDeviceId);
      return;
    } catch (err) {
      console.error("All camera attempts failed:", err);
      printErrorMsg(err);
    }
  };

  const handleSuccessfulStream = async (stream, overrideDeviceId) => {
    streamRef.current = stream;
    
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
      setCameraActive(true);
    }

    let devices = [];
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
      try {
        devices = await navigator.mediaDevices.enumerateDevices();
      } catch (e) {
        console.error("Error enumerating devices:", e);
      }
    }
    
    const scored = scanDevicesForWideAngle(devices);
    setVideoDevices(scored);

    const activeTrack = stream.getVideoTracks()[0];
    const settings = activeTrack ? activeTrack.getSettings() : null;
    const currentId = settings ? settings.deviceId : null;

    if (scored.length > 0) {
      const bestDevice = scored[0];
      // Auto-upgrade to the widest lens if current is different and not explicitly overridden.
      // Score threshold > 10 ensures we actually have a wide-angle lens.
      if (!overrideDeviceId && currentId && currentId !== bestDevice.deviceId && bestDevice.score > 10) {
        console.log(`Auto-upgrading to ultra-wide lens: ${bestDevice.displayName}`);
        setSelectedDeviceId(bestDevice.deviceId);
        
        // Stop current tracks first
        stream.getTracks().forEach(track => track.stop());
        
        // Release hardware slightly before re-opening
        setTimeout(() => startCamera(bestDevice.deviceId), 300);
        return;
      }
      
      if (!overrideDeviceId) {
        setSelectedDeviceId(bestDevice.deviceId);
      }
    } else if (currentId && !selectedDeviceId) {
      setSelectedDeviceId(currentId);
    }
  };

  const printErrorMsg = (err) => {
    console.error('Error opening camera:', err);
    setErrorMsg('Kamera konnte nicht geöffnet werden. Bitte überprüfe die Berechtigungen.');
  };

  // Stop Camera stream
  const stopCamera = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  };

  // Frame Capturing loop
  useEffect(() => {
    if (cameraActive && isConnected) {
      const intervalMs = 1000 / fps;
      intervalRef.current = setInterval(() => {
        captureAndSendFrame();
      }, intervalMs);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [cameraActive, isConnected, fps]);

  const captureAndSendFrame = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    const socket = socketRef.current;

    if (!video || !canvas || !socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas dimensions matching video input stream
    if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
    }

    // Draw video frame to canvas
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    // Convert canvas to JPEG blob and send as binary bytes
    canvas.toBlob((blob) => {
      if (blob && socket.readyState === WebSocket.OPEN) {
        socket.send(blob);
      }
    }, 'image/jpeg', 0.65); // quality compression
  };

  // Simulator helper: send card placements to desktop via WebSocket
  const sendBoardStateUpdate = (updatedCards) => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        type: 'board_state',
        cards: updatedCards
      }));
    }
  };

  const handleAddCardSimulation = () => {
    const template = SIMULATED_TEMPLATES[selectedTemplateIdx];
    const newCard = {
      id: `sim-card-${Math.random().toString(36).substring(2, 9)}`,
      name: template.name,
      image_url: template.image_url,
      type: template.type,
      x: sliderX,
      y: sliderY,
      tapped: isTapped
    };

    const newCards = [...simulatedCards, newCard];
    setSimulatedCards(newCards);
    sendBoardStateUpdate(newCards);
  };

  const handleToggleCardTapped = (id) => {
    const newCards = simulatedCards.map(c => 
      c.id === id ? { ...c, tapped: !c.tapped } : c
    );
    setSimulatedCards(newCards);
    sendBoardStateUpdate(newCards);
  };

  const handleRemoveCard = (id) => {
    const newCards = simulatedCards.filter(c => c.id !== id);
    setSimulatedCards(newCards);
    sendBoardStateUpdate(newCards);
  };

  const handleClearBoard = () => {
    setSimulatedCards([]);
    sendBoardStateUpdate([]);
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0F0F12', color: '#FFF', padding: '20px', boxSizing: 'border-box', fontFamily: 'inherit' }}>
      
      {/* 1. Header with Status */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '1px solid #2C2C35', paddingBottom: '15px' }}>
        <div>
          <h2 style={{ color: '#FFF', margin: 0, fontSize: '1.4rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: isConnected ? '#30D158' : '#FF453A', display: 'inline-block' }} />
            Grana Streamer
          </h2>
          <span style={{ fontSize: '0.8rem', color: '#8E8E93' }}>Session: {sessionId}</span>
        </div>
        
        <button
          onClick={() => navigate('/playfield')}
          style={{
            background: 'rgba(255,255,255,0.08)',
            border: 'none',
            color: '#FFF',
            padding: '8px 16px',
            borderRadius: '20px',
            cursor: 'pointer',
            fontSize: '0.85rem'
          }}
        >
          Zum Dashboard
        </button>
      </div>

      {!isSecure && (
        <div style={{ background: 'rgba(255, 69, 58, 0.15)', color: '#FF453A', padding: '16px', borderRadius: '12px', fontSize: '0.9rem', marginBottom: '20px', border: '1px solid rgba(255, 69, 58, 0.3)', lineHeight: '1.4' }}>
          <div style={{ fontWeight: 'bold', marginBottom: '8px', fontSize: '1rem' }}>⚠️ Kamera-Zugriff blockiert (Unsicherer Kontext)</div>
          <p style={{ margin: '0 0 10px 0', color: '#FF453A' }}>
            iOS Safari blockiert den Kamerazugriff über unverschlüsseltes HTTP auf externen IP-Adressen (Sicherheitsrichtlinie).
          </p>
          <div style={{ fontSize: '0.85rem', color: '#E5E5EA' }}>
            <span style={{ fontWeight: 'bold' }}>Lösung:</span>
            <ul style={{ margin: '5px 0 0 0', paddingLeft: '20px' }}>
              <li>
                <strong>Option A:</strong> Öffne Safari Einstellungen → Erweitert → Feature Flags (oder Experimental Features) → Aktiviere <strong>"Media Capture on Insecure Sites"</strong>.
              </li>
              <li>
                <strong>Option B:</strong> Verwende ein HTTPS-Tunnel-Tool wie ngrok: <code>ngrok http 5175</code>.
              </li>
              <li>
                <strong>Option C:</strong> Nutze den <strong>Battlefield-Simulator</strong> unten auf dieser Seite, um die Erkennung und 3D-Ansicht ohne physische Kamera zu testen.
              </li>
            </ul>
          </div>
        </div>
      )}

      {errorMsg && (
        <div style={{ background: 'rgba(255, 69, 58, 0.15)', color: '#FF453A', padding: '12px 16px', borderRadius: '12px', fontSize: '0.9rem', marginBottom: '20px', border: '1px solid rgba(255, 69, 58, 0.3)' }}>
          {errorMsg}
        </div>
      )}

      {qaWarning && (
        <div style={{ background: 'rgba(255, 159, 10, 0.15)', color: '#FF9F0A', padding: '12px 16px', borderRadius: '12px', fontSize: '0.9rem', marginBottom: '20px', border: '1px solid rgba(255, 159, 10, 0.3)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ fontWeight: 'bold' }}>⚠️ QA-Empfehlung (Agent 4):</div>
          <div>{qaWarning}</div>
          {videoDevices.length > 1 && (
            <button
              onClick={() => {
                const currentIndex = videoDevices.findIndex(d => d.deviceId === selectedDeviceId);
                const nextIndex = (currentIndex + 1) % videoDevices.length;
                const nextDevice = videoDevices[nextIndex];
                setSelectedDeviceId(nextDevice.deviceId);
                stopCamera();
                setTimeout(() => startCamera(nextDevice.deviceId), 250);
              }}
              style={{
                background: '#FF9F0A',
                color: '#000',
                border: 'none',
                padding: '6px 12px',
                borderRadius: '6px',
                fontWeight: 'bold',
                cursor: 'pointer',
                alignSelf: 'flex-start',
                fontSize: '0.8rem'
              }}
            >
              Nächste Kamera testen
            </button>
          )}
        </div>
      )}

      {/* 2. Main Grid Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '20px' }}>
        
        {/* Camera Control Panel */}
        <div style={{ background: '#1C1C1E', borderRadius: '16px', padding: '20px', border: '1px solid #2C2C35' }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: '1.1rem', color: '#FFF', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Video size={18} />
            Live Kamera-Stream
          </h3>
          
          {videoDevices.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '14px' }}>
              <label style={{ fontSize: '0.85rem', color: '#8E8E93', fontWeight: 500 }}>Kamera-Linse wählen:</label>
              <select
                value={selectedDeviceId}
                onChange={async (e) => {
                  const devId = e.target.value;
                  setSelectedDeviceId(devId);
                  if (cameraActive) {
                    stopCamera();
                    setTimeout(() => startCamera(devId), 250);
                  }
                }}
                style={{
                  width: '100%',
                  background: '#2C2C2E',
                  color: '#FFF',
                  border: '1px solid #3A3A3C',
                  padding: '12px 14px',
                  borderRadius: '10px',
                  fontSize: '0.9rem',
                  outline: 'none',
                  cursor: 'pointer'
                }}
              >
                {videoDevices.map((device, idx) => (
                  <option key={device.deviceId} value={device.deviceId}>
                    {device.displayName || device.label || `Linse ${idx + 1}`} {device.score > 20 ? ' [Weitwinkel - Empfohlen]' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div style={{ display: 'flex', gap: '10px', marginBottom: '16px' }}>
            {!cameraActive ? (
              <button
                onClick={() => startCamera()}
                disabled={!isConnected}
                style={{
                  flexGrow: 1,
                  background: '#0071E3',
                  color: '#FFF',
                  border: 'none',
                  padding: '12px',
                  borderRadius: '10px',
                  fontWeight: 'bold',
                  cursor: isConnected ? 'pointer' : 'not-allowed',
                  opacity: isConnected ? 1 : 0.5
                }}
              >
                Kamera starten
              </button>
            ) : (
              <button
                onClick={stopCamera}
                style={{
                  flexGrow: 1,
                  background: '#FF453A',
                  color: '#FFF',
                  border: 'none',
                  padding: '12px',
                  borderRadius: '10px',
                  fontWeight: 'bold',
                  cursor: 'pointer'
                }}
              >
                Kamera stoppen
              </button>
            )}
            
            <select
              value={fps}
              onChange={(e) => setFps(Number(e.target.value))}
              style={{
                background: '#2C2C2E',
                color: '#FFF',
                border: '1px solid #3A3A3C',
                padding: '10px',
                borderRadius: '10px',
                width: '130px'
              }}
              title="Stream FPS"
            >
              <option value="2">2 FPS</option>
              <option value="3">3 FPS (Empfohlen)</option>
              <option value="5">5 FPS</option>
              <option value="10">10 FPS</option>
            </select>
          </div>

          <div style={{ width: '100%', background: '#000', borderRadius: '12px', overflow: 'hidden', aspectRatio: '4/3', position: 'relative' }}>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: cameraActive ? 'block' : 'none' }}
            />
            {!cameraActive && (
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, display: 'flex', alignItems: 'center', justifyContext: 'center', color: '#8E8E93', fontSize: '0.9rem', width: '100%', justifyContent: 'center' }}>
                Kamera inaktiv
              </div>
            )}
          </div>
          {/* Hidden Canvas used to convert video to image bytes */}
          <canvas ref={canvasRef} style={{ display: 'none' }} />
        </div>

        {/* Tactical Simulator Panel */}
        <div style={{ background: '#1C1C1E', borderRadius: '16px', padding: '20px', border: '1px solid #2C2C35' }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: '1.1rem', color: '#FFF', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={18} style={{ color: '#BF5AF2' }} />
            Battlefield-Simulator
          </h3>
          <p style={{ margin: '0 0 20px 0', fontSize: '0.85rem', color: '#8E8E93', lineHeight: 1.4 }}>
            Platziere virtuelle Karten direkt auf dem Desktop-Spielfeld, um Interaktionen, 3D-Effekte und die KI-Taktiken ohne Kameraaufbau zu testen.
          </p>

          {/* Form */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
            
            {/* Card selector */}
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', color: '#8E8E93', marginBottom: '6px' }}>Karte wählen:</label>
              <select
                value={selectedTemplateIdx}
                onChange={(e) => setSelectedTemplateIdx(Number(e.target.value))}
                style={{
                  width: '100%',
                  background: '#2C2C2E',
                  color: '#FFF',
                  border: '1px solid #3A3A3C',
                  padding: '12px',
                  borderRadius: '10px'
                }}
              >
                {SIMULATED_TEMPLATES.map((item, idx) => (
                  <option key={idx} value={idx}>{item.name} ({item.type})</option>
                ))}
              </select>
            </div>

            {/* Coordinates */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#8E8E93', marginBottom: '6px' }}>X-Position ({sliderX}%):</label>
                <input
                  type="range"
                  min="5"
                  max="90"
                  value={sliderX}
                  onChange={(e) => setSliderX(Number(e.target.value))}
                  style={{ width: '100%' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#8E8E93', marginBottom: '6px' }}>Y-Position ({sliderY}%):</label>
                <input
                  type="range"
                  min="5"
                  max="90"
                  value={sliderY}
                  onChange={(e) => setSliderY(Number(e.target.value))}
                  style={{ width: '100%' }}
                />
              </div>
            </div>

            {/* Tapped & Add button */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '15px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.9rem' }}>
                <input
                  type="checkbox"
                  checked={isTapped}
                  onChange={(e) => setIsTapped(e.target.checked)}
                  style={{ width: '18px', height: '18px' }}
                />
                Getappt ablegen
              </label>

              <button
                onClick={handleAddCardSimulation}
                disabled={!isConnected}
                style={{
                  background: '#30D158',
                  color: '#FFF',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: '10px',
                  fontWeight: 'bold',
                  cursor: isConnected ? 'pointer' : 'not-allowed',
                  opacity: isConnected ? 1 : 0.5
                }}
              >
                Karte platzieren
              </button>
            </div>

          </div>

          {/* Placed cards list */}
          {simulatedCards.length > 0 && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h4 style={{ margin: 0, fontSize: '0.9rem', color: '#8E8E93' }}>Karten auf dem Feld ({simulatedCards.length})</h4>
                <button
                  onClick={handleClearBoard}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#FF453A',
                    cursor: 'pointer',
                    fontSize: '0.85rem'
                  }}
                >
                  Alle entfernen
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '200px', overflowY: 'auto' }}>
                {simulatedCards.map((card) => (
                  <div
                    key={card.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      background: '#2C2C2E',
                      padding: '8px 12px',
                      borderRadius: '8px'
                    }}
                  >
                    <div>
                      <span style={{ fontWeight: '500', fontSize: '0.9rem' }}>{card.name}</span>
                      <span style={{ fontSize: '0.75rem', color: '#8E8E93', marginLeft: '10px' }}>
                        (X: {card.x}%, Y: {card.y}%{card.tapped ? ', tap' : ''})
                      </span>
                    </div>
                    
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        onClick={() => handleToggleCardTapped(card.id)}
                        style={{
                          background: 'rgba(255,255,255,0.06)',
                          border: 'none',
                          color: '#FFF',
                          padding: '4px 8px',
                          borderRadius: '4px',
                          cursor: 'pointer',
                          fontSize: '0.75rem'
                        }}
                      >
                        {card.tapped ? 'Enttappen' : 'Tappen'}
                      </button>
                      <button
                        onClick={() => handleRemoveCard(card.id)}
                        style={{
                          background: 'rgba(255, 69, 58, 0.1)',
                          border: 'none',
                          color: '#FF453A',
                          padding: '4px 8px',
                          borderRadius: '4px',
                          cursor: 'pointer',
                          fontSize: '0.75rem'
                        }}
                      >
                        Löschen
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>

      </div>
    </div>
  );
}

export default MobileCamera;
