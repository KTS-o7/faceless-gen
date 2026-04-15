import abc
import os
import uuid
from pathlib import Path

from elevenlabs import ElevenLabs

from backend.models.config import settings


class TTSProvider(abc.ABC):
    """Abstract base class for Text-to-Speech providers."""

    @abc.abstractmethod
    def synthesize(self, text: str, output_dir: str) -> str:
        """
        Synthesize speech from text and save to output_dir.

        Args:
            text: The text to synthesize.
            output_dir: Directory where the audio file will be saved.

        Returns:
            Absolute path to the saved .mp3 file.
        """
        ...


class ElevenLabsTTSProvider(TTSProvider):
    """ElevenLabs TTS provider using the v2+ SDK."""

    def __init__(self) -> None:
        self._client = ElevenLabs(api_key=settings.elevenlabs_api_key)

    def synthesize(self, text: str, output_dir: str) -> str:
        """Synthesize text to speech and save as MP3."""
        os.makedirs(output_dir, exist_ok=True)
        filename = f"voiceover_{uuid.uuid4().hex[:8]}.mp3"
        output_path = os.path.join(output_dir, filename)

        audio_generator = self._client.text_to_speech.convert(
            voice_id=settings.elevenlabs_voice_id,
            text=text,
            model_id="eleven_monolingual_v1",
            output_format="mp3_44100_128",
        )

        with open(output_path, "wb") as f:
            for chunk in audio_generator:
                if isinstance(chunk, bytes):
                    f.write(chunk)

        return os.path.abspath(output_path)


def get_tts_provider() -> TTSProvider:
    """Factory — returns the configured TTS provider."""
    return ElevenLabsTTSProvider()
