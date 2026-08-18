import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

/**
 * Rückmeldungen und Bestätigungen für die ganze App.
 *
 * Ersetzt 63 Aufrufe von window.alert() und einen von window.confirm(). Die
 * nativen Dialoge blockieren die Seite, lassen sich nicht gestalten, zeigen auf
 * dem Handy die technische Herkunftsadresse an ("localhost:5175 sagt:") und
 * wirken bei einem Bezahlprodukt unfertig.
 *
 * Zwei Bausteine:
 *   melde.erfolg / .fehler / .info  -> kurze Einblendung, blockiert nichts
 *   bestaetige({...})               -> Rückfrage, liefert true/false
 */

const MeldungContext = createContext(null);

const ANZEIGEDAUER = { erfolg: 3500, info: 4000, fehler: 7000 };

// ----------------------------------------------------------------------
// Gestaltung: bewusst inline, nicht über CSS-Klassen
// ----------------------------------------------------------------------
// Vorher standen hier Klassennamen (.rueckfrage-hintergrund, .meldungs-liste
// und weitere). Die gab es in keiner Stilvorlage -- im ausgelieferten Paket
// waren es null Treffer. Ergebnis: Die Rückfrage erschien als schmuckloses
// <div> ganz am Ende der Seite, ohne Überlagerung und ohne feste Position.
// Auf einer langen Seite steht sie damit weit unterhalb des Bildschirms.
//
// Für den Nutzer sah das so aus, als täte der Knopf nichts. Betroffen war
// nicht nur eine Stelle, sondern jede Rückfrage der Anwendung -- darunter
// "Konto endgültig löschen" und "Premium-Abo kündigen". Wer kündigen wollte,
// klickte ins Leere.
//
// Die übrige Anwendung gestaltet sich über style={{...}} direkt am Element.
// Genau das wird hier jetzt auch gemacht: Es kann nicht mehr auseinanderfallen,
// weil es keine zweite Datei mehr gibt, die dazu passen müsste. Und es lässt
// sich prüfen -- die Tests laufen mit css:false, eine ausgelagerte Stilvorlage
// wäre dort unsichtbar, ein Inline-Wert steht im DOM.
const FARBEN = {
  erfolg: { rand: '#1a7f37', punkt: '#1a7f37' },
  fehler: { rand: '#c62828', punkt: '#c62828' },
  info:   { rand: '#555e6b', punkt: '#555e6b' },
};

// Über allem: Die Rückfrage blockiert die Bedienung und muss deshalb auch
// über Kartenvorschauen (z-index 1000) und sonstigen Überlagerungen liegen.
const Z_RUECKFRAGE = 12000;
const Z_MELDUNGEN = 11000;

const STIL = {
  hintergrund: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0, 0, 0, 0.55)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '20px',
    zIndex: Z_RUECKFRAGE,
  },
  dialog: {
    background: 'var(--bg-card, #fff)',
    color: 'var(--text-main, #111)',
    borderRadius: '14px',
    padding: '26px',
    width: 'min(30rem, 100%)',
    boxShadow: '0 24px 60px rgba(0, 0, 0, 0.35)',
    textAlign: 'left',
  },
  titel: { margin: '0 0 10px', fontSize: '1.15rem', fontWeight: 700 },
  text: { margin: '0 0 22px', color: 'var(--text-muted, #555)', lineHeight: 1.55 },
  knopfreihe: { display: 'flex', gap: '10px', justifyContent: 'flex-end', flexWrap: 'wrap' },
  liste: {
    position: 'fixed',
    top: '16px',
    right: '16px',
    left: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    zIndex: Z_MELDUNGEN,
    // Die Leiste selbst darf nichts abfangen -- nur die Meldungen darin.
    pointerEvents: 'none',
    maxWidth: 'min(26rem, calc(100vw - 32px))',
  },
};

function knopfStil(art) {
  const gemeinsam = {
    padding: '10px 18px',
    borderRadius: '9px',
    fontSize: '0.95rem',
    fontWeight: 600,
    cursor: 'pointer',
    border: '1px solid transparent',
  };
  if (art === 'gefahr') {
    return { ...gemeinsam, background: '#c62828', color: '#fff' };
  }
  if (art === 'abbrechen') {
    return {
      ...gemeinsam,
      background: 'transparent',
      color: 'var(--text-muted, #555)',
      borderColor: 'var(--border-color, #ccc)',
    };
  }
  return { ...gemeinsam, background: 'var(--text-main, #111)', color: 'var(--bg-card, #fff)' };
}

let zaehler = 0;

export function MeldungProvider({ children }) {
  const [meldungen, setMeldungen] = useState([]);
  const [frage, setFrage] = useState(null);
  const aufloesen = useRef(null);
  const zeitgeber = useRef(new Map());

  const entfernen = useCallback((id) => {
    setMeldungen((alt) => alt.filter((m) => m.id !== id));
    const t = zeitgeber.current.get(id);
    if (t) {
      clearTimeout(t);
      zeitgeber.current.delete(id);
    }
  }, []);

  const zeigen = useCallback((art, text) => {
    if (!text) return;
    const id = ++zaehler;
    setMeldungen((alt) => [...alt, { id, art, text: String(text) }]);
    const t = setTimeout(() => entfernen(id), ANZEIGEDAUER[art] ?? 4000);
    zeitgeber.current.set(id, t);
  }, [entfernen]);

  // Beim Aushängen alle Zeitgeber aufräumen -- sonst laufen sie ins Leere.
  useEffect(() => {
    const offen = zeitgeber.current;
    return () => {
      offen.forEach((t) => clearTimeout(t));
      offen.clear();
    };
  }, []);

  const melde = useMemo(() => ({
    erfolg: (text) => zeigen('erfolg', text),
    fehler: (text) => zeigen('fehler', text),
    info: (text) => zeigen('info', text),
  }), [zeigen]);

  const bestaetige = useCallback((optionen) => {
    const {
      titel = 'Bist du sicher?',
      text = '',
      bestaetigenText = 'Ja, weiter',
      abbrechenText = 'Abbrechen',
      gefaehrlich = false,
    } = typeof optionen === 'string' ? { titel: optionen } : (optionen || {});

    setFrage({ titel, text, bestaetigenText, abbrechenText, gefaehrlich });
    return new Promise((resolve) => { aufloesen.current = resolve; });
  }, []);

  const antworten = useCallback((wert) => {
    setFrage(null);
    if (aufloesen.current) {
      aufloesen.current(wert);
      aufloesen.current = null;
    }
  }, []);

  // Escape bricht die Rückfrage ab -- wie bei einem nativen Dialog erwartet.
  useEffect(() => {
    if (!frage) return undefined;
    const beiTaste = (e) => { if (e.key === 'Escape') antworten(false); };
    window.addEventListener('keydown', beiTaste);
    return () => window.removeEventListener('keydown', beiTaste);
  }, [frage, antworten]);

  const wert = useMemo(() => ({ melde, bestaetige }), [melde, bestaetige]);

  return (
    <MeldungContext.Provider value={wert}>
      {children}
      <MeldungsListe meldungen={meldungen} entfernen={entfernen} />
      {frage && <Rueckfrage frage={frage} antworten={antworten} />}
    </MeldungContext.Provider>
  );
}

function MeldungsListe({ meldungen, entfernen }) {
  if (meldungen.length === 0) return null;
  return (
    <div
      style={STIL.liste}
      // role="status" statt "alert": Screenreader unterbrechen den Nutzer nicht
      // mitten im Satz, lesen die Meldung aber vor.
      role="status"
      aria-live="polite"
    >
      {meldungen.map((m) => {
        const farbe = FARBEN[m.art] || FARBEN.info;
        return (
          <div
            key={m.id}
            data-art={m.art}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '12px',
              background: 'var(--bg-card, #fff)',
              color: 'var(--text-main, #111)',
              borderRadius: '10px',
              borderLeft: `4px solid ${farbe.rand}`,
              padding: '12px 14px',
              boxShadow: '0 10px 28px rgba(0, 0, 0, 0.22)',
              textAlign: 'left',
              // Die Leiste ist durchlässig, die Meldung selbst nicht --
              // sonst liesse sich das Kreuz nicht anklicken.
              pointerEvents: 'auto',
            }}
          >
            <span style={{ flex: 1, fontSize: '0.92rem', lineHeight: 1.45 }}>{m.text}</span>
            <button
              type="button"
              onClick={() => entfernen(m.id)}
              aria-label="Meldung schliessen"
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--text-muted, #666)',
                cursor: 'pointer',
                fontSize: '1.1rem',
                lineHeight: 1,
                padding: '2px 4px',
              }}
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}

function Rueckfrage({ frage, antworten }) {
  const knopf = useRef(null);
  // Fokus in den Dialog holen, damit Enter und Tab dort landen.
  useEffect(() => { knopf.current?.focus(); }, []);

  return (
    <div style={STIL.hintergrund} onClick={() => antworten(false)} data-testid="rueckfrage-hintergrund">
      <div
        style={STIL.dialog}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="rueckfrage-titel"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="rueckfrage-titel" style={STIL.titel}>{frage.titel}</h3>
        {frage.text && <p style={STIL.text}>{frage.text}</p>}
        <div style={STIL.knopfreihe}>
          <button type="button" style={knopfStil('abbrechen')} onClick={() => antworten(false)}>
            {frage.abbrechenText}
          </button>
          <button
            type="button"
            ref={knopf}
            style={knopfStil(frage.gefaehrlich ? 'gefahr' : 'bestaetigen')}
            onClick={() => antworten(true)}
          >
            {frage.bestaetigenText}
          </button>
        </div>
      </div>
    </div>
  );
}

// Notnagel, falls der Provider fehlt. Absichtlich KEIN throw: ein vergessener
// Provider würde dem Nutzer sonst eine weisse Seite zeigen -- deutlich
// schlimmer als eine fehlende Einblendung. Die Rückfrage fällt auf den nativen
// Dialog zurück, damit ein "Wirklich löschen?" nicht stillschweigend als "ja"
// durchgeht. Im Entwicklungsmodus gibt es eine deutliche Warnung.
const NOTNAGEL = {
  melde: {
    erfolg: (t) => console.warn('[Meldung ohne Provider]', t),
    fehler: (t) => console.warn('[Meldung ohne Provider]', t),
    info: (t) => console.warn('[Meldung ohne Provider]', t),
  },
  bestaetige: (optionen) => {
    const titel = typeof optionen === 'string' ? optionen : (optionen?.titel || 'Bist du sicher?');
    const text = typeof optionen === 'string' ? '' : (optionen?.text || '');
    return Promise.resolve(
      typeof window !== 'undefined' && typeof window.confirm === 'function'
        ? window.confirm(text ? `${titel}\n\n${text}` : titel)
        : false
    );
  },
};

/** Zugriff aus jeder Komponente: const { melde, bestaetige } = useMeldung(); */
export function useMeldung() {
  const wert = useContext(MeldungContext);
  if (!wert) {
    if (import.meta.env?.DEV) {
      console.warn('useMeldung ohne <MeldungProvider> -- Meldungen sind hier unsichtbar.');
    }
    return NOTNAGEL;
  }
  return wert;
}

export default MeldungProvider;
