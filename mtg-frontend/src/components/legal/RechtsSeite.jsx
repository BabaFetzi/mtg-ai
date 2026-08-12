import { Link } from 'react-router-dom';
import { RECHTSSTAND, betreiberAngabenVollstaendig } from './betreiber';

/**
 * Gemeinsamer Rahmen für Impressum, Datenschutz und AGB.
 *
 * Bewusst schlicht und ohne eigene Navigation: Rechtstexte müssen auch dann
 * lesbar sein, wenn niemand angemeldet ist -- Stripe und die Aufsichtsbehörden
 * erwarten sie öffentlich erreichbar.
 */
function RechtsSeite({ titel, untertitel, children }) {
  const unvollstaendig = !betreiberAngabenVollstaendig();

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-main)', color: 'var(--text-main)' }}>
      <div style={{ maxWidth: '52rem', margin: '0 auto', padding: 'clamp(32px, 7vw, 72px) 20px 80px' }}>

        <Link
          to="/"
          style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textDecoration: 'none' }}
        >
          ← Zurück zu Grana
        </Link>

        <h1 style={{
          fontSize: 'clamp(1.8rem, 6vw, 2.6rem)', fontWeight: 800, letterSpacing: '-0.02em',
          margin: '24px 0 8px', overflowWrap: 'break-word'
        }}>
          {titel}
        </h1>
        {untertitel && (
          <p style={{ color: 'var(--text-muted)', margin: '0 0 8px', fontSize: '1.02rem' }}>
            {untertitel}
          </p>
        )}
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', margin: '0 0 36px' }}>
          Stand: {RECHTSSTAND}
        </p>

        {/* Nur in der Entwicklung sichtbar: erinnert daran, dass die
            Betreiberangaben noch Platzhalter sind. Auf der veröffentlichten
            Seite hat so ein Hinweis nichts zu suchen. */}
        {unvollstaendig && import.meta.env.DEV && (
          <div style={{
            border: '1px solid #B2601A', background: 'rgba(178, 96, 26, 0.12)',
            borderRadius: '10px', padding: '14px 16px', marginBottom: '32px', fontSize: '0.92rem'
          }}>
            <strong>Nur in der Entwicklung sichtbar:</strong> In{' '}
            <code>src/components/legal/betreiber.js</code> stehen noch Platzhalter.
            Diese müssen vor der Veröffentlichung durch die echten Angaben ersetzt werden.
          </div>
        )}

        <div className="rechtstext">{children}</div>

        <p style={{
          marginTop: '56px', paddingTop: '20px', borderTop: '1px solid var(--border-color)',
          color: 'var(--text-muted)', fontSize: '0.85rem'
        }}>
          Dieser Text ist ein sorgfältig erstellter Entwurf und ersetzt keine
          Rechtsberatung. Lass ihn vor der Veröffentlichung von einer Anwältin
          oder einem Anwalt prüfen.
        </p>
      </div>
    </div>
  );
}

/** Abschnittsüberschrift mit Nummer -- erleichtert das Verweisen im Support. */
export function Abschnitt({ nummer, titel, children }) {
  return (
    <section style={{ marginBottom: '36px' }}>
      <h2 style={{
        fontSize: '1.15rem', fontWeight: 700, margin: '0 0 12px',
        display: 'flex', gap: '10px', alignItems: 'baseline'
      }}>
        {nummer && (
          <span style={{ color: 'var(--accent-color)', fontVariantNumeric: 'tabular-nums' }}>
            {nummer}
          </span>
        )}
        <span>{titel}</span>
      </h2>
      <div style={{ color: 'var(--text-muted)', lineHeight: 1.7 }}>{children}</div>
    </section>
  );
}

export default RechtsSeite;
