"""
routers/vision.py – Live Playfield Streaming and Card Detection WebSocket Router

Endpoints:
    WS /api/vision/stream/{session_id} – Camera stream ingestion (role=camera) and display (role=display)
"""

import asyncio
import json
import logging
import time
import cv2
import numpy as np
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from auth import decode_token
from database import check_user_premium
from services.ai_service import model_lite
from services.local_matcher import sync_deck_locally, load_and_compute_descriptors, match_card_crop
from services.usage_limiter import check_and_increment_vision_minutes

logger = logging.getLogger(__name__)

# Mindestabstand zwischen zwei Gemini-Aufrufen auf /ws (Sekunden). Ohne diese
# Drossel macht der Endpoint bis zu 2 Gemini-Calls/Sekunde (Bild-Erkennung +
# Advice) -- siehe KI-Kosten-Audit: das kostet ~CHF 2.80/Stunde und kann ein
# ganzes Monatsabo in unter einer Stunde aufbrauchen. 12.5s entspricht der
# bereits im /stream-Endpoint etablierten Drossel (siehe vision_detection_loop).
VISION_WS_MIN_GEMINI_INTERVAL_SECONDS = 12.5

router = APIRouter(
    prefix="/api/vision",
    tags=["Vision Stream"],
)

# Global flag to track free-tier quota exhaustion
gemini_quota_exhausted = False

async def detect_cards_from_image(jpeg_bytes: bytes) -> Dict[str, Any]:
    global gemini_quota_exhausted
    if not model_lite or gemini_quota_exhausted:
        return {"cards": []}
    try:
        prompt = (
            "Analyze this image of a Magic: The Gathering battlefield. "
            "Detect all cards, their names, coordinates (x and y, 0-100), and whether they are tapped. "
            "Return JSON in this format: {\"cards\": [{\"name\": \"Card Name\", \"zone\": \"battlefield\", \"tapped\": false, \"x\": 50, \"y\": 50}]}"
        )
        response = await asyncio.to_thread(
            model_lite.generate_content,
            [{"mime_type": "image/jpeg", "data": jpeg_bytes}, prompt],
            generation_config={"response_mime_type": "application/json"}
        )
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
    except Exception as e:
        err_msg = str(e)
        logger.warning("Error in detect_cards_from_image: %s", err_msg)
        if "429" in err_msg or "quota" in err_msg.lower():
            gemini_quota_exhausted = True
        return {"cards": []}

async def generate_board_advice(cards: List[Dict[str, Any]]) -> str:
    global gemini_quota_exhausted
    if gemini_quota_exhausted:
        return (
            "⚠️ Grana AI Hinweis: Das tägliche Limit der kostenlosen Gemini-KI (20 Anfragen/Tag) ist erschöpft. "
            "Das System läuft im Demonstrations-Modus und simuliert Karten auf deinen erkannten Spielfeld-Positionen, "
            "damit du die Echtzeit-Erfassung und 3D-Overlays testen kannst."
        )
    if not model_lite:
        return "Grana AI: No advice available."
    try:
        prompt = (
            f"Analyze the following Magic: The Gathering battlefield cards: {json.dumps(cards)}. "
            "Provide tactical advice, check for synergies, infinite combos, and suggest your next moves."
        )
        response = await asyncio.to_thread(model_lite.generate_content, prompt)
        return response.text
    except Exception as e:
        err_msg = str(e)
        logger.warning("Error in generate_board_advice: %s", err_msg)
        if "429" in err_msg or "quota" in err_msg.lower():
            gemini_quota_exhausted = True
            return (
                "⚠️ Grana AI Hinweis: Das tägliche Limit der kostenlosen Gemini-KI (20 Anfragen/Tag) ist erschöpft. "
                "Das System läuft im Demonstrations-Modus und simuliert Karten auf deinen erkannten Spielfeld-Positionen, "
                "damit du die Echtzeit-Erfassung und 3D-Overlays testen kannst."
            )
        return "Grana AI: Error generating advice."

def detect_card_bounds_and_warp(jpeg_bytes: bytes, info: dict = None, camera_y_scale: float = 1.0) -> List[Dict[str, Any]]:
    """
    Uses OpenCV to find rectangular card contours in the image.
    Performs perspective transform to get a flat top-down view of each card.
    Detects whether the card is tapped (based on aspect ratio) and calculates
    coordinates on a 0-100 grid.
    Supports playmat perspective warping to correct camera angle distortion.
    """
    if info is not None:
        info["playmat_detected"] = False

    # Decode JPEG bytes
    nparr = np.frombuffer(jpeg_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    img_h, img_w = img.shape[:2]

    # 1. Base Image preprocessing
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 30, 150)

    # Apply morphological closing with a precise (2, 2) kernel to prevent card/playmat edge merging
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    edged = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel)

    # 2. Find playmat contour (the largest rectangle covering 10% to 95% of the frame)
    # We try to find it on the clean Canny edge map first (which has less noise)
    contours_canny, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    
    playmat_contour = None
    max_playmat_area = 0
    min_playmat_area = (img_h * img_w) * 0.20
    max_allowed_area = (img_h * img_w) * 0.95

    def find_best_contour(contours_list):
        nonlocal max_playmat_area, playmat_contour
        for c in contours_list:
            area = cv2.contourArea(c)
            if area < min_playmat_area or area > max_allowed_area:
                continue
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.03 * peri, True)
            if len(approx) == 4:
                if area > max_playmat_area:
                    max_playmat_area = area
                    playmat_contour = approx
            else:
                # Fallback: if the shape has rounded corners (5-8 vertices) but is highly rectangular/trapezoidal (solidity > 0.5)
                # Lowering solidity to 0.5 to support steep perspective warp angles (where the shape resembles a trapezoid)
                rect_pm = cv2.minAreaRect(c)
                box_pm = cv2.boxPoints(rect_pm)
                box_pm = np.int32(box_pm)
                rect_area = rect_pm[1][0] * rect_pm[1][1]
                if rect_area > 0 and (area / rect_area) > 0.5:
                    if area > max_playmat_area:
                        max_playmat_area = area
                        playmat_contour = box_pm.reshape(4, 1, 2)

    find_best_contour(contours_canny)

    # Fallback to adaptive thresholded edge map if Canny edges were too broken (due to glare/shadows)
    if playmat_contour is None:
        thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 75, 2)
        combined_edges = cv2.bitwise_or(edged, cv2.bitwise_not(thresh))
        # Apply a morphological close with a larger kernel to bridge gaps in the playmat border
        kernel_pm = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        combined_edges = cv2.morphologyEx(combined_edges, cv2.MORPH_CLOSE, kernel_pm)
        
        contours_thresh, _ = cv2.findContours(combined_edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        find_best_contour(contours_thresh)

    # 3. Apply playmat perspective warp if detected
    is_playmat_warped = False
    M_playmat_inv = None
    img_for_cards = img
    edged_for_cards = edged

    if playmat_contour is not None:
        pts_pm = playmat_contour.reshape(4, 2)
        # Stable sort playmat corners
        pts_pm_y = pts_pm[np.argsort(pts_pm[:, 1]), :]
        top_two = pts_pm_y[:2, :]
        bottom_two = pts_pm_y[2:, :]
        top_two = top_two[np.argsort(top_two[:, 0]), :]
        tl_pm = top_two[0]
        tr_pm = top_two[1]
        bottom_two = bottom_two[np.argsort(bottom_two[:, 0]), :]
        bl_pm = bottom_two[0]
        br_pm = bottom_two[1]
        rect_playmat = np.array([tl_pm, tr_pm, br_pm, bl_pm], dtype="float32")

        dst_playmat = np.array([
            [0, 0],
            [img_w - 1, 0],
            [img_w - 1, img_h - 1],
            [0, img_h - 1]
        ], dtype="float32")

        M_playmat = cv2.getPerspectiveTransform(rect_playmat, dst_playmat)
        _, M_playmat_inv = cv2.invert(M_playmat)
        
        # Warp the frame to get a clean top-down view of the playmat
        img_warped = cv2.warpPerspective(img, M_playmat, (img_w, img_h))
        
        # Re-run preprocessing on the warped playmat frame for clean card detection
        gray_warped = cv2.cvtColor(img_warped, cv2.COLOR_BGR2GRAY)
        blurred_warped = cv2.GaussianBlur(gray_warped, (5, 5), 0)
        edged_warped = cv2.Canny(blurred_warped, 30, 150)
        edged_warped = cv2.morphologyEx(edged_warped, cv2.MORPH_CLOSE, kernel)
        
        img_for_cards = img_warped
        edged_for_cards = edged_warped
        is_playmat_warped = True
        if info is not None:
            info["playmat_detected"] = True

    # 4. Find card contours on the active frame
    contours_cards, _ = cv2.findContours(edged_for_cards.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    min_area = (img_h * img_w) * 0.003  # At least 0.3% of image area
    max_area = (img_h * img_w) * 0.20   # At most 20% of image area

    raw_candidates = []
    for c in contours_cards:
        area = cv2.contourArea(c)
        if area < min_area or area > max_area:
            continue

        # Approximate polygon
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)

        # Relax vertex check (4-12 points) to be robust against tilted/low-res cards
        if len(approx) >= 4 and len(approx) <= 12:
            rect_rot = cv2.minAreaRect(c)
            (cx, cy), (w, h), angle = rect_rot
            if w > 0 and h > 0:
                ratio = w / h if w < h else h / w
                # MTG card aspect ratio is ~0.715. Allow 0.30 to 1.05 to handle extreme camera tilt and perspective distortion.
                if ratio >= 0.30 and ratio <= 1.05:
                    box_pts = cv2.boxPoints(rect_rot)
                    box_pts = np.int32(box_pts)
                    approx_box = box_pts.reshape(4, 1, 2)
                    raw_candidates.append({
                        "box": approx_box,
                        "cx": cx,
                        "cy": cy,
                        "area": area,
                        "ratio_score": abs(ratio - 0.715)
                    })

    # Deduplicate candidate contours that represent the same card
    # If centers are within 8% of the image diagonal, keep the one with the smaller area (the inner contour)
    deduped_candidates = []
    diag = np.sqrt(img_h**2 + img_w**2)
    threshold_dist = diag * 0.08

    for cand in raw_candidates:
        is_duplicate = False
        for idx, existing in enumerate(deduped_candidates):
            dist = np.sqrt((cand["cx"] - existing["cx"])**2 + (cand["cy"] - existing["cy"])**2)
            if dist < threshold_dist:
                is_duplicate = True
                if cand["area"] < existing["area"]:
                    deduped_candidates[idx] = cand
                break
        if not is_duplicate:
            deduped_candidates.append(cand)

    card_candidates = [cand["box"] for cand in deduped_candidates]

    detected_cards = []
    for idx, approx in enumerate(card_candidates):
        pts = approx.reshape(4, 2)

        # Stable sort card corners
        pts_y = pts[np.argsort(pts[:, 1]), :]
        top_two = pts_y[:2, :]
        bottom_two = pts_y[2:, :]
        top_two = top_two[np.argsort(top_two[:, 0]), :]
        tl = top_two[0]
        tr = top_two[1]
        bottom_two = bottom_two[np.argsort(bottom_two[:, 0]), :]
        bl = bottom_two[0]
        br = bottom_two[1]
        rect = np.array([tl, tr, br, bl], dtype="float32")

        # Determine tapped status using robust vector-based aspect ratio & orientation check
        active_y_scale = 1.0 if is_playmat_warped else camera_y_scale
        
        d01 = np.linalg.norm(pts[1] - pts[0])
        d12 = np.linalg.norm(pts[2] - pts[1])
        d23 = np.linalg.norm(pts[3] - pts[2])
        d30 = np.linalg.norm(pts[0] - pts[3])
        
        # Avoid division by zero
        if d01 == 0 or d12 == 0 or d23 == 0 or d30 == 0:
            continue
            
        # Classify sides as vertical (pointing mostly along image Y-axis) or horizontal
        # Check unit vector of Side 1 (pts[1] - pts[0])
        v1 = (pts[1] - pts[0]) / d01
        is_side1_vertical = bool(abs(v1[1]) > abs(v1[0]))
        
        if is_side1_vertical:
            L_vert = (d01 + d23) / 2.0
            L_horiz = (d12 + d30) / 2.0
        else:
            L_vert = (d12 + d30) / 2.0
            L_horiz = (d01 + d23) / 2.0
            
        ratio_vert_horiz = L_vert / L_horiz if L_horiz > 0 else 0
        
        # Threshold is approximately 1.0 * active_y_scale
        is_tapped = bool(ratio_vert_horiz <= 1.0 * active_y_scale)
        
        # Estimate Y-scale for feedback tracking
        y_scale_est = ratio_vert_horiz / 1.4 if not is_tapped else ratio_vert_horiz / 0.714
        
        if is_tapped:
            dst = np.array([
                [0, 0],
                [350 - 1, 0],
                [350 - 1, 250 - 1],
                [0, 250 - 1]
            ], dtype="float32")
            warp_w, warp_h = 350, 250
        else:
            dst = np.array([
                [0, 0],
                [250 - 1, 0],
                [250 - 1, 350 - 1],
                [0, 350 - 1]
            ], dtype="float32")
            warp_w, warp_h = 250, 350

        # Warp card crop from the flat playmat space or the raw frame
        M_card = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(img_for_cards, M_card, (warp_w, warp_h))

        # Rotate horizontal crop by 90 degrees counter-clockwise to make it vertical (250x350)
        # to match the template orientation and aspect ratio for ORB matching.
        if is_tapped:
            warped = cv2.rotate(warped, cv2.ROTATE_90_COUNTERCLOCKWISE)

        _, warped_jpeg = cv2.imencode('.jpg', warped)
        warped_bytes = warped_jpeg.tobytes()

        # Coordinate mapping back to raw frame coordinates for display overlays
        if is_playmat_warped and M_playmat_inv is not None:
            # Calculate center in warped space
            cx_warped = np.mean(rect[:, 0])
            cy_warped = np.mean(rect[:, 1])
            
            # Map center and corner points back to raw coordinate space
            pts_to_transform = np.array([[ [cx_warped, cy_warped] ]], dtype="float32")
            transformed_center = cv2.perspectiveTransform(pts_to_transform, M_playmat_inv)[0][0]
            center_x = int(transformed_center[0] / img_w * 100)
            center_y = int(transformed_center[1] / img_h * 100)
            
            transformed_corners = cv2.perspectiveTransform(rect.reshape(-1, 1, 2), M_playmat_inv).reshape(4, 2)
            box_pts = [[int(pt[0] / img_w * 100), int(pt[1] / img_h * 100)] for pt in transformed_corners]
        else:
            # Standard fallback mapping
            center_x = int(np.mean(pts[:, 0]) / img_w * 100)
            center_y = int(np.mean(pts[:, 1]) / img_h * 100)
            box_pts = [[int(pt[0] / img_w * 100), int(pt[1] / img_h * 100)] for pt in rect]

        detected_cards.append({
            "warped_bytes": warped_bytes,
            "x": center_x,
            "y": center_y,
            "tapped": is_tapped,
            "box": box_pts,
            "y_scale_est": y_scale_est
        })

    return detected_cards

async def identify_single_card(warped_bytes: bytes) -> str:
    """
    Sends the cropped card image to Gemini to identify the card name.
    """
    global gemini_quota_exhausted
    if not model_lite or gemini_quota_exhausted:
        return "Unknown Card"
    try:
        prompt = (
            "Identify the exact English name of this Magic: The Gathering card. "
            "Return ONLY the card name, nothing else."
        )
        response = await asyncio.to_thread(
            model_lite.generate_content,
            [{"mime_type": "image/jpeg", "data": warped_bytes}, prompt]
        )
        name = response.text.strip()
        name = name.replace('"', '').replace("'", "").strip()
        return name
    except Exception as e:
        err_msg = str(e)
        logger.warning("Error identifying card crop: %s", err_msg)
        if "429" in err_msg or "quota" in err_msg.lower():
            gemini_quota_exhausted = True
        return "Unknown Card"

@router.websocket("/ws")
async def ws_vision_endpoint(websocket: WebSocket, token: str = ""):
    # Browser-WebSockets können keinen Authorization-Header mitschicken, daher
    # wird das JWT hier als Query-Param übergeben und manuell verifiziert --
    # der bisherige `benutzername`-Query-Param wurde entfernt, weil er dem
    # Client blind vertraute (Premium-Umgehung + Kontingent-Diebstahl auf
    # fremde Nutzer möglich).
    payload = decode_token(token) if token else None
    benutzername = payload.get("sub") if payload else None
    if not benutzername:
        await websocket.close(code=4401, reason="Nicht authentifiziert")
        return

    await websocket.accept()
    # Letzter tatsächlich ausgeführter Gemini-Aufruf dieser Verbindung, plus die
    # zuletzt bekannten Ergebnisse -- so friert die Anzeige zwischen zwei
    # gedrosselten Intervallen nicht auf "keine Karten" ein.
    last_gemini_time = 0.0
    last_cards: List[Dict[str, Any]] = []
    last_advice = ""
    try:
        while True:
            data = await websocket.receive_bytes()
            is_premium = await check_user_premium(benutzername)

            now = time.time()
            if now - last_gemini_time >= VISION_WS_MIN_GEMINI_INTERVAL_SECONDS:
                if check_and_increment_vision_minutes(benutzername, VISION_WS_MIN_GEMINI_INTERVAL_SECONDS / 60):
                    last_gemini_time = now
                    detection = await detect_cards_from_image(data)
                    last_cards = detection.get("cards", [])
                    last_advice = await generate_board_advice(last_cards)
                else:
                    last_advice = (
                        "⚠️ Grana AI Hinweis: Dein monatliches Live-Vision-Limit ist erreicht. "
                        "Es setzt sich zu Beginn des nächsten Monats zurück."
                    )

            await websocket.send_json({
                "cards": last_cards,
                "advice": last_advice
            })
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        if "Stop loop" in str(e):
            raise e
        logger.exception("WS error")

# In-memory session store
# session_id -> {
#    "camera": WebSocket or None,
#    "displays": List[WebSocket],
#    "latest_frame": bytes or None,
#    "ai_task": asyncio.Task or None
# }
active_sessions: Dict[str, Dict[str, Any]] = {}

# Mock cards data with Scryfall image links
MOCK_CARDS = [
    {
        "id": "card-1",
        "name": "Godo, Bandit Warlord",
        "image_url": "https://api.scryfall.com/cards/named?exact=Godo,%20Bandit%20Warlord&format=image",
        "type": "Legendary Creature — Kor Soldier Bandit",
        "x": 25,
        "y": 30,
        "tapped": False,
        "cmc": 6
    },
    {
        "id": "card-2",
        "name": "Helm of the Host",
        "image_url": "https://api.scryfall.com/cards/named?exact=Helm%20of%20the%20Host&format=image",
        "type": "Legendary Artifact — Equipment",
        "x": 40,
        "y": 30,
        "tapped": False,
        "cmc": 4
    },
    {
        "id": "card-3",
        "name": "Sol Ring",
        "image_url": "https://api.scryfall.com/cards/named?exact=Sol%20Ring&format=image",
        "type": "Artifact",
        "x": 65,
        "y": 60,
        "tapped": True,
        "cmc": 1
    },
    {
        "id": "card-4",
        "name": "Black Lotus",
        "image_url": "https://api.scryfall.com/cards/named?exact=Black%20Lotus&format=image",
        "type": "Artifact",
        "x": 80,
        "y": 60,
        "tapped": False,
        "cmc": 0
    }
]

async def vision_detection_loop(session_id: str):
    """
    Background loop that runs every 2 seconds for active sessions.
    It reads the latest JPEG frame from the camera, runs card detection,
    performs Scryfall cache enrichment, fetches rules/combos advice,
    and broadcasts the updated board state to all displays.
    """
    from services.scryfall import fetch_card_details_cached
    import urllib.parse
    import time
    
    logger.info("Starting vision detection loop for session %s", session_id)
    while session_id in active_sessions:
        session = active_sessions[session_id]
        
        # If camera is disconnected and no displays are connected, stop the loop
        if not session["camera"] and not session["displays"]:
            break
            
        latest_frame = session.get("latest_frame")
        displays = session.get("displays", [])
        
        if latest_frame is not None and displays:
            # Consume the latest frame
            session["latest_frame"] = None
            
            try:
                # Initialize session state for tracking if not present
                if "tracked_cards" not in session:
                    session["tracked_cards"] = []
                if "next_card_id_num" not in session:
                    session["next_card_id_num"] = 0
                if "last_full_scan_time" not in session:
                    session["last_full_scan_time"] = 0.0
                if "last_card_signature" not in session:
                    session["last_card_signature"] = ""
                if "last_advice" not in session:
                    session["last_advice"] = ""
                if "last_gemini_request_time" not in session:
                    session["last_gemini_request_time"] = 0.0
                if "consecutive_missing_playmat" not in session:
                    session["consecutive_missing_playmat"] = 0
                if "camera_y_scale" not in session:
                    session["camera_y_scale"] = 0.70
                    
                # 1. Run card detection using hybrid OpenCV + Gemini approach
                from services.ai_service import KI_VERFUEGBAR, model
                
                cards_raw = []
                detected_shapes = []
                
                if KI_VERFUEGBAR and model:
                    try:
                        info_dict = {}
                        curr_y_scale = session.get("camera_y_scale", 0.70)
                        detected_shapes = detect_card_bounds_and_warp(latest_frame, info=info_dict, camera_y_scale=curr_y_scale)
                        
                        # Update camera Y-scale running average
                        if detected_shapes:
                            y_scales = [np.clip(s["y_scale_est"], 0.35, 0.95) for s in detected_shapes if "y_scale_est" in s]
                            if y_scales:
                                avg_est = float(np.mean(y_scales))
                                session["camera_y_scale"] = 0.9 * curr_y_scale + 0.1 * avg_est
                        
                        # Agent 4: Verify playmat detection (FOV check)
                        if not info_dict.get("playmat_detected", False):
                            session["consecutive_missing_playmat"] += 1
                        else:
                            session["consecutive_missing_playmat"] = 0
                            
                        # If playmat is missing consecutively, notify the camera client via socket
                        if session["consecutive_missing_playmat"] >= 3:
                            camera_socket = session.get("camera")
                            if camera_socket:
                                await camera_socket.send_json({
                                    "type": "qa_feedback",
                                    "status": "warning",
                                    "message": "Spielfeld-Rahmen (Playmat) nicht erkannt. Bitte Kamera-Abstand anpassen oder Weitwinkel-Linse (0.5x) wählen."
                                })
                    except Exception as ex:
                        logger.debug("Error in OpenCV preprocessing: %s", ex, exc_info=True)
                        
                    previous_tracked = session["tracked_cards"]
                    current_tracked = []
                    next_card_id_num = session["next_card_id_num"]
                    
                    if detected_shapes:
                        # Match shapes with previously tracked cards
                        for shape in detected_shapes:
                            best_match = None
                            best_dist = 9999.0
                            
                            for prev in previous_tracked:
                                dx = shape["x"] - prev["x"]
                                dy = shape["y"] - prev["y"]
                                dist = (dx*dx + dy*dy) ** 0.5
                                
                                if dist < 8.0 and dist < best_dist:
                                    best_match = prev
                                    best_dist = dist
                                    
                            if best_match is not None:
                                # Found a match! Reuse the card name, scryfall data and ID
                                if best_match in previous_tracked:
                                    previous_tracked.remove(best_match)
                                matched_card = best_match.copy()
                                matched_card["x"] = shape["x"]
                                matched_card["y"] = shape["y"]
                                
                                # Hysteresis/Voting for tapped status to prevent flickering
                                tapped_history = matched_card.get("tapped_history", [])
                                tapped_history.append(shape["tapped"])
                                if len(tapped_history) > 5:
                                    tapped_history.pop(0)
                                matched_card["tapped_history"] = tapped_history
                                
                                tapped_votes = sum(1 for t in tapped_history if t)
                                matched_card["tapped"] = tapped_votes >= 3
                                
                                matched_card["box"] = shape["box"]
                                current_tracked.append(matched_card)
                            else:
                                # New card detected! Identify it locally using ORB feature matching
                                logger.debug("New card shape found at (%s, %s). Matching locally...", shape['x'], shape['y'])
                                card_name, confidence = match_card_crop(shape["warped_bytes"])
                                
                                if card_name == "Unknown Card":
                                    # If no local deck features are loaded yet, fall back to demo cards
                                    from services.local_matcher import card_features
                                    if not card_features:
                                        demo_names = ["Godo, Bandit Warlord", "Helm of the Host", "Sol Ring", "Black Lotus", "Mountain"]
                                        card_name = demo_names[next_card_id_num % len(demo_names)]
                                
                                # Agent 4 (QA Plausibility Check):
                                # Verify if the card belongs to the selected deck or standard basics/demo cards.
                                is_plausible = True
                                if card_name != "Unknown Card":
                                    deck_card_names = session.get("deck_card_names", set())
                                    allowed_basics = {
                                        "mountain", "forest", "swamp", "island", "plains",
                                        "sol ring", "black lotus", "godo, bandit warlord", "helm of the host"
                                    }
                                    name_lower = card_name.lower().strip()
                                    if deck_card_names and name_lower not in deck_card_names and name_lower not in allowed_basics:
                                        logger.info("Agent 4 (QA): Blocked card '%s' because it is not in the synced decklist.", card_name)
                                        is_plausible = False

                                if card_name != "Unknown Card" and is_plausible:
                                    new_card = {
                                        "id": f"card-{next_card_id_num}",
                                        "name": card_name,
                                        "x": shape["x"],
                                        "y": shape["y"],
                                        "tapped": shape["tapped"],
                                        "tapped_history": [shape["tapped"]],
                                        "box": shape["box"]
                                    }
                                    next_card_id_num += 1
                                    current_tracked.append(new_card)
                                    
                        session["next_card_id_num"] = next_card_id_num
                        session["tracked_cards"] = current_tracked
                        cards_raw = current_tracked
                        
                    if not cards_raw:
                        # Fallback: keep previous cards to prevent flickering
                        cards_raw = session["tracked_cards"]
                else:
                    # Mock cards for local testing if Gemini is not available
                    cards_raw = [
                        {"name": "Godo, Bandit Warlord", "tapped": False, "x": 25, "y": 30, "box": [[20, 20], [30, 20], [30, 40], [20, 40]]},
                        {"name": "Helm of the Host", "tapped": False, "x": 40, "y": 30, "box": [[35, 20], [45, 20], [45, 40], [35, 40]]},
                        {"name": "Sol Ring", "tapped": True, "x": 65, "y": 60, "box": [[60, 50], [70, 50], [70, 70], [60, 70]]},
                        {"name": "Black Lotus", "tapped": False, "x": 80, "y": 60, "box": [[75, 50], [85, 50], [85, 70], [75, 70]]}
                    ]
                
                # 2. Enrich cards with Scryfall details
                enriched_cards = []
                if cards_raw:
                    names = [c["name"] for c in cards_raw if c.get("name")]
                    scryfall_details = await fetch_card_details_cached(names)
                    
                    for idx, c in enumerate(cards_raw):
                        name_clean = c["name"].lower().strip()
                        details = scryfall_details.get(name_clean)
                        
                        if details:
                            img = details["image"]
                            c_type = details["type"]
                            cmc = details["cmc"]
                        else:
                            img = f"https://api.scryfall.com/cards/named?exact={urllib.parse.quote(c['name'])}&format=image"
                            c_type = "Unknown"
                            cmc = 0
                            
                        enriched_cards.append({
                            "id": c.get("id", f"card-{idx}"),
                            "name": c["name"],
                            "image_url": img,
                            "type": c_type,
                            "x": c.get("x", 50),
                            "y": c.get("y", 50),
                            "tapped": c.get("tapped", False),
                            "cmc": cmc,
                            "box": c.get("box")
                        })

                # 2.5 Stacking / Attachment detection
                # We calculate the overlap between each pair of cards
                for idx_a, card_a in enumerate(enriched_cards):
                    card_a["stacked_on"] = None
                    card_a["is_stacked"] = False

                for idx_a, card_a in enumerate(enriched_cards):
                    box_a = card_a.get("box")
                    if not box_a or len(box_a) < 4:
                        continue
                    # Get axis-aligned bounding box (AABB) in 0-100 coordinates
                    xs_a = [pt[0] for pt in box_a]
                    ys_a = [pt[1] for pt in box_a]
                    xmin_a, xmax_a = min(xs_a), max(xs_a)
                    ymin_a, ymax_a = min(ys_a), max(ys_a)
                    area_a = (xmax_a - xmin_a) * (ymax_a - ymin_a)
                    if area_a <= 0:
                        continue

                    for idx_b, card_b in enumerate(enriched_cards):
                        if idx_a == idx_b:
                            continue
                        box_b = card_b.get("box")
                        if not box_b or len(box_b) < 4:
                            continue
                        xs_b = [pt[0] for pt in box_b]
                        ys_b = [pt[1] for pt in box_b]
                        xmin_b, xmax_b = min(xs_b), max(xs_b)
                        ymin_b, ymax_b = min(ys_b), max(ys_b)
                        area_b = (xmax_b - xmin_b) * (ymax_b - ymin_b)
                        if area_b <= 0:
                            continue

                        # Calculate intersection AABB
                        x_overlap = max(0, min(xmax_a, xmax_b) - max(xmin_a, xmin_b))
                        y_overlap = max(0, min(ymax_a, ymax_b) - max(ymin_a, ymin_b))
                        intersection = x_overlap * y_overlap

                        # Overlap ratio relative to the smaller card
                        smaller_area = min(area_a, area_b)
                        overlap_ratio = intersection / smaller_area if smaller_area > 0 else 0

                        if overlap_ratio > 0.35:
                            # Stack detected! Decide which is stacked on which.
                            type_a = card_a.get("type", "").lower()
                            type_b = card_b.get("type", "").lower()

                            is_aura_eq_a = "aura" in type_a or "equipment" in type_a
                            is_aura_eq_b = "aura" in type_b or "equipment" in type_b

                            # Decide parent (base card) and child (attachment/stacked card)
                            if is_aura_eq_a and not is_aura_eq_b:
                                card_a["stacked_on"] = card_b["id"]
                                card_a["is_stacked"] = True
                            elif is_aura_eq_b and not is_aura_eq_a:
                                card_b["stacked_on"] = card_a["id"]
                                card_b["is_stacked"] = True
                            else:
                                # Fallback: the one with the smaller area is stacked on the larger one.
                                if area_a < area_b:
                                    card_a["stacked_on"] = card_b["id"]
                                    card_a["is_stacked"] = True
                                else:
                                    card_b["stacked_on"] = card_a["id"]
                                    card_b["is_stacked"] = True
                
                # 3. Generate strategic advice
                # Calculate board signature to detect if anything changed
                card_names_and_status = sorted([f"{c['name']} (tapped: {c['tapped']})" for c in cards_raw if c.get("name")])
                board_signature = "|".join(card_names_and_status)
                
                previous_signature = session["last_card_signature"]
                advice = session["last_advice"]
                
                if board_signature != previous_signature:
                    # Request advice with rate limiting
                    now_time = time.time()
                    last_gemini_time = session.get("last_gemini_request_time", 0.0)
                    
                    if now_time - last_gemini_time >= 12.5:
                        session["last_card_signature"] = board_signature
                        if cards_raw:
                            logger.info("Board state changed to: %s. Requesting AI advice...", board_signature)
                            session["last_gemini_request_time"] = now_time
                            advice = await generate_board_advice(cards_raw)
                            session["last_advice"] = advice
                        else:
                            advice = ""
                            session["last_advice"] = ""
                
                # 4. Broadcast board state to displays
                board_state_msg = {
                    "type": "board_state",
                    "cards": enriched_cards,
                    "advice": advice
                }
                
                for disp in list(displays):
                    try:
                        await disp.send_json(board_state_msg)
                    except Exception:
                        logger.exception("Error sending board state to display")
                        
            except Exception:
                logger.exception("Error in vision detection loop for session %s", session_id)
                
        # Sleep for 2 seconds before the next check
        await asyncio.sleep(2.0)
        
    logger.info("Stopped vision detection loop for session %s", session_id)

@router.websocket("/stream/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str, role: str):
    await websocket.accept()
    
    # Initialize session in registry if not exists
    if session_id not in active_sessions:
        active_sessions[session_id] = {
            "camera": None,
            "displays": [],
            "latest_frame": None,
            "ai_task": None
        }
        
    if role == "camera":
        # Close previous camera connection if open
        old_cam = active_sessions[session_id]["camera"]
        if old_cam:
            try:
                await old_cam.close()
            except Exception:
                pass
        active_sessions[session_id]["camera"] = websocket
        logger.info("Camera connected for session %s", session_id)
        
        # Start the background detection task if not already running
        ai_task = active_sessions[session_id].get("ai_task")
        if not ai_task or ai_task.done():
            active_sessions[session_id]["ai_task"] = asyncio.create_task(vision_detection_loop(session_id))
            
    elif role == "display":
        active_sessions[session_id]["displays"].append(websocket)
        logger.info("Display connected for session %s", session_id)
        # Send initial info message
        await websocket.send_json({
            "type": "info",
            "message": "Erfolgreich mit dem Playfield-Stream verbunden."
        })
        
    try:
        while True:
            # Wait for message from client
            message = await websocket.receive()
            
            if message.get("type") == "websocket.disconnect":
                break
            
            if "bytes" in message:
                # Binary message (JPEG frame from camera)
                data = message["bytes"]
                if role == "camera":
                    # Store latest frame for background loop
                    active_sessions[session_id]["latest_frame"] = data
                    
                    # Broadcast frame to all display clients
                    displays = active_sessions[session_id]["displays"]
                    for disp in list(displays):
                        try:
                            await disp.send_bytes(data)
                        except Exception:
                            pass
            
            elif "text" in message:
                # Text/JSON message (can be a board_state update, ping, control message, etc.)
                text_data = message["text"]
                try:
                    data = json.loads(text_data)
                except Exception:
                    data = {"text": text_data}
                    
                # Broadcast the JSON data appropriately
                if role == "camera":
                    # Forward camera updates (e.g., custom board_state message) to displays
                    displays = active_sessions[session_id]["displays"]
                    for disp in list(displays):
                        try:
                            await disp.send_json(data)
                        except Exception:
                            pass
                elif role == "display":
                    # Check if it's a sync_deck command from the user interface
                    if isinstance(data, dict) and data.get("type") == "sync_deck":
                        deck_liste = data.get("deck_liste", "")
                        logger.info("WebSocket: Syncing deck locally for session %s...", session_id)
                        try:
                            await websocket.send_json({
                                "type": "info",
                                "message": "Synchronisiere Kartendaten lokal auf dem PC..."
                            })
                            # Download card template images offline
                            await sync_deck_locally(deck_liste)
                            # Load descriptors into memory
                            load_and_compute_descriptors()
                            # Parse card names and save in active session context for Agent 4 plausibility check
                            from services.local_matcher import parse_decklist
                            parsed_deck = parse_decklist(deck_liste)
                            if session_id in active_sessions:
                                active_sessions[session_id]["deck_card_names"] = {
                                    c["name"].lower().strip() for c in parsed_deck if c.get("name")
                                }
                            await websocket.send_json({
                                "type": "info",
                                "message": "Karten offline synchronisiert. Bereit zur Erkennung!"
                            })
                        except Exception as sync_err:
                            logger.exception("Error syncing deck")
                            await websocket.send_json({
                                "type": "info",
                                "message": f"Fehler bei Offline-Synchronisierung: {sync_err}"
                            })

                    # Forward control messages from displays to camera (if any)
                    camera = active_sessions[session_id]["camera"]
                    if camera:
                        try:
                            await camera.send_json(data)
                        except Exception:
                            pass
                            
    except WebSocketDisconnect:
        logger.info("Role %s disconnected from session %s", role, session_id)
    except Exception:
        logger.exception("WebSocket error in session %s (role=%s)", session_id, role)
    finally:
        # Clean up session registry on disconnect
        if role == "camera":
            if active_sessions.get(session_id) and active_sessions[session_id]["camera"] == websocket:
                active_sessions[session_id]["camera"] = None
        elif role == "display":
            if active_sessions.get(session_id) and websocket in active_sessions[session_id]["displays"]:
                active_sessions[session_id]["displays"].remove(websocket)
                
        # Clean up empty session
        if session_id in active_sessions:
            sess = active_sessions[session_id]
            if not sess["camera"] and not sess["displays"]:
                # Cancel task if running
                task = sess.get("ai_task")
                if task and not task.done():
                    task.cancel()
                active_sessions.pop(session_id, None)
                logger.info("Session %s cleaned up.", session_id)
