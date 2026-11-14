"""Optional, local pose estimates for posture feedback and push-up counting."""
from __future__ import annotations

import math
import threading
import time

_lock = threading.RLock()
_pose = None
_landmarks = None
_mode = ""
_notify = None
_last = 0.0
_bad_since = None
_last_notice = 0.0
_phase = "up"
_reps = 0


def start(mode: str, notify=None) -> str:
    global _pose, _landmarks, _mode, _notify, _last, _bad_since, _last_notice, _phase, _reps
    if mode not in ("posture", "pushups"):
        return "Unknown pose activity."
    try:
        import mediapipe as mp
        import cv2
        _ = cv2.resize
        landmarks = mp.solutions.pose.PoseLandmark
        pose = mp.solutions.pose.Pose(static_image_mode=False, model_complexity=0,
                                     smooth_landmarks=True, enable_segmentation=False,
                                     min_detection_confidence=.55,
                                     min_tracking_confidence=.55)
    except Exception as exc:
        return f"Pose model unavailable: {type(exc).__name__}. Install optional fitness support if allowed."
    with _lock:
        _pose, _landmarks, _mode, _notify = pose, landmarks, mode, notify
        _last, _bad_since, _last_notice, _phase, _reps = 0.0, None, 0.0, "up", 0
    return f"{mode} monitor on; camera frames are processed locally and not saved."


def stop():
    global _pose, _landmarks, _mode, _notify, _bad_since
    with _lock:
        pose, _pose = _pose, None
        _landmarks, _mode, _notify, _bad_since = None, "", None, None
    if pose:
        try: pose.close()
        except Exception: pass


def status():
    with _lock: return {"active": bool(_pose), "mode": _mode, "pushups": _reps}


def _angle(a, b, c):
    radians = math.atan2(c.y - b.y, c.x - b.x) - math.atan2(a.y - b.y, a.x - b.x)
    value = abs(math.degrees(radians))
    return 360 - value if value > 180 else value


def feed(frame):
    global _last, _bad_since, _last_notice, _phase, _reps
    with _lock:
        pose, landmarks, mode, notify = _pose, _landmarks, _mode, _notify
        if pose is None or time.monotonic() - _last < .20: return
        _last = time.monotonic()
    try:
        import cv2
        small = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        result = pose.process(rgb)
        marks = result.pose_landmarks.landmark if result.pose_landmarks else None
    except Exception:
        return
    if not marks: return
    L = landmarks
    if mode == "posture":
        ear = marks[L.LEFT_EAR.value]; shoulder = marks[L.LEFT_SHOULDER.value]
        hip = marks[L.LEFT_HIP.value]
        if min(ear.visibility, shoulder.visibility, hip.visibility) < .6: return
        lean = abs(math.degrees(math.atan2(hip.x - shoulder.x, shoulder.y - hip.y)))
        poor = lean > 18 or ear.x - shoulder.x > .16
        now = time.monotonic()
        with _lock:
            if poor and _bad_since is None: _bad_since = now
            if not poor: _bad_since = None
            warn = poor and _bad_since is not None and now - _bad_since > 12 and now - _last_notice > 60
            if warn: _last_notice = now
        if warn and notify: notify("Posture may be leaning; check your position. This is not a medical assessment.")
    elif mode == "pushups":
        pairs = ((L.LEFT_SHOULDER.value, L.LEFT_ELBOW.value, L.LEFT_WRIST.value),
                 (L.RIGHT_SHOULDER.value, L.RIGHT_ELBOW.value, L.RIGHT_WRIST.value))
        angles = []
        for a, b, c in pairs:
            pts = (marks[a], marks[b], marks[c])
            if min(p.visibility for p in pts) >= .65: angles.append(_angle(*pts))
        if not angles: return
        bend = sum(angles) / len(angles)
        notice = None
        with _lock:
            if bend < 90: _phase = "down"
            elif bend > 155 and _phase == "down":
                _phase = "up"; _reps += 1; notice = f"Flexões contadas: {_reps}"
        if notice and notify: notify(notice)
