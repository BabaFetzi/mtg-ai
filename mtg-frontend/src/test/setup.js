import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// RTL hängt Komponenten in das echte jsdom-`document` -- ohne expliziten
// Unmount nach jedem Test würden mehrere Tests denselben DOM akkumulieren
// und sich gegenseitig Queries (getByText etc.) kaputt machen.
afterEach(() => {
  cleanup();
});
