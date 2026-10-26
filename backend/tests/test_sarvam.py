import asyncio
import base64
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sarvamai.core.api_error import ApiError

import app.api.routes as routes
import app.services.assistant as assistant_service
import app.services.sarvam as sarvam_service
from app.core.config import Settings
from app.schemas.api import Recommendation


def _settings(**overrides):
    defaults = {
        "sarvam_api_key": "test-key",
        "sarvam_stt_model": "saaras:v4",
        "sarvam_chat_model": "sarvam-105b",
        "sarvam_tts_model": "bulbul:v4-flash",
        "sarvam_tts_speaker": "shubh_enhi_ads",
        "sarvam_tts_enabled": True,
        "ai_timeout_seconds": 4,
    }
    return SimpleNamespace(**(defaults | overrides))


def test_sarvam_transcription_uses_auto_language_and_preserves_transcript(monkeypatch):
    calls = []

    class FakeSpeechToText:
        async def transcribe(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(transcript="मेरा आज का profit बताओ", language_code="hi-IN")

    client = SimpleNamespace(speech_to_text=FakeSpeechToText())

    @asynccontextmanager
    async def fake_client():
        yield client

    monkeypatch.setattr(sarvam_service, "get_settings", lambda: _settings())
    monkeypatch.setattr(sarvam_service, "sarvam_client", fake_client)

    transcript, language = asyncio.run(
        sarvam_service.transcribe_audio(b"audio", "question.webm", "audio/webm")
    )

    assert transcript == "मेरा आज का profit बताओ"
    assert language == "hi-IN"
    assert calls[0]["model"] == "saaras:v4"
    assert calls[0]["language_code"] == "unknown"
    assert "mode" not in calls[0]
    assert calls[0]["file"] == ("question.webm", b"audio", "audio/webm")


def test_saaras_v3_requests_documented_codemix_mode(monkeypatch):
    calls = []

    class FakeSpeechToText:
        async def transcribe(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(transcript="मेरा profit", language_code="hi-IN")

    client = SimpleNamespace(speech_to_text=FakeSpeechToText())

    @asynccontextmanager
    async def fake_client():
        yield client

    monkeypatch.setattr(sarvam_service, "get_settings", lambda: _settings(sarvam_stt_model="saaras:v3"))
    monkeypatch.setattr(sarvam_service, "sarvam_client", fake_client)

    asyncio.run(sarvam_service.transcribe_audio(b"audio", "question.webm", "audio/webm"))

    assert calls[0]["mode"] == "codemix"


def test_bulbul_audio_is_decoded_and_uses_configured_voice(monkeypatch):
    calls = []

    class FakeTextToSpeech:
        async def convert(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(audios=[base64.b64encode(b"mp3-data").decode("ascii")])

    client = SimpleNamespace(text_to_speech=FakeTextToSpeech())

    @asynccontextmanager
    async def fake_client():
        yield client

    monkeypatch.setattr(sarvam_service, "get_settings", lambda: _settings())
    monkeypatch.setattr(sarvam_service, "sarvam_client", fake_client)

    audio = asyncio.run(sarvam_service.synthesize_speech("आज की बिक्री ठीक है।", "hi-IN"))

    assert audio == b"mp3-data"
    assert calls[0]["model"] == "bulbul:v4-flash"
    assert calls[0]["speaker"] == "shubh_enhi_ads"
    assert calls[0]["language_code"] == "hi-IN"
    assert calls[0]["output_audio_codec"] == "mp3"


def test_speech_length_and_timeout_are_reported(monkeypatch):
    monkeypatch.setattr(sarvam_service, "get_settings", lambda: _settings())
    with pytest.raises(HTTPException) as too_long:
        asyncio.run(sarvam_service.synthesize_speech("x" * 2501, "en-IN"))
    assert too_long.value.status_code == 422

    class FakeSpeechToText:
        async def transcribe(self, **kwargs):
            raise TimeoutError()

    client = SimpleNamespace(speech_to_text=FakeSpeechToText())

    @asynccontextmanager
    async def fake_client():
        yield client

    monkeypatch.setattr(sarvam_service, "sarvam_client", fake_client)
    with pytest.raises(HTTPException) as timed_out:
        asyncio.run(sarvam_service.transcribe_audio(b"audio", "question.mp3", "audio/mpeg"))
    assert timed_out.value.status_code == 504


def test_missing_sarvam_key_is_reported_without_attempting_a_request(monkeypatch):
    monkeypatch.setattr(sarvam_service, "get_settings", lambda: _settings(sarvam_api_key=""))
    with pytest.raises(HTTPException) as missing_key:
        asyncio.run(sarvam_service.transcribe_audio(b"audio", "question.mp3", "audio/mpeg"))
    assert missing_key.value.status_code == 503


def test_sarvam_rate_limit_is_converted_to_safe_retry_error(monkeypatch):
    class FakeSpeechToText:
        async def transcribe(self, **kwargs):
            raise ApiError(status_code=429, body={"message": "provider details"})

    client = SimpleNamespace(speech_to_text=FakeSpeechToText())

    @asynccontextmanager
    async def fake_client():
        yield client

    monkeypatch.setattr(sarvam_service, "get_settings", lambda: _settings())
    monkeypatch.setattr(sarvam_service, "sarvam_client", fake_client)
    with pytest.raises(HTTPException) as rate_limited:
        asyncio.run(sarvam_service.transcribe_audio(b"audio", "question.mp3", "audio/mpeg"))
    assert rate_limited.value.status_code == 503
    assert "provider details" not in rate_limited.value.detail


def test_settings_include_sarvam_defaults_and_audio_limit():
    settings = Settings(
        _env_file=None,
        sarvam_api_key="",
        sarvam_chat_model="sarvam-105b",
        sarvam_stt_model="saaras:v4",
        sarvam_tts_model="bulbul:v4-flash",
        sarvam_max_audio_bytes=5_000_000,
    )
    assert settings.sarvam_chat_model == "sarvam-105b"
    assert settings.sarvam_stt_model == "saaras:v4"
    assert settings.sarvam_tts_model == "bulbul:v4-flash"
    assert settings.sarvam_max_audio_bytes == 5_000_000


def test_voice_response_language_can_be_changed_and_detects_hinglish():
    assert routes.response_language_for_voice("Isko simple Hindi mein samjhao", "en-IN", "en") == "hi"
    assert routes.response_language_for_voice("Aaj meri sales kitni hui", "en-IN", "en") == "hi"
    assert routes.response_language_for_voice("Please explain this in English", "hi-IN", "hi") == "en"


def test_voice_endpoint_calls_shared_assistant_and_returns_text_on_speech_failure(client, auth, monkeypatch):
    captured = {}

    async def fake_transcribe(audio, filename, content_type):
        captured["audio"] = (audio, filename, content_type)
        return "Mera aaj ka profit batao", "hi-IN"

    async def fake_answer(db, merchant_id, request):
        captured["request"] = request
        return Recommendation(
            title="आज का कारोबार",
            message="दर्ज बिक्री से सकल लाभ बताया जा सकता है।",
            next_action="Review business insights",
            source="rules",
        )

    async def unavailable_tts(text, language_code):
        raise HTTPException(status_code=503, detail="Speech provider unavailable.")

    monkeypatch.setattr(routes, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(routes, "answer_question", fake_answer)
    monkeypatch.setattr(routes, "synthesize_speech", unavailable_tts)

    response = client.post(
        "/api/merchants/personal/assistant/voice",
        headers=auth,
        files={"audio": ("question.webm", b"recorded-audio", "audio/webm")},
        data={"language": "auto", "context_json": "[]", "speech_enabled": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"] == "Mera aaj ka profit batao"
    assert payload["transcript_language"] == "hi-IN"
    assert payload["response"]["message"] == "दर्ज बिक्री से सकल लाभ बताया जा सकता है।"
    assert payload["speech_audio"] is None
    assert payload["speech_error"] == "Speech provider unavailable."
    assert captured["request"].language == "hi"
    assert captured["request"].question == payload["transcript"]
    assert captured["audio"][0] == b"recorded-audio"


def test_voice_endpoint_rejects_invalid_audio_and_context(client, auth):
    unsupported = client.post(
        "/api/merchants/personal/assistant/voice",
        headers=auth,
        files={"audio": ("notes.txt", b"text", "text/plain")},
    )
    assert unsupported.status_code == 415

    empty = client.post(
        "/api/merchants/personal/assistant/voice",
        headers=auth,
        files={"audio": ("empty.webm", b"", "audio/webm")},
    )
    assert empty.status_code == 422

    invalid_context = client.post(
        "/api/merchants/personal/assistant/voice",
        headers=auth,
        files={"audio": ("question.webm", b"audio", "audio/webm")},
        data={"context_json": "not-json"},
    )
    assert invalid_context.status_code == 422


def test_voice_endpoint_enforces_audio_limit_and_merchant_auth(client, auth, monkeypatch):
    original_settings = routes.get_settings()
    small_audio_limit = original_settings.model_copy(update={"sarvam_max_audio_bytes": 4})
    monkeypatch.setattr(routes, "get_settings", lambda: small_audio_limit)
    oversized = client.post(
        "/api/merchants/personal/assistant/voice",
        headers=auth,
        files={"audio": ("question.webm", b"12345", "audio/webm")},
    )
    assert oversized.status_code == 413

    unauthenticated = client.post(
        "/api/merchants/personal/assistant/voice",
        files={"audio": ("question.webm", b"audio", "audio/webm")},
    )
    assert unauthenticated.status_code == 401


def test_sarvam_tool_calls_use_the_validated_merchant_scoped_registry(client, auth, monkeypatch):
    monkeypatch.setattr(
        assistant_service,
        "get_settings",
        lambda: _settings(llm_api_key="", llm_model=""),
    )
    calls = []

    def model_response(content=None, tool_calls=None):
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, tool_calls=tool_calls or [])
        )])

    tool_call = SimpleNamespace(
        id="call-inventory",
        function=SimpleNamespace(name="get_inventory_status", arguments="{}"),
    )

    async def fake_complete_chat(messages, **options):
        calls.append((messages, options))
        if len(calls) == 1:
            return model_response(tool_calls=[tool_call])
        return model_response(
            content=(
                '{"title":"Stock","message":"Rice has 2 recorded units.",'
                '"evidence":["Rice: 2 in stock."],"missing_information":[],"'
                'next_action":"Count stock","observed_data":[],"assumptions":[]}'
            )
        )

    monkeypatch.setattr(assistant_service, "complete_chat", fake_complete_chat)

    response = client.post(
        "/api/merchants/personal/assistant",
        headers=auth,
        json={"question": "How can I improve my shop?", "language": "en"},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "llm"
    assert any(
        message["role"] == "tool" and "Rice" in message["content"]
        for message in calls[-1][0]
    )
    assert calls[0][1]["tool_choice"] == "auto"
    assert all(item["type"] == "function" for item in calls[0][1]["tools"])


def test_hinglish_sales_question_uses_recorded_data_rules(client, auth, monkeypatch):
    monkeypatch.setattr(
        assistant_service,
        "get_settings",
        lambda: _settings(llm_api_key="", llm_model=""),
    )

    async def unexpected_model_call(*args, **kwargs):
        raise AssertionError("Recorded sales questions must use deterministic records.")

    monkeypatch.setattr(assistant_service, "complete_chat", unexpected_model_call)
    response = client.post(
        "/api/merchants/personal/assistant",
        headers=auth,
        json={"question": "Aaj meri total sales kitni hui?", "language": "hi"},
    )

    assert response.status_code == 200
    assert response.json()["source"] == "rules"
    assert "आज" in response.json()["title"]
    assert "No sales" not in response.json()["message"]


def test_invalid_tool_arguments_do_not_run_operations(client, auth, monkeypatch):
    monkeypatch.setattr(
        assistant_service,
        "get_settings",
        lambda: _settings(llm_api_key="", llm_model=""),
    )
    call = SimpleNamespace(
        id="call-invalid",
        function=SimpleNamespace(
            name="get_inventory_status",
            arguments='{"merchant_id":"other"}',
        ),
    )
    requests = []

    def model_response(content=None, tool_calls=None):
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=content, tool_calls=tool_calls or [])
        )])

    async def fake_complete_chat(messages, **options):
        requests.append(messages)
        if len(requests) == 1:
            return model_response(tool_calls=[call])
        return model_response(
            content=(
                '{"title":"No operation","message":"No change was made.",'
                '"evidence":[],"missing_information":[],"next_action":"Ask again",'
                '"observed_data":[],"assumptions":[]}'
            )
        )

    monkeypatch.setattr(assistant_service, "complete_chat", fake_complete_chat)
    response = client.post(
        "/api/merchants/personal/assistant",
        headers=auth,
        json={"question": "Could you help me improve?", "language": "en"},
    )

    assert response.status_code == 200
    tool_result = next(item for item in requests[-1] if item["role"] == "tool")
    assert "Arguments were invalid" in tool_result["content"]
    assert "other-rice" not in tool_result["content"]
