"""Explicit UI-only optional installer; refuses plans above 20 MB."""
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

LIMIT = 20 * 1024 * 1024


def install():
    from .tts_edge import PACKAGES
    try:
        with tempfile.TemporaryDirectory(prefix="jinx-edge-plan-") as tmp:
            report = Path(tmp) / "report.json"
            plan = subprocess.run([sys.executable, "-m", "pip", "install", "--dry-run", "--only-binary=:all:",
                "--report", str(report), *PACKAGES], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
            if plan.returncode:
                return False, "Não foi possível resolver dependências / Could not resolve dependencies"
            rows = json.loads(report.read_text(encoding="utf-8"))["install"]
            total = 0
            artifacts = []
            for row in rows:
                url = row["download_info"]["url"]
                # Do not fetch arbitrary destinations from a custom package index.
                from urllib.parse import urlsplit
                parsed = urlsplit(url)
                if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org":
                    return False, "Origem do pacote exige revisão / Package source requires review"
                with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=15) as head:
                    size = int(head.headers.get("Content-Length") or 0)
                if size <= 0:
                    return False, "Tamanho não confirmado; instalação suspensa / Size unverified; install stopped"
                total += size
                digest = row.get("download_info", {}).get("archive_info", {}).get("hashes", {}).get("sha256")
                if not digest or len(digest) != 64:
                    return False, "Hash do pacote não confirmado / Package hash unverified"
                artifacts.append(url + "#sha256=" + digest)
            if total > LIMIT:
                return False, "Plano acima de 20 MB; peça aprovação antes de instalar / Plan above 20 MB; request approval before installing"
            if artifacts:
                result = subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", *artifacts],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
                if result.returncode:
                    return False, "Instalação falhou / Installation failed"
            from importlib import invalidate_caches
            invalidate_caches()
            from .tts_edge import available
            return available(), "Dependências verificadas; reabra o painel / Dependencies checked; reopen panel"
    except Exception:
        return False, "Instalação não verificada / Installation unverified"
