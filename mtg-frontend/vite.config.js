import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],

  // Entwicklungsausgaben fliegen aus dem Produktions-Build.
  //
  // Warum: Im Quelltext stehen rund 17 console.log (Kamera-Auswahl,
  // WebSocket-Zustand, Deck-Synchronisation). Zugangsdaten stehen nicht darin,
  // aber sie zeigen Fremden den inneren Ablauf, laufen bei jedem Kamerabild
  // mit, und sie machen die Konsole so voll, dass eine ECHTE Fehlermeldung
  // darin untergeht.
  //
  // WICHTIG ist, was BLEIBT: console.warn und console.error. Die Fehlergrenze
  // (components/layout/Fehlergrenze.jsx) schreibt ihren Fehler ausdrücklich
  // dorthin -- ein pauschales Entfernen aller console-Aufrufe würde genau die
  // Meldung verschlucken, wegen der man später nachsehen kann, was einem
  // Nutzer passiert ist.
  //
  // Über `define` statt über eine Minifier-Einstellung: Vite 8 transformiert
  // mit Oxc, und weder `esbuild.pure` noch ein Oxc-Gegenstück greift hier
  // (nachgemessen: die Aufrufe standen unverändert im Bundle). `define`
  // ersetzt den Ausdruck beim Zusammenbauen und ist die eingebaute, von der
  // Werkzeugkette unabhängige Möglichkeit.
  //
  // Nur bei `vite build`: im Entwicklungsbetrieb bleibt alles sichtbar.
  ...(command === 'build'
    ? { define: { 'console.log': '(()=>{})', 'console.debug': '(()=>{})' } }
    : {}),

  server: {
    port: 5175,
    allowedHosts: true,
    // HIER IST DIE MAGIE: Leitet alle /api Anfragen ans Backend weiter!
    proxy: {
      '/api/vision/stream': {
        target: 'ws://127.0.0.1:8001',
        changeOrigin: true,
        ws: true,
        secure: false,
      },
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        secure: false,
      }
    }
  },
  // https://vitest.dev/config/ -- läuft über dieselbe Vite-Config (Plugins,
  // Aliase etc.), damit Tests dasselbe Modul-Resolving sehen wie `vite dev`.
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    globals: true,
    css: false,
  },
}))
