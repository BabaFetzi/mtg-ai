import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import './index.css'

// Globaler Fetch-Interceptor: hängt das Bearer-Token an alle /api/-Requests
// und erneuert bei 401 automatisch das Access-Token per Refresh-Token
// (siehe utils/authFetch.js).
import { installAuthInterceptor } from './utils/authFetch';
import { MeldungProvider } from './components/layout/Meldungen';
import Fehlergrenze from './components/layout/Fehlergrenze';
installAuthInterceptor();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      {/* Ganz aussen: Rückmeldungen und Rückfragen müssen aus jeder
          Komponente erreichbar sein, auch aus der Landing Page. */}
      <MeldungProvider>
        {/* Ohne diese Grenze entfernt React bei einem unbehandelten Fehler den
            ganzen Baum -- der Nutzer sieht dann eine WEISSE SEITE ohne Hinweis
            und ohne Weg zurück. Innerhalb von MeldungProvider, damit die
            Ersatzansicht dieselbe Gestaltung benutzen kann. */}
        <Fehlergrenze>
          <App />
        </Fehlergrenze>
      </MeldungProvider>
    </BrowserRouter>
  </StrictMode>,
)