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

  test('ein Klick daneben schliesst das Menü', async () => {
    const nutzer = userEvent.setup();
    zeigeKopfzeile();

    await nutzer.click(screen.getByRole('button', { name: /tester/ }));
    await nutzer.click(document.body);

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Abmelden' })).not.toBeInTheDocument();
    });
  });
});
