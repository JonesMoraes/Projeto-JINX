"""Dispatch live frames to opt-in local observers; no frame retention."""
def feed(frame):
    from core import presence, pose_monitor
    from core.gesture_control import control
    control.feed(frame)
    presence.feed(frame)
    pose_monitor.feed(frame)
    try:
        from vision.faces.service import get_service
        identity = get_service()
        if identity.active:
            identity.feed(frame)
    except Exception:
        pass


def stop():
    from core import presence, pose_monitor
    from core.gesture_control import control
    control.stop()
    presence.stop()
    pose_monitor.stop()
    try:
        from vision.faces.service import get_service
        get_service().stop()
    except Exception:
        pass
