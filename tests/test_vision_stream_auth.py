"""
tests/test_vision_stream_auth.py – Zugriffsschutz für /api/vision/stream

Der Endpoint war zuvor komplett ungeschützt (kein Login, kein Premium) und
löst Gemini-Aufrufe aus. Jetzt gilt:
- role=display: gültiges Access-Token + Premium nötig (erstellt die Session)
- role=camera: darf nur EXISTIERENDEN Sessions beitreten (Handy ist beim
  QR-Scan nicht eingeloggt; die Session-ID des Premium-Displays ist die
  Zugangsberechtigung)
- Refresh-Tokens werden nicht akzeptiert
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from main import app
from auth import create_access_token, create_refresh_token

client = TestClient(app)


def _expect_close(url, code):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(url) as ws:
            ws.receive_json()
    assert exc_info.value.code == code


def test_display_without_token_is_rejected():
    _expect_close("/api/vision/stream/s1?role=display", 4401)


def test_display_with_garbage_token_is_rejected():
    _expect_close("/api/vision/stream/s1?role=display&token=kein.echtes.token", 4401)


def test_display_with_refresh_token_is_rejected():
    """Ein Refresh-Token ist KEIN gültiger Zugang (type-Claim-Trennung)."""
    refresh = create_refresh_token({"sub": "premiumuser"})
    _expect_close(f"/api/vision/stream/s1?role=display&token={refresh}", 4401)


@patch("routers.vision.check_user_premium", new_callable=AsyncMock)
def test_display_free_user_is_rejected(mock_premium):
    mock_premium.return_value = False
    token = create_access_token({"sub": "freeuser"})
    _expect_close(f"/api/vision/stream/s1?role=display&token={token}", 4403)


def test_camera_cannot_create_session():
    """Eine Kamera ohne vorher geöffnete (Premium-)Display-Session kommt
    nicht rein -- sie kann keine Session anlegen."""
    _expect_close("/api/vision/stream/gibt-es-nicht?role=camera", 4404)


def test_invalid_role_is_rejected():
    token = create_access_token({"sub": "x"})
    _expect_close(f"/api/vision/stream/s1?role=hacker&token={token}", 4400)


@patch("routers.vision.check_user_premium", new_callable=AsyncMock)
def test_premium_display_then_camera_flow_works(mock_premium):
    """Positivfall: Premium-Display öffnet die Session, Kamera tritt bei,
    Frames werden weitergeleitet (bisheriges Verhalten bleibt erhalten)."""
    mock_premium.return_value = True
    token = create_access_token({"sub": "premiumuser"})

    with client.websocket_connect(
        f"/api/vision/stream/auth_flow_sess?role=display&token={token}"
    ) as display_ws:
        info = display_ws.receive_json()
        assert info["type"] == "info"

        with client.websocket_connect(
            "/api/vision/stream/auth_flow_sess?role=camera"
        ) as camera_ws:
            frame = b"fake-jpeg-frame"
            camera_ws.send_bytes(frame)
            assert display_ws.receive_bytes() == frame
