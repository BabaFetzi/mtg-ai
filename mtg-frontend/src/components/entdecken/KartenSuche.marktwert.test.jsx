import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import KartenSuche from './KartenSuche';

// Reproduziert den gefixten Bug: Bei Sol Ring war der erste/ausgewählte Print eine
// Secret-Lair-Promo ohne EUR-Preis, sodass die Marktwert-Box fälschlich 0.00 €
// anzeigte, obwohl andere Editionen (und das Feld `marktwert`) einen echten Preis
// haben. Die Box soll den besten Marktpreis statt 0.00 € zeigen.
function mockFetch(searchResponse) {
  global.fetch = vi.fn((url) => {
    const u = String(url);
    if (u.includes('/api/sammlung/')) {
      return Promise.resolve({ ok: true, json: async () => ({ erfolg: true, alben: {} }) });
    }
    if (u.includes('/api/suche/')) {
      return Promise.resolve({ ok: true, json: async () => searchResponse });
    }
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
}

describe('KartenSuche – Marktwert-Anzeige', () => {
  test('zeigt den besten Marktpreis statt 0.00 €, wenn der erste Print keinen Preis hat', async () => {
    const user = userEvent.setup();
    mockFetch({
      name: 'Sol Ring',
      typ: 'Artifact',
      text_de: 'Originaltext',
      marktwert: '1.14',
      prints: [
        { set_name: 'Secret Lair Drop', bild_url: '', preis: '0.00' }, // ausgewählt (Index 0), kein Preis
        { set_name: 'Commander', bild_url: '', preis: '1.14' },
      ],
    });

    render(
      <MemoryRouter>
        <KartenSuche currentUser="tester" />
      </MemoryRouter>
    );

    await user.type(screen.getByPlaceholderText(/Kartennamen eingeben/i), 'Sol Ring');
    await user.keyboard('{Enter}');

    await screen.findByRole('heading', { name: 'Sol Ring' });

    // Marktwert-Box zeigt den besten Preis (1.14 €), NICHT 0.00 €.
    await waitFor(() => {
      const priceP = [...document.querySelectorAll('p')].find(
        (p) => p.style.fontWeight === '700' && /€/.test(p.textContent)
      );
      expect(priceP).toBeTruthy();
      expect(priceP.textContent).toMatch(/1\.14\s*€/);
      expect(priceP.textContent).not.toMatch(/0\.00/);
    });
  });

  test('zeigt den Preis der gewählten Edition, wenn diese einen echten Preis hat', async () => {
    const user = userEvent.setup();
    mockFetch({
      name: 'Lightning Bolt',
      typ: 'Instant',
      text_de: 'Originaltext',
      marktwert: '1.00',
      prints: [
        { set_name: 'Beta', bild_url: '', preis: '4.50' }, // Index 0 hat echten Preis
      ],
    });

    render(
      <MemoryRouter>
        <KartenSuche currentUser="tester" />
      </MemoryRouter>
    );

    await user.type(screen.getByPlaceholderText(/Kartennamen eingeben/i), 'Lightning Bolt');
    await user.keyboard('{Enter}');
    await screen.findByRole('heading', { name: 'Lightning Bolt' });

    await waitFor(() => {
      const priceP = [...document.querySelectorAll('p')].find(
        (p) => p.style.fontWeight === '700' && /€/.test(p.textContent)
      );
      expect(priceP.textContent).toMatch(/4\.50\s*€/);
    });
  });
});
