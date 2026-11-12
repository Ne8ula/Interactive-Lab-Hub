"""Capture one unlabeled Pi-webcam calibration image without opening a GUI."""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True)
parser.add_argument('--camera', type=int, default=0)
parser.add_argument('--preview', action='store_true')
parser.add_argument('--seconds', type=float, default=600,
                    help='Maximum live preview duration; Escape closes early')
args = parser.parse_args()
out = Path(args.output)
out.mkdir(parents=True, exist_ok=True)
cap = cv2.VideoCapture(args.camera)
try:
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        raise RuntimeError('Camera could not be opened')
    for _ in range(30):
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError('Camera read failed')
    if args.preview:
        start = time.monotonic()
        while time.monotonic() - start < args.seconds:
            cv2.imshow('Pi USB webcam - position camera - ESC to finish', frame)
            if cv2.waitKey(30) & 255 == 27:
                break
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError('Camera read failed')
    if not cv2.imwrite(str(out / 'calibration.png'), frame):
        raise RuntimeError('Could not save calibration image')
    receipt = dict(utc=datetime.now(timezone.utc).isoformat(),
                   camera_index=args.camera, size=[frame.shape[1], frame.shape[0]],
                   label=None, purpose='Unlabeled optical framing check')
    (out / 'calibration.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))
finally:
    cap.release()
    cv2.destroyAllWindows()
