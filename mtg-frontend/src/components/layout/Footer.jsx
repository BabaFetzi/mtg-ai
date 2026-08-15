import { Link } from 'react-router-dom';

/**
 * Fusszeile mit den Pflichtlinks.
 *
 * Impressum, Datenschutz und AGB müssen von jeder Seite aus erreichbar sein --
 * sowohl für ausgeloggte Besucher als auch im angemeldeten Bereich. Deshalb
 * steht diese Komponente an beiden Stellen.
 */
function Footer() {
  const link = {
    color: 'var(--text-muted)',
    textDecoration: 'none',
    fontSize: '0.88rem',
    whiteSpace: 'nowrap',
    // Die Links waren 23px hoch -- auf dem Handy kaum zu treffen.
    display: 'inline-flex',
    alignItems: 'center',
    minHeight: '44px',
    padding: '0 2px',
  };

  return (
    <footer style={{
      borderTop: '1px solid var(--border-color)',
      background: 'var(--bg-main)',
      // Unten zusätzlich Platz für den fest schwebenden Judge-Knopf
      // (60px hoch, 24px über dem Rand). Ohne diese Reserve lag er am
      // Seitenende genau über den Pflichtlinks.
      padding: 'clamp(24px, 5vw, 40px) 20px calc(clamp(24px, 5vw, 40px) + 84px)',
      marginTop: '60px',
    }}>
      <div style={{
        maxWidth: '1200px', margin: '0 auto',
        display: 'flex', flexWrap: 'wrap', gap: '16px 28px',
        alignItems: 'center', justifyContent: 'space-between',
      }}>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', margin: 0, maxWidth: '40rem' }}>
          Grana ist ein unabhängiges Werkzeug und steht in keiner Verbindung zu
          Wizards of the Coast. Kartendaten von Scryfall.
        </p>

        <nav style={{ display: 'flex', flexWrap: 'wrap', gap: '16px 22px' }}>
          <Link to="/impressum" style={link}>Impressum</Link>
          <Link to="/datenschutz" style={link}>Datenschutz</Link>
          <Link to="/agb" style={link}>AGB</Link>
        </nav>
      </div>
    </footer>
  );
}

export default Footer;
