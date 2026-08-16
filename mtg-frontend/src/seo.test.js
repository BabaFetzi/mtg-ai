import { readFileSync } from 'fs';
import { resolve } from 'path';

// Was Suchmaschinen und Chat-Vorschauen von der Seite sehen. Bisher gab es
// davon fast nichts -- und die Seite gab sich sogar als englischsprachig aus.

const wurzel = resolve(__dirname, '..');
const lies = (pfad) => readFileSync(resolve(wurzel, pfad), 'utf-8');

test('die Seite gibt sich als deutschsprachig aus', () => {
  // Stand vorher auf "en". Vorleseprogramme sprechen die Seite dann mit
  // englischer Aussprache, und Suchmaschinen ordnen sie falsch ein.
  expect(lies('index.html')).toMatch(/<html lang="de">/);
});

test('Titel und Beschreibung sagen, worum es geht', () => {
  const html = lies('index.html');

  expect(html).toMatch(/<title>[^<]*Magic[^<]*<\/title>/);
  const beschreibung = html.match(/name="description" content="([^"]+)"/);
  expect(beschreibung).not.toBeNull();
  // Zu kurz sagt nichts, zu lang wird in der Trefferliste abgeschnitten.
  expect(beschreibung[1].length).toBeGreaterThan(70);
  expect(beschreibung[1].length).toBeLessThan(180);
});

test('geteilte Links bekommen eine Vorschau', () => {
  const html = lies('index.html');

  expect(html).toMatch(/property="og:title"/);
  expect(html).toMatch(/property="og:description"/);
  expect(html).toMatch(/property="og:image"/);
});

test('das Vorschaubild gibt es wirklich', () => {
  // Ein og:image, das ins Leere zeigt, ist schlechter als keines: die
  // Vorschau bleibt leer und wirkt kaputt.
  const html = lies('index.html');
  const bild = html.match(/property="og:image" content="\/([^"]+)"/);

  expect(bild).not.toBeNull();
  const datei = readFileSync(resolve(wurzel, 'public', bild[1]));
  expect(datei.length).toBeGreaterThan(1000);
  // PNG-Kennung -- viele Dienste zeigen SVG nicht an.
  expect(datei.subarray(1, 4).toString()).toBe('PNG');
});

test('robots.txt hält angemeldete Bereiche aus dem Index', () => {
  const robots = lies('public/robots.txt');

  for (const bereich of ['/sammlung', '/decks', '/konto']) {
    expect(robots).toContain(`Disallow: ${bereich}`);
  }
  expect(robots).toMatch(/Sitemap:/);
});

test('die sitemap.xml ist gültiges XML mit dem richtigen Namensraum', () => {
  const xml = lies('public/sitemap.xml');

  // Der Namensraum lautet sitemaps.org (Mehrzahl) -- mit sitemap.org wird die
  // Datei stillschweigend ignoriert.
  expect(xml).toContain('http://www.sitemaps.org/schemas/sitemap/0.9');
  // Doppelte Bindestriche sind in XML-Kommentaren verboten und machen die
  // ganze Datei ungültig. Genau daran ist meine erste Fassung gescheitert.
  const kommentare = xml.match(/<!--[\s\S]*?-->/g) || [];
  for (const k of kommentare) {
    expect(k.slice(4, -3)).not.toContain('--');
  }
  expect(xml).toMatch(/<loc>https:\/\/[^<]+\/<\/loc>/);
});

test('die Rechtsseiten stehen in der sitemap', () => {
  const xml = lies('public/sitemap.xml');

  for (const seite of ['impressum', 'datenschutz', 'agb']) {
    expect(xml).toContain(`/${seite}<`);
  }
});
