import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
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
})