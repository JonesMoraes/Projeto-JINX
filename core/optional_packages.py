"""Explicit settings-only installation with a bounded, hashed PyPI plan."""
import importlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

GROUPS = {"office": ("python-pptx", "python-docx", "openpyxl", "pypdf"),
          "youtube": ("youtube-transcript-api",), "meeting": ("SoundCard>=0.4,<1",),
          "fitness": ("mediapipe",)}
MODULES = {"office": ("pptx", "docx", "openpyxl", "pypdf"), "youtube": ("youtube_transcript_api",),
           "meeting": ("soundcard",), "fitness": ("mediapipe",)}


def install(group):
    if group not in GROUPS:
        return False, "Grupo desconhecido / Unknown package group"
    try:
        with tempfile.TemporaryDirectory(prefix="jinx-optional-") as temp:
            report = Path(temp) / "plan.json"
            result = subprocess.run([sys.executable, "-m", "pip", "install", "--dry-run", "--only-binary=:all:",
                "--report", str(report, shell=False), *GROUPS[group]], capture_output=True, timeout=120)
            if result.returncode:
                return False, "Plano de dependências indisponível / Dependency plan unavailable"
            total, artifacts = 0, []
            for row in json.loads(report.read_text(encoding="utf-8"))["install"]:
                info = row["download_info"]
                url = info["url"]
                if urlsplit(url).scheme != "https" or urlsplit(url).hostname != "files.pythonhosted.org":
                    raise ValueError("Untrusted package source")
                with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=10) as response:
                    size = int(response.headers.get("Content-Length", 0))
                digest = info.get("archive_info", {}).get("hashes", {}).get("sha256", "")
                if size <= 0 or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
                    raise ValueError("Size/hash unverified")
                total += size
                artifacts.append(url + "#sha256=" + digest)
            if total > 20 * 1024 * 1024:
                return False, "Download acima de 20 MB: exige sua aprovação / Download above 20 MB: requires your approval"
            if artifacts:
                result = subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", *artifacts],
                                        capture_output=True, timeout=180, shell=False)
                if result.returncode:
                    return False, "Instalação falhou; confira o ambiente / Installation failed; check environment"
            importlib.invalidate_caches()
            if not all(importlib.util.find_spec(m) is not None for m in MODULES[group]):
                return False, "Pacote não detectado após instalação / Package not detected after installation"
            return True, f"Dependências verificadas ({total / 1048576:.2f} MB baixados) / Dependencies checked"
    except Exception:
        return False, "Instalação não verificada / Installation unverified"
