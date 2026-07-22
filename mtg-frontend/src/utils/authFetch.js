// ============================================================================
// utils/authFetch.js – Zentrale Token-Verwaltung + globaler Fetch-Interceptor
//
// Verantwortlich für:
//  - Speichern/Lesen/Löschen von Access- und Refresh-Token (localStorage)
//  - Automatisches Anhängen des Bearer-Headers an alle /api/-Requests
//  - Automatisches Erneuern des Access-Tokens bei 401-Antworten über
//    POST /api/auth/refresh (einmaliger Retry des Original-Requests)
//
// Damit bleibt ein Nutzer nach Ablauf des 30-Minuten-Access-Tokens
// eingeloggt, solange sein Refresh-Token (30 Tage) gültig ist. Schlägt der
// Refresh fehl, werden die Tokens gelöscht und das Event "auth:logout"
// gefeuert, damit die App ihren Login-Zustand zurücksetzen kann.
// ============================================================================

const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

export function getAccessToken() {
  return localStorage.getItem(ACCESS_KEY) || "";
}

export function setTokens(accessToken, refreshToken) {
  localStorage.setItem(ACCESS_KEY, accessToken || "");
  if (refreshToken) {
    localStorage.setItem(REFRESH_KEY, refreshToken);
  }
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

// Endpunkte, bei denen ein 401 KEIN Token-Problem ist (falsches Passwort,
// ungültiges Refresh-Token) -- hier niemals einen Refresh-Zyklus starten.
const NO_REFRESH_PATHS = ["/api/login", "/api/register", "/api/auth/refresh"];

function isApiUrl(url) {
  return typeof url === "string" && (url.startsWith("/api/") || url.includes("/api/"));
}

function shouldTryRefresh(url) {
  return isApiUrl(url) && !NO_REFRESH_PATHS.some((p) => url.includes(p));
}

// Single-Flight: laufen mehrere Requests parallel in ein 401, wird nur EIN
// Refresh ausgeführt; alle anderen warten auf dasselbe Promise. Nach
// Abschluss wird das Promise sofort (Mikrotask, deterministisch) freigegeben:
// bereits Wartende halten die Referenz, spätere 401s starten einen frischen
// Refresh-Versuch.
let refreshPromise = null;

async function doRefresh(fetchImpl) {
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  if (!refreshToken) return false;
  try {
    const res = await fetchImpl("/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    if (!data || !data.access_token) return false;
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

function refreshTokens(fetchImpl) {
  if (!refreshPromise) {
    refreshPromise = doRefresh(fetchImpl).finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

function withAuthHeader(options) {
  const token = getAccessToken();
  if (!token) return options;
  return {
    ...options,
    headers: { ...(options.headers || {}), Authorization: `Bearer ${token}` },
  };
}

/**
 * Installiert den globalen Fetch-Interceptor. Einmalig beim App-Start
 * aufrufen (main.jsx). `targetWindow` ist injizierbar für Tests.
 */
export function installAuthInterceptor(targetWindow = window) {
  const originalFetch = targetWindow.fetch.bind(targetWindow);

  targetWindow.fetch = async (url, options = {}) => {
    if (!isApiUrl(url)) {
      return originalFetch(url, options);
    }

    let response = await originalFetch(url, withAuthHeader(options));

    if (response.status === 401 && shouldTryRefresh(url)) {
      const refreshed = await refreshTokens(originalFetch);
      if (refreshed) {
        // Original-Request genau EINMAL mit dem neuen Token wiederholen.
        response = await originalFetch(url, withAuthHeader(options));
      } else {
        clearTokens();
        targetWindow.dispatchEvent(new Event("auth:logout"));
      }
    }
    return response;
  };

  return () => {
    targetWindow.fetch = originalFetch;
    refreshPromise = null;
  };
}
