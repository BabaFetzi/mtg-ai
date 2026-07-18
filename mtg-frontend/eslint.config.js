import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
  {
    // Vitest läuft mit `globals: true` (siehe vite.config.js) -- describe/
    // test/expect/vi etc. sind zur Laufzeit global, ESLint muss das separat
    // wissen, sonst gelten sie als "not defined" (no-undef).
    files: ['**/*.test.{js,jsx}', 'src/test/**/*.{js,jsx}'],
    languageOptions: {
      // `global` (statt `window`) wird in Tests genutzt, um z.B. `fetch` zu
      // mocken -- das ist Node-Land, nicht Browser-Land, daher zusätzlich
      // globals.node.
      globals: { ...globals.vitest, ...globals.node },
    },
  },
])
