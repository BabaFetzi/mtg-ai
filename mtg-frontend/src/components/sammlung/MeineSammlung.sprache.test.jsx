import { MemoryRouter } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import MeineSammlung from './MeineSammlung';

// Magic-Karten erscheinen in elf Sprachen. Wer eine deutsche Sammlung führt,
// muss sie beim Tauschen und Verkaufen von einer englischen unterscheiden
// können. Fehlt die Angabe, darf dort nichts stehen -- "Englisch" zu
// unterstellen wäre erfunden.

const SAMMLUNG = {
  erfolg: true,
  alben: {
    Ordner: [
      { id: 1, name: 'Lightning Bolt', bild_url: '', preis: '2.00', livePreis: '2.00', foil: false, sprache: 'de' },
      { id: 2, name: 'Sol Ring', bild_url: '', preis: '1.50', livePreis: '1.50', foil: true, sprache: null },
    ],
  },
};

function zeigeSammlung() {
  global.fetch = vi.fn((url) => {
    if (typeof url === 'string' && url.includes('/filter')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ erfolg: true, karten: [] }) });
    }
    if (typeof url === 'string' && url.startsWith('/api/sammlung/')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => SAMMLUNG });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
  });

  render(
    <MemoryRouter initialEntries={['/sammlung?tab=dashboard']}>
      <MeineSammlung currentUser="tester" userRole="premium" setUserRole={() => {}} />
    </MemoryRouter>
  );
}

test('die Sprache steht als Kürzel an der Karte', async () => {
  zeigeSammlung();

  expect(await screen.findByText('Lightning Bolt')).toBeInTheDocument();
  expect(screen.getByTitle('Deutsch')).toHaveTextContent('DE');
});

test('ohne erfasste Sprache steht kein Kürzel da', async () => {
  zeigeSammlung();

  await screen.findByText('Sol Ring');
  // Nur die eine deutsche Karte trägt ein Kürzel -- für Sol Ring wird nichts
  // erfunden.
  expect(screen.queryByTitle('Englisch')).not.toBeInTheDocument();
});

test('Auflage und Zustand stehen an der Karte', async () => {
  // Vorher stand nur der Name da. Welche Auflage jemand besitzt und in welchem
  // Zustand, entscheidet aber über den Wert -- zwischen Erstausgabe und
  // Nachdruck liegt bei alten Karten das Zehnfache.
  global.fetch = vi.fn((url) => {
    if (typeof url === 'string' && url.includes('/filter')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ erfolg: true, karten: [] }) });
    }
    if (typeof url === 'string' && url.startsWith('/api/sammlung/')) {
      return Promise.resolve({
        ok: true, status: 200, json: async () => ({
          erfolg: true,
          alben: {
            Ordner: [{
              id: 1, name: 'Lightning Bolt', bild_url: '', preis: '480.00', livePreis: '480.00',
              foil: false, sprache: 'en', zustand: 'EX', edition: 'lea',
              edition_name: 'Limited Edition Alpha', sammlernummer: '161',
            }],
          },
        }),
      });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
  });

  render(
    <MemoryRouter initialEntries={['/sammlung?tab=dashboard']}>
      <MeineSammlung currentUser="tester" userRole="premium" setUserRole={() => {}} />
    </MemoryRouter>
  );

  expect(await screen.findByText('Lightning Bolt')).toBeInTheDocument();
  expect(screen.getByText('LEA · #161')).toBeInTheDocument();
  expect(screen.getByTitle('Excellent')).toHaveTextContent('EX');
  // Der Preis steht an der Karte und in der Summe -- beide aus dem
  // gespeicherten Druck, nicht vom 2-Euro-Nachdruck.
  expect(screen.getAllByText('480,00 €').length).toBeGreaterThan(0);
});

test('ohne Auflage und Zustand steht dort nichts', async () => {
  zeigeSammlung();

  await screen.findByText('Sol Ring');
  expect(screen.queryByText(/·\s*#/)).not.toBeInTheDocument();
});
