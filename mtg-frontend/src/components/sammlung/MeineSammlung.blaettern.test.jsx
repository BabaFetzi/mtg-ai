import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MeineSammlung from './MeineSammlung';

// Ein Ordner kam bisher immer vollständig -- bei 15000 Karten 4,5 MB, die der
// Browser laden, entpacken und rendern musste. Jetzt kommen 100 auf einmal.
//
// Beim Blättern kann viel schiefgehen, ohne dass es auffällt: doppelte Karten,
// verlorene Karten, eine Schaltfläche, die nie verschwindet, oder eine, die
// nach dem Ordnerwechsel die Karten des alten Ordners anhängt. Genau dafür
// sind diese Tests da.

const ORDNER = 'Ordner A';

/** Baut die Antwort auf /filter aus einem Gesamtbestand. */
function seiteAus(alleKarten, url) {
  const params = new URL(url, 'http://x').searchParams;
  const seite = parseInt(params.get('seite') || '1', 10);
  const proSeite = parseInt(params.get('pro_seite') || '100', 10);
  const anfang = (seite - 1) * proSeite;
  return {
    erfolg: true,
    karten: alleKarten.slice(anfang, anfang + proSeite),
    gesamt: alleKarten.length,
    seite,
    pro_seite: proSeite,
  };
}

function karten(anzahl, praefix = 'Karte') {
  return Array.from({ length: anzahl }, (_, i) => ({
    id: i + 1, name: `${praefix} ${String(i + 1).padStart(3, '0')}`,
    bild_url: '', preis: '1.00', price: '1.00', album_name: ORDNER,
  }));
}

function zeigeOrdner(alleKarten) {
  const rufe = [];
  global.fetch = vi.fn((url) => {
    rufe.push(String(url));
    const antwort = (daten) => Promise.resolve({ ok: true, status: 200, json: async () => daten });
    if (typeof url === 'string') {
      if (url.includes('/uebersicht')) {
        return antwort({
          erfolg: true,
          alben: [{ name: ORDNER, anzahl: alleKarten.length, wert: 10, vorschau: [] }],
          gesamtwert: 10,
          wunschliste: { anzahl: 0, wert: 0 },
        });
      }
      if (url.includes('/filter')) return antwort(seiteAus(alleKarten, url));
      if (url.includes('/editions')) return antwort({ erfolg: true, editions: [] });
    }
    return antwort({});
  });

  render(
    <MemoryRouter initialEntries={['/sammlung?tab=alben']}>
      <MeineSammlung currentUser="tester" userRole="premium" setUserRole={() => {}} />
    </MemoryRouter>
  );
  return rufe;
}

async function ordnerOeffnen(name = ORDNER) {
  const kachel = await screen.findByText(name);
  await userEvent.click(kachel);
}

test('ein grosser Ordner laedt zuerst nur eine Seite', async () => {
  zeigeOrdner(karten(250));
  await ordnerOeffnen();

  expect(await screen.findByText('Karte 001')).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText('100 von 250 Karten')).toBeInTheDocument());
  // Die 101. Karte darf noch nicht da sein -- sonst kam doch alles auf einmal.
  expect(screen.queryByText('Karte 101')).not.toBeInTheDocument();
});

test('"Mehr laden" haengt die naechste Seite an, statt sie zu ersetzen', async () => {
  zeigeOrdner(karten(250));
  await ordnerOeffnen();
  await screen.findByText('Karte 001');

  await userEvent.click(await screen.findByRole('button', { name: /Weitere 100 laden/ }));

  expect(await screen.findByText('Karte 101')).toBeInTheDocument();
  // Die erste Seite muss stehen bleiben. Wuerde sie ersetzt, waere "Mehr
  // laden" in Wahrheit ein Seitenwechsel -- und die Karten oben verschwunden.
  expect(screen.getByText('Karte 001')).toBeInTheDocument();
  expect(screen.getByText('200 von 250 Karten')).toBeInTheDocument();
});

test('am Ende verschwindet die Schaltflaeche und die Gesamtzahl bleibt stehen', async () => {
  zeigeOrdner(karten(150));
  await ordnerOeffnen();
  await screen.findByText('Karte 001');

  // Die letzte Seite ist nur halb voll -- die Beschriftung muss das sagen.
  await userEvent.click(await screen.findByRole('button', { name: /Weitere 50 laden/ }));

  await waitFor(() => expect(screen.getByText('150 Karten')).toBeInTheDocument());
  expect(screen.queryByRole('button', { name: /Weitere/ })).not.toBeInTheDocument();
});

test('ein kleiner Ordner zeigt gar keine Schaltflaeche', async () => {
  zeigeOrdner(karten(3));
  await ordnerOeffnen();

  await screen.findByText('Karte 001');
  expect(screen.getByText('3 Karten')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Weitere/ })).not.toBeInTheDocument();
});

test('der Server bekommt Seite und Seitengroesse mitgeteilt', async () => {
  const rufe = zeigeOrdner(karten(250));
  await ordnerOeffnen();
  await screen.findByText('Karte 001');

  await userEvent.click(await screen.findByRole('button', { name: /Weitere 100 laden/ }));
  await screen.findByText('Karte 101');

  const filterRufe = rufe.filter(u => u.includes('/filter'));
  const letzter = filterRufe[filterRufe.length - 1];
  expect(letzter).toContain('seite=2');
  expect(letzter).toContain('pro_seite=100');
});

test('eine andere Sortierung laedt neu, statt das Geladene umzusortieren', async () => {
  // Der wichtigste Test hier. Sortierte der Browser nur die geladenen 100,
  // hiesse "Preis: Hoch nach Tief" in Wahrheit "die teuerste der ersten 100" --
  // die teuerste Karte des Ordners bliebe unsichtbar. Das sieht nicht falsch
  // aus, ist es aber, und deshalb muss der Server sortieren.
  const rufe = zeigeOrdner(karten(250));
  await ordnerOeffnen();
  await screen.findByText('Karte 001');
  const vorher = rufe.filter(u => u.includes('/filter')).length;

  await userEvent.selectOptions(screen.getByLabelText('Sortierung'), 'priceDesc');

  await waitFor(() => {
    const filterRufe = rufe.filter(u => u.includes('/filter'));
    expect(filterRufe.length).toBeGreaterThan(vorher);
    expect(filterRufe[filterRufe.length - 1]).toContain('sortierung=priceDesc');
  });
  // Und wieder bei Seite 1 -- sonst faengt die neue Reihenfolge mittendrin an.
  expect(rufe[rufe.length - 1]).toContain('seite=1');
});

test('der Zaehler nennt alle Treffer, nicht nur die geladenen', async () => {
  // "Karten gefunden: 100" bei 250 vorhandenen waere schlicht falsch.
  zeigeOrdner(karten(250));
  await ordnerOeffnen();
  await screen.findByText('Karte 001');

  const zaehler = await screen.findByText(/Karten gefunden:/);
  expect(zaehler).toHaveTextContent('250');
});

test('die Ordneruebersicht laedt gar keine Kartenliste', async () => {
  // Sie zeigt keine einzelne Karte an. Trotzdem wurde die erste Seite des
  // Filters mitgeladen -- 40 KB bei jedem Oeffnen der Sammlung, die nie
  // jemand zu sehen bekam.
  const rufe = zeigeOrdner(karten(250));
  await screen.findByText(ORDNER);
  await waitFor(() => expect(rufe.some(u => u.includes('/uebersicht'))).toBe(true));

  expect(rufe.filter(u => u.includes('/filter'))).toEqual([]);
});

test('die Ordneruebersicht laedt nicht mehr die ganze Sammlung', async () => {
  // Der eigentliche Zweck der Umstellung: der alte Endpunkt, der alle Karten
  // liefert, darf beim Oeffnen der Sammlung gar nicht mehr aufgerufen werden.
  const rufe = zeigeOrdner(karten(250));
  await screen.findByText(ORDNER);

  const vollstaendig = rufe.filter(u => /\/api\/sammlung\/[^/?]+$/.test(u));
  expect(vollstaendig).toEqual([]);
});
