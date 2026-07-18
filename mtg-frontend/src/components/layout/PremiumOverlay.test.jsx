import { MemoryRouter, useLocation } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PremiumOverlay from './PremiumOverlay';

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe">{location.pathname}</div>;
}

function renderOverlay({ onShowPremiumModal, initialPath = '/decks' } = {}) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <LocationProbe />
      <PremiumOverlay onShowPremiumModal={onShowPremiumModal} />
    </MemoryRouter>
  );
}

describe('PremiumOverlay', () => {
  test('zeigt den Premium-Hinweis an', () => {
    renderOverlay();
    expect(screen.getByText('Premium Feature')).toBeInTheDocument();
    expect(screen.getByText(/Inhalt verborgen/i)).toBeInTheDocument();
  });

  test('ruft onShowPremiumModal auf und navigiert NICHT weg, wenn ein Callback übergeben wurde', async () => {
    const user = userEvent.setup();
    const onShowPremiumModal = vi.fn();
    renderOverlay({ onShowPremiumModal });

    await user.click(screen.getByText('Premium Feature'));

    expect(onShowPremiumModal).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/decks');
  });

  test('navigiert zu /premium, wenn kein Modal-Callback übergeben wurde', async () => {
    const user = userEvent.setup();
    renderOverlay({ onShowPremiumModal: undefined });

    await user.click(screen.getByText('Premium Feature'));

    expect(screen.getByTestId('location-probe')).toHaveTextContent('/premium');
  });
});
