import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AuflagenWahl from './AuflagenWahl';

/**
 * Die Auswahl der Auflage im Deckbau.
 *
 * Zwei Zusagen werden hier festgehalten, weil sie sonst beim nächsten Umbau
 * leise verschwinden:
 *
 * 1. Nichts wird vorausgewählt -- der Besitz einer Auflage macht noch kein
 *    Deck mit vier Exemplaren daraus.
 * 2. Lässt sich nichts laden, sagt der Dialog das und behauptet nicht, es gäbe
 *    keine Auflagen.
 */

const AUFLAGEN = [
  { id: 'id-lea', set: 'lea', set_name: 'Limited Edition Alpha', sammlernummer: '161',
    bild_url: 'bild-lea', preis: '480.00', besitzt: 0 },
  { id: 'id-2xm', set: '2xm', set_name: 'Double Masters', sammlernummer: '123',
    bild_url: 'bild-2xm', preis: '1.20', besitzt: 2 },
  { id: 'id-m10', set: 'm10', set_name: 'Magic 2010', sammlernummer: '146',
    bild_url: '', preis: '0.00', besitzt: 0 },
];

function antworte(daten, ok = true) {
  global.fetch = vi.fn(() => Promise.resolve({
    ok,
    json: () => Promise.resolve(daten),
  }));
}

beforeEach(() => {
  antworte({ name: 'Lightning Bolt', auflagen: AUFLAGEN });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function zeige(zusatz = {}) {
  const props = {
    kartenName: 'Lightning Bolt',
    aktuell: null,
    onWaehlen: vi.fn(),
    onSchliessen: vi.fn(),
    ...zusatz,
  };
  render(<AuflagenWahl {...props} />);
  return props;
}

describe('AuflagenWahl', () => {
  test('zeigt alle Auflagen mit Set, Nummer und Preis', async () => {
    zeige();

    expect(await screen.findByText('Double Masters')).toBeInTheDocument();
    expect(screen.getByText('Limited Edition Alpha')).toBeInTheDocument();
    expect(screen.getByText('2XM · 123')).toBeInTheDocument();
    expect(screen.getByText('480.00 €')).toBeInTheDocument();
  });

  test('markiert die Auflagen aus der eigenen Sammlung', async () => {
    zeige();
    expect(await screen.findByText('2× in deiner Sammlung')).toBeInTheDocument();
  });

  test('wählt von sich aus nichts aus', async () => {
    /**
     * Der Punkt "keine erfundenen Daten": Wer EINE Alpha-Auflage besitzt, hat
     * deshalb nicht vier davon im Deck. Eine automatische Übernahme würde den
     * Deckwert um ein Vielfaches verfälschen.
     */
    const props = zeige();
    await screen.findByText('Double Masters');

    expect(props.onWaehlen).not.toHaveBeenCalled();
    expect(screen.queryByText('Aktuell im Deck')).not.toBeInTheDocument();
  });

  test('gibt die angeklickte Auflage weiter', async () => {
    const props = zeige();
    const kachel = (await screen.findByText('Double Masters')).closest('button');

    await userEvent.click(kachel);

    expect(props.onWaehlen).toHaveBeenCalledWith(
      expect.objectContaining({ set: '2xm', sammlernummer: '123' })
    );
  });

  test('kennzeichnet die aktuell im Deck stehende Auflage', async () => {
    zeige({ aktuell: { set: '2xm', sammlernummer: '123' } });

    const kachel = (await screen.findByText('Double Masters')).closest('button');
    expect(within(kachel).getByText('Aktuell im Deck')).toBeInTheDocument();
  });

  test('bietet das Aufheben nur an, wenn etwas festgelegt ist', async () => {
    const { unmount } = render(
      <AuflagenWahl kartenName="Lightning Bolt" aktuell={null}
                    onWaehlen={vi.fn()} onSchliessen={vi.fn()} />
    );
    await screen.findByText('Double Masters');
    expect(screen.queryByRole('button', { name: /Festlegung aufheben/ })).not.toBeInTheDocument();
    unmount();

    zeige({ aktuell: { set: '2xm', sammlernummer: '123' } });
    await screen.findAllByText('Double Masters');
    expect(screen.getAllByRole('button', { name: /Festlegung aufheben/ }).length).toBeGreaterThan(0);
  });

  test('das Aufheben meldet null zurück', async () => {
    const props = zeige({ aktuell: { set: '2xm', sammlernummer: '123' } });
    await screen.findByText('Double Masters');

    await userEvent.click(screen.getByRole('button', { name: /Festlegung aufheben/ }));

    expect(props.onWaehlen).toHaveBeenCalledWith(null);
  });

  test('filtert auf die eigenen Auflagen', async () => {
    zeige();
    await screen.findByText('Double Masters');

    await userEvent.click(screen.getByRole('button', { name: /Nur aus meiner Sammlung/ }));

    expect(screen.getByText('Double Masters')).toBeInTheDocument();
    expect(screen.queryByText('Limited Edition Alpha')).not.toBeInTheDocument();
  });

  test('ohne eigene Auflagen gibt es keinen Filter', async () => {
    antworte({ name: 'Lightning Bolt', auflagen: AUFLAGEN.map((a) => ({ ...a, besitzt: 0 })) });
    zeige();
    await screen.findByText('Double Masters');

    expect(screen.queryByRole('button', { name: /Nur aus meiner Sammlung/ })).not.toBeInTheDocument();
  });

  test('sagt es, wenn nichts abrufbar ist', async () => {
    antworte({ name: 'Lightning Bolt', auflagen: [], nicht_gefunden: true });
    zeige();

    expect(await screen.findByText(/keine Auflagen abrufbar/)).toBeInTheDocument();
    expect(screen.getByText(/bisherige Auswahl bleibt unverändert/)).toBeInTheDocument();
  });

  test('überlebt einen Netzwerkfehler', async () => {
    global.fetch = vi.fn(() => Promise.reject(new Error('offline')));
    zeige();

    expect(await screen.findByText(/konnten nicht geladen werden/)).toBeInTheDocument();
  });

  test('fehlender Preis wird benannt statt als 0,00 € behauptet', async () => {
    zeige();
    expect(await screen.findByText('kein Preis hinterlegt')).toBeInTheDocument();
  });

  test('Klick auf den Hintergrund schliesst', async () => {
    const props = zeige();
    await screen.findByText('Double Masters');

    await userEvent.click(screen.getByTestId('auflagen-hintergrund'));

    expect(props.onSchliessen).toHaveBeenCalled();
  });

  test('Klick im Dialog schliesst nicht', async () => {
    const props = zeige();
    const ueberschrift = await screen.findByText('Auflage wählen');

    await userEvent.click(ueberschrift);

    expect(props.onSchliessen).not.toHaveBeenCalled();
  });
});
