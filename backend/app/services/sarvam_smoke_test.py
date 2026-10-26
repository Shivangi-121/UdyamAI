import asyncio

from fastapi import HTTPException

from app.core.config import get_settings
from app.services.sarvam import complete_chat, synthesize_speech, transcribe_audio


async def smoke_test() -> None:
    if not get_settings().sarvam_api_key:
        raise SystemExit("Set SARVAM_API_KEY in backend/.env before running this smoke test.")

    sample_text = "UdyamAI Sarvam voice integration check."
    audio = await synthesize_speech(sample_text, "en-IN")
    transcript, language = await transcribe_audio(audio, "smoke-test.mp3", "audio/mpeg")
    response = await complete_chat(
        [
            {"role": "system", "content": "Reply with one short JSON object containing a message string."},
            {"role": "user", "content": "Confirm that the Sarvam chat API is reachable."},
        ],
        max_tokens=80,
        response_format={"type": "json_object"},
    )
    try:
        message = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Sarvam returned an invalid smoke-test response.") from exc
    if not message:
        raise HTTPException(status_code=502, detail="Sarvam returned an empty smoke-test response.")

    print(f"TTS generated {len(audio)} audio bytes.")
    print(f"STT recognized: {transcript!r} ({language or 'language unknown'}).")
    print(f"Chat response: {message}")


if __name__ == "__main__":
    asyncio.run(smoke_test())
