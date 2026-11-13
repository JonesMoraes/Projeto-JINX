"""Optional Edge TTS provider; adapter for JINX's PCM contract (see NOTICE.md)."""
import asyncio
import re
import sys
from contextlib import aclosing
from importlib.util import find_spec
from . import audio
from .base import Field

VOICES = ("pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "en-US-AriaNeural", "en-US-GuyNeural")
PACKAGES = ("edge-tts>=7,<8", "miniaudio>=1.61,<2")


def available():
    return all(find_spec(name) is not None for name in ("edge_tts", "miniaudio"))


class EdgeTTS:
    def __init__(self, cfg):
        self.voice_id = str(cfg.get("voice_id") or VOICES[0])
        self.rate = str(cfg.get("rate") or "+0%")
        if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}-[A-Za-z]+Neural", self.voice_id):
            raise ValueError("Voz inválida / Invalid voice")
        if not re.fullmatch(r"[+-]\d{1,3}%", self.rate) or not -50 <= int(self.rate[:-1]) <= 100:
            raise ValueError("Velocidade deve ficar entre -50% e +100% / Rate must be -50% to +100%")
        self.caps = {"audio_out": True}

    def voices(self):
        if find_spec("edge_tts") is None:
            raise RuntimeError("Instale edge-tts para consultar vozes / Install edge-tts to list voices")
        import edge_tts
        async def fetch():
            async with asyncio.timeout(15):
                rows = await edge_tts.list_voices()
                result = [(r["ShortName"], r["ShortName"] + " · " + r.get("Gender", ""))
                          for r in rows if r.get("Locale", "").startswith(("pt-BR", "en-"))]
                if not result:
                    raise RuntimeError("Nenhuma voz PT-BR/EN retornada / No PT-BR/EN voices returned")
                return sorted(result, key=lambda row: (not row[0].startswith("pt-BR"), row[0]))
        return asyncio.run(fetch())

    def probe(self):
        if not available():
            return False, "Instale as dependências opcionais no painel / Install optional dependencies in the panel"
        try:
            listed = self.voices()
            if self.voice_id not in {value for value, label in listed}:
                return False, "Voz não listada; atualize o seletor / Voice not listed; refresh selector"
            return True, "Voz listada; use OUVIR TESTE para verificar áudio / Voice listed; use LISTEN TEST to verify audio"
        except Exception:
            return False, "Lista de vozes não verificada / Voice list unverified"

    async def speak(self, text, voice=""):
        if not str(text).strip():
            return
        if not available():
            raise RuntimeError("Instale edge-tts e miniaudio nas configurações / Install edge-tts and miniaudio in settings")
        if len(text) > 5000:
            raise ValueError("Divida o texto em trechos menores / Split the text into shorter pieces")
        import edge_tts
        data = bytearray()
        selected = voice or self.voice_id
        try:
            async with asyncio.timeout(40):
                communicator = edge_tts.Communicate(text, selected, rate=self.rate)
                async with aclosing(communicator.stream()) as stream:
                    async for message in stream:
                        if message.get("type") == "audio":
                            data.extend(message["data"])
                            if len(data) > 6_000_000:
                                raise ValueError("Audio limit exceeded")
            if not data:
                raise RuntimeError("No audio returned")
            pcm = await asyncio.to_thread(_decode, bytes(data))
            if not pcm:
                raise RuntimeError("Empty decoded audio")
            for chunk in audio.chunk(pcm):
                yield chunk
        except asyncio.CancelledError:
            raise
        except Exception:
            raise RuntimeError("Áudio Edge TTS não confirmado; confira conexão/voz / Edge TTS audio unverified; check connection/voice") from None

    def playback_test(self, cancel=None):
        import sounddevice as sd
        from core import audio_devices
        from memory.config_manager import get_output_device
        if not available():
            return False, "Instale as dependências opcionais / Install optional dependencies"
        text = "This is a voice test in English." if self.voice_id.startswith("en-") else "Este é um teste de voz em português do Brasil."
        async def collect():
            return b"".join([chunk async for chunk in self.speak(text)])
        try:
            pcm = asyncio.run(collect())
            if not pcm or cancel is not None and cancel.is_set():
                return False, "Teste cancelado ou sem áudio / Test cancelled or no audio"
            name = get_output_device()
            device = audio_devices.resolve(name, "output")
            if name and device is None:
                return False, "Saída escolhida indisponível / Selected output unavailable"
            with sd.RawOutputStream(samplerate=audio.SPEAKER_RATE, channels=1, dtype="int16", device=device) as stream:
                for chunk in audio.chunk(pcm):
                    if cancel is not None and cancel.is_set():
                        return False, "Teste cancelado / Test cancelled"
                    if stream.write(chunk):
                        return False, "Saída perdeu amostras; teste não confirmado / Output underflow; test unverified"
            return True, "Áudio enviado à saída escolhida; confirme se ouviu / Audio sent to selected output; confirm you heard it"
        except Exception:
            return False, "Síntese/reprodução não confirmada / Synthesis/playback unverified"


def _decode(data):
    import miniaudio
    decoded = miniaudio.decode(data, output_format=miniaudio.SampleFormat.SIGNED16,
                              nchannels=1, sample_rate=audio.SPEAKER_RATE)
    samples = decoded.samples
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


PROVIDER = {"id": "edge_tts", "kind": "tts", "label": "Edge TTS — vozes online / online voices",
    "hint": "Microsoft online · sem conta/chave · instalação opcional / no account/key · optional install",
    "requires": ("edge_tts", "miniaudio"), "install": "edge-tts",
    "install_label": "INSTALAR EDGE TTS + ÁUDIO / INSTALL",
    "needs": (Field("voice_id", "Voz / Voice", kind="choice", choices=VOICES, default=VOICES[0]),
              Field("rate", "Velocidade / Rate", default="+0%", required=False,
                    hint="-50% a +100%; use sinal / use a sign")),
    "caps": {"audio_out": True}, "factory": EdgeTTS}
