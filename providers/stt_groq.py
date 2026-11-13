"""Groq hearing provider adapted from jgm-source's groq_listen; see NOTICE.md."""
import re
from importlib.util import find_spec
from .stt_whisper import WhisperSTT
from .base import Field
from . import audio

BASE = "https://api.groq.com/openai/v1"
MODELS = ("whisper-large-v3-turbo", "whisper-large-v3")


class GroqError(RuntimeError):
    pass


def language_code(value):
    code = str(value or "").strip().lower()
    code = {"auto": "", "pt-br": "pt", "portuguese": "pt", "english": "en"}.get(code, code)
    if code and not re.fullmatch(r"[a-z]{2}", code):
        raise ValueError("Idioma deve ser pt, en ou código ISO de duas letras / Use a two-letter ISO language code")
    return code


class GroqSTT(WhisperSTT):
    def __init__(self, cfg):
        super().__init__({**cfg, "backend": "api", "base_url": BASE,
                          "model": cfg.get("model") or MODELS[0], "device": "cpu"})
        self.language = language_code(cfg.get("language"))

    def _validate(self):
        if not self.api_key:
            raise RuntimeError("Cadastre SUA chave Groq / Enter YOUR Groq API key")
        if self.model_name not in MODELS:
            raise RuntimeError("Modelo de audição Groq inválido / Invalid Groq hearing model")

    def _api_blocking(self, pcm, sample_rate):
        import httpx
        self._validate()
        language = language_code(self.language)
        data = {"model": self.model_name, "response_format": "verbose_json"}
        if language:
            data["language"] = language
        try:
            with httpx.Client(timeout=20.0, follow_redirects=False) as client:
                response = client.post(BASE + "/audio/transcriptions", headers={"Authorization": "Bearer " + self.api_key},
                    data=data, files={"file": ("speech.wav", audio.to_wav(pcm, rate=sample_rate), "audio/wav")})
                if response.status_code != 200:
                    raise GroqError(f"Groq HTTP {response.status_code}; confira sua chave/cota / check your key/quota")
                result = response.json()
                if not isinstance(result, dict) or not isinstance(result.get("text"), str):
                    raise ValueError("Invalid transcript")
                text = result["text"].strip()
                detected = result.get("language") or language
                try:
                    detected = language_code(detected)
                except ValueError:
                    detected = language
                self._accept_language(detected, 1.0, text)
                return text
        except GroqError:
            raise
        except Exception:
            raise RuntimeError("Falha na transcrição Groq / Groq transcription failed") from None

    def probe(self):
        import httpx
        try:
            self._validate()
            with httpx.Client(timeout=12.0, follow_redirects=False) as client:
                response = client.get(BASE + "/models", headers={"Authorization": "Bearer " + self.api_key})
                if response.status_code != 200:
                    return False, f"Groq HTTP {response.status_code}; confira sua chave/permissão / check your key/permission"
                items = response.json().get("data", [])
                if not any(row.get("id") == self.model_name for row in items):
                    return False, "Modelo não listado para sua conta / Model not listed for your account"
            return True, "Conexão/modelo verificados; use GRAVAR para testar a transcrição / Connection/model verified; use RECORD to test transcription"
        except Exception:
            return False, "Chave/modelo ausente ou conexão não verificada / Missing key/model or connection unverified"

    def models(self):
        return list(MODELS)

    def record_test(self, cancel=None):
        """Only called by the explicit record button; never at startup/probe."""
        self._validate()
        if cancel is not None and cancel.is_set():
            return False, "Gravação cancelada / Recording cancelled"
        import asyncio
        import sounddevice as sd
        from core import audio_devices
        from memory.config_manager import get_input_device
        name = get_input_device()
        device = audio_devices.resolve(name, "input")
        if name and device is None:
            raise RuntimeError("Microfone escolhido indisponível / Selected microphone unavailable")
        try:
            chunks = []
            with sd.RawInputStream(samplerate=audio.MIC_RATE, channels=1, dtype="int16", device=device) as stream:
                for _ in range(40):
                    if cancel is not None and cancel.is_set():
                        return False, "Gravação cancelada / Recording cancelled"
                    pcm, overflow = stream.read(audio.MIC_RATE // 10)
                    if overflow:
                        return False, "Captura perdeu áudio; tente novamente / Audio overflow; retry"
                    chunks.append(bytes(pcm))
            if cancel is not None and cancel.is_set():
                return False, "Gravação cancelada / Recording cancelled"
            text = asyncio.run(self.transcribe(b"".join(chunks), audio.MIC_RATE))
            if not text:
                return False, "Nenhuma fala transcrita / No speech transcribed"
            return True, "Transcrição / Transcript: " + text[:400]
        except Exception:
            return False, "Gravação/transcrição não verificada; confira microfone, chave e cota / Recording/transcription unverified; check microphone, key and quota"


PROVIDER = {"id": "groq_stt", "kind": "stt", "label": "Groq — audição / hearing",
    "hint": "Transcrição online PT-BR/EN · SUA chave · sem modelo local / Online transcription with YOUR key",
    "requires": (), "caps": {}, "factory": GroqSTT,
    "needs": (
        Field("api_key", "SUA chave Groq / YOUR Groq key", kind="secret", default=""),
        Field("model", "Modelo de audição / Hearing model", kind="choice", choices=MODELS, default=MODELS[0]),
        Field("language", "Idioma / Language (pt, en; vazio = auto)", default="", required=False,
              hint="pt para PT-BR; en para inglês; vazio detecta / blank detects language"),
    )}


def available():
    return find_spec("httpx") is not None
