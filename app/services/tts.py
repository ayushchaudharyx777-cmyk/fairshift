"""Server-side text-to-speech (Gemini TTS) so every language can be spoken on any device.

Browsers only speak languages whose voice is installed on the device (often just English on Windows).
When the browser has no matching voice, the worker UI asks this service for a WAV instead.
"""
import asyncio
import hashlib
import io
import logging
import wave
from collections import OrderedDict
from typing import Optional

from google import genai

from app.config import get_settings
from app.services import ai

logger = logging.getLogger("fairshift.tts")

SAMPLE_RATE = 24000   # Gemini TTS returns 24 kHz, 16-bit, mono PCM
_CACHE: "OrderedDict[str, bytes]" = OrderedDict()
_MAX_CACHE = 32


class TTSUnavailable(Exception):
    """Raised when speech cannot be produced (no key, quota, model error, timeout)."""


def pcm_to_wav(pcm: bytes, rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


async def _tts_pcm(text: str) -> bytes:
    """Call Gemini TTS and return raw PCM. Patched in tests."""
    from google.genai import types
    st = get_settings()
    client = genai.Client(api_key=st.GEMINI_API_KEY.strip())
    response = await client.aio.models.generate_content(
        model=st.GEMINI_TTS_MODEL,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=st.GEMINI_TTS_VOICE)
                )
            ),
        ),
    )
    return response.candidates[0].content.parts[0].inline_data.data


async def synthesize_wav(text: str, language: str) -> bytes:
    if not ai.is_configured():
        raise TTSUnavailable("GEMINI_API_KEY is not configured")
    key = hashlib.sha256(f"{language}|{text}".encode("utf-8")).hexdigest()
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    try:
        pcm: Optional[bytes] = await asyncio.wait_for(_tts_pcm(text), timeout=30.0)
    except Exception as exc:
        logger.info("TTS failed: %s", ai.safe_error(exc))
        raise TTSUnavailable(ai.safe_error(exc)) from exc
    if not pcm:
        raise TTSUnavailable("Empty audio from model")
    wav = pcm_to_wav(pcm)
    _CACHE[key] = wav
    if len(_CACHE) > _MAX_CACHE:
        _CACHE.popitem(last=False)
    return wav
