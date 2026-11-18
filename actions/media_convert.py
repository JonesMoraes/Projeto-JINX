"""Batch image conversion with Pillow and audio/video conversion via FFmpeg."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from core import outcome, undo

_IMAGE_FORMATS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP",
                  "bmp": "BMP", "tiff": "TIFF"}
_FFMPEG_FORMATS = {"mp4": "mp4", "mov": "mov", "mkv": "matroska", "webm": "webm",
                   "mp3": "mp3", "wav": "wav", "flac": "flac", "m4a": "ipod",
                   "aac": "adts", "ogg": "ogg"}


def _paths(raw) -> list[Path]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw or len(raw) > 100:
        raise ValueError("files must contain 1–100 paths")
    paths = []
    for item in raw:
        path = Path(str(item)).expanduser()
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"not a regular file: {item}")
        paths.append(path.resolve(strict=True))
    return paths


def _output_path(source: Path, output_dir: Path, extension: str) -> Path:
    candidate = output_dir / f"{source.stem}-converted.{extension}"
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = output_dir / f"{source.stem}-converted-v{index}.{extension}"
        if not candidate.exists():
            return candidate
        index += 1


def _save_image(source: Path, target: Path, fmt: str, quality: int,
                max_width: int, max_height: int) -> None:
    from PIL import Image, ImageOps
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original).convert("RGBA" if "A" in original.getbands() else "RGB")
        if max_width or max_height:
            bound_w = max_width or image.width
            bound_h = max_height or image.height
            image.thumbnail((bound_w, bound_h), Image.Resampling.LANCZOS)
        if fmt == "JPEG" and image.mode == "RGBA":
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        options = {"quality": quality} if fmt in {"JPEG", "WEBP"} else {}
        image.save(target, format=fmt, **options)
    with Image.open(target) as check:
        check.verify()


def _save_ffmpeg(source: Path, target: Path, extension: str, ffmpeg: str,
                 timeout: int, max_width: int, max_height: int) -> None:
    command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
    if max_width or max_height:
        width = max_width or -2
        height = max_height or -2
        command.extend(("-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease"))
    command.extend(("-f", _FFMPEG_FORMATS[extension], str(target)))
    completed = subprocess.run(command, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout, shell=False)
    if completed.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise RuntimeError((completed.stderr or "FFmpeg conversion failed")[-2000:])
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1", str(target)],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=20)
        if probe.returncode != 0:
            target.unlink(missing_ok=True)
            raise RuntimeError("FFprobe could not verify the converted media")


def media_convert(parameters: dict, **_context) -> str:
    p = parameters or {}
    created: list[Path] = []
    try:
        sources = _paths(p.get("files", p.get("file_path", "")))
        extension = str(p.get("format", "")).lower().lstrip(".")
        if extension not in _IMAGE_FORMATS and extension not in _FFMPEG_FORMATS:
            raise ValueError("unsupported format; choose PNG/JPEG/WEBP/BMP/TIFF or MP4/MOV/MKV/MP3/WAV/FLAC/M4A/AAC/OGG")
        output_dir = Path(str(p.get("output_dir") or sources[0].parent)).expanduser().absolute()
        output_dir.mkdir(parents=True, exist_ok=True)
        quality = int(p.get("quality", 90))
        max_width, max_height = int(p.get("max_width", 0)), int(p.get("max_height", 0))
        timeout = max(10, min(int(p.get("timeout_seconds", 600)), 3600))
        if not 1 <= quality <= 100 or min(max_width, max_height) < 0:
            raise ValueError("quality must be 1–100 and dimensions must be non-negative")
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg and extension in _FFMPEG_FORMATS:
            try:
                import imageio_ffmpeg
                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            except (ImportError, RuntimeError):
                ffmpeg = None
        if extension in _FFMPEG_FORMATS and not ffmpeg:
            return outcome.failed("media_convert", "FFmpeg was not found; install FFmpeg or imageio-ffmpeg to convert audio/video.")
        for source in sources:
            target = _output_path(source, output_dir, extension)
            fd, raw_temp = tempfile.mkstemp(prefix=f".{target.stem}-{uuid.uuid4().hex[:6]}.",
                                            suffix=f".{extension}", dir=output_dir)
            import os
            os.close(fd)
            temp = Path(raw_temp)
            try:
                if extension in _IMAGE_FORMATS:
                    _save_image(source, temp, _IMAGE_FORMATS[extension], quality,
                                max_width, max_height)
                else:
                    _save_ffmpeg(source, temp, extension, ffmpeg, timeout,
                                 max_width, max_height)
                temp.replace(target)
                created.append(target)
            finally:
                temp.unlink(missing_ok=True)
        digests = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in created}
        def undo_outputs() -> str:
            for path, digest in digests.items():
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    return outcome.failed("media_convert_undo", "An output changed; outputs were left intact.")
            for path in digests:
                path.unlink()
            return outcome.done("media_convert_undo", count=len(digests))
        undo.push_undo("Media conversion: " + str(len(created)) + " file(s)", undo_outputs)
        return outcome.done("media_convert", outputs=outcome.untrusted(
            "converted-files", "; ".join(map(str, created))), count=len(created),
            sources_preserved=True, verified=True)
    except Exception as exc:
        for path in created:
            path.unlink(missing_ok=True)
        return outcome.failed("media_convert", str(exc))


TOOL = {
    "name": "media_convert",
    "description": "Batch-convert images using Pillow and audio/video using FFmpeg. Preserves source files, supports quality and maximum dimensions, and verifies outputs.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "files": {"type": "ARRAY", "items": {"type": "STRING"}},
            "file_path": {"type": "STRING"}, "format": {"type": "STRING"},
            "output_dir": {"type": "STRING"}, "quality": {"type": "INTEGER"},
            "max_width": {"type": "INTEGER"}, "max_height": {"type": "INTEGER"},
            "timeout_seconds": {"type": "INTEGER"},
        },
        "required": ["format"],
    },
    "handler": media_convert,
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
    "tier": "extra",
    "brief": "Batch media conversion with Pillow and FFmpeg.",
}
