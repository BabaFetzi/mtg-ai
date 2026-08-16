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

function baueFallsNoetig() {
  if (!existsSync(distDir)) {
    execSync('npx vite build', { cwd: wurzel, stdio: 'pipe' });
  }
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
