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

function Zeile({ karte, gewaehlt, umschalten }) {
  const fehlt = karte.fehlt > 0;
  // Auswählbar ist nur, was auch fehlt -- bei allem anderen gäbe es nichts
  // zu übernehmen, und ein Häkchen ohne Wirkung ist irreführend.
  const waehlbar = fehlt && typeof umschalten === 'function';

  const inhalt = (
    <>
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
    </>
  );

  const rahmen = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '12px',
    padding: '10px 0',
    borderTop: '1px solid var(--border-color)',
  };

  if (!waehlbar) return <div style={rahmen}>{inhalt}</div>;

  // Die ganze Zeile ist das Bedienelement, nicht nur das kleine Kästchen --
  // auf dem Handy trifft man ein 18px-Quadrat kaum.
  return (
    <label style={{ ...rahmen, cursor: 'pointer' }}>
      <input
        type="checkbox"
        checked={gewaehlt}
        onChange={() => umschalten(karte.name)}
        style={{ width: '18px', height: '18px', flexShrink: 0, cursor: 'pointer' }}
      />
      {inhalt}
    </label>
  );
}

function SammlungsAbgleich({ daten, laedt, onUebernehmen, uebernimmt }) {
  // Standardländer sind beliebig austauschbar und werden von den wenigsten
  // Spielern einzeln erfasst -- deshalb standardmässig aus.
  const [mitLaendern, setMitLaendern] = useState(false);
  const [alleZeigen, setAlleZeigen] = useState(false);
  // Abgewählte Karten statt ausgewählter: Der Normalfall ist "alles
  // übernehmen". Würde man die Auswahl sammeln, stünde man vor einer leeren
  // Menge und müsste erst alles ankreuzen, bevor der Knopf etwas tut --
  // mehr Arbeit für den häufigeren Fall.
  const [abgewaehlt, setAbgewaehlt] = useState(() => new Set());

  const umschalten = (name) => {
    setAbgewaehlt((alt) => {
      const neu = new Set(alt);
      if (neu.has(name)) neu.delete(name);
      else neu.add(name);
      return neu;
    });
  };
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

  const gewaehlte = fehlende.filter((k) => !abgewaehlt.has(k.name));
  // Exemplare, nicht Kartennamen: Bei "4x Blitzschlag" sind das vier.
  const gewaehlteExemplare = gewaehlte.reduce((summe, k) => summe + (k.fehlt || 0), 0);
  // "preis" ist der Einzelpreis je Karte (services/bestand.py), der Gesamtwert
  // also Preis mal fehlende Exemplare -- dieselbe Rechnung wie im Backend.
  const gewaehlterWert = gewaehlte.reduce(
    (summe, k) => summe + (parseFloat(k.preis || 0) || 0) * (k.fehlt || 0), 0);
  const alleGewaehlt = abgewaehlt.size === 0;
  // Standardländer stehen nicht in der Liste und lassen sich deshalb auch
  // nicht einzeln abwählen -- für sie gilt weiterhin nur das Häkchen unten.
  const laenderExemplare = mitLaendern ? (daten.standardlaender_fehlend || 0) : 0;
  const nichtsGewaehlt = gewaehlteExemplare === 0 && laenderExemplare === 0;

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
            {/* "Exemplare" statt "Karten": Oben stand "41 Karten fehlen", der
                Aufklapper darunter sagte "Alle 23 fehlenden Karten anzeigen".
                Beides stimmte -- 41 Exemplare verteilt auf 23 verschiedene
                Karten --, las sich aber wie ein Widerspruch. */}
            <strong>{daten.fehlend}</strong>{' '}
            {daten.fehlend === 1 ? 'Exemplar fehlt' : 'Exemplare fehlen'} dir noch
            {fehlende.length > 0 && daten.fehlend !== fehlende.length && (
              <> ({fehlende.length} verschiedene Karten)</>
            )}
            {' '}— zusammen etwa <strong>{formatEuro(daten.fehlender_wert)}</strong>.
          </>
        )}
      </p>

      {daten.standardlaender_fehlend > 0 && (
        <p style={{ margin: '0 0 8px', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
          Dazu {daten.standardlaender_fehlend} Standardländer, die hier nicht mitgerechnet sind.
        </p>
      )}

      {fehlende.length > 0 && onUebernehmen && (
        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: '14px',
          marginTop: '14px', fontSize: '0.85rem',
        }}>
          <button
            type="button"
            className="link-button"
            onClick={() => setAbgewaehlt(new Set())}
            disabled={alleGewaehlt}
            style={{ opacity: alleGewaehlt ? 0.45 : 1 }}
          >
            Alle auswählen
          </button>
          <button
            type="button"
            className="link-button"
            onClick={() => setAbgewaehlt(new Set(fehlende.map((k) => k.name)))}
            disabled={gewaehlte.length === 0}
            style={{ opacity: gewaehlte.length === 0 ? 0.45 : 1 }}
          >
            Keine
          </button>
        </div>
      )}

      {fehlende.length > 0 && (
        <div style={{ marginTop: '10px' }}>
          {sichtbare.map((k) => (
            <Zeile
              key={k.name}
              karte={k}
              gewaehlt={!abgewaehlt.has(k.name)}
              umschalten={onUebernehmen ? umschalten : undefined}
            />
          ))}
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
            disabled={uebernimmt || nichtsGewaehlt}
            onClick={() => onUebernehmen({
              mitStandardlaendern: mitLaendern,
              // Sind alle angekreuzt, wird KEINE Liste mitgeschickt. Das ist
              // nicht dasselbe wie eine Liste mit allen Namen: ohne Liste
              // nimmt der Server, was gerade fehlt. Hat sich die Sammlung
              // zwischenzeitlich geändert, stimmt das -- eine mitgeschickte
              // Liste wäre dann veraltet.
              nurKarten: alleGewaehlt ? null : gewaehlte.map((k) => k.name),
            })}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '10px',
              opacity: nichtsGewaehlt ? 0.5 : 1,
              cursor: nichtsGewaehlt ? 'not-allowed' : 'pointer',
            }}
          >
            {uebernimmt && <span className="spinner" style={{ width: '14px', height: '14px', borderWidth: '2px', margin: 0 }} />}
            {uebernimmt
              ? 'Wird übernommen...'
              : alleGewaehlt
                ? 'Fehlende Karten in die Sammlung übernehmen'
                : `${gewaehlteExemplare} ${gewaehlteExemplare === 1 ? 'Exemplar' : 'Exemplare'} `
                  + `übernehmen — ${formatEuro(gewaehlterWert)}`}
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
