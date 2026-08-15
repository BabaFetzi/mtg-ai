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
      className="meldungs-liste"
      // role="status" statt "alert": Screenreader unterbrechen den Nutzer nicht
      // mitten im Satz, lesen die Meldung aber vor.
      role="status"
      aria-live="polite"
    >
      {meldungen.map((m) => (
        <div key={m.id} className={`meldung meldung-${m.art}`}>
          <span className="meldung-text">{m.text}</span>
          <button
            type="button"
            className="meldung-schliessen"
            onClick={() => entfernen(m.id)}
            aria-label="Meldung schliessen"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

function Rueckfrage({ frage, antworten }) {
  const knopf = useRef(null);
  // Fokus in den Dialog holen, damit Enter und Tab dort landen.
  useEffect(() => { knopf.current?.focus(); }, []);

  return (
    <div className="rueckfrage-hintergrund" onClick={() => antworten(false)}>
      <div
        className="rueckfrage"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="rueckfrage-titel"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="rueckfrage-titel" className="rueckfrage-titel">{frage.titel}</h3>
        {frage.text && <p className="rueckfrage-text">{frage.text}</p>}
        <div className="rueckfrage-knoepfe">
          <button type="button" className="secondary-btn" onClick={() => antworten(false)}>
            {frage.abbrechenText}
          </button>
          <button
            type="button"
            ref={knopf}
            className={frage.gefaehrlich ? 'gefahr-btn' : 'primary-btn'}
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
