import pytest
import os
import cv2
import numpy as np
import json
from unittest.mock import AsyncMock, patch, MagicMock

import services.local_matcher as local_matcher

def test_metadata_save_load():
    test_mapping = {"test_image.jpg": "Sol Ring"}
    
    with patch("builtins.open", new_callable=MagicMock) as mock_open:
        local_matcher.save_metadata(test_mapping)
        mock_open.assert_called_once_with(local_matcher.METADATA_PATH, "w", encoding="utf-8")
        
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", new_callable=MagicMock) as mock_open:
        mock_file = mock_open.return_value.__enter__.return_value
        mock_file.read.return_value = '{"test_image.jpg": "Sol Ring"}'
        
        mapping = local_matcher.load_metadata()
        assert mapping["test_image.jpg"] == "Sol Ring"

@pytest.mark.asyncio
async def test_sync_deck_locally_mocked():
    deck_list = "1 Godo, Bandit Warlord\n1 Helm of the Host"
    
    mock_details = {
        "godo, bandit warlord": {"name": "Godo, Bandit Warlord", "image": "http://mockurl.com/godo.jpg"},
        "helm of the host": {"name": "Helm of the Host", "image": "http://mockurl.com/helm.jpg"}
    }
    
    with patch("services.local_matcher.fetch_card_details_cached", new_callable=AsyncMock) as mock_fetch, \
         patch("services.local_matcher.download_image", new_callable=AsyncMock) as mock_download, \
         patch("services.local_matcher.load_metadata", return_value={}), \
         patch("services.local_matcher.save_metadata") as mock_save, \
         patch("services.local_matcher.os.path.exists", return_value=False):
         
        mock_fetch.return_value = mock_details
        mock_download.return_value = True
        
        synced = await local_matcher.sync_deck_locally(deck_list)
        
        assert len(synced) == 2
        assert "Godo, Bandit Warlord" in synced
        assert "Helm of the Host" in synced
        assert mock_download.call_count == 2
        assert mock_save.call_count == 1

def test_load_and_compute_descriptors_mocked():
    mock_metadata = {
        "godo.jpg": "Godo, Bandit Warlord",
        "helm.jpg": "Helm of the Host"
    }
    
    # Create and write temporary mock images with random noise to ensure ORB detects keypoints
    mock_img = np.random.randint(0, 255, (500, 500), dtype=np.uint8)
    
    os.makedirs(local_matcher.IMAGE_DIR, exist_ok=True)
    godo_path = os.path.join(local_matcher.IMAGE_DIR, "godo.jpg")
    helm_path = os.path.join(local_matcher.IMAGE_DIR, "helm.jpg")
    
    try:
        cv2.imwrite(godo_path, mock_img)
        cv2.imwrite(helm_path, mock_img)
        
        with patch("services.local_matcher.load_metadata", return_value=mock_metadata):
            local_matcher.load_and_compute_descriptors()
            
            # Verify both cards got descriptors loaded into memory
            assert "Godo, Bandit Warlord" in local_matcher.card_features
            assert "Helm of the Host" in local_matcher.card_features
    finally:
        if os.path.exists(godo_path):
            os.remove(godo_path)
        if os.path.exists(helm_path):
            os.remove(helm_path)

def test_match_card_crop_success():
    # Setup mock template descriptors in memory
    mock_des = np.zeros((50, 32), dtype=np.uint8)
    
    # Create mock crop image
    img = np.zeros((140, 100), dtype=np.uint8)
    cv2.rectangle(img, (10, 10), (90, 130), 255, -1)
    
    # Preprocess img like in match_card_crop to get the exact pHash
    img_processed = cv2.equalizeHist(img)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    img_processed = cv2.filter2D(img_processed, -1, kernel)
    correct_phash = local_matcher.compute_phash(img_processed)
    
    local_matcher.card_features = {
        "Sol Ring": ([], mock_des, correct_phash)
    }
    
    _, encoded = cv2.imencode(".jpg", img)
    crop_bytes = encoded.tobytes()
    
    # Mock ORB descriptor extraction to match Sol Ring descriptor
    mock_orb = MagicMock()
    mock_orb.detectAndCompute.return_value = ([], mock_des)
    local_matcher.orb = mock_orb
    
    # Mock BFMatcher to return perfect matches
    mock_bf = MagicMock()
    mock_match = MagicMock()
    mock_match.distance = 10.0
    mock_match_far = MagicMock()
    mock_match_far.distance = 100.0
    # Provide 20 matches to pass the QA threshold of 12 good matches
    mock_bf.knnMatch.return_value = [[mock_match, mock_match_far]] * 20
    
    with patch("services.local_matcher.cv2.BFMatcher", return_value=mock_bf):
        name, confidence = local_matcher.match_card_crop(crop_bytes)
        assert name == "Sol Ring"
        assert confidence > 0.0

def test_phash_and_hamming_distance():
    # Create two identical dummy images
    img1 = np.zeros((100, 100), dtype=np.uint8)
    cv2.rectangle(img1, (10, 10), (90, 90), 255, -1)
    
    img2 = np.zeros((100, 100), dtype=np.uint8)
    cv2.rectangle(img2, (10, 10), (90, 90), 255, -1)
    
    hash1 = local_matcher.compute_phash(img1)
    hash2 = local_matcher.compute_phash(img2)
    
    # Identical images must produce the same hash, so distance is 0
    assert hash1 == hash2
    assert local_matcher.hamming_distance(hash1, hash2) == 0
    
    # Create a completely different image
    img3 = np.zeros((100, 100), dtype=np.uint8)
    cv2.circle(img3, (50, 50), 30, 255, -1)
    hash3 = local_matcher.compute_phash(img3)
    
    # Different images must produce different hashes, so distance > 0
    dist = local_matcher.hamming_distance(hash1, hash3)
    assert dist > 0
