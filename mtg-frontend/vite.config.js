import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: [
      'feminism-dirtiness-blissful.ngrok-free.dev'
    ],
    // HIER IST DIE MAGIE: Leitet alle /api Anfragen ans Backend weiter!
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      }
    }
  }
})