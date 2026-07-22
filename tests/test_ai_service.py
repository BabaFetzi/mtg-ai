"""
tests/test_ai_service.py

Testet den Adapter, der die bisherige `.generate_content(...)`-Schnittstelle auf
das neue native google-genai SDK abbildet (Migration weg vom veralteten
google-generativeai / kompatibel mit den neuen "AQ."-Keys). Kein echter
Netzwerkzugriff -- der SDK-Client wird gemockt.
"""

import logging

import pytest

import services.ai_service as ai
from services.ai_service import _GeminiModel, _normalize_contents, _to_config
from google.genai import types


class _FakeModels:
    def __init__(self, response=None, error=None):
        self.calls = []
        self._response = response
        self._error = error

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self._error:
            raise self._error
        return self._response


class _FakeClient:
    def __init__(self, response=None, error=None):
        self.models = _FakeModels(response=response, error=error)


def test_string_content_passed_through():
    client = _FakeClient(response=object())
    m = _GeminiModel(client, "gemini-2.5-flash-lite")
    m.generate_content("Was ist Trample?")
    call = client.models.calls[0]
    assert call["model"] == "gemini-2.5-flash-lite"
    assert call["contents"] == "Was ist Trample?"
    assert call["config"] is None


def test_multimodal_dict_becomes_part():
    client = _FakeClient(response=object())
    m = _GeminiModel(client, "gemini-2.5-flash-lite")
    m.generate_content(
        [{"mime_type": "image/jpeg", "data": b"\xff\xd8\xff"}, "Erkenne die Karte"],
        generation_config={"response_mime_type": "application/json"},
    )
    call = client.models.calls[0]
    # Bild-Dict wurde zu types.Part, String bleibt String
    assert isinstance(call["contents"][0], types.Part)
    assert call["contents"][1] == "Erkenne die Karte"
    # generation_config -> GenerateContentConfig
    assert isinstance(call["config"], types.GenerateContentConfig)
    assert call["config"].response_mime_type == "application/json"


def test_normalize_and_config_helpers():
    assert _normalize_contents("hallo") == "hallo"
    assert _to_config(None) is None
    cfg = _to_config({"response_mime_type": "application/json"})
    assert isinstance(cfg, types.GenerateContentConfig)


def test_error_is_logged_with_status_and_reraised(caplog):
    class FakeAPIError(Exception):
        def __init__(self):
            super().__init__("invalid key")
            self.code = 400
            self.status = "INVALID_ARGUMENT"
            self.message = "API key not valid"

    client = _FakeClient(error=FakeAPIError())
    m = _GeminiModel(client, "gemini-2.5-flash")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(FakeAPIError):
            m.generate_content("frage")

    # Der echte Gemini-Statuscode muss im Log auftauchen (Diagnose).
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "http_status=400" in joined
    assert "INVALID_ARGUMENT" in joined


def test_module_exposes_shared_key_env_name():
    # Judge und Scanner teilen sich denselben Key über diese eine Variable.
    assert ai.GEMINI_API_KEY_ENV == "GEMINI_API_KEY"
