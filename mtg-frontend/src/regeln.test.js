import { describe, test, expect } from 'vitest';
import { ESLint } from 'eslint';

/**
 * Ein Hook in einer gewöhnlichen Funktion -- der Fehler, der den Knopf
 * "Fehlende Karten in die Sammlung übernehmen" lahmgelegt hat.
 *
 * Was passiert war: In DecksView.jsx stand
 *
 *     function getCardCountStatus(totalCards, format) {
 *       const { melde, bestaetige } = useMeldung();
 *
 * -- also in einer Hilfsfunktion, nicht in der Komponente. Damit gab es in
 * DecksView weder `melde` noch `bestaetige`. Jeder Klick endete sofort mit
 * "bestaetige is not defined": keine Rückfrage, kein API-Aufruf, keine
 * Meldung. Für den Nutzer tat der Knopf schlicht nichts. Betroffen war auch
 * das Löschen eines Decks und jede Rückmeldung dieser Ansicht.
 *
 * Warum ein eigener Test und nicht "npm run lint"
 * -----------------------------------------------
 * eslint-plugin-react-hooks ist längst eingerichtet und hätte den Fehler
 * punktgenau gemeldet -- nur führt niemand den Linter aus. Ein Werkzeug, das
 * man erst aufrufen muss, hat den Fehler nicht verhindert.
 *
 * Geprüft wird ausschliesslich rules-of-hooks. Die übrigen 85 Meldungen sind
 * Altbestand (ungenutzte Variablen, Abhängigkeitslisten); sie alle zur
 * Bedingung zu machen hiesse, den Testlauf ab sofort rot zu lassen. Diese
 * eine Regel ist die gefährliche: Sie bricht nicht den Stil, sondern die
 * laufende Anwendung -- und zwar lautlos.
 */

const REGEL = 'react-hooks/rules-of-hooks';

describe('Regeln, die zur Laufzeit brechen', () => {
  test(`kein Verstoss gegen ${REGEL}`, async () => {
    const eslint = new ESLint({ cwd: process.cwd() });
    const ergebnisse = await eslint.lintFiles(['src/**/*.{js,jsx}']);

    const verstoesse = ergebnisse.flatMap((datei) =>
      datei.messages
        .filter((m) => m.ruleId === REGEL)
        .map((m) => `${datei.filePath.replace(process.cwd() + '/', '')}:${m.line} ${m.message}`)
    );

    expect(verstoesse, verstoesse.join('\n')).toEqual([]);
  }, 120000);
});
