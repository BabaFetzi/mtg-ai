import { MemoryRouter } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import MeineSammlung from './MeineSammlung';

// Magic-Karten erscheinen in elf Sprachen. Wer eine deutsche Sammlung führt,
// muss sie beim Tauschen und Verkaufen von einer englischen unterscheiden
// können. Fehlt die Angabe, darf dort nichts stehen -- "Englisch" zu
// unterstellen wäre erfunden.
//
// Die Angaben stehen im Finanz-Dashboard an den wertvollsten Karten. Die
// kommen seit der Umstellung fertig sortiert vom Server (/top) -- vorher lud
// die Ansicht die vollständige Sammlung, um zehn Karten anzuzeigen.

const TOP_KARTEN = [
  { id: 1, name: 'Lightning Bolt', bild_url: '', preis: '2.00', livePreis: '2.00', foil: false, sprache: 'de', albumName: 'Ordner' },
  { id: 2, name: 'Sol Ring', bild_url: '', preis: '1.50', livePreis: '1.50', foil: true, sprache: null, albumName: 'Ordner' },
];

/** Antwortet auf die Endpunkte, die das Dashboard benutzt. */
function fetchMitTop(topKarten) {
  return vi.fn((url) => {
    const antwort = (daten) => Promise.resolve({ ok: true, status: 200, json: async () => daten });
    if (typeof url === 'string') {
      if (url.includes('/top')) return antwort({ erfolg: true, karten: topKarten });
      if (url.includes('/uebersicht')) {
        return antwort({
          erfolg: true,
          alben: [{ name: 'Ordner', anzahl: topKarten.length, wert: 3.5, vorschau: topKarten }],
          gesamtwert: 3.5,
          wunschliste: { anzahl: 0, wert: 0 },
        });
      }
      if (url.includes('/filter')) return antwort({ erfolg: true, karten: [], gesamt: 0 });
    }
    return antwort({});
  });
}

function zeigeDashboard(topKarten = TOP_KARTEN) {
  global.fetch = fetchMitTop(topKarten);

  render(
    <MemoryRouter initialEntries={['/sammlung?tab=dashboard']}>
      <MeineSammlung currentUser="tester" userRole="premium" setUserRole={() => {}} />
    </MemoryRouter>
  );
}

test('die Sprache steht als Kürzel an der Karte', async () => {
  zeigeDashboard();

  expect(await screen.findByText('Lightning Bolt')).toBeInTheDocument();
  expect(screen.getByTitle('Deutsch')).toHaveTextContent('DE');
});

test('ohne erfasste Sprache steht kein Kürzel da', async () => {
  zeigeDashboard();

  await screen.findByText('Sol Ring');
  // Nur die eine deutsche Karte trägt ein Kürzel -- für Sol Ring wird nichts
  // erfunden.
  expect(screen.queryByTitle('Englisch')).not.toBeInTheDocument();
});

test('Auflage und Zustand stehen an der Karte', async () => {
  // Vorher stand nur der Name da. Welche Auflage jemand besitzt und in welchem
  // Zustand, entscheidet aber über den Wert -- zwischen Erstausgabe und
  // Nachdruck liegt bei alten Karten das Zehnfache.
  zeigeDashboard([{
    id: 1, name: 'Lightning Bolt', bild_url: '', preis: '480.00', livePreis: '480.00',
    foil: false, sprache: 'en', zustand: 'EX', edition: 'lea',
    edition_name: 'Limited Edition Alpha', sammlernummer: '161', albumName: 'Ordner',
  }]);

  expect(await screen.findByText('Lightning Bolt')).toBeInTheDocument();
  expect(screen.getByText('LEA · #161')).toBeInTheDocument();
  expect(screen.getByTitle('Excellent')).toHaveTextContent('EX');
  // Der Preis steht an der Karte -- aus dem gespeicherten Druck, nicht vom
  // 2-Euro-Nachdruck.
  expect(screen.getAllByText('480,00 €').length).toBeGreaterThan(0);
});

test('ohne Auflage und Zustand steht dort nichts', async () => {
  zeigeDashboard();

  await screen.findByText('Sol Ring');
  expect(screen.queryByText(/·\s*#/)).not.toBeInTheDocument();
});
