import os
import tempfile
import asyncio
from pathlib import Path

from config import TTS_OUTPUT_DIR

TTS_DIR = TTS_OUTPUT_DIR


class TTSEngine:
    def __init__(self):
        self.edge_available = False
        self.gtts_available = False

        try:
            import edge_tts
            self.edge_available = True
        except ImportError:
            pass

        try:
            import gtts
            self.gtts_available = True
        except ImportError:
            pass

    async def synthesize(self, text: str, voice: str = "en-US-AriaNeural") -> dict:
        if self.edge_available:
            return await self._edge_tts(text, voice)
        elif self.gtts_available:
            return await self._gtts(text)
        else:
            return {"error": "No TTS engine available. Install edge-tts or gtts.", "audio": None}

    async def _edge_tts(self, text: str, voice: str) -> dict:
        try:
            import edge_tts

            filename = f"tts_{hash(text) & 0xFFFFFFFF}.mp3"
            filepath = TTS_DIR / filename

            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(filepath))

            return {
                "audio": f"/api/tts/audio/{filename}",
                "provider": "edge-tts",
                "voice": voice,
            }
        except Exception as e:
            return {"error": str(e), "audio": None}

    async def _gtts(self, text: str) -> dict:
        try:
            from gtts import gTTS

            filename = f"tts_{hash(text) & 0xFFFFFFFF}.mp3"
            filepath = TTS_DIR / filename

            tts = gTTS(text=text, lang="en")
            tts.save(str(filepath))

            return {
                "audio": f"/api/tts/audio/{filename}",
                "provider": "gtts",
                "voice": "en",
            }
        except Exception as e:
            return {"error": str(e), "audio": None}

    async def list_voices(self) -> list:
        voices = []
        if self.edge_available:
            try:
                import edge_tts
                v = await edge_tts.list_voices()
                voices = [{"id": voice["ShortName"], "name": voice["FriendlyName"],
                           "locale": voice["Locale"], "provider": "edge-tts"} for voice in v[:50]]
            except Exception:
                pass
        return voices
