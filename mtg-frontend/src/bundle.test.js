import { execSync } from 'child_process';
import { existsSync, readdirSync, readFileSync, statSync } from 'fs';
import { gzipSync } from 'zlib';
import { resolve } from 'path';

// Was jeder Erstbesucher laden muss, bevor er irgendetwas sieht.
//
// Vorher kam die gesamte Anwendung in einem Stück: 616 KB, darunter das
// Spielfeld mit der Kameraerkennung, die Rechtsseiten und die
// Kontoverwaltung -- Dinge, die die meisten Besucher nie öffnen. Jede Ansicht
// wird jetzt einzeln nachgeladen (App.jsx).
//
// Ohne eine feste Grenze wächst so etwas unbemerkt wieder zu: ein Import an
// der falschen Stelle zieht ein ganzes Paket zurück ins erste Bündel, und
// niemand sieht es, weil die Anwendung ja funktioniert.

const wurzel = resolve(__dirname, '..');
const distDir = resolve(wurzel, 'dist/assets');

// Grenzen mit Luft nach oben, aber nicht so viel, dass ein zurückgerutschtes
// Paket unbemerkt bliebe. Gemessen nach der Umstellung: 386 KB roh,
// 114 KB gepackt.
const MAX_ROH_KB = 450;
const MAX_GEPACKT_KB = 135;

// Gebaut wird IMMER frisch und ausdrücklich mit NODE_ENV=production.
//
// Beides ist nötig, und beides war vorher falsch:
//
// 1. `if (!existsSync(distDir))` mass irgendein Paket, das zufällig herumlag --
//    womöglich Wochen alt und von einem ganz anderen Stand. Der Test sagte
//    dann nichts über den Code aus, den man gerade geändert hat.
//
// 2. vitest setzt NODE_ENV=test. Vite minifiziert dann NICHT, und dasselbe
//    Startpaket wiegt 627 statt 387 KB. Auf einem frischen Checkout wäre der
//    Test also mit "Startpaket zu gross" gescheitert -- einer Meldung, die
//    einen auf die Suche nach einem Fehler schickt, den es nicht gibt.
//    Bestanden hat er bisher nur, weil ein von Hand gebautes dist/ da war.
//
// Der Build dauert rund zwei Sekunden. Ein Mass, das vom Zufall abhängt, ist
// die nicht wert.
function baueFallsNoetig() {
  execSync('npx vite build', {
    cwd: wurzel,
    stdio: 'pipe',
    env: { ...process.env, NODE_ENV: 'production' },
  });
}

function einstiegsBuendel() {
  const dateien = readdirSync(distDir).filter((d) => d.endsWith('.js'));
  // Das Einstiegspaket heisst index-*.js; die Ansichten tragen ihren
  // Komponentennamen.
  const einstieg = dateien.filter((d) => d.startsWith('index-'));
  expect(einstieg.length).toBe(1);
  return resolve(distDir, einstieg[0]);
}

describe('Startpaket', () => {
  beforeAll(baueFallsNoetig);

  test('bleibt unter der Grenze', () => {
    const pfad = einstiegsBuendel();
    const roh = statSync(pfad).size / 1024;
    const gepackt = gzipSync(readFileSync(pfad)).length / 1024;

    expect(roh, `Startpaket ${roh.toFixed(0)} KB roh`).toBeLessThan(MAX_ROH_KB);
    expect(gepackt, `Startpaket ${gepackt.toFixed(0)} KB gepackt`).toBeLessThan(MAX_GEPACKT_KB);
  });

  test('die schweren Ansichten liegen in eigenen Paketen', () => {
    const dateien = readdirSync(distDir).filter((d) => d.endsWith('.js'));

    // Wird eine davon wieder fest eingebunden, verschwindet ihr Paket und das
    // Startpaket wächst -- die Grenze oben würde es erst später merken.
    for (const name of ['DecksView', 'MeineSammlung', 'PlayfieldView', 'KontoSeite']) {
      expect(
        dateien.some((d) => d.startsWith(`${name}-`)),
        `${name} hat kein eigenes Paket -- wird es wieder direkt importiert?`
      ).toBe(true);
    }
  });
});

// ======================================================================
// Was im ausgelieferten Paket stehen darf
// ======================================================================
// Im Quelltext stehen rund 17 Entwicklungsausgaben (Kamera-Auswahl,
// WebSocket-Zustand, Deck-Synchronisation). Zugangsdaten stehen nicht darin,
// aber sie zeigen Fremden den inneren Ablauf und machen die Konsole so voll,
// dass eine ECHTE Fehlermeldung darin untergeht.
//
// Sie werden beim Bauen ersetzt (vite.config.js). Ob das WIRKLICH passiert,
// haengt an der Werkzeugkette: `esbuild.pure` hatte in Vite 8 keine Wirkung,
// die Aufrufe standen unveraendert im Bundle. Deshalb wird hier das gebaute
// Ergebnis nachgesehen und nicht die Einstellung.

function alleBuendel() {
  return readdirSync(distDir)
    .filter((d) => d.endsWith('.js'))
    .map((d) => readFileSync(resolve(distDir, d), 'utf-8'));
}

describe('Ausgeliefertes Paket', () => {
  beforeAll(baueFallsNoetig);

  test('enthaelt keine Entwicklungsausgaben mehr', () => {
    const treffer = alleBuendel().reduce(
      (summe, inhalt) => summe + (inhalt.match(/console\.(log|debug)\(/g) || []).length,
      0
    );

    expect(treffer, `${treffer}x console.log/debug im gebauten Paket`).toBe(0);
  });

  test('behaelt console.error und console.warn', () => {
    // Die Fehlergrenze schreibt ihren Fehler ausdruecklich nach console.error.
    // Ein pauschales Entfernen aller console-Aufrufe wuerde genau die Meldung
    // verschlucken, wegen der man spaeter nachsehen kann, was passiert ist --
    // das waere schlimmer als die Ausgaben stehenzulassen.
    const inhalt = alleBuendel().join('');

    expect(inhalt).toContain('console.error');
    expect(inhalt).toContain('console.warn');
  });
});
