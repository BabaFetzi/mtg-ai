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

function Zeile({ karte, gewaehlt, umschalten, menge, mengeSetzen, mengeOrdnen }) {
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

  // Stückzahl anpassen -- wer erst zwei von vier gekauft hat, übernimmt zwei.
  // Nur sichtbar, wenn überhaupt mehr als eines fehlt: bei einem einzelnen
  // Exemplar gäbe es nichts einzustellen, und ein Feld ohne Wahl ist Ballast.
  const mengenfeld = waehlbar && karte.fehlt > 1 && typeof mengeSetzen === 'function' && (
    <input
      type="number"
      min="1"
      max={karte.fehlt}
      value={menge}
      aria-label={`Anzahl für ${karte.name}`}
      disabled={!gewaehlt}
      onClick={(e) => e.preventDefault()}
      onChange={(e) => mengeSetzen(karte.name, e.target.value)}
      onBlur={() => mengeOrdnen(karte.name)}
      style={{
        width: '58px', padding: '4px 6px', textAlign: 'right', flexShrink: 0,
        border: '1px solid var(--border-color)', borderRadius: '6px',
        background: 'transparent', color: 'inherit',
        opacity: gewaehlt ? 1 : 0.4,
      }}
    />
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
      {mengenfeld}
    </label>
  );
}

const NEUER_ORDNER = '__neu__';

function SammlungsAbgleich({ daten, laedt, onUebernehmen, uebernimmt, ordnerliste, standardOrdner }) {
  // Standardländer sind beliebig austauschbar und werden von den wenigsten
  // Spielern einzeln erfasst -- deshalb standardmässig aus.
  const [mitLaendern, setMitLaendern] = useState(false);
  const [alleZeigen, setAlleZeigen] = useState(false);
  // Abgewählte Karten statt ausgewählter: Der Normalfall ist "alles
  // übernehmen". Würde man die Auswahl sammeln, stünde man vor einer leeren
  // Menge und müsste erst alles ankreuzen, bevor der Knopf etwas tut --
  // mehr Arbeit für den häufigeren Fall.
  const [abgewaehlt, setAbgewaehlt] = useState(() => new Set());

  // Nur die ABWEICHENDEN Stückzahlen. Wer nichts verstellt, steht nicht drin --
  // dann gilt "alles, was fehlt", und das bleibt richtig, auch wenn sich die
  // Sammlung zwischenzeitlich ändert.
  const [mengen, setMengen] = useState(() => ({}));
  const [ordner, setOrdner] = useState(null);   // null = Vorbelegung (Deckname)
  const [neuerOrdner, setNeuerOrdner] = useState('');

  const umschalten = (name) => {
    setAbgewaehlt((alt) => {
      const neu = new Set(alt);
      if (neu.has(name)) neu.delete(name);
      else neu.add(name);
      return neu;
    });
  };

  // Gespeichert wird die EINGABE, nicht die fertige Zahl.
  //
  // Der Unterschied ist kein Feinschliff: Wird bei jedem Tastendruck gerundet
  // und der Zustand bei leerem Feld gelöscht, springt die Anzeige beim Leeren
  // sofort auf die volle Zahl zurück. Wer dann "1" tippt, steht vor "31" --
  // und das wird auf 3 gedeckelt. Man kann die Zahl also gar nicht
  // verkleinern, obwohl genau das der Zweck des Feldes ist.
  //
  // Deshalb: beim Tippen nur merken, beim Verlassen des Feldes ordnen.
  const mengeSetzen = (name, roh) => {
    setMengen((alt) => ({ ...alt, [name]: roh }));
  };

  const mengeOrdnen = (name) => {
    const karte = (daten?.karten || []).find((k) => k.name === name);
    const hoechstens = karte?.fehlt || 1;

    setMengen((alt) => {
      const zahl = parseInt(alt[name], 10);
      const neu = { ...alt };
      // Leer oder Unsinn heisst "wieder alles" -- der Eintrag verschwindet,
      // und damit gilt wieder die volle fehlende Menge.
      if (!Number.isFinite(zahl)) delete neu[name];
      else neu[name] = String(Math.max(1, Math.min(hoechstens, zahl)));
      return neu;
    });
  };

  // Was im Feld steht (Zeichenkette, damit man es leeren kann).
  const mengeAnzeige = (karte) =>
    mengen[karte.name] !== undefined ? mengen[karte.name] : String(karte.fehlt || 0);

  // Womit gerechnet wird. Immer gedeckelt -- die Anzeige darf nie mehr
  // versprechen, als der Server anlegt.
  const mengeVon = (karte) => {
    const zahl = parseInt(mengen[karte.name], 10);
    if (!Number.isFinite(zahl)) return karte.fehlt || 0;
    return Math.max(0, Math.min(karte.fehlt || 0, zahl));
  };

  // Wirklich verstellt ist nur, was von der fehlenden Menge ABWEICHT. Ein Feld
  // anzutippen und wieder auf denselben Wert zu setzen, darf nicht dazu
  // führen, dass eine Liste mitgeschickt wird.
  const verstellt = (karte) => mengeVon(karte) !== (karte.fehlt || 0);

  // Wohin die Karten wandern. Vorbelegt ist der Deckname -- das bisherige
  // Verhalten, damit sich für niemanden etwas ändert, der nichts anfasst.
  const vorbelegung = standardOrdner || '';
  const zielordner = ordner === NEUER_ORDNER
    ? neuerOrdner.trim()
    : (ordner ?? vorbelegung);
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
  // Exemplare, nicht Kartennamen: Bei "4x Blitzschlag" sind das vier -- oder
  // weniger, wenn die Stückzahl von Hand verringert wurde.
  const gewaehlteExemplare = gewaehlte.reduce((summe, k) => summe + mengeVon(k), 0);
  // "preis" ist der Einzelpreis je Karte (services/bestand.py), der Gesamtwert
  // also Preis mal übernommene Exemplare -- dieselbe Rechnung wie im Backend.
  const gewaehlterWert = gewaehlte.reduce(
    (summe, k) => summe + (parseFloat(k.preis || 0) || 0) * mengeVon(k), 0);
  // "Unverändert" heisst: nichts abgewählt UND keine Stückzahl verstellt. Nur
  // dann darf ohne Liste übernommen werden.
  const alleGewaehlt = abgewaehlt.size === 0 && !fehlende.some(verstellt);
  // Standardländer stehen nicht in der Liste und lassen sich deshalb auch
  // nicht einzeln abwählen -- für sie gilt weiterhin nur das Häkchen unten.
  const laenderExemplare = mitLaendern ? (daten.standardlaender_fehlend || 0) : 0;
  const nichtsGewaehlt = gewaehlteExemplare === 0 && laenderExemplare === 0;
  // "Neuer Ordner" ohne Namen: Ohne diese Prüfung fiele der Zielordner still
  // auf den Decknamen zurück, und die Karten lägen woanders als erwartet.
  const ordnerFehlt = ordner === NEUER_ORDNER && !neuerOrdner.trim();

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
              menge={mengeAnzeige(k)}
              mengeSetzen={onUebernehmen ? mengeSetzen : undefined}
              mengeOrdnen={mengeOrdnen}
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
        }}>
          {/* Zielordner. Steht ÜBER dem Knopf, weil man die Frage "wohin?"
              beantwortet haben will, bevor man auslöst -- danach ist es zu
              spät. */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '10px',
            flexWrap: 'wrap', marginBottom: '16px',
          }}>
            <label htmlFor="abgleich-ordner" style={{ fontSize: '0.88rem', color: 'var(--text-muted)' }}>
              Ordner:
            </label>
            <select
              id="abgleich-ordner"
              value={ordner ?? vorbelegung}
              onChange={(e) => setOrdner(e.target.value)}
              style={{
                padding: '7px 10px', borderRadius: '8px',
                border: '1px solid var(--border-color)',
                background: 'transparent', color: 'inherit', maxWidth: '18rem',
              }}
            >
              {/* Der Deckname zuerst und immer dabei -- auch wenn es den
                  Ordner noch gar nicht gibt. Er wird beim Übernehmen
                  angelegt, so wie bisher. */}
              {vorbelegung && <option value={vorbelegung}>{vorbelegung}</option>}
              {(ordnerliste || [])
                .filter((o) => o && o !== vorbelegung)
                .map((o) => <option key={o} value={o}>{o}</option>)}
              <option value={NEUER_ORDNER}>Neuer Ordner…</option>
            </select>

            {ordner === NEUER_ORDNER && (
              <input
                type="text"
                value={neuerOrdner}
                autoFocus
                placeholder="Name des Ordners"
                aria-label="Name des neuen Ordners"
                onChange={(e) => setNeuerOrdner(e.target.value)}
                style={{
                  padding: '7px 10px', borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                  background: 'transparent', color: 'inherit', minWidth: '12rem',
                }}
              />
            )}
          </div>

        <div style={{
          display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap',
        }}>
          <button
            type="button"
            className="primary-btn"
            disabled={uebernimmt || nichtsGewaehlt || ordnerFehlt}
            onClick={() => onUebernehmen({
              mitStandardlaendern: mitLaendern,
              // Sind alle angekreuzt und keine Stückzahl verstellt, wird KEINE
              // Liste mitgeschickt. Das ist nicht dasselbe wie eine Liste mit
              // allen Namen: ohne Liste nimmt der Server, was gerade fehlt.
              // Hat sich die Sammlung zwischenzeitlich geändert, stimmt das --
              // eine mitgeschickte Liste wäre dann veraltet.
              nurKarten: alleGewaehlt ? null : gewaehlte.map((k) => (
                verstellt(k)
                  ? { name: k.name, anzahl: mengeVon(k) }  // genau so viele
                  : k.name                                 // alles, was fehlt
              )),
              ordner: zielordner,
            })}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '10px',
              opacity: nichtsGewaehlt || ordnerFehlt ? 0.5 : 1,
              cursor: nichtsGewaehlt || ordnerFehlt ? 'not-allowed' : 'pointer',
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
