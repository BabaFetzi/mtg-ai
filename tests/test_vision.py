import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
import numpy as np
import cv2
from main import app
from auth import create_access_token
import routers.vision

client = TestClient(app)

_TEST_TOKEN = create_access_token({"sub": "tester"})

@patch("routers.vision.check_user_premium", new_callable=AsyncMock)
def test_vision_websocket_streaming(mock_premium):
    # Test dynamic display connection and camera frame forwarding.
    # /stream verlangt inzwischen Login + Premium für role=display.
    mock_premium.return_value = True
    with client.websocket_connect(f"/api/vision/stream/test_session_stream?role=display&token={_TEST_TOKEN}") as display_ws:
        # Display receives the welcome/status info message first
        info = display_ws.receive_json()
        assert info["type"] == "info"
        
        with client.websocket_connect("/api/vision/stream/test_session_stream?role=camera") as camera_ws:
            test_frame = b"fake-jpeg-frame-data-12345"
            camera_ws.send_bytes(test_frame)
            
            # The display should receive the camera's forwarded binary frame
            received = display_ws.receive_bytes()
            assert received == test_frame

@pytest.mark.asyncio
async def test_detect_cards_from_image():
    # Mock Gemini model
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"cards": [{"name": "Sol Ring", "zone": "battlefield", "tapped": false, "x": 10, "y": 20}]}'
    mock_model.generate_content.return_value = mock_response
    
    original_model = routers.vision.model_lite
    routers.vision.model_lite = mock_model
    try:
        res = await routers.vision.detect_cards_from_image(b"dummy")
        assert "cards" in res
        assert len(res["cards"]) == 1
        assert res["cards"][0]["name"] == "Sol Ring"
    finally:
        routers.vision.model_lite = original_model

@pytest.mark.asyncio
async def test_generate_board_advice():
    # Mock Gemini model
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Sol Ring allows fast ramping."
    mock_model.generate_content.return_value = mock_response
    
    original_model = routers.vision.model_lite
    routers.vision.model_lite = mock_model
    try:
        advice = await routers.vision.generate_board_advice([{"name": "Sol Ring"}])
        assert "ramping" in advice.lower()
    finally:
        routers.vision.model_lite = original_model

def test_detect_card_bounds_and_warp_untapped():
    # Create a black image
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw a white rectangle that is untapped (width < height)
    # Start at (250, 150), end at (410, 370) -> width 160, height 220
    cv2.rectangle(img, (250, 150), (410, 370), (255, 255, 255), -1)
    _, encoded = cv2.imencode(".jpg", img)
    jpeg_bytes = encoded.tobytes()
    
    res = routers.vision.detect_card_bounds_and_warp(jpeg_bytes)
    assert len(res) > 0
    # The detected card should not be tapped
    assert res[0]["tapped"] is False
    assert "warped_bytes" in res[0]
    assert "x" in res[0]
    assert "y" in res[0]
    assert "box" in res[0]

def test_detect_card_bounds_and_warp_tapped():
    # Create a black image
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw a white rectangle that is tapped (width > height)
    # Start at (200, 180), end at (420, 340) -> width 220, height 160
    cv2.rectangle(img, (200, 180), (420, 340), (255, 255, 255), -1)
    _, encoded = cv2.imencode(".jpg", img)
    jpeg_bytes = encoded.tobytes()
    
    res = routers.vision.detect_card_bounds_and_warp(jpeg_bytes)
    assert len(res) > 0
    # The detected card should be tapped
    assert res[0]["tapped"] is True

def test_detect_card_bounds_and_warp_invalid():
    # Invalid bytes should return an empty list
    res = routers.vision.detect_card_bounds_and_warp(b"invalid_bytes_here")
    assert res == []

@pytest.mark.asyncio
async def test_identify_single_card():
    # Mock Gemini model
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '"Sol Ring"'
    mock_model.generate_content.return_value = mock_response
    
    original_model = routers.vision.model_lite
    routers.vision.model_lite = mock_model
    try:
        res = await routers.vision.identify_single_card(b"dummy_bytes")
        assert res == "Sol Ring"
    finally:
        routers.vision.model_lite = original_model

@pytest.mark.asyncio
async def test_identify_single_card_error():
    mock_model = MagicMock()
    mock_model.generate_content.side_effect = Exception("API error")
    
    original_model = routers.vision.model_lite
    routers.vision.model_lite = mock_model
    try:
        res = await routers.vision.identify_single_card(b"dummy_bytes")
        assert res == "Unknown Card"
    finally:
        routers.vision.model_lite = original_model

@pytest.mark.asyncio
async def test_identify_single_card_no_model():
    original_model = routers.vision.model_lite
    routers.vision.model_lite = None
    try:
        res = await routers.vision.identify_single_card(b"dummy_bytes")
        assert res == "Unknown Card"
    finally:
        routers.vision.model_lite = original_model

def test_overlap_and_stacking_logic():
    enriched_cards = [
        {
            "id": "card-0",
            "name": "Godo, Bandit Warlord",
            "type": "Legendary Creature — Kor Soldier Bandit",
            "x": 30,
            "y": 30,
            "box": [[20, 20], [40, 20], [40, 40], [20, 40]]
        },
        {
            "id": "card-1",
            "name": "Helm of the Host",
            "type": "Legendary Artifact — Equipment",
            "x": 35,
            "y": 30,
            "box": [[25, 20], [45, 20], [45, 40], [25, 40]]
        }
    ]
    
    # Run stacking logic
    for idx_a, card_a in enumerate(enriched_cards):
        card_a["stacked_on"] = None
        card_a["is_stacked"] = False

    for idx_a, card_a in enumerate(enriched_cards):
        box_a = card_a.get("box")
        xs_a = [pt[0] for pt in box_a]
        ys_a = [pt[1] for pt in box_a]
        xmin_a, xmax_a = min(xs_a), max(xs_a)
        ymin_a, ymax_a = min(ys_a), max(ys_a)
        area_a = (xmax_a - xmin_a) * (ymax_a - ymin_a)

        for idx_b, card_b in enumerate(enriched_cards):
            if idx_a == idx_b:
                continue
            box_b = card_b.get("box")
            xs_b = [pt[0] for pt in box_b]
            ys_b = [pt[1] for pt in box_b]
            xmin_b, xmax_b = min(xs_b), max(xs_b)
            ymin_b, ymax_b = min(ys_b), max(ys_b)
            area_b = (xmax_b - xmin_b) * (ymax_b - ymin_b)

            x_overlap = max(0, min(xmax_a, xmax_b) - max(xmin_a, xmin_b))
            y_overlap = max(0, min(ymax_a, ymax_b) - max(ymin_a, ymin_b))
            intersection = x_overlap * y_overlap
            smaller_area = min(area_a, area_b)
            overlap_ratio = intersection / smaller_area if smaller_area > 0 else 0

            if overlap_ratio > 0.35:
                type_a = card_a.get("type", "").lower()
                type_b = card_b.get("type", "").lower()
                is_aura_eq_a = "aura" in type_a or "equipment" in type_a
                is_aura_eq_b = "aura" in type_b or "equipment" in type_b

                if is_aura_eq_a and not is_aura_eq_b:
                    card_a["stacked_on"] = card_b["id"]
                    card_a["is_stacked"] = True
                elif is_aura_eq_b and not is_aura_eq_a:
                    card_b["stacked_on"] = card_a["id"]
                    card_b["is_stacked"] = True
                else:
                    if area_a < area_b:
                        card_a["stacked_on"] = card_b["id"]
                        card_a["is_stacked"] = True
                    else:
                        card_b["stacked_on"] = card_a["id"]
                        card_b["is_stacked"] = True
                        
    # Card 1 (Helm of the Host - Equipment) must be stacked_on Card 0 (Godo - Creature)
    assert enriched_cards[1]["stacked_on"] == "card-0"
    assert enriched_cards[1]["is_stacked"] is True
    assert enriched_cards[0]["stacked_on"] is None


# ============================================================================
# Regressionstests: /api/vision/ws hat vorher pro Sekunde bis zu 2 Gemini-Calls
# gemacht (Bild-Erkennung + Advice), komplett ungedrosselt -- siehe
# KI-Kosten-Audit (~CHF 2.80/Stunde). Diese Tests beweisen, dass die 12.5s-
# Drossel und das monatliche Vision-Minuten-Limit jetzt greifen.
# ============================================================================
@pytest.mark.asyncio
async def test_ws_vision_throttles_gemini_calls_within_window(monkeypatch):
    call_count = {"detect": 0}

    async def fake_detect(jpeg_bytes):
        call_count["detect"] += 1
        return {"cards": [{"name": f"Card-{call_count['detect']}"}]}

    async def fake_advice(cards):
        return "advice"

    monkeypatch.setattr(routers.vision, "detect_cards_from_image", fake_detect)
    monkeypatch.setattr(routers.vision, "generate_board_advice", fake_advice)
    monkeypatch.setattr(routers.vision, "check_user_premium", AsyncMock(return_value=True))
    monkeypatch.setattr(routers.vision, "check_and_increment_vision_minutes", AsyncMock(return_value=True))
    # Große Schwelle -> der zweite Frame landet garantiert noch im selben Drossel-Fenster.
    monkeypatch.setattr(routers.vision, "VISION_WS_MIN_GEMINI_INTERVAL_SECONDS", 60.0)

    with client.websocket_connect(f"/api/vision/ws?token={_TEST_TOKEN}") as ws:
        ws.send_bytes(b"frame1")
        r1 = ws.receive_json()
        assert r1["cards"][0]["name"] == "Card-1"

        ws.send_bytes(b"frame2")
        r2 = ws.receive_json()
        # Noch innerhalb der Drossel -> kein zweiter Gemini-Call, letzter Stand wird erneut gesendet.
        assert r2["cards"][0]["name"] == "Card-1"

    assert call_count["detect"] == 1


@pytest.mark.asyncio
async def test_ws_vision_calls_gemini_again_after_throttle_window_passes(monkeypatch):
    call_count = {"detect": 0}

    async def fake_detect(jpeg_bytes):
        call_count["detect"] += 1
        return {"cards": [{"name": f"Card-{call_count['detect']}"}]}

    async def fake_advice(cards):
        return "advice"

    monkeypatch.setattr(routers.vision, "detect_cards_from_image", fake_detect)
    monkeypatch.setattr(routers.vision, "generate_board_advice", fake_advice)
    monkeypatch.setattr(routers.vision, "check_user_premium", AsyncMock(return_value=True))
    monkeypatch.setattr(routers.vision, "check_and_increment_vision_minutes", AsyncMock(return_value=True))
    # Winzige Schwelle -> das asyncio.sleep(1) im Loop reicht, um sie zu überschreiten.
    monkeypatch.setattr(routers.vision, "VISION_WS_MIN_GEMINI_INTERVAL_SECONDS", 0.01)

    with client.websocket_connect(f"/api/vision/ws?token={_TEST_TOKEN}") as ws:
        ws.send_bytes(b"frame1")
        ws.receive_json()
        ws.send_bytes(b"frame2")
        ws.receive_json()

    assert call_count["detect"] == 2


@pytest.mark.asyncio
async def test_ws_vision_blocked_when_monthly_minutes_limit_reached(monkeypatch):
    async def fake_detect_should_not_run(jpeg_bytes):
        raise AssertionError("Gemini darf nicht aufgerufen werden, wenn das Monatslimit erreicht ist")

    monkeypatch.setattr(routers.vision, "detect_cards_from_image", fake_detect_should_not_run)
    monkeypatch.setattr(routers.vision, "check_user_premium", AsyncMock(return_value=True))
    monkeypatch.setattr(routers.vision, "check_and_increment_vision_minutes", AsyncMock(return_value=False))

    with client.websocket_connect(f"/api/vision/ws?token={_TEST_TOKEN}") as ws:
        ws.send_bytes(b"frame1")
        r1 = ws.receive_json()

    assert "Limit" in r1["advice"]
    assert r1["cards"] == []
