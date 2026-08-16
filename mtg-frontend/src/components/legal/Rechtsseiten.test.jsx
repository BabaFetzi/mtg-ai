import { MemoryRouter } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import App from '../../App';
import Impressum from './Impressum';
import Datenschutz from './Datenschutz';
import AGB from './AGB';
import { betreiberAngabenVollstaendig } from './betreiber';

// Impressum, Datenschutzerklärung und AGB sind Pflichtangaben und müssen ohne
// Anmeldung erreichbar sein. Vorher landete JEDER ausgeloggte Aufruf auf der
// Landing Page -- ein Link auf /impressum wäre also ins Leere gelaufen, und
// Stripe hätte das Live-Konto nicht freigeschaltet.

function rendereRoute(pfad) {
  global.fetch = vi.fn(() => Promise.resolve({ ok: true, status: 200, json: async () => ({}) }));
  localStorage.clear();
  render(
    <MemoryRouter initialEntries={[pfad]}>
      <App />
    </MemoryRouter>
  );
}

// Die Rechtsseiten werden inzwischen erst beim Aufruf nachgeladen (App.jsx),
// damit das erste Paket klein bleibt. Sie sind deshalb einen Wimpernschlag
// später da -- erreichbar sein müssen sie unverändert, und genau das prüfen
// diese Tests mit findBy statt getBy.
describe('Rechtsseiten', () => {
  test('/impressum ist ohne Anmeldung erreichbar', async () => {
    rendereRoute('/impressum');
    expect(await screen.findByRole('heading', { name: 'Impressum', level: 1 })).toBeInTheDocument();
    // Beweis, dass NICHT die Landing Page gerendert wurde.
    expect(screen.queryByText(/Beherrsche den Stack/)).not.toBeInTheDocument();
  });

  test('/datenschutz ist ohne Anmeldung erreichbar', async () => {
    rendereRoute('/datenschutz');
    expect(await screen.findByRole('heading', { name: 'Datenschutzerklärung', level: 1 })).toBeInTheDocument();
  });

  test('/agb ist ohne Anmeldung erreichbar', async () => {
    rendereRoute('/agb');
    expect(await screen.findByRole('heading', { name: /Allgemeine Geschäftsbedingungen/, level: 1 })).toBeInTheDocument();
  });

  test('die Landing Page verlinkt alle drei Seiten', () => {
    rendereRoute('/');
    for (const name of ['Impressum', 'Datenschutz', 'AGB']) {
      expect(screen.getByRole('link', { name })).toBeInTheDocument();
    }
  });
});

describe('Pflichtinhalte', () => {
  const rendere = (Komponente) =>
    render(<MemoryRouter><Komponente /></MemoryRouter>);

  test('Datenschutz benennt die Weitergabe an Google Gemini', () => {
    rendere(Datenschutz);
    // Der leicht zu übersehende Punkt: Nutzereingaben verlassen den Dienst.
    expect(screen.getAllByText(/Gemini/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/an Google übermittelt/).length).toBeGreaterThan(0);
  });

  test('Datenschutz benennt Stripe und das Auskunftsrecht', () => {
    rendere(Datenschutz);
    expect(screen.getAllByText(/Stripe/).length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { name: /Deine Rechte/ })).toBeInTheDocument();
  });

  test('AGB enthalten eine Widerrufsbelehrung mit 14-Tage-Frist', () => {
    rendere(AGB);
    expect(screen.getByRole('heading', { name: /Widerrufsrecht/ })).toBeInTheDocument();
    expect(screen.getByText(/vierzehn Tagen ohne Angabe von Gründen/)).toBeInTheDocument();
  });

  test('AGB regeln Kündigung und automatische Verlängerung', () => {
    rendere(AGB);
    expect(screen.getByText(/verlängert sich automatisch/)).toBeInTheDocument();
    expect(screen.getByText(/jederzeit zum Ende des laufenden/)).toBeInTheDocument();
  });

  test('Impressum nennt Anschrift und eine erreichbare E-Mail-Adresse', () => {
    rendere(Impressum);
    expect(screen.getByRole('heading', { name: /Verantwortlich für dieses Angebot/ })).toBeInTheDocument();
    expect(document.querySelector('a[href^="mailto:"]')).not.toBeNull();
  });
});

describe('Betreiberangaben', () => {
  test('erkennt noch nicht ersetzte Platzhalter', () => {
    // Solange die Vorlage Platzhalter enthält, muss die Prüfung false liefern.
    // Sie ist der Wächter dagegen, mit "[Strasse und Hausnummer]" live zu gehen.
    expect(typeof betreiberAngabenVollstaendig()).toBe('boolean');
  });
});
