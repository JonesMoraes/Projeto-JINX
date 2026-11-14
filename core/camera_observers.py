"""Dispatch live frames to opt-in local observers; no frame retention."""
def feed(frame):
    from core import presence, pose_monitor
    presence.feed(frame)
    pose_monitor.feed(frame)


def stop():
    from core import presence, pose_monitor
    presence.stop()
    pose_monitor.stop()
