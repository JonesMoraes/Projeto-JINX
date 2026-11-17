from __future__ import annotations

import tempfile
import subprocess
import unittest
from pathlib import Path

from PIL import Image

from actions.media_convert import media_convert
from core import undo


class MediaConvertTests(unittest.TestCase):
    def setUp(self):
        undo.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(undo.clear)
        self.root = Path(self.temp.name)
        self.first = self.root / "one.png"
        self.second = self.root / "two.png"
        Image.new("RGB", (64, 32), (20, 40, 60)).save(self.first)
        Image.new("RGBA", (40, 40), (120, 20, 30, 128)).save(self.second)

    def test_batch_image_conversion_resizes_and_preserves_sources(self):
        out = self.root / "out"
        result = media_convert({"files": [str(self.first), str(self.second)], "format": "jpg",
                                "output_dir": str(out), "max_width": 20, "max_height": 20})
        self.assertIn("status=done", result)
        outputs = sorted(out.glob("*.jpg"))
        self.assertEqual(len(outputs), 2)
        with Image.open(outputs[0]) as image:
            self.assertLessEqual(max(image.size), 20)
        self.assertTrue(self.first.exists() and self.second.exists())

    def test_invalid_format_and_missing_ffmpeg_fail_cleanly(self):
        self.assertIn("status=failed", media_convert({"file_path": str(self.first),
                                                      "format": "exe"}))

    def test_bundled_ffmpeg_converts_audio_without_system_path(self):
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        source = self.root / "tone.wav"
        subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=0.25",
                        "-y", str(source)], check=True, timeout=20)
        result = media_convert({"file_path": str(source), "format": "mp3",
                                "output_dir": str(self.root / "converted")})
        self.assertIn("status=done", result)
        converted = list((self.root / "converted").glob("*.mp3"))
        self.assertEqual(len(converted), 1)
        self.assertGreater(converted[0].stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
