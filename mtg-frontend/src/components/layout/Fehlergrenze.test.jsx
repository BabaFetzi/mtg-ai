/**
 * Ein Fehler in einem Bauteil darf nicht die ganze Seite kosten.
 *
 * React entfernt bei einem unbehandelten Fehler den KOMPLETTEN Baum. Fuer den
 * Nutzer heisst das nicht "eine Funktion streikt", sondern "die Webseite ist
 * weiss" -- kein Hinweis, kein Weg zurueck, nichts zum Melden.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import Fehlergrenze from './Fehlergrenze';

function Kaputt() {
  throw new Error('Karte ohne Preis');
}

describe('Fehlergrenze', () => {
  beforeEach(() => {
    // React schreibt den Fehler selbst in die Konsole -- das ist im Test nur Laerm.
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('zeigt im Normalfall einfach den Inhalt', () => {
    render(<Fehlergrenze><p>Meine Sammlung</p></Fehlergrenze>);

    expect(screen.getByText('Meine Sammlung')).toBeTruthy();
  });

  it('faengt einen Fehler ab, statt die Seite leer zu lassen', () => {
    render(<Fehlergrenze><Kaputt /></Fehlergrenze>);

    expect(screen.getByRole('alert')).toBeTruthy();
    expect(screen.getByText(/schiefgelaufen/i)).toBeTruthy();
  });

  it('bietet einen Weg zurueck', () => {
    render(<Fehlergrenze><Kaputt /></Fehlergrenze>);

    expect(screen.getByRole('button', { name: /neu laden/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /startseite/i })).toBeTruthy();
  });

  it('beruhigt zur Datenlage -- das ist die erste Sorge des Nutzers', () => {
    render(<Fehlergrenze><Kaputt /></Fehlergrenze>);

    expect(screen.getByText(/Daten sind nicht betroffen/i)).toBeTruthy();
  });

  it('verraet dem Nutzer nicht die technische Ursache', () => {
    render(<Fehlergrenze><Kaputt /></Fehlergrenze>);

    expect(screen.queryByText(/Karte ohne Preis/)).toBeNull();
  });
});
