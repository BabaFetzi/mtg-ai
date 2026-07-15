from fastapi.testclient import TestClient

from main import app, get_allowed_origins, DEV_ORIGINS

client = TestClient(app)


def test_get_allowed_origins_defaults_to_localhost_dev_only(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert get_allowed_origins() == DEV_ORIGINS


def test_get_allowed_origins_uses_only_configured_domains(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://grana.app, https://www.grana.app")
    origins = get_allowed_origins()
    assert origins == ["https://grana.app", "https://www.grana.app"]
    # Configuring real production domains must not silently keep localhost allowed too.
    assert "http://localhost:5175" not in origins


def test_wildcard_origin_is_never_returned(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert "*" not in get_allowed_origins()
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://grana.app")
    assert "*" not in get_allowed_origins()


# ============================================================================
# Regression tests against the live app: the old config was
# allow_origins=["*"], so starlette's CORSMiddleware reflected literally any
# Origin header back as Access-Control-Allow-Origin. These prove that's gone
# by exercising the actual middleware, not just the origin list.
# ============================================================================
def test_configured_dev_origin_is_reflected_by_cors_middleware():
    response = client.get("/health", headers={"Origin": "http://localhost:5175"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5175"


def test_arbitrary_origin_is_not_reflected_by_cors_middleware():
    response = client.get("/health", headers={"Origin": "https://evil-attacker.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
