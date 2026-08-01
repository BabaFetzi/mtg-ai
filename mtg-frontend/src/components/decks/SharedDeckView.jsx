import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';

/**
 * Öffentliche, schreibgeschützte Ansicht eines geteilten Decks.
 *
 * Bewusst OHNE Login erreichbar (siehe App.jsx: /shared/decks/:id umgeht den
 * Login-Gate). Nutzt nur den öffentlichen, read-only Endpunkt
 * /api/v1/shared/decks/{id}, der keine privaten Daten preisgibt.
 */
function SharedDeckView() {
  const { id } = useParams();
  const [deck, setDeck] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ok | notfound | error

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/v1/shared/decks/${id}`);
        if (res.status === 404) { if (!cancelled) setStatus('notfound'); return; }
        if (!res.ok) { if (!cancelled) setStatus('error'); return; }
        const data = await res.json();
        if (!cancelled) { setDeck(data); setStatus('ok'); }
      } catch {
        if (!cancelled) setStatus('error');
      }
    })();
    return () => { cancelled = true; };
  }, [id]);

  // Deckliste in Zeilen mit Anzahl + Name parsen (rein zur Anzeige).
  const parseLines = (liste) => {
    if (!liste) return [];
    return liste.split('\n').map(l => l.trim()).filter(Boolean).map(line => {
      const m = line.match(/^(\d+)[xX]?\s+(.+)$/);
      if (m) return { count: parseInt(m[1], 10), name: m[2].trim() };
      return { count: 1, name: line };
    });
  };

  const cards = deck ? parseLines(deck.liste) : [];
  const total = cards.reduce((acc, c) => acc + (c.count || 1), 0);

  const copyList = () => {
    if (!deck?.liste) return;
    navigator.clipboard?.writeText(deck.liste);
    alert('Deckliste in die Zwischenablage kopiert!');
  };

  const wrapStyle = { maxWidth: '760px', margin: '0 auto', padding: '48px 20px', fontFamily: 'inherit' };

  if (status === 'loading') {
    return <div style={wrapStyle}><div className="spinner"></div><p style={{ color: 'var(--text-muted)', marginTop: 15 }}>Deck wird geladen…</p></div>;
  }
  if (status === 'notfound') {
    return <div style={wrapStyle}><h2>Deck nicht gefunden</h2><p style={{ color: 'var(--text-muted)' }}>Dieses geteilte Deck existiert nicht (mehr).</p><a href="/" style={{ color: 'var(--accent-color)' }}>Zur Startseite</a></div>;
  }
  if (status === 'error') {
    return <div style={wrapStyle}><h2>Fehler</h2><p style={{ color: 'var(--text-muted)' }}>Das Deck konnte nicht geladen werden. Bitte später erneut versuchen.</p></div>;
  }

  return (
    <div style={wrapStyle}>
      <p style={{ textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '6px' }}>
        Geteiltes Deck · {(deck.format || 'commander')}
      </p>
      <h1 style={{ fontSize: '2.2rem', margin: '0 0 6px' }}>{deck.name || 'Unbenanntes Deck'}</h1>
      <p style={{ color: 'var(--text-muted)', margin: '0 0 24px' }}>
        von {deck.besitzer || 'unbekannt'} · {total} {total === 1 ? 'Karte' : 'Karten'}
      </p>

      <button className="primary-btn" onClick={copyList} style={{ marginBottom: '28px', padding: '10px 20px' }}>
        Deckliste kopieren
      </button>

      {cards.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>Dieses Deck enthält keine Karten.</p>
      ) : (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border-color)',
          borderRadius: '16px', padding: '20px 24px'
        }}>
          {cards.map((c, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', gap: '12px',
              padding: '7px 0', borderBottom: i < cards.length - 1 ? '1px solid var(--border-color)' : 'none'
            }}>
              <span style={{ color: 'var(--text-main)' }}>{c.name}</span>
              <span style={{ color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>×{c.count}</span>
            </div>
          ))}
        </div>
      )}

      <p style={{ marginTop: '32px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
        Erstellt mit Grana · <a href="/" style={{ color: 'var(--accent-color)' }}>Eigene Sammlung starten</a>
      </p>
    </div>
  );
}

export default SharedDeckView;
