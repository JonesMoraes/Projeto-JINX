"""Local video editing through the system FFmpeg executable."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from core import outcome

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv"}
_MAX_INPUT_BYTES = 8 * 1024 * 1024 * 1024
_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_FFPROBE = shutil.which("ffprobe") or "ffprobe"

PLUGIN = {
    "name": "video_editor",
    "description": (
        "Edit a local video for social media: remove silent sections, create Portuguese or multilingual "
        "Whisper subtitles as SRT or burn them into the video, and crop/pad to vertical 9:16 or square 1:1 "
        "with a blurred background. Requires an explicit local video path. Does not upload or publish media."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["cut_silence", "subtitles", "resize"]},
        "path": {"type": "STRING", "description": "Absolute path to the user's local video"},
        "format": {"type": "STRING", "enum": ["9:16", "1:1"]},
        "burn_in": {"type": "BOOLEAN", "description": "Burn subtitles in video; false creates SRT"},
        "model": {"type": "STRING", "enum": ["tiny", "base", "small", "medium", "large-v3"]},
        "silence_db": {"type": "NUMBER", "description": "Silence threshold in dBFS, default -35"},
        "min_silence": {"type": "NUMBER", "description": "Minimum silence duration in seconds, default 0.6"},
    }, "required": ["action", "path"]},
    "behavior": "NON_BLOCKING",
    "scheduling": "SILENT",
}


def _input_path(value):
    if not value:
        raise ValueError("Informe o caminho completo do vídeo local.")
    path = Path(str(value)).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in _VIDEO_EXTENSIONS:
        raise ValueError("O caminho precisa apontar para um arquivo de vídeo suportado.")
    if path.stat().st_size > _MAX_INPUT_BYTES:
        raise ValueError("Vídeos acima de 8 GB não são aceitos por esta ferramenta.")
    return path


def _run(command, timeout=7200):
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout, check=False)
    if result.returncode:
        detail = (result.stderr or "FFmpeg falhou").strip().splitlines()
        raise RuntimeError(detail[-1][:240] if detail else "FFmpeg falhou")
    return result


def _find_binaries():
    global _FFMPEG, _FFPROBE
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        _FFMPEG, _FFPROBE = ffmpeg, ffprobe
        return
    configured = str(os.environ.get("JINX_FFMPEG_DIR") or "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.extend((Path(__file__).resolve().parent.parent / "tools" / "ffmpeg" / "bin",
                       Path(__file__).resolve().parent.parent / "ffmpeg" / "bin"))
    for directory in candidates:
        candidate_ffmpeg, candidate_ffprobe = directory / "ffmpeg.exe", directory / "ffprobe.exe"
        if candidate_ffmpeg.is_file() and candidate_ffprobe.is_file():
            _FFMPEG, _FFPROBE = str(candidate_ffmpeg), str(candidate_ffprobe)
            return
    raise RuntimeError("FFmpeg/ffprobe não encontrados no PATH. Instale FFmpeg ou defina JINX_FFMPEG_DIR.")


def _probe(path):
    result = _run([_FFPROBE, "-v", "error", "-show_streams", "-show_format",
                   "-of", "json", str(path)], timeout=30)
    data = json.loads(result.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("O arquivo não contém uma faixa de vídeo.")
    duration = float(data.get("format", {}).get("duration") or 0)
    if duration <= 0:
        raise ValueError("Não foi possível confirmar a duração do vídeo.")
    return video, duration


def _encoder_args():
    encoders = _run([_FFMPEG, "-hide_banner", "-encoders"], timeout=30).stdout
    if re.search(r"\bh264_amf\b", encoders):
        return ["-c:v", "h264_amf", "-quality", "balanced"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]


def _cut_silence(path, video, duration, params):
    threshold = float(params.get("silence_db", -35))
    minimum = float(params.get("min_silence", 0.6))
    if not -60 <= threshold <= -10 or not 0.2 <= minimum <= 5:
        raise ValueError("Limite de silêncio deve ficar entre -60 e -10 dBFS; duração entre 0,2 e 5 s.")
    detect = _run([_FFMPEG, "-hide_banner", "-nostats", "-i", str(path), "-vn",
                   "-af", f"silencedetect=noise={threshold}dB:d={minimum}", "-f", "null", "-"],
                  timeout=min(3600, max(120, int(duration * 8))))
    times = []
    for line in detect.stderr.splitlines():
        start = re.search(r"silence_start:\s*([\d.]+)", line)
        end = re.search(r"silence_end:\s*([\d.]+)", line)
        if start:
            times.append(("start", float(start.group(1))))
        if end:
            times.append(("end", float(end.group(1))))
    silences, opened = [], None
    for kind, at in times:
        if kind == "start":
            opened = at
        elif opened is not None:
            silences.append((opened, min(at, duration)))
            opened = None
    if opened is not None:
        silences.append((opened, duration))
    kept, cursor = [], 0.0
    for start, end in silences:
        start, end = max(cursor, start), max(cursor, end)
        if start > cursor:
            kept.append((cursor, start))
        cursor = end
    if cursor < duration:
        kept.append((cursor, duration))
    if not kept:
        return None, len(silences)
    out = path.with_name(f"{path.stem}_sem_silencios.mp4")
    filters, labels = [], []
    # Probe stream metadata to preserve audio where the source has it.
    streams = json.loads(_run([_FFPROBE, "-v", "error", "-show_streams", "-of", "json", str(path)], 30).stdout).get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    for i, (start, end) in enumerate(kept):
        filters.append(f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{i}]")
        if has_audio:
            filters.append(f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[a{i}]")
            labels.append(f"[v{i}][a{i}]")
        else:
            labels.append(f"[v{i}]")
    concat = "".join(labels) + f"concat=n={len(kept)}:v=1:a={1 if has_audio else 0}[vout]" + ("[aout]" if has_audio else "")
    filters.append(concat)
    command = [_FFMPEG, "-hide_banner", "-y", "-i", str(path), "-filter_complex", ";".join(filters), "-map", "[vout]"]
    if has_audio:
        command += ["-map", "[aout]"]
    command += _encoder_args() + ["-c:a", "aac", "-movflags", "+faststart", str(out)]
    _run(command, timeout=min(7200, max(300, int(duration * 20))))
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError("FFmpeg não produziu um arquivo de saída válido.")
    return out, len(silences)


def _subtitles(path, video, params):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("Whisper ausente; instale faster-whisper no painel Engine & Providers.") from None
    model_name = str(params.get("model") or "small")
    if model_name not in {"tiny", "base", "small", "medium", "large-v3"}:
        raise ValueError("Modelo Whisper inválido.")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(path), beam_size=1, vad_filter=True)
    rows = list(segments)
    if not rows:
        raise RuntimeError("Whisper não encontrou fala para legendar.")
    srt = path.with_suffix(".srt")
    def stamp(seconds):
        ms = max(0, round(seconds * 1000))
        hours, ms = divmod(ms, 3_600_000)
        minutes, ms = divmod(ms, 60_000)
        secs, ms = divmod(ms, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"
    content = "\n\n".join(f"{i}\n{stamp(seg.start)} --> {stamp(seg.end)}\n{seg.text.strip()}"
                           for i, seg in enumerate(rows, 1)) + "\n"
    srt.write_text(content, encoding="utf-8-sig")
    if not params.get("burn_in", False):
        return srt, len(rows), getattr(info, "language", "")
    out = path.with_name(f"{path.stem}_legendado.mp4")
    subtitle_filter = "subtitles=filename='" + str(srt).replace("\\", "/").replace(":", r"\:").replace("'", r"\'") + "'"
    _run([_FFMPEG, "-hide_banner", "-y", "-i", str(path), "-vf", subtitle_filter,
          *_encoder_args(), "-c:a", "copy", "-movflags", "+faststart", str(out)],
         timeout=7200)
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError("O vídeo legendado não foi criado.")
    return out, len(rows), getattr(info, "language", "")


def _resize(path, video, params):
    fmt = str(params.get("format") or "9:16")
    if fmt == "9:16":
        width, height = 1080, 1920
    elif fmt == "1:1":
        width = height = 1080
    else:
        raise ValueError("Formato aceito: 9:16 ou 1:1.")
    out = path.with_name(f"{path.stem}_{'vertical' if fmt == '9:16' else 'quadrado'}.mp4")
    vf = (f"split[fg][bg];[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
          f"crop={width}:{height},gblur=sigma=24[blur];[fg]scale={width}:{height}:"
          f"force_original_aspect_ratio=decrease[fit];[blur][fit]overlay=(W-w)/2:(H-h)/2,"
          "setsar=1")
    _run([_FFMPEG, "-hide_banner", "-y", "-i", str(path), "-filter_complex", vf,
          "-map", "0:a?", *_encoder_args(), "-c:a", "aac", "-movflags", "+faststart", str(out)],
         timeout=7200)
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError("A versão redimensionada não foi criada.")
    return out


def _edit(params):
    _find_binaries()
    path = _input_path(params.get("path"))
    video, duration = _probe(path)
    action = params.get("action")
    if action == "cut_silence":
        output, count = _cut_silence(path, video, duration, params)
        return output, {"silence_sections": count}
    if action == "subtitles":
        output, count, language = _subtitles(path, video, params)
        return output, {"subtitle_lines": count, "language": language}
    if action == "resize":
        output = _resize(path, video, params)
        return output, {"format": params.get("format") or "9:16"}
    raise ValueError("Ação aceita: cut_silence, subtitles ou resize.")


def run(parameters, player=None, session_memory=None):
    params = dict(parameters or {})
    try:
        output, facts = _edit(params)
        if player and callable(getattr(player, "show_content", None)):
            player.show_content("Edição de vídeo concluída", str(output))
        return outcome.done("video_editor", path=str(output), verified=output.is_file(), **facts)
    except Exception as exc:
        return outcome.failed("video_editor", str(exc)[:240])
