import { MemoryRouter } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import JudgeWidget from './JudgeWidget';

// `userRole` kommt in der echten App aus einem State, der beim Laden per
// GET /api/user/role/{user} gesetzt wird -- diese Tests setzen es direkt als
// Prop, um sowohl den Normalfall (Premium-User bekommt eine echte Antwort)
// als auch die früher gefixte Race Condition nachzustellen: das Frontend
// hält den Nutzer (noch) für Premium, das Backend antwortet aber mit der
// Paywall, weil der Rollen-Stand dort bereits/immer noch "free" ist.
function renderOpenWidget({ userRole = 'premium', onShowPremiumModal } = {}) {
  const setOpen = vi.fn();
  // MemoryRouter, weil das für free-Nutzer gerenderte PremiumOverlay
  // intern useNavigate() aufruft.
  render(
    <MemoryRouter>
      <JudgeWidget
        open={true}
        setOpen={setOpen}
        currentUser="hovertest"
        userRole={userRole}
        onShowPremiumModal={onShowPremiumModal}
      />
    </MemoryRouter>
  );
  return { setOpen };
}

async function askQuestion(user, question) {
  const input = screen.getByPlaceholderText('Frag den Judge...');
  await user.type(input, question);
  await user.keyboard('{Enter}');
}

describe('JudgeWidget', () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  test('Premium-Nutzer bekommt die echte Judge-Antwort im Chat angezeigt', async () => {
    const user = userEvent.setup();
    global.fetch.mockResolvedValueOnce({
      json: async () => ({ antwort: 'Der Stack löst sich von oben nach unten auf.' }),
    });

    renderOpenWidget({ userRole: 'premium' });
    await askQuestion(user, 'Wie funktioniert der Stack?');

    expect(await screen.findByText('Der Stack löst sich von oben nach unten auf.')).toBeInTheDocument();
    expect(screen.queryByText(/PAYWALL/i)).not.toBeInTheDocument();
  });

  test('Paywall-Antwort (HTTP 200, error: "paywall") zeigt eine klare Upgrade-Meldung statt des rohen "PAYWALL:"-Texts', async () => {
    const user = userEvent.setup();
    const onShowPremiumModal = vi.fn();
    global.fetch.mockResolvedValueOnce({
      json: async () => ({
        error: 'paywall',
        antwort: 'PAYWALL: Der KI-Judge steht nur Premium-Mitgliedern zur Verfügung. Bitte upgrade deine Rolle im Premium-Tab!',
      }),
    });

    // userRole="premium", damit Input/Button nicht disabled sind -- genau die
    // Situation, in der die alte Rolle im Frontend noch "premium" ist, das
    // Backend aber bereits/immer noch "free" sieht.
    renderOpenWidget({ userRole: 'premium', onShowPremiumModal });
    await askQuestion(user, 'Wie funktioniert der Stack?');

    expect(
      await screen.findByText(
        'Diese Funktion ist nur für Premium-Mitglieder verfügbar. Upgrade deine Rolle im Premium-Tab, um den KI-Judge zu nutzen.'
      )
    ).toBeInTheDocument();
    // Der alte Bug: der rohe Text mit "PAYWALL:"-Präfix landete unverändert im Chat.
    expect(screen.queryByText(/^PAYWALL:/)).not.toBeInTheDocument();
    expect(onShowPremiumModal).toHaveBeenCalledTimes(1);
  });

  test('Free-Nutzer sieht das Premium-Overlay, Eingabe und Senden-Button sind deaktiviert', () => {
    renderOpenWidget({ userRole: 'free' });

    expect(screen.getByText('Premium Feature')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Frag den Judge...')).toBeDisabled();
  });

  test('Netzwerkfehler zeigt eine Fehlermeldung im Chat, statt zu crashen', async () => {
    const user = userEvent.setup();
    global.fetch.mockRejectedValueOnce(new Error('network down'));

    renderOpenWidget({ userRole: 'premium' });
    await askQuestion(user, 'Wie funktioniert der Stack?');

    expect(await screen.findByText('Verbindungsfehler zum Judge-Netzwerk.')).toBeInTheDocument();
  });
});
