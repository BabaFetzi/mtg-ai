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
  return `${formatZahl((Number(wert) || 0) * 100, 0)} %`;
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
      <img src={SYMBOL[farbe.farbe]} alt={farbe.farbname} style={{ width: '22px', height: '22px' }} />

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
              Schwerste Anforderung: {farbe.haertester_bedarf}× {farbe.farbname} auf Zug {farbe.zug}
              {farbe.haerteste_karte ? ` (${farbe.haerteste_karte})` : ''} —{' '}
              {prozent(farbe.wahrscheinlichkeit)} Chance, das rechtzeitig zu haben.
            </>
          ) : (
            'Keine Karte im Deck verlangt diese Farbe.'
          )}
        </p>
      </div>

      <div style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
        {knapp ? (
          <>
            <div style={{ fontWeight: 700, color: 'var(--danger-color)' }}>
              {farbe.fehlende_laender} zu wenig
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              empfohlen: {farbe.empfohlene_laender}
            </div>
          </>
        ) : (
          <div style={{ fontWeight: 700, color: 'var(--price-color)' }}>reicht</div>
        )}
      </div>
    </div>
  );
}

function Farbquellen({ daten }) {
  if (!daten || !Array.isArray(daten.farben) || daten.farben.length === 0) return null;

  const knappe = daten.farben.filter((f) => !f.reicht);

  return (
    <div style={{
      background: 'rgba(0, 0, 0, 0.15)',
      border: '1px solid var(--border-color)',
      borderRadius: '20px',
      padding: '30px',
      marginBottom: '40px',
    }}>
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

      {daten.farben.map((f) => <Zeile key={f.farbe} farbe={f} />)}

      <p style={{ margin: '18px 0 0', fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
        Gerechnet wird die Wahrscheinlichkeit, bis zu dem Zug, in dem die Karte
        fällig ist, genug Quellen gezogen zu haben — auf dem Spiel (also eine
        Karte weniger) und ohne Mulligan. Als ausreichend gilt ab
        {' '}{prozent(daten.ziel)}. Manasteine und Manakreaturen sind getrennt
        ausgewiesen: sie müssen erst gespielt werden und zählen deshalb nicht in
        die Rechnung.
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
