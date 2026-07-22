// ============================================================================
// authFetch.test.js – Beweist den automatischen Token-Refresh im Frontend:
// Access-Token abgelaufen (401) -> Interceptor holt neues Token -> Original-
// Request wird wiederholt -> Nutzer bleibt eingeloggt.
// ============================================================================

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { installAuthInterceptor, setTokens, clearTokens, getAccessToken } from "./authFetch";

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("authFetch Interceptor", () => {
  let uninstall;
  let baseFetch;

  beforeEach(() => {
    clearTokens();
    baseFetch = vi.fn();
    window.fetch = baseFetch;
    uninstall = installAuthInterceptor(window);
  });

  afterEach(() => {
    uninstall();
    clearTokens();
  });

  it("hängt das Bearer-Token an /api/-Requests an", async () => {
    setTokens("mein-access", "mein-refresh");
    baseFetch.mockResolvedValueOnce(jsonResponse({ ok: true }));

    await window.fetch("/api/sammlung/alice");

    const [, options] = baseFetch.mock.calls[0];
    expect(options.headers.Authorization).toBe("Bearer mein-access");
  });

  it("KERNSZENARIO: 401 -> automatischer Refresh -> Retry mit neuem Token -> eingeloggt", async () => {
    setTokens("abgelaufen", "gueltiges-refresh");

    baseFetch.mockImplementation(async (url, options = {}) => {
      if (url === "/api/auth/refresh") {
        const body = JSON.parse(options.body);
        expect(body.refresh_token).toBe("gueltiges-refresh");
        return jsonResponse({
          erfolg: true,
          access_token: "frisches-access",
          refresh_token: "frisches-refresh",
        });
      }
      // Erster Versuch mit abgelaufenem Token -> 401, Retry mit frischem -> 200
      const auth = options.headers?.Authorization;
      if (auth === "Bearer abgelaufen") return jsonResponse({ detail: "expired" }, 401);
      if (auth === "Bearer frisches-access") return jsonResponse({ erfolg: true, alben: {} });
      return jsonResponse({ detail: "unexpected" }, 500);
    });

    const res = await window.fetch("/api/sammlung/alice");
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data.erfolg).toBe(true);
    // Neue Tokens wurden gespeichert (Rotation)
    expect(getAccessToken()).toBe("frisches-access");
    expect(localStorage.getItem("refresh_token")).toBe("frisches-refresh");
  });

  it("scheiternder Refresh -> Tokens gelöscht + auth:logout Event", async () => {
    setTokens("abgelaufen", "kaputtes-refresh");
    const logoutListener = vi.fn();
    window.addEventListener("auth:logout", logoutListener);

    baseFetch.mockImplementation(async (url) => {
      if (url === "/api/auth/refresh") return jsonResponse({ detail: "invalid" }, 401);
      return jsonResponse({ detail: "expired" }, 401);
    });

    const res = await window.fetch("/api/sammlung/alice");

    expect(res.status).toBe(401);
    expect(getAccessToken()).toBe("");
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(logoutListener).toHaveBeenCalled();
    window.removeEventListener("auth:logout", logoutListener);
  });

  it("401 beim Login startet KEINEN Refresh-Zyklus (falsches Passwort)", async () => {
    setTokens("", "irgendein-refresh");
    baseFetch.mockResolvedValue(jsonResponse({ erfolg: false }, 401));

    await window.fetch("/api/login", { method: "POST", body: "{}" });

    const refreshCalls = baseFetch.mock.calls.filter(([u]) => u === "/api/auth/refresh");
    expect(refreshCalls.length).toBe(0);
  });

  it("parallele 401s lösen nur EINEN Refresh aus (Single-Flight)", async () => {
    setTokens("abgelaufen", "gueltiges-refresh");
    let refreshCount = 0;

    baseFetch.mockImplementation(async (url, options = {}) => {
      if (url === "/api/auth/refresh") {
        refreshCount += 1;
        await new Promise((r) => setTimeout(r, 20));
        return jsonResponse({ erfolg: true, access_token: "neu", refresh_token: "neu-r" });
      }
      const auth = options.headers?.Authorization;
      if (auth === "Bearer neu") return jsonResponse({ ok: true });
      return jsonResponse({}, 401);
    });

    await Promise.all([
      window.fetch("/api/decks/alice"),
      window.fetch("/api/sammlung/alice"),
      window.fetch("/api/trends"),
    ]);

    expect(refreshCount).toBe(1);
  });
});
