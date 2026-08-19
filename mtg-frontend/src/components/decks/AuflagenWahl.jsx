import { useEffect, useMemo, useState } from 'react';
import { getFallbackCardImage } from '../../utils/scryfallHelpers';

/**
 * Auswahl der Auflage (Edition) einer Karte im Deck.
 *
 * Dieselbe Karte gibt es oft in dutzenden Auflagen. Welche davon im Deck
 * steckt, entscheidet über Bild und Preis -- ein Lightning Bolt aus Alpha
 * kostet das Hundertfache des Nachdrucks. Bisher liess sich das gar nicht
 * angeben; die App zeigte immer den Standarddruck.
 *
 * Zwei Entscheidungen, die hier sichtbar werden:
 *
 * 1. **Nichts wird vorausgewählt.** Wer eine Auflage besitzt, baut deshalb
 *    nicht automatisch vier davon ins Deck -- das wären erfundene Daten. Die
 *    eigenen Auflagen stehen oben und sind markiert, gewählt wird von Hand.
 * 2. **"Keine Festlegung" bleibt jederzeit möglich.** Wer die Auflage nicht
 *    kennt oder es nicht genau nimmt, soll nicht gezwungen werden, irgendeine
 *    anzugeben.
 *
 * Ausschliesslich Inline-Stile: Klassennamen, die es in der CSS-Datei nicht
 * gibt, haben in diesem Projekt schon einmal einen ganzen Dialog unsichtbar
 * gemacht.
 */

const FARBEN = {
  hintergrund: 'rgba(0, 0, 0, 0.75)',
  karte: 'var(--bg-card)',
  rand: 'var(--border-color)',
  gedaempft: 'var(--text-muted)',
  text: 'var(--text-main)',
  besitz: '#30D158',
  warnung: '#FF9F0A',
};

const Z_EBENE = 12500;

function auflageGleich(a, b) {
  if (!a || !b) return false;
  const set = (x) => (x.set || '').toLowerCase();
  if (set(a) !== set(b)) return false;
  const nummer = (x) => (x.sammlernummer || '').toLowerCase();
  if (!nummer(a) || !nummer(b)) return true;
  return nummer(a) === nummer(b);
}

function preisText(auflage) {
  const wert = parseFloat(auflage?.preis);
  if (!Number.isFinite(wert) || wert <= 0) return 'kein Preis hinterlegt';
  return `${wert.toFixed(2)} €`;
}

function AuflagenWahl({ kartenName, aktuell, onWaehlen, onSchliessen }) {
  const [auflagen, setAuflagen] = useState([]);
  const [laedt, setLaedt] = useState(true);
  const [fehler, setFehler] = useState('');
  const [nurEigene, setNurEigene] = useState(false);

  // Der Dialog wird pro Karte neu eingehängt (siehe `key` im DeckEditor),
  // deshalb genügen die Anfangswerte -- kein Zurücksetzen im Effekt, das eine
  // zusätzliche Renderrunde auslösen würde.
  useEffect(() => {
    let abgebrochen = false;

    fetch(`/api/karten/auflagen/${encodeURIComponent(kartenName)}`)
      .then((r) => r.json().catch(() => ({})))
      .then((daten) => {
        if (abgebrochen) return;
        const liste = Array.isArray(daten.auflagen) ? daten.auflagen : [];
        setAuflagen(liste);
        if (!liste.length) {
          // Ehrlich benennen statt eine leere Fläche zu zeigen.
          setFehler(daten.nicht_gefunden
            ? `Zu "${kartenName}" sind keine Auflagen abrufbar.`
            : 'Die Auflagen konnten nicht geladen werden.');
        }
      })
      .catch(() => {
        if (!abgebrochen) setFehler('Die Auflagen konnten nicht geladen werden.');
      })
      .finally(() => {
        if (!abgebrochen) setLaedt(false);
      });

    return () => { abgebrochen = true; };
  }, [kartenName]);

  const eigeneAnzahl = useMemo(
    () => auflagen.filter((a) => (a.besitzt || 0) > 0).length,
    [auflagen]
  );

  const sichtbar = useMemo(() => {
    // Eigene Auflagen zuerst -- danach die Reihenfolge von Scryfall (neueste
    // Sets zuerst), die für die Suche nach einer bestimmten Edition die
    // brauchbarste ist.
    const sortiert = [...auflagen].sort(
      (a, b) => (b.besitzt || 0 ? 1 : 0) - (a.besitzt || 0 ? 1 : 0)
    );
    return nurEigene ? sortiert.filter((a) => (a.besitzt || 0) > 0) : sortiert;
  }, [auflagen, nurEigene]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Auflage wählen für ${kartenName}`}
      data-testid="auflagen-hintergrund"
      onClick={onSchliessen}
      style={{
        position: 'fixed', inset: 0, background: FARBEN.hintergrund,
        backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: Z_EBENE, padding: '20px',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: FARBEN.karte, border: `1px solid ${FARBEN.rand}`,
          borderRadius: '20px', padding: '26px', width: 'min(920px, 100%)',
          maxHeight: '86vh', display: 'flex', flexDirection: 'column', gap: '18px',
          boxShadow: '0 20px 60px rgba(0,0,0,0.35)', color: FARBEN.text,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '16px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.3rem' }}>Auflage wählen</h3>
            <p style={{ margin: '6px 0 0', fontSize: '0.9rem', color: FARBEN.gedaempft, lineHeight: 1.5 }}>
              {kartenName} — die Auflage bestimmt Bild und Preis im Deck.
              Für den Abgleich mit deiner Sammlung zählt weiterhin jede Auflage.
            </p>
          </div>
          <button
            type="button"
            onClick={onSchliessen}
            aria-label="Schliessen"
            style={{
              background: 'transparent', border: 'none', color: FARBEN.gedaempft,
              fontSize: '1.5rem', lineHeight: 1, cursor: 'pointer', padding: '0 4px',
            }}
          >
            ×
          </button>
        </div>

        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
          {eigeneAnzahl > 0 && (
            <button
              type="button"
              onClick={() => setNurEigene((v) => !v)}
              style={{
                padding: '7px 14px', fontSize: '0.85rem', borderRadius: '16px',
                cursor: 'pointer', width: 'auto',
                border: `1px solid ${nurEigene ? FARBEN.besitz : FARBEN.rand}`,
                background: nurEigene ? FARBEN.besitz : 'transparent',
                color: nurEigene ? '#fff' : FARBEN.text,
              }}
            >
              Nur aus meiner Sammlung ({eigeneAnzahl})
            </button>
          )}
          {aktuell?.set && (
            <button
              type="button"
              onClick={() => onWaehlen(null)}
              style={{
                padding: '7px 14px', fontSize: '0.85rem', borderRadius: '16px',
                cursor: 'pointer', width: 'auto', border: `1px solid ${FARBEN.rand}`,
                background: 'transparent', color: FARBEN.text,
              }}
            >
              Festlegung aufheben
            </button>
          )}
        </div>

        <div style={{ overflowY: 'auto', flexGrow: 1, minHeight: 0 }}>
          {laedt && (
            <div style={{ padding: '40px 0', textAlign: 'center', color: FARBEN.gedaempft }}>
              Auflagen werden geladen …
            </div>
          )}

          {!laedt && fehler && (
            <div style={{ padding: '30px 0', textAlign: 'center', color: FARBEN.warnung, lineHeight: 1.6 }}>
              {fehler}
              <div style={{ color: FARBEN.gedaempft, fontSize: '0.88rem', marginTop: '8px' }}>
                Deine bisherige Auswahl bleibt unverändert.
              </div>
            </div>
          )}

          {!laedt && !fehler && (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
              gap: '16px',
            }}>
              {sichtbar.map((auflage) => {
                const gewaehlt = auflageGleich(auflage, aktuell);
                const besitzt = auflage.besitzt || 0;
                return (
                  <button
                    key={auflage.id || `${auflage.set}-${auflage.sammlernummer}`}
                    type="button"
                    onClick={() => onWaehlen(auflage)}
                    style={{
                      display: 'flex', flexDirection: 'column', gap: '8px', width: '100%',
                      padding: '10px', borderRadius: '14px', cursor: 'pointer',
                      textAlign: 'left', background: 'var(--bg-main)',
                      border: `2px solid ${gewaehlt ? 'var(--accent-color)' : (besitzt ? FARBEN.besitz : 'transparent')}`,
                      color: FARBEN.text,
                    }}
                  >
                    {/* Fällt ein Kartenbild aus, tritt derselbe Platzhalter ein
                        wie überall sonst in der App. Ohne ihn bliebe an dieser
                        Stelle eine leere Fläche -- ausgerechnet in einem Dialog,
                        in dem man nach dem Bild auswählt. */}
                    <img
                      src={auflage.bild_url || getFallbackCardImage(kartenName, auflage.set_name)}
                      alt={`${kartenName}, ${auflage.set_name || auflage.set}`}
                      loading="lazy"
                      onError={(e) => {
                        e.target.onerror = null;
                        e.target.src = getFallbackCardImage(kartenName, auflage.set_name);
                      }}
                      style={{ width: '100%', borderRadius: '4.75% / 3.5%', display: 'block' }}
                    />

                    <div style={{ fontSize: '0.82rem', fontWeight: 600, lineHeight: 1.3 }}>
                      {auflage.set_name || (auflage.set || '').toUpperCase()}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: FARBEN.gedaempft }}>
                      {(auflage.set || '').toUpperCase()}
                      {auflage.sammlernummer ? ` · ${auflage.sammlernummer}` : ''}
                    </div>
                    <div style={{ fontSize: '0.8rem', fontVariantNumeric: 'tabular-nums' }}>
                      {preisText(auflage)}
                    </div>
                    {besitzt > 0 && (
                      <div style={{
                        fontSize: '0.72rem', fontWeight: 700, color: '#fff',
                        background: FARBEN.besitz, borderRadius: '10px',
                        padding: '3px 9px', alignSelf: 'flex-start',
                      }}>
                        {besitzt}× in deiner Sammlung
                      </div>
                    )}
                    {gewaehlt && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--accent-color)', fontWeight: 700 }}>
                        Aktuell im Deck
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default AuflagenWahl;
