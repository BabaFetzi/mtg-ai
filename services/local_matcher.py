"""
services/local_matcher.py – Offline MTG Card Recognition Engine

This service implements a 100% offline card identification pipeline:
- Agent 1 (Data): Downloads and caches card images from Scryfall locally.
- Agent 2 (Matching): Pre-computes ORB descriptors and performs keypoint feature matching on crops.
- Agent 3 (QA): Validates matching results using confidence thresholds and format checks.
"""

import os
import cv2
import json
import numpy as np
import httpx
import asyncio
from typing import Dict, List, Any, Tuple

from services.scryfall import fetch_card_details_cached, parse_decklist

# Directories and paths in the workspace root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, "data", "card_images")
METADATA_PATH = os.path.join(BASE_DIR, "data", "metadata.json")

os.makedirs(IMAGE_DIR, exist_ok=True)

# In-memory store of pre-computed card features
# canonical_name -> (keypoints, descriptors, phash)
card_features: Dict[str, Tuple[List[Any], np.ndarray, str]] = {}
orb = cv2.ORB_create(nfeatures=1500, scaleFactor=1.2, nlevels=8, edgeThreshold=31)

def compute_phash(img: np.ndarray) -> str:
    """Computes a 64-bit Perceptual Hash (pHash) of an image using DCT."""
    # Resize to 32x32 and convert to float32
    resized = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA)
    img_float = np.float32(resized)
    # Compute 2D Discrete Cosine Transform (DCT)
    dct = cv2.dct(img_float)
    # Extract top-left 8x8 region of DCT coefficients
    dct_8x8 = dct[0:8, 0:8]
    # Compute mean of coefficients, excluding the DC term (0,0)
    flat = dct_8x8.flatten()
    mean = np.mean(flat[1:])
    # Build 64-bit binary string
    bits = "".join(["1" if val > mean else "0" for val in flat])
    # Convert binary to hex string
    hex_str = ""
    for i in range(0, 64, 4):
        chunk = bits[i:i+4]
        hex_str += hex(int(chunk, 2))[2:]
    return hex_str

def hamming_distance(hash1: str, hash2: str) -> int:
    """Calculates the Hamming distance between two hex-encoded hashes."""
    if len(hash1) != len(hash2):
        return 99
    val1 = int(hash1, 16)
    val2 = int(hash2, 16)
    return bin(val1 ^ val2).count('1')

def save_metadata(mapping: Dict[str, str]):
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)

def load_metadata() -> Dict[str, str]:
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

async def download_image(url: str, filepath: str) -> bool:
    """Downloads a single image to disk with timeout and retries."""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=15.0)
                if resp.status_code == 200:
                    with open(filepath, "wb") as f:
                        f.write(resp.content)
                    return True
        except Exception as e:
            print(f"Attempt {attempt+1} failed downloading {url}: {e}")
            await asyncio.sleep(1.0)
    return False

# ======================================================================
# Agent 1 (Data-Manager): Local Caching & Sync
# ======================================================================

async def sync_deck_locally(deck_liste_str: str) -> List[str]:
    """
    Parses the decklist, fetches metadata & image URLs from Scryfall cache,
    downloads missing images, and updates the local metadata mapping.
    """
    parsed = parse_decklist(deck_liste_str)
    card_names = [c["name"] for c in parsed]
    if not card_names:
        return []

    # Batch lookup Scryfall data
    scryfall_details = await fetch_card_details_cached(card_names)
    
    metadata = load_metadata()
    synced_cards = []
    
    for name in card_names:
        name_lower = name.lower().strip()
        details = scryfall_details.get(name_lower)
        if not details or not details.get("image"):
            continue
            
        canonical_name = details["name"]
        
        # Create safe filename
        safe_filename = "".join([c if c.isalnum() else "_" for c in canonical_name.lower().strip()]) + ".jpg"
        filepath = os.path.join(IMAGE_DIR, safe_filename)
        
        if not os.path.exists(filepath):
            print(f"Offline Sync: Downloading card artwork for {canonical_name}...")
            success = await download_image(details["image"], filepath)
            if success:
                metadata[safe_filename] = canonical_name
                synced_cards.append(canonical_name)
        else:
            metadata[safe_filename] = canonical_name
            synced_cards.append(canonical_name)
            
    save_metadata(metadata)
    print(f"Offline Sync complete: {len(synced_cards)} cards verified locally.")
    return synced_cards

# ======================================================================
# Agent 2 (Matching-Engine): Feature Extraction & Keypoint Matcher
# ======================================================================

def load_and_compute_descriptors():
    """Loads all cached images, runs ORB descriptor extraction, and stores in memory."""
    global card_features
    card_features.clear()
    
    metadata = load_metadata()
    if not metadata:
        print("Local Matcher: No cards metadata found. Run sync first.")
        return
        
    loaded_count = 0
    for filename, canonical_name in metadata.items():
        filepath = os.path.join(IMAGE_DIR, filename)
        if not os.path.exists(filepath):
            continue
            
        # Load grayscale
        img = cv2.imread(filepath, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
            
        # Compute ORB descriptors
        kp, des = orb.detectAndCompute(img, None)
        if des is not None:
            phash = compute_phash(img)
            card_features[canonical_name] = (kp, des, phash)
            loaded_count += 1
            
    print(f"Local Matcher: Loaded ORB keypoints for {loaded_count} cards in memory.")

def match_card_crop(crop_bytes: bytes) -> Tuple[str, float]:
    """
    Decodes the cropped image, runs ORB keypoint extraction,
    and runs a k-NN descriptor matcher with Lowe's ratio test.
    
    Returns (best_card_name, confidence).
    """
    global card_features
    if not card_features:
        load_and_compute_descriptors()
        
    if not card_features:
        return "Unknown Card", 0.0
        
    # Decode JPEG bytes
    nparr = np.frombuffer(crop_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return "Unknown Card", 0.0
        
    # Preprocessing: Equalize histogram to improve contrast and reduce reflection glare
    img = cv2.equalizeHist(img)
    
    # Apply 2D sharpening filter to enhance card text and details
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    img = cv2.filter2D(img, -1, kernel)
    
    # Compute ORB descriptors on the crop
    kp_crop, des_crop = orb.detectAndCompute(img, None)
    if des_crop is None or len(des_crop) < 15:
        return "Unknown Card", 0.0

    # Compute pHash of the crop
    phash_crop = compute_phash(img)
        
    # Brute-Force Matcher with Hamming distance
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    
    best_match = "Unknown Card"
    max_good_matches = 0
    best_phash_dist = 99
    best_combined_score = 0.0
    
    # Compare against all cards in memory
    for name, (kp_template, des_template, phash_template) in card_features.items():
        if des_template is None or len(des_template) < 15:
            continue
            
        try:
            # 1. Compute pHash distance
            phash_dist = hamming_distance(phash_crop, phash_template)
            
            # 2. Compute ORB matches
            matches = bf.knnMatch(des_crop, des_template, k=2)
            
            # Lowe's ratio test (filter out ambiguous keypoint matches)
            good_matches = []
            for pair in matches:
                if len(pair) == 2:
                    m, n = pair
                    if m.distance < 0.75 * n.distance:
                        good_matches.append(m)
            
            match_count = len(good_matches)
            
            # 3. Combined scoring heuristic
            # pHash distance <= 12 is a very strong match.
            # pHash distance > 22 is a mismatch.
            phash_score = max(0.0, (22 - phash_dist) / 10.0)
            orb_score = min(match_count / 30.0, 1.0)
            
            # Hybrid combined score (0.4 weight on global structure, 0.6 on keypoints)
            combined_score = 0.4 * phash_score + 0.6 * orb_score
            
            # Veto Rule: if pHash distance is too high (> 22) AND ORB matches are low (< 12), reject
            if phash_dist > 22 and match_count < 12:
                combined_score = 0.0
                
            if combined_score > best_combined_score:
                best_combined_score = combined_score
                max_good_matches = match_count
                best_phash_dist = phash_dist
                best_match = name
        except Exception as e:
            print(f"Error matching descriptor for {name}: {e}")
            continue

    # ======================================================================
    # Agent 3 (QA): Plausibility & Confidence Score
    # ======================================================================
    confidence = best_combined_score
    
    # Combined Veto rule: reject if combined score is low, or both matching counts are poor
    if best_combined_score < 0.45 or (max_good_matches < 12 and best_phash_dist > 18):
        return "Unknown Card", 0.0
        
    return best_match, confidence
