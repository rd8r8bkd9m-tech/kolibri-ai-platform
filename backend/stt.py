class STTEngine:
    def __init__(self):
        pass

    async def transcribe(self, audio_data: bytes, language: str = "en") -> dict:
        return {
            "error": "STT not yet configured. Whisper requires GPU or significant CPU.",
            "text": None,
        }
