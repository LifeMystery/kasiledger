"""Speech-to-text for voice notes.

  none           -> voice notes are politely refused (owner is asked to type)
  local_whisper  -> free, runs on your computer with faster-whisper
                    (pip install -r requirements-voice.txt). Good for English,
                    weaker for isiZulu/Sesotho. A paid service (Azure Speech) can be
                    added later as another class with the same `transcribe` method.
"""
from __future__ import annotations

from pathlib import Path

from .. import config


class SpeechToText:
    name = "none"
    available = False

    def transcribe(self, audio_path: Path) -> str | None:
        return None


class LocalWhisper(SpeechToText):
    name = "local_whisper"

    def __init__(self) -> None:
        self._model = None
        try:
            import faster_whisper  # noqa: F401

            self.available = True
        except ImportError:
            print("[speech] faster-whisper is not installed: pip install -r requirements-voice.txt")
            self.available = False

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            # int8 on CPU keeps it light enough for a normal laptop
            self._model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, audio_path: Path) -> str | None:
        if not self.available:
            return None
        try:
            segments, _info = self._load().transcribe(str(audio_path), beam_size=1, vad_filter=True)
            text = " ".join(s.text.strip() for s in segments).strip()
            return text or None
        except Exception as exc:  # noqa: BLE001
            print(f"[speech] transcription failed: {exc}")
            return None


_instance: SpeechToText | None = None


def get_speech() -> SpeechToText:
    global _instance
    if _instance is None:
        _instance = LocalWhisper() if config.SPEECH == "local_whisper" else SpeechToText()
    return _instance
