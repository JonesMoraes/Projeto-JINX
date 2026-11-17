"""YuNet + SFace backend using the installed OpenCV DNN face APIs."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

from vision.faces.base import FaceDetection, default_model_directory, normalize_embedding

_MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def _verified(path: Path, expected: str) -> bool:
    if not path.is_file():
        return False
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


def ensure_models(directory: Path | None = None, *, download: bool = True) -> dict[str, Path]:
    """Return SHA-256-verified models, downloading only from pinned upstream URLs."""
    folder = Path(directory or default_model_directory())
    folder.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, (url, expected) in _MODELS.items():
        target = folder / name
        if not _verified(target, expected):
            target.unlink(missing_ok=True)
            if not download:
                raise FileNotFoundError(f"Verified face model is missing: {name}")
            fd, temp_name = tempfile.mkstemp(prefix=f"{name}.", suffix=".part", dir=folder)
            digest = hashlib.sha256()
            total = 0
            try:
                with os.fdopen(fd, "wb") as output:
                    request = Request(url, headers={"User-Agent": "JINX local face identity"})
                    with urlopen(request, timeout=45) as response:
                        while chunk := response.read(1024 * 1024):
                            total += len(chunk)
                            if total > 100_000_000:
                                raise ValueError("Face model exceeds the 100 MB download cap")
                            digest.update(chunk)
                            output.write(chunk)
                if digest.hexdigest() != expected:
                    raise ValueError(f"SHA-256 verification failed for {name}")
                os.replace(temp_name, target)
            except Exception:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
                raise
        result[name] = target
    return result


class OpenCVFaceBackend:
    """OpenCV Zoo YuNet detector and SFace 128-dimensional recognizer."""

    name = "opencv_sface"
    dimension = 128
    threshold = 0.363

    def __init__(self, *, model_dir: Path | None = None, download: bool = True,
                 provider: str = "cpu") -> None:
        import cv2

        paths = ensure_models(model_dir, download=download)
        self._cv2 = cv2
        self.provider = provider.strip().lower()
        self._detector = cv2.FaceDetectorYN.create(
            str(paths["face_detection_yunet_2023mar.onnx"]), "", (320, 320),
            0.85, 0.3, 5000)
        self._recognizer = cv2.FaceRecognizerSF.create(
            str(paths["face_recognition_sface_2021dec.onnx"]), "")
        self._set_provider(self.provider)

    def _set_provider(self, provider: str) -> None:
        if provider != "cpu":
            raise ValueError("This OpenCV Python API build exposes CPU inference only")

    def detect(self, frame: np.ndarray) -> list[FaceDetection]:
        if frame is None or frame.ndim != 3 or frame.shape[2] < 3:
            return []
        height, width = frame.shape[:2]
        if width < 2 or height < 2:
            return []
        self._detector.setInputSize((width, height))
        _status, rows = self._detector.detect(frame)
        if rows is None:
            return []
        output = []
        for row in rows:
            values = tuple(float(v) for v in row.tolist())
            x, y, w, h = (int(round(v)) for v in values[:4])
            if w <= 0 or h <= 0:
                continue
            output.append(FaceDetection(
                bbox=(x, y, w, h), score=float(values[14]),
                landmarks=tuple(values[4:14]), raw=values))
        return output

    def embed(self, frame: np.ndarray, detection: FaceDetection) -> np.ndarray:
        row = np.asarray(detection.raw, dtype=np.float32)
        if row.size < 15:
            raise ValueError("YuNet alignment data is missing")
        aligned = self._recognizer.alignCrop(frame, row)
        feature = self._recognizer.feature(aligned)
        return normalize_embedding(feature, expected_dim=self.dimension)


def create_backend(name: str = "opencv_sface", **kwargs):
    if name == "opencv_sface":
        return OpenCVFaceBackend(**kwargs)
    if name == "insightface":
        raise RuntimeError("InsightFace is optional and is not installed in this build")
    raise ValueError(f"Unknown face backend: {name}")
