import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DeckEditor from './DeckEditor';
import MeldungProvider from '../layout/Meldungen';

/**
 * Der Weg vom Klick bis zur gespeicherten Auflage.
 *
 * Warum dieser Test in einem echten Rendering läuft und nicht nur die
 * Hilfsfunktionen prüft: In genau dieser Ansicht hat schon einmal ein Knopf
 * gar nichts getan, weil ein Hook in der falschen Funktion stand. Die
 * Bausteine waren alle richtig -- nur zusammen ergaben sie keinen Klick.
 * Deshalb wird hier gedrückt und nachgesehen, WAS an den Server geht.
 */

const DECK = { id: 7, name: 'Burn', liste: '4x Lightning Bolt' };

const KARTEN_IM_DECK = [{
  count: 4, name: 'Lightning Bolt', image: 'bild-standard', type: 'Instant', cmc: 1,
  price: '3.00', sideboard: false,
  set: null, set_name: '', sammlernummer: null,
  auflage_gewuenscht: false, auflage_gefunden: false,
}];

const AUFLAGEN = [
  { id: 'id-2xm', set: '2xm', set_name: 'Double Masters', sammlernummer: '123',
    bild_url: 'bild-2xm', preis: '1.20', besitzt: 2 },
  { id: 'id-lea', set: 'lea', set_name: 'Limited Edition Alpha', sammlernummer: '161',
    bild_url: 'bild-lea', preis: '480.00', besitzt: 0 },
];

let gesendet;

function antwortFuer(url, optionen) {
  if (url === '/api/deck/visualize') return { karten: KARTEN_IM_DECK };
  if (url.startsWith('/api/karten/auflagen/')) {
    return { name: 'Lightning Bolt', auflagen: AUFLAGEN };
  }
  if (url === '/api/deck/auflage') {
    return { erfolg: true, deck_liste: '4x Lightning Bolt (2XM) 123' };
  }
  if (url === '/api/deck/add-card' || url === '/api/deck/remove-card') {
    return { erfolg: true, deck_liste: '4x Lightning Bolt (2XM) 123' };
  }
  return {};
}

beforeEach(() => {
  gesendet = [];
  global.fetch = vi.fn((url, optionen) => {
    gesendet.push({ url, body: optionen?.body ? JSON.parse(optionen.body) : null });
    return Promise.resolve({ ok: true, status: 200, json: async () => antwortFuer(url, optionen) });
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function zeigeEditor() {
  render(
    <MeldungProvider>
      <DeckEditor selectedDeck={DECK} currentUser="tester" ladeDecks={vi.fn()} />
    </MeldungProvider>
  );
}

function anfragenAn(pfad) {
  return gesendet.filter((a) => a.url === pfad);
}

describe('Deck-Editor: Auflage einer Karte', () => {
  test('unter jeder Karte steht ein Knopf für die Auflage', async () => {
    zeigeEditor();
    expect(await screen.findByRole('button', { name: 'Auflage wählen' })).toBeInTheDocument();
  });

  test('der Knopf öffnet die Auswahl', async () => {
    zeigeEditor();

    await userEvent.click(await screen.findByRole('button', { name: 'Auflage wählen' }));

    expect(await screen.findByText('Double Masters')).toBeInTheDocument();
    expect(screen.getByText('2× in deiner Sammlung')).toBeInTheDocument();
  });

  test('die gewählte Auflage geht mit Set und Nummer an den Server', async () => {
    zeigeEditor();
    await userEvent.click(await screen.findByRole('button', { name: 'Auflage wählen' }));
    await userEvent.click((await screen.findByText('Double Masters')).closest('button'));

    await waitFor(() => expect(anfragenAn('/api/deck/auflage')).toHaveLength(1));
    expect(anfragenAn('/api/deck/auflage')[0].body).toEqual({
      deck_id: 7,
      card_name: 'Lightning Bolt',
      alt_set: null,
      alt_sammlernummer: null,
      set: '2xm',
      sammlernummer: '123',
    });
  });

  test('nach der Wahl schliesst der Dialog und es kommt eine Rückmeldung', async () => {
    zeigeEditor();
    await userEvent.click(await screen.findByRole('button', { name: 'Auflage wählen' }));
    await userEvent.click((await screen.findByText('Double Masters')).closest('button'));

    expect(await screen.findByText(/Auflage 2XM übernommen/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByTestId('auflagen-hintergrund')).not.toBeInTheDocument();
    });
  });

  test('ein Fehler vom Server wird gezeigt, nicht verschluckt', async () => {
    /**
     * Der alte Ablauf schrieb Fehler nur auf die Konsole. Für den Nutzer sah
     * das aus, als täte der Knopf nichts -- genau die Beschwerde, mit der das
     * hier angefangen hat.
     */
    global.fetch = vi.fn((url) => Promise.resolve({
      ok: true, status: 200,
      json: async () => (url === '/api/deck/visualize'
        ? { karten: KARTEN_IM_DECK }
        : (url.startsWith('/api/karten/auflagen/')
          ? { name: 'Lightning Bolt', auflagen: AUFLAGEN }
          : { erfolg: false, error: 'Deck nicht gefunden.' })),
    }));

    zeigeEditor();
    await userEvent.click(await screen.findByRole('button', { name: 'Auflage wählen' }));
    await userEvent.click((await screen.findByText('Double Masters')).closest('button'));

    expect(await screen.findByText('Deck nicht gefunden.')).toBeInTheDocument();
  });

  test('+ und − schicken die Auflage der angeklickten Karte mit', async () => {
    /**
     * Ohne die Auflage träfe das Erhöhen die falsche Zeile, sobald dieselbe
     * Karte in zwei Auflagen im Deck steht.
     */
    global.fetch = vi.fn((url, optionen) => {
      gesendet.push({ url, body: optionen?.body ? JSON.parse(optionen.body) : null });
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => (url === '/api/deck/visualize'
          ? { karten: [{ ...KARTEN_IM_DECK[0], set: 'lea', sammlernummer: '161',
                         auflage_gewuenscht: true, auflage_gefunden: true }] }
          : { erfolg: true, deck_liste: '5x Lightning Bolt (LEA) 161' }),
      });
    });

    zeigeEditor();
    await userEvent.click(await screen.findByTitle('Erhöhen'));

    await waitFor(() => expect(anfragenAn('/api/deck/add-card')).toHaveLength(1));
    expect(anfragenAn('/api/deck/add-card')[0].body).toEqual({
      deck_id: 7, card_name: 'Lightning Bolt', set: 'lea', sammlernummer: '161',
    });
  });

  test('eine nicht auffindbare Auflage wird gekennzeichnet', async () => {
    /**
     * Keine erfundenen Daten: Zeigt die App den Standarddruck, weil die
     * gewählte Auflage nicht abrufbar war, muss man das sehen können.
     */
    global.fetch = vi.fn((url) => Promise.resolve({
      ok: true, status: 200,
      json: async () => (url === '/api/deck/visualize'
        ? { karten: [{ ...KARTEN_IM_DECK[0], set: 'zzz', sammlernummer: '999',
                       auflage_gewuenscht: true, auflage_gefunden: false }] }
        : {}),
    }));

    zeigeEditor();

    const knopf = await screen.findByRole('button', { name: /ZZZ · 999/ });
    expect(knopf).toHaveAttribute('title', expect.stringContaining('nicht abrufen'));
  });
});
