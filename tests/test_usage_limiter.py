import importlib
import socket
import subprocess
import time as time_module

import pytest
import redis as redis_lib


def _get_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def redis_url():
    """Startet einen echten, isolierten redis-server-Prozess für diese Tests --
    kein Mock, um zu beweisen, dass die INCR/EXPIRE-Logik tatsächlich funktioniert."""
    port = _get_free_port()
    try:
        proc = subprocess.Popen(
            ["redis-server", "--port", str(port), "--save", "", "--appendonly", "no"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pytest.skip("redis-server ist in dieser Umgebung nicht installiert")

    url = f"redis://127.0.0.1:{port}/0"
    client = redis_lib.from_url(url, socket_timeout=1)
    for _ in range(50):
        try:
            client.ping()
            break
        except Exception:
            time_module.sleep(0.1)
    else:
        proc.terminate()
        pytest.skip("redis-server ist nicht rechtzeitig gestartet")

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def ul(redis_url, monkeypatch):
    """Frisch geladenes usage_limiter-Modul mit REDIS_URL auf den Test-Redis gesetzt."""
    monkeypatch.setenv("REDIS_URL", redis_url)
    import services.usage_limiter as usage_limiter
    importlib.reload(usage_limiter)
    return usage_limiter


def test_ai_usage_allows_up_to_limit_then_blocks(ul):
    username = "limit_test_user"
    results = [ul.check_and_increment_ai_usage(username, limit=3) for _ in range(5)]
    assert results == [True, True, True, False, False]


def test_ai_usage_limit_is_tracked_per_user(ul):
    for _ in range(3):
        assert ul.check_and_increment_ai_usage("user_a", limit=3) is True
    assert ul.check_and_increment_ai_usage("user_a", limit=3) is False

    # Ein anderer Nutzer hat ein unabhängiges eigenes Budget.
    assert ul.check_and_increment_ai_usage("user_b", limit=3) is True


def test_vision_minutes_allows_up_to_limit_then_blocks(ul):
    username = "vision_limit_user"
    results = [
        ul.check_and_increment_vision_minutes(username, minutes=1.0, limit=3.0)
        for _ in range(5)
    ]
    assert results == [True, True, True, False, False]


def test_usage_limit_without_benutzername_is_not_enforced(ul):
    # Kein Nutzername (z.B. anonymer Aufruf) darf nicht versehentlich irgendjemanden sperren.
    for _ in range(10):
        assert ul.check_and_increment_ai_usage("", limit=1) is True


def test_usage_limit_fails_open_without_redis(monkeypatch):
    """Ohne REDIS_URL (oder falls Redis nicht erreichbar ist) darf das Limit
    NIE greifen -- ein Redis-Ausfall soll das Produkt nicht für alle sperren."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    import services.usage_limiter as usage_limiter
    importlib.reload(usage_limiter)

    for _ in range(50):
        assert usage_limiter.check_and_increment_ai_usage("anyone", limit=1) is True
        assert usage_limiter.check_and_increment_vision_minutes("anyone", minutes=100.0, limit=1.0) is True
