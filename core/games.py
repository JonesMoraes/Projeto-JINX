"""Installed-game discovery from local launcher metadata; never downloads games."""
import json
import os
import platform
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import quote
import psutil
from core import outcome


def read(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError("Manifest absent/too large")
    return path.read_text(encoding="utf-8-sig")


def contained(root, relative):
    root = Path(root).resolve()
    result = (root / relative).resolve()
    if not result.is_relative_to(root) or result == root:
        raise ValueError("Path escapes installation")
    return result


def steam(root):
    root = Path(root)
    libraries = {root}
    try:
        for value in re.findall(r'"path"\s+"([^"\n]+)"', read(root / "steamapps/libraryfolders.vdf")):
            libraries.add(Path(value.replace("\\\\", "\\")))
    except (OSError, ValueError):
        pass
    rows = []
    for library in libraries:
        for manifest in list((library / "steamapps").glob("appmanifest_*.acf"))[:2000]:
            try:
                fields = dict(re.findall(r'"(appid|name|installdir)"\s+"([^"\n]+)"', read(manifest)))
                game_id = fields["appid"]
                location = contained(library / "steamapps/common", fields["installdir"])
                if not game_id.isdigit() or not location.is_dir():
                    continue
                rows.append({"store": "steam", "id": game_id, "name": fields["name"], "root": str(location),
                             "launch": "steam://rungameid/" + game_id})
            except (OSError, ValueError, KeyError):
                continue
    return rows


def epic(folder):
    rows = []
    for path in list(Path(folder).glob("*.item"))[:2000]:
        try:
            d = json.loads(read(path))
            game_id = d["AppName"]
            location = Path(d["InstallLocation"])
            exe = contained(location, d["LaunchExecutable"])
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", game_id) or not exe.is_file():
                continue
            rows.append({"store": "epic", "id": game_id, "name": d["DisplayName"], "root": str(location.resolve()),
                         "launch": "com.epicgames.launcher://apps/" + quote(game_id, safe="") + "?action=launch&silent=true"})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return rows


def riot(path):
    try:
        mapping = json.loads(read(path)).get("associated_client", {})
        rows = []
        for game, client in mapping.items():
            game, client = Path(game), Path(client)
            product = {"valorant.exe": "valorant", "leagueclient.exe": "league_of_legends"}.get(game.name.lower())
            if product and game.is_file() and client.is_file() and client.name.lower() == "riotclientservices.exe":
                rows.append({"store": "riot", "id": product, "name": "VALORANT" if product == "valorant" else "League of Legends",
                    "root": str(game.parent.resolve()), "launch": str(client.resolve()), "product": product})
        return rows
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def registry_value(hive, key, value):
    import winreg
    try:
        with winreg.OpenKey(hive, key) as handle:
            return winreg.QueryValueEx(handle, value)[0]
    except OSError:
        return None


def discover():
    if platform.system() != "Windows":
        roots = [Path.home() / ".steam/steam", Path.home() / "Library/Application Support/Steam"]
    else:
        import winreg
        roots = [registry_value(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                 registry_value(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")]
    rows = []
    for root in roots:
        if root:
            rows.extend(steam(root))
    if platform.system() == "Windows":
        import winreg
        data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        epic_data = registry_value(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Epic Games\EpicGamesLauncher", "AppDataPath")
        rows.extend(epic(Path(epic_data) / "Manifests" if epic_data else data / "Epic/EpicGamesLauncher/Data/Manifests"))
        rows.extend(riot(data / "Riot Games/RiotClientInstalls.json"))
    return list({(r["store"], r["id"]): r for r in rows}.values())


def running(root):
    root = Path(root).resolve()
    for process in psutil.process_iter(["exe"]):
        try:
            if process.info["exe"] and Path(process.info["exe"]).resolve().is_relative_to(root):
                return True
        except (psutil.Error, OSError):
            continue
    return False


def launch(row):
    if row["store"] == "riot":
        subprocess.Popen([row["launch"], "--launch-product=" + row["product"], "--launch-patchline=live"])
    else:
        from actions.open_app import _LAUNCHERS, _SYSTEM
        if not _LAUNCHERS[_SYSTEM](row["launch"]):
            return outcome.failed("game_launch", "Launcher recusou / Launcher refused")
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if running(row["root"]):
            return outcome.done("game_launch", game=row["name"])
        time.sleep(.2)
    return outcome.unverified("game_launch", "Solicitado ao launcher, processo do jogo ainda não observado / Requested from launcher; game process not observed yet", game=row["name"])
