import { describe, test, expect } from 'vitest';
import { zaehleAuswahl } from './uebernahme';

// Die Zahl aus dieser Rechnung steht in der Rueckfrage ("3 Exemplare werden
// angelegt"). Stimmt sie nicht mit dem Knopf und dem Ergebnis ueberein,
// bestaetigt jemand etwas anderes, als danach passiert -- und merkt es nicht.

const BOLT = { name: 'Lightning Bolt', fehlt: 4, standardland: false };
const SOL = { name: 'Sol Ring', fehlt: 1, standardland: false };
const BERG = { name: 'Mountain', fehlt: 12, standardland: true };
const VOLLSTAENDIG = { name: 'Island', fehlt: 0, standardland: false };
const KARTEN = [BOLT, SOL, BERG, VOLLSTAENDIG];

describe('zaehleAuswahl', () => {
  test('ohne Liste gilt die Gesamtzahl', () => {
    expect(zaehleAuswahl(null, KARTEN, 5)).toBe(5);
    expect(zaehleAuswahl(undefined, KARTEN, 5)).toBe(5);
  });

  test('blosse Namen bedeuten alles, was fehlt', () => {
    expect(zaehleAuswahl(['Lightning Bolt', 'Sol Ring'], KARTEN, 5)).toBe(5);
  });

  test('eine verringerte Stueckzahl wird mitgezaehlt', () => {
    // DER Fehler: Mit includes(name) fiel diese Form heraus. Der Knopf bot 3
    // an, die Rueckfrage kuendigte 1 an, angelegt wurden 3.
    const auswahl = [{ name: 'Lightning Bolt', anzahl: 2 }, 'Sol Ring'];

    expect(zaehleAuswahl(auswahl, KARTEN, 5)).toBe(3);
  });

  test('mehr als fehlt wird gedeckelt', () => {
    expect(zaehleAuswahl([{ name: 'Lightning Bolt', anzahl: 999 }], KARTEN, 5)).toBe(4);
  });

  test('eine negative Zahl zieht nichts ab', () => {
    expect(zaehleAuswahl([{ name: 'Lightning Bolt', anzahl: -3 }, 'Sol Ring'], KARTEN, 5)).toBe(1);
  });

  test('anzahl ohne Wert heisst alles', () => {
    expect(zaehleAuswahl([{ name: 'Lightning Bolt' }], KARTEN, 5)).toBe(4);
  });

  test('Standardlaender zaehlen hier nicht mit', () => {
    // Sie haengen am eigenen Haekchen und werden getrennt addiert.
    expect(zaehleAuswahl(['Mountain'], KARTEN, 5)).toBe(0);
  });

  test('vollstaendig vorhandene Karten zaehlen nicht', () => {
    expect(zaehleAuswahl(['Island'], KARTEN, 5)).toBe(0);
  });

  test('ein unbekannter Name wird uebergangen', () => {
    expect(zaehleAuswahl(['Black Lotus', 'Sol Ring'], KARTEN, 5)).toBe(1);
  });

  test('eine leere Liste ergibt null', () => {
    // "Nichts angekreuzt" heisst nichts -- nicht alles.
    expect(zaehleAuswahl([], KARTEN, 5)).toBe(0);
  });
});
