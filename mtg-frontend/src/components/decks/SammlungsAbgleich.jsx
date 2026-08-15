import { useState } from 'react';
import { formatEuro } from '../../utils/format';

/**
 * Deckliste gegen die eigene Sammlung.
 *
 * Die Frage, die sich bei jedem neuen Deck stellt: was davon habe ich schon,
 * was muss ich noch besorgen und was kostet das? Bisher musste man dafür jede
 * Karte einzeln in der Sammlung nachschlagen.
 */

// So viele fehlende Karten stehen ohne Aufklappen da.
const GEKUERZT = 12;

function Zeile({ karte }) {
  const fehlt = karte.fehlt > 0;
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '12px',
      padding: '10px 0',
      borderTop: '1px solid var(--border-color)',
    }}>
      <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {karte.name}
        {karte.standardland && (
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginLeft: '8px' }}>
            Standardland
          </span>
        )}
        {!karte.gefunden && (
          <span style={{ fontSize: '0.78rem', color: 'var(--danger-color)', marginLeft: '8px' }}>
            nicht gefunden
          </span>
        )}
      </span>

      <span style={{
        whiteSpace: 'nowrap',
        fontWeight: 600,
        color: fehlt ? 'var(--danger-color)' : 'var(--price-color)',
      }}>
        {karte.vorhanden} / {karte.benoetigt}
        {fehlt && <span style={{ fontWeight: 400, marginLeft: '8px' }}>{karte.fehlt} fehlen</span>}
      </span>
    </div>
  );
}

function SammlungsAbgleich({ daten, laedt, onUebernehmen, uebernimmt }) {
  // Standardländer sind beliebig austauschbar und werden von den wenigsten
  // Spielern einzeln erfasst -- deshalb standardmässig aus.
  const [mitLaendern, setMitLaendern] = useState(false);
  const [alleZeigen, setAlleZeigen] = useState(false);
  if (laedt) {
    return (
      <div className="analyse-block" style={{ marginBottom: '40px', textAlign: 'center' }}>
        <div className="spinner" />
        <p style={{ marginTop: '15px', color: 'var(--text-muted)' }}>Sammlung wird abgeglichen...</p>
      </div>
    );
  }

  if (!daten || !Array.isArray(daten.karten) || daten.karten.length === 0) return null;

  const fehlende = daten.karten.filter((k) => k.fehlt > 0 && !k.standardland);
  // Bei 41 fehlenden Karten wird die Seite sonst zur Endlosliste.
  const sichtbare = alleZeigen ? fehlende : fehlende.slice(0, GEKUERZT);

  return (
    <div className="analyse-block" style={{ marginBottom: '40px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '15px', flexWrap: 'wrap' }}>
        <h4 style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.08em', margin: 0 }}>
          Abgleich mit deiner Sammlung
        </h4>
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          {daten.vorhanden} von {daten.benoetigt} Karten vorhanden
        </span>
      </div>

      <p style={{ margin: '12px 0 4px' }}>
        {daten.fehlend === 0 ? (
          <span style={{ color: 'var(--price-color)', fontWeight: 600 }}>
            Du besitzt alle Karten dieses Decks.
          </span>
        ) : (
          <>
            <strong>{daten.fehlend}</strong> {daten.fehlend === 1 ? 'Karte fehlt' : 'Karten fehlen'} dir noch —
            {' '}zusammen etwa <strong>{formatEuro(daten.fehlender_wert)}</strong>.
          </>
        )}
      </p>

      {daten.standardlaender_fehlend > 0 && (
        <p style={{ margin: '0 0 8px', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
          Dazu {daten.standardlaender_fehlend} Standardländer, die hier nicht mitgerechnet sind.
        </p>
      )}

      {fehlende.length > 0 && (
        <div style={{ marginTop: '10px' }}>
          {sichtbare.map((k) => <Zeile key={k.name} karte={k} />)}
          {fehlende.length > GEKUERZT && (
            <button
              type="button"
              className="link-button"
              onClick={() => setAlleZeigen((z) => !z)}
              style={{ marginTop: '12px' }}
            >
              {alleZeigen
                ? 'Weniger anzeigen'
                : `Alle ${fehlende.length} fehlenden Karten anzeigen`}
            </button>
          )}
        </div>
      )}

      {/* Die fehlenden Karten in die Sammlung übernehmen. Ergänzt werden genau
          die fehlenden Exemplare -- zweimal Drücken ändert beim zweiten Mal
          nichts. */}
      {onUebernehmen && (daten.fehlend > 0 || daten.standardlaender_fehlend > 0) && (
        <div style={{
          marginTop: '20px', paddingTop: '18px', borderTop: '1px solid var(--border-color)',
          display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap',
        }}>
          <button
            type="button"
            className="primary-btn"
            disabled={uebernimmt}
            onClick={() => onUebernehmen({ mitStandardlaendern: mitLaendern })}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '10px' }}
          >
            {uebernimmt && <span className="spinner" style={{ width: '14px', height: '14px', borderWidth: '2px', margin: 0 }} />}
            {uebernimmt ? 'Wird übernommen...' : 'Fehlende Karten in die Sammlung übernehmen'}
          </button>

          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.88rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={mitLaendern}
              onChange={(e) => setMitLaendern(e.target.checked)}
              style={{ width: '18px', height: '18px', cursor: 'pointer' }}
            />
            Standardländer mit übernehmen
          </label>
        </div>
      )}

      <p style={{ margin: '18px 0 0', fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
        Gezählt werden die Exemplare in deinen Ordnern, unabhängig von Ausgabe
        und Sprache. Der Betrag ist der aktuelle Marktpreis der fehlenden
        Karten, ohne Standardländer.
      </p>
    </div>
  );
}

export default SammlungsAbgleich;
