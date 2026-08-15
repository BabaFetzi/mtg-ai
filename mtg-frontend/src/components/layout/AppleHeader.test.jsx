import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AppleHeader from './AppleHeader';

// Punkt 4 der Oberflächen-Überarbeitung: sechs namenlose Farbkreise und der
// Hell/Dunkel-Schalter standen dauerhaft zwischen den Seitenlinks und sahen aus
// wie Bedienelemente der aktuellen Seite. Sie sind Einstellungen und liegen
// jetzt im Menü unter dem Benutzernamen.

function zeigeKopfzeile(zusatz = {}) {
  const props = {
    currentUser: 'tester',
    setCurrentUser: vi.fn(),
    isDarkMode: true,
    setIsDarkMode: vi.fn(),
    activeTheme: 'default',
    setActiveTheme: vi.fn(),
    ...zusatz,
  };
  render(
    <MemoryRouter>
      <AppleHeader {...props} />
    </MemoryRouter>
  );
  return props;
}

describe('AppleHeader – Konto-Menü', () => {
  test('Farbwelten und Abmelden sind erst im Menü, nicht in der Leiste', async () => {
    const nutzer = userEvent.setup();
    zeigeKopfzeile();

    expect(screen.queryByRole('button', { name: /Abmelden/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Gebirge/ })).not.toBeInTheDocument();

    await nutzer.click(screen.getByRole('button', { name: /tester/ }));

    expect(screen.getByRole('button', { name: /Abmelden/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Gebirge/ })).toBeInTheDocument();
  });

  test('Farbwelt wählen reicht die Auswahl nach oben', async () => {
    const nutzer = userEvent.setup();
    const props = zeigeKopfzeile();

    await nutzer.click(screen.getByRole('button', { name: /tester/ }));
    await nutzer.click(screen.getByRole('button', { name: /Wald/ }));

    expect(props.setActiveTheme).toHaveBeenCalledWith('forest');
  });

  test('der Design-Schalter benennt das Ziel statt nur ein Symbol zu zeigen', async () => {
    const nutzer = userEvent.setup();
    const props = zeigeKopfzeile({ isDarkMode: true });

    await nutzer.click(screen.getByRole('button', { name: /tester/ }));
    await nutzer.click(screen.getByRole('button', { name: 'Helles Design' }));

    expect(props.setIsDarkMode).toHaveBeenCalledWith(false);
  });

  test('Abmelden meldet ab und schliesst das Menü', async () => {
    const nutzer = userEvent.setup();
    const props = zeigeKopfzeile();

    await nutzer.click(screen.getByRole('button', { name: /tester/ }));
    await nutzer.click(screen.getByRole('button', { name: 'Abmelden' }));

    expect(props.setCurrentUser).toHaveBeenCalledWith(null);
  });

  test('Escape schliesst das Menü', async () => {
    const nutzer = userEvent.setup();
    zeigeKopfzeile();

    await nutzer.click(screen.getByRole('button', { name: /tester/ }));
    expect(screen.getByRole('button', { name: 'Abmelden' })).toBeInTheDocument();

    await nutzer.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Abmelden' })).not.toBeInTheDocument();
    });
  });

  test('ein Klick daneben schliesst das Konto-Menü', async () => {
    const nutzer = userEvent.setup();
    zeigeKopfzeile();

    await nutzer.click(screen.getByRole('button', { name: /tester/ }));
    await nutzer.click(document.body);

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Abmelden' })).not.toBeInTheDocument();
    });
  });
});

// Auf dem Handy lief die waagrechte Linkliste aus dem Bild: bei 390px lagen
// "Grana Pro Upgrade" und das Konto ausserhalb des Fensters, gemessen im
// Browser. Die Unterpunkte öffneten sich ausserdem nur beim Darüberfahren mit
// der Maus -- auf einem Touchgerät gibt es das nicht.
describe('AppleHeader – Handy-Navigation', () => {
  test('der Menüknopf öffnet die Bereiche samt Unterpunkten', async () => {
    const nutzer = userEvent.setup();
    zeigeKopfzeile();

    expect(screen.queryByRole('button', { name: 'Synergie-Analyse' })).not.toBeInTheDocument();

    await nutzer.click(screen.getByRole('button', { name: 'Menü öffnen' }));

    expect(screen.getByRole('button', { name: 'Synergie-Analyse' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Proxy-Druck (PDF)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Grana Pro Upgrade' })).toBeInTheDocument();
  });

  test('ein Unterpunkt schliesst das Menü wieder', async () => {
    const nutzer = userEvent.setup();
    zeigeKopfzeile();

    await nutzer.click(screen.getByRole('button', { name: 'Menü öffnen' }));
    await nutzer.click(screen.getByRole('button', { name: 'MTG Rules Judge' }));

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'MTG Rules Judge' })).not.toBeInTheDocument();
    });
  });

  test('Abmelden und Farbwelt sind auch auf dem Handy erreichbar', async () => {
    const nutzer = userEvent.setup();
    const props = zeigeKopfzeile();

    await nutzer.click(screen.getByRole('button', { name: 'Menü öffnen' }));
    await nutzer.click(screen.getByRole('button', { name: /Sumpf/ }));
    expect(props.setActiveTheme).toHaveBeenCalledWith('swamp');

    await nutzer.click(screen.getByRole('button', { name: 'Abmelden' }));
    expect(props.setCurrentUser).toHaveBeenCalledWith(null);
  });

  test('Escape schliesst die Handy-Navigation', async () => {
    const nutzer = userEvent.setup();
    zeigeKopfzeile();

    await nutzer.click(screen.getByRole('button', { name: 'Menü öffnen' }));
    await nutzer.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Synergie-Analyse' })).not.toBeInTheDocument();
    });
  });
});
