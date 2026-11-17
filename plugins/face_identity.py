"""Explicit local face identity, enrollment, and unknown-cluster management."""
import json
from pathlib import Path

from core import outcome
from core.plugin_jobs import Jobs
from vision.faces.service import get_service

_jobs = Jobs("Face identity")
_event_unsubscribers = []

PLUGIN = {
    "name": "face_identity",
    "description": (
        "Local-only face identity. Actions: start/stop visible webcam recognition, status, "
        "enroll_photo (path + name), enroll_live (name spoken while a person is visible), "
        "bootstrap_owner_photo, bootstrap_owner_live, list_people, unknowns, name_unknown, "
        "forget, correct. Embeddings and metadata stay in local SQLite; raw frames/crops "
        "are not saved or sent to any model. Identity is contextual only and never unlocks "
        "or authorizes sensitive actions. Requires local consent to enroll another person."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": [
            "start", "stop", "status", "enroll_photo", "enroll_live",
            "bootstrap_owner_photo", "bootstrap_owner_live", "list_people",
            "unknowns", "name_unknown", "merge_unknowns", "forget", "correct"]},
        "name": {"type": "STRING"}, "path": {"type": "STRING"},
        "unknown_id": {"type": "STRING"}, "merge_id": {"type": "STRING"},
        "track_id": {"type": "INTEGER"},
        "camera": {"type": "STRING"},
    }, "required": ["action"]},
    "behavior": "NON_BLOCKING", "scheduling": "SILENT",
}

PLUGIN_SETTINGS = {"namespace": "face_identity", "title": "IDENTIDADE LOCAL / LOCAL IDENTITY",
                   "fields": []}


def _person_text(person):
    return (f"{person['name']} · {person['sample_count']} amostra(s) · "
            f"consentimento={'sim' if person['consent'] else 'não'}")


def _background(work, player):
    return _jobs.start(work, player)


def _enroll_photo(path, name, owner=False):
    service = get_service()
    was_active = service.active
    if service.backend is None:
        service.start()
    try:
        target = Path(path).expanduser()
        if target.is_dir():
            paths = sorted(item for item in target.iterdir()
                           if item.is_file() and item.suffix.lower() in
                           {".jpg", ".jpeg", ".png", ".bmp", ".webp"})[:100]
        else:
            paths = [target]
        if not paths:
            raise ValueError("No supported image files were found")
        profile = {"role": "owner", "access": "full"} if owner else None
        return service.enroll_photos(paths, name, minimum_samples=10 if owner else 1,
                                     profile=profile)
    finally:
        if not was_active:
            service.stop()


def run(parameters, player=None, session_memory=None):
    try:
        p = parameters or {}
        action = str(p.get("action", "status")).lower()
        service = get_service()
        camera = str(p.get("camera") or "webcam").strip()[:80] or "webcam"
        name = str(p.get("name") or "").strip()

        if action == "status":
            return outcome.done("face_identity", **service.status())
        if action == "start":
            if player is None or not callable(getattr(player, "start_camera_stream", None)):
                return outcome.failed("face_identity", "Abra o HUD para iniciar a câmera local visível.")
            def start_camera():
                try:
                    message = service.start()
                    _listen_for_events(player)
                    player.start_camera_stream()
                    return outcome.done("face_identity_start", note=message,
                                        note_privacy="Local processing; no frames retained.")
                except Exception as exc:
                    service.stop()
                    return outcome.failed("face_identity_start", f"{type(exc).__name__}: {str(exc)[:180]}")
            return _background(start_camera, player)
        if action == "stop":
            service.stop()
            _clear_event_listeners()
            if player is not None and callable(getattr(player, "stop_camera_stream", None)):
                player.stop_camera_stream()
            return outcome.done("face_identity", active=False)
        if action == "enroll_photo":
            if not name or not p.get("path"):
                return outcome.failed("face_identity", "Informe o nome e o caminho da foto.")
            return _background(lambda: outcome.done("face_enroll_photo",
                person=_person_text(_enroll_photo(p["path"], name))), player)
        if action == "enroll_live":
            if not name:
                return outcome.failed("face_identity", "Diga o nome exato da pessoa visível.")
            return outcome.done("face_enroll_live", person=_person_text(service.enroll_live(name, camera=camera)))
        if action == "bootstrap_owner_photo":
            if not name or not p.get("path"):
                return outcome.failed("face_identity", "Informe seu nome e uma foto nítida.")
            return _background(lambda: outcome.done("face_owner_enroll",
                person=_person_text(_enroll_photo(p["path"], name, owner=True))), player)
        if action == "bootstrap_owner_live":
            if not name:
                return outcome.failed("face_identity", "Informe o nome do proprietário.")
            person = service.enroll_live(name, camera=camera)
            service.store.create_person(name, consent=True,
                                        profile={"role": "owner", "access": "full"})
            return outcome.done("face_owner_enroll", person=_person_text(service.store.get_person(person["id"])))
        if action == "list_people":
            people = service.store.list_people()
            text = "\n".join(_person_text(person) for person in people) or "Nenhuma pessoa cadastrada."
            if player is not None and callable(getattr(player, "show_content", None)):
                player.show_content("Pessoas conhecidas", text)
            return outcome.done("face_people", data=outcome.untrusted("face-people", json.dumps(people, ensure_ascii=False)))
        if action == "unknowns":
            rows = service.store.list_unknowns()
            text = "\n".join(f"{row['id']} · {row['n']} aparições · última {row['last_seen']}" for row in rows) or "Nenhum grupo desconhecido."
            if player is not None and callable(getattr(player, "show_content", None)):
                player.show_content("Pessoas desconhecidas", text)
            return outcome.done("face_unknowns", data=outcome.untrusted("face-unknowns", json.dumps(rows, ensure_ascii=False)))
        if action == "name_unknown":
            person = service.name_unknown(str(p.get("unknown_id", "")), name)
            return outcome.done("face_name_unknown", person=_person_text(person))
        if action == "merge_unknowns":
            merged = service.store.merge_unknowns(str(p.get("unknown_id", "")),
                                                   str(p.get("merge_id", "")))
            return outcome.done("face_merge_unknowns", merged=merged)
        if action == "forget":
            if not name:
                return outcome.failed("face_identity", "Informe o nome da pessoa a esquecer.")
            removed = service.forget(name)
            return outcome.done("face_forget", person=name, removed=removed)
        if action == "correct":
            if not name or p.get("track_id") is None:
                return outcome.failed("face_identity", "Informe o track_id e a identidade correta.")
            service.correct(int(p["track_id"]), name, camera=camera)
            return outcome.done("face_correction", track_id=p["track_id"], correct_name=name)
        return outcome.failed("face_identity", "Ação desconhecida.")
    except Exception as exc:
        return outcome.failed("face_identity", f"{type(exc).__name__}: {str(exc)[:220]}")


def _listen_for_events(player):
    from vision.faces.service import _BUS

    while _event_unsubscribers:
        _event_unsubscribers.pop()()

    def notify(event):
        if event.name == "unknown_person":
            callback = getattr(player, "request_say", None)
            if callable(callback):
                callback("Ask the user to name this newly seen person. Do not identify them by guessing.")
        elif event.name == "identity_conflict":
            callback = getattr(player, "request_say", None)
            if callable(callback):
                callback("Identity conflict detected. Ask the user which enrolled person this track belongs to.")
        elif event.name == "presence":
            callback = getattr(player, "write_log", None)
            if callable(callback):
                callback(f"SYS: {event.payload.get('person')} {event.payload.get('event')} · {event.payload.get('camera')}")

    _event_unsubscribers.append(_BUS.subscribe("unknown_person", notify))
    _event_unsubscribers.append(_BUS.subscribe("identity_conflict", notify))
    _event_unsubscribers.append(_BUS.subscribe("presence", notify))


def _clear_event_listeners():
    while _event_unsubscribers:
        _event_unsubscribers.pop()()
