"""Dispatch live frames to opt-in local observers; no frame retention."""
def feed(frame):
    from core import presence, pose_monitor
    from core.gesture_control import control
    control.feed(frame)
    presence.feed(frame)
    pose_monitor.feed(frame)


def stop():
    from core import presence, pose_monitor
    from core.gesture_control import control
    control.stop()
    presence.stop()
    pose_monitor.stop()
