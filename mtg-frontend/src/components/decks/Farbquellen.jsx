import { formatZahl } from '../../utils/format';

/**
 * Farbquellen gegen Farbbedarf.
 *
 * Die häufigste Ursache dafür, dass ein durchdachtes Deck trotzdem verliert:
 * zu wenige Länder einer Farbe. Eine Karte mit {R}{R}{R} auf Zug 3 braucht
 * deutlich mehr rote Quellen als eine mit einem einzelnen {R} auf Zug 4 -- das
 * sieht man einer Deckliste nicht an.
 *
 * Die Zahlen kommen aus einer Rechnung (hypergeometrische Verteilung über die
 * bis dahin gesehenen Karten), nicht aus einer Faustregel. Deshalb steht die
 * Annahme auch sichtbar unter der Tabelle.
 */

const SYMBOL = {
  W: 'https://svgs.scryfall.io/card-symbols/W.svg',
  U: 'https://svgs.scryfall.io/card-symbols/U.svg',
  B: 'https://svgs.scryfall.io/card-symbols/B.svg',
  R: 'https://svgs.scryfall.io/card-symbols/R.svg',
  G: 'https://svgs.scryfall.io/card-symbols/G.svg',
};

function prozent(wert) {
  const p = (Number(wert) || 0) * 100;
  // Gerundet würden aus 99,8 Prozent glatte "100 %" -- eine Sicherheit, die
  // es nicht gibt. Dasselbe umgekehrt: 0,4 Prozent sind nicht "0 %".
  if (p >= 99.5 && p < 100) return 'über 99 %';
  if (p > 0 && p < 0.5) return 'unter 1 %';
  return `${formatZahl(p, 0)} %`;
}

function Zeile({ farbe }) {
  const knapp = !farbe.reicht;
  const anteil = farbe.empfohlene_laender > 0
    ? Math.min(100, (farbe.laender / farbe.empfohlene_laender) * 100)
    : 100;

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'auto minmax(0, 1fr) auto',
      alignItems: 'center',
      gap: '14px',
      padding: '14px 0',
      borderTop: '1px solid var(--border-color)',
    }}>
      {/* Bei einer Hybridanforderung stehen beide Symbole nebeneinander:
          {U/R} ist EINE Anforderung an den gemeinsamen Vorrat, nicht zwei. */}
      <span style={{ display: 'flex', gap: '3px' }}>
        {(farbe.farben || [farbe.farbe]).map((f) => (
          <img key={f} src={SYMBOL[f]} alt="" style={{ width: '22px', height: '22px' }} />
        ))}
      </span>

      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', flexWrap: 'wrap' }}>
          <strong>{farbe.laender} Länder</strong>
          {farbe.weitere_quellen > 0 && (
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              + {farbe.weitere_quellen} weitere Quellen
            </span>
          )}
        </div>

        <div style={{
          height: '6px',
          borderRadius: '3px',
          background: 'var(--btn-secondary)',
          margin: '8px 0',
          overflow: 'hidden',
        }}>
          <div style={{
            width: `${anteil}%`,
            height: '100%',
            background: knapp ? 'var(--danger-color)' : 'var(--price-color)',
          }} />
        </div>

        <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          {farbe.haertester_bedarf > 0 ? (
            <>
              Schwerste Anforderung: {farbe.haertester_bedarf}× {farbe.hybrid ? `${farbe.farbname} (eines von beiden)` : farbe.farbname} auf Zug {farbe.zug}
              {farbe.haerteste_karte ? ` (${farbe.haerteste_karte})` : ''} —{' '}
              {prozent(farbe.wahrscheinlichkeit)} Chance, das rechtzeitig zu haben.
            </>
          ) : (
            'Keine Karte im Deck verlangt diese Farbe.'
          )}
        </p>
      </div>

      <div style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
        {!knapp && <div style={{ fontWeight: 700, color: 'var(--price-color)' }}>reicht</div>}

        {/* "empfohlen: 0" wäre sinnlos: erreichbar === false heisst, dass auch
            jedes Land der Farbe nicht reichen würde. Dann hilft keine
            Umverteilung, sondern nur mehr Länder oder eine weniger
            farbintensive Karte. */}
        {knapp && farbe.erreichbar === false && (
          <div style={{ fontWeight: 700, color: 'var(--danger-color)' }}>
            so nicht erreichbar
          </div>
        )}

        {knapp && farbe.erreichbar !== false && (
          <>
            <div style={{ fontWeight: 700, color: 'var(--danger-color)' }}>
              {farbe.fehlende_laender} zu wenig
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              empfohlen: {farbe.empfohlene_laender}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Farbquellen({ daten }) {
  if (!daten || !Array.isArray(daten.farben) || daten.farben.length === 0) return null;

  const knappe = daten.farben.filter((f) => !f.reicht);

  // Zwei einfarbige Anforderungen, deren Empfehlungen zusammen mehr Quellen
  // verlangen, als das Deck Länder hat: dann ist "10 Inseln mehr" kein Rat,
  // den man befolgen kann. Was hilft, sind Länder, die beide Farben liefern.
  const einfarbigKnapp = knappe.filter((f) => !f.hybrid && f.erreichbar !== false);
  const summeEmpfohlen = einfarbigKnapp.reduce((s, f) => s + (f.empfohlene_laender || 0), 0);
  const hinweisMehrfarbig = einfarbigKnapp.length > 1 && summeEmpfohlen > daten.laender_gesamt
    ? `${einfarbigKnapp.map((f) => f.farbname).join(' und ')} bräuchten zusammen `
      + `${summeEmpfohlen} Quellen, das Deck hat aber nur ${daten.laender_gesamt} Länder. `
      + `Mehr Inseln oder Gebirge helfen hier nicht weiter — nötig sind Länder, `
      + `die beide Farben liefern (Duale, Ländersucher), oder weniger farbintensive Karten.`
    : null;

  return (
    <div className="analyse-block" style={{ marginBottom: '40px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '15px', flexWrap: 'wrap' }}>
        <h4 style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.08em', margin: 0 }}>
          Farbquellen
        </h4>
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          {daten.laender_gesamt} Länder in {daten.deckgroesse} Karten
        </span>
      </div>

      <p style={{ margin: '12px 0 4px', color: knappe.length ? 'var(--danger-color)' : 'var(--text-main)' }}>
        {knappe.length === 0
          ? 'Jede Farbe hat genug Quellen für ihre schwerste Anforderung.'
          : `${knappe.length === 1 ? 'Eine Farbe hat' : `${knappe.length} Farben haben`} zu wenige Quellen: ${knappe.map((f) => f.farbname).join(', ')}.`}
      </p>

      {daten.farben.map((f) => <Zeile key={f.schluessel || f.farbe} farbe={f} />)}

      {hinweisMehrfarbig && (
        <p style={{ margin: '10px 0 0', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          {hinweisMehrfarbig}
        </p>
      )}

      <p style={{ margin: '18px 0 0', fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
        Gerechnet wird die Wahrscheinlichkeit, bis zu dem Zug, in dem die Karte
        fällig ist, genug Quellen gezogen zu haben — auf dem Spiel (also eine
        Karte weniger). Starthände mit weniger als zwei oder mehr als fünf
        Ländern gelten als gemulligant, höchstens einmal. Als ausreichend gilt
        ab {prozent(daten.ziel)}. Manasteine und Manakreaturen zählen ab dem Zug
        nach ihren Kosten mit — vorher können sie noch nicht im Spiel sein.
      </p>

      {Array.isArray(daten.nicht_gefunden) && daten.nicht_gefunden.length > 0 && (
        <p style={{ margin: '10px 0 0', fontSize: '0.78rem', color: 'var(--danger-color)' }}>
          Nicht gefunden und daher nicht mitgerechnet: {daten.nicht_gefunden.join(', ')}
        </p>
      )}
    </div>
  );
}

export default Farbquellen;
