import asyncio
import base64
import binascii
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from fastapi import HTTPException
from sarvamai import AsyncSarvamAI
from sarvamai.core.api_error import ApiError

from app.core.config import get_settings


@asynccontextmanager
async def sarvam_client() -> AsyncIterator[AsyncSarvamAI]:
    settings = get_settings()
    if not settings.sarvam_api_key:
        raise HTTPException(status_code=503, detail="Sarvam AI is not configured.")
    async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as transport:
        yield AsyncSarvamAI(
            api_subscription_key=settings.sarvam_api_key,
            timeout=settings.ai_timeout_seconds,
            httpx_client=transport,
        )


def provider_http_error(error: ApiError) -> HTTPException:
    status = getattr(error, "status_code", None)
    if status in (401, 403):
        return HTTPException(status_code=503, detail="Sarvam AI credentials are not accepted.")
    if status == 429:
        return HTTPException(status_code=503, detail="Sarvam AI is rate-limiting requests. Try again shortly.")
    if isinstance(status, int) and status >= 500:
        return HTTPException(status_code=503, detail="Sarvam AI is temporarily unavailable. Please retry.")
    return HTTPException(status_code=502, detail="Sarvam AI could not process the request.")


async def run_sarvam(operation: Callable[[], Awaitable[Any]]) -> Any:
    try:
        return await operation()
    except ApiError as exc:
        raise provider_http_error(exc) from exc
    except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
        raise HTTPException(status_code=504, detail="Sarvam AI timed out. Please retry.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Sarvam AI is temporarily unavailable. Please retry.") from exc


async def transcribe_audio(audio: bytes, filename: str, content_type: str) -> tuple[str, str | None]:
    settings = get_settings()

    async def operation():
        async with sarvam_client() as client:
            options: dict[str, Any] = {
                "file": (filename, audio, content_type),
                "model": settings.sarvam_stt_model,
                "language_code": "unknown",
            }
            if settings.sarvam_stt_model == "saaras:v3":
                options["mode"] = "codemix"
            return await client.speech_to_text.transcribe(**options)

    response = await run_sarvam(operation)
    try:
        transcript = response.transcript.strip()
        language_code = response.language_code
    except (AttributeError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Sarvam AI returned an invalid transcript response.") from exc
    if language_code is not None and not isinstance(language_code, str):
        raise HTTPException(status_code=502, detail="Sarvam AI returned an invalid language code.")
    if not transcript:
        raise HTTPException(status_code=422, detail="No speech was recognized. Please try recording again.")
    return transcript, language_code


async def complete_chat(messages: list[dict[str, Any]], **options: Any):
    settings = get_settings()

    async def operation():
        async with sarvam_client() as client:
            return await client.chat.completions(
                model=settings.sarvam_chat_model,
                messages=messages,
                **options,
            )

    return await run_sarvam(operation)


async def synthesize_speech(text: str, language_code: str) -> bytes:
    settings = get_settings()
    if not settings.sarvam_tts_enabled:
        raise HTTPException(status_code=503, detail="Speech output is disabled.")
    if not text.strip():
        raise HTTPException(status_code=422, detail="Speech text cannot be empty.")
    if len(text) > 2500:
        raise HTTPException(status_code=422, detail="Speech text exceeds the supported 2,500-character limit.")
    if language_code not in {"en-IN", "hi-IN"}:
        raise HTTPException(status_code=422, detail="Speech output supports Hindi and English.")

    async def operation():
        async with sarvam_client() as client:
            return await client.text_to_speech.convert(
                text=text,
                model=settings.sarvam_tts_model,
                language_code=language_code,
                speaker=settings.sarvam_tts_speaker,
                output_audio_codec="mp3",
            )

    response = await run_sarvam(operation)
    audios = getattr(response, "audios", None)
    if not isinstance(audios, list) or not audios or not isinstance(audios[0], str):
        raise HTTPException(status_code=502, detail="Sarvam AI returned no speech audio.")
    try:
        audio = base64.b64decode(audios[0], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=502, detail="Sarvam AI returned invalid speech audio.") from exc
    if not audio:
        raise HTTPException(status_code=502, detail="Sarvam AI returned empty speech audio.")
    return audio
