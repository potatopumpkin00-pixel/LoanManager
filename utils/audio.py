"""
utils/audio.py — Audio conversion (OGA → MP3) and Text-to-Speech (Edge-TTS).

Handles:
- Converting Telegram voice messages (OGA/OGG) to MP3 for Whisper
- Generating Tamil/English voice responses using Edge-TTS
"""
import asyncio
import os
import re
import tempfile
from pathlib import Path

import edge_tts

# Locate ffmpeg binary
_ffmpeg_exe = "ffmpeg"  # default: assume system ffmpeg
try:
    import imageio_ffmpeg
    _ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    pass

# Edge-TTS voice names
VOICES = {
    "ta": "ta-IN-PallaviNeural",   # Tamil female
    "en": "en-IN-NeerjaNeural",    # English (India) female
}


def oga_to_mp3(oga_path: str) -> str:
    """
    Convert an OGA/OGG voice file to MP3 using ffmpeg directly.

    Args:
        oga_path: Path to the input OGA file.

    Returns:
        Path to the converted MP3 file.
    """
    import subprocess

    mp3_path = oga_path.rsplit(".", 1)[0] + ".mp3"
    subprocess.run(
        [_ffmpeg_exe, "-y", "-i", oga_path, "-vn", "-ar", "16000",
         "-ac", "1", "-b:a", "64k", mp3_path],
        check=True, capture_output=True,
    )
    return mp3_path


def detect_language(text: str) -> str:
    """
    Detect if text is primarily Tamil or English.

    Uses Unicode range detection:
    - Tamil characters: U+0B80 to U+0BFF
    """
    tamil_chars = len(re.findall(r"[\u0B80-\u0BFF]", text))
    total_alpha = len(re.findall(r"[a-zA-Z\u0B80-\u0BFF]", text))

    if total_alpha == 0:
        return "en"

    tamil_ratio = tamil_chars / total_alpha
    return "ta" if tamil_ratio > 0.3 else "en"


async def text_to_speech(text: str, lang: str = None) -> str:
    """
    Convert text to speech using Edge-TTS.

    Args:
        text: Text to convert to speech.
        lang: Language code ('ta' or 'en'). Auto-detected if None.

    Returns:
        Path to the generated MP3 file.
    """
    if lang is None:
        lang = detect_language(text)

    voice = VOICES.get(lang, VOICES["en"])

    # Create a temp file for the output
    tmp_dir = tempfile.gettempdir()
    output_path = os.path.join(tmp_dir, f"tts_response_{id(text)}.mp3")

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

    return output_path


def text_to_speech_sync(text: str, lang: str = None) -> str:
    """Synchronous wrapper for text_to_speech."""
    return asyncio.run(text_to_speech(text, lang))
