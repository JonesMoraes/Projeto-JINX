"""Private MediaPipe process: raw RGB stdin, landmarks-only JSON stdout.

Run with the isolated gesture interpreter. Never controls the mouse, stores
frames or opens a camera. Documentation: Google AI Edge Hand Landmarker Python.
"""
import json
import struct
import sys
import time


def main():
    import numpy as np
    import mediapipe as mp
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=sys.argv[1]),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=1,
        min_hand_detection_confidence=.7, min_hand_presence_confidence=.7,
        min_tracking_confidence=.7)
    with mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
        print(json.dumps({'ready': True}), flush=True)
        timestamp = 0
        while True:
            header = sys.stdin.buffer.read(4)
            if len(header) != 4:
                return
            size = struct.unpack('<I', header)[0]
            if size != 480 * 270 * 3:
                raise ValueError('Invalid RGB frame size')
            data = sys.stdin.buffer.read(size)
            if len(data) != size:
                return
            pixels = np.frombuffer(data, dtype=np.uint8).reshape(270, 480, 3)
            timestamp = max(timestamp + 1, int(time.monotonic() * 1000))
            result = detector.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=pixels), timestamp)
            points = [[p.x, p.y] for p in result.hand_landmarks[0]] if result.hand_landmarks else []
            print(json.dumps({'points': points}), flush=True)


if __name__ == '__main__':
    main()
