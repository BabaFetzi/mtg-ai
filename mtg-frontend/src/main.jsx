import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import './index.css'

// Globaler Fetch-Interceptor: hängt das Bearer-Token an alle /api/-Requests
// und erneuert bei 401 automatisch das Access-Token per Refresh-Token
// (siehe utils/authFetch.js).
import { installAuthInterceptor } from './utils/authFetch';
installAuthInterceptor();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)