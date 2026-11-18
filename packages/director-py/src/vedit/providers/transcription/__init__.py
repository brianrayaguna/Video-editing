"""Speech-to-text capability provider implementations."""

from vedit.providers.transcription.veed import VeedTranscriptionProvider
from vedit.providers.transcription.xai import XaiTranscriptionProvider

__all__ = ["VeedTranscriptionProvider", "XaiTranscriptionProvider"]
