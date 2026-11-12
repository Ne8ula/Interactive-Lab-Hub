"""Show actual Pi inference on saved webcam frames; this display is not a live feed."""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
from a4_camera import Model

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--model-dir', required=True)
parser.add_argument('--test-root', required=True)
parser.add_argument('--failure-image', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--seconds', type=float, default=180)
args = parser.parse_args()
model_dir = Path(args.model_dir)
model = Model(str(model_dir/'model.tflite'), str(model_dir/'labels.txt'))
cases = []
for label in ('WORK', 'VIDEO', 'NEUTRAL'):
    paths = sorted((Path(args.test_root)/label).glob('*/processed/0005.png'))
    if len(paths) != 1:
        raise ValueError(f'Expected exactly one test session for {label}')
    cases.append((label, 'Test capture', paths[0]))
cases.append(('WORK', 'Live-run failure', Path(args.failure_image)))
canvas = np.full((405, 976, 3), 245, np.uint8)
cv2.putText(canvas, 'A4 model 2 - inference on recorded Pi webcam frames',
            (12, 27), cv2.FONT_HERSHEY_SIMPLEX, .63, (30,30,30), 1, cv2.LINE_AA)
cv2.putText(canvas, 'Saved inputs, recomputed on Pi; this window does not use the camera.',
            (12, 52), cv2.FONT_HERSHEY_SIMPLEX, .5, (60,60,60), 1, cv2.LINE_AA)
records = []
for i, (expected, origin, path) in enumerate(cases):
    image = cv2.imread(str(path))
    if image is None or image.shape != (224,224,3):
        raise ValueError(f'Invalid image: {path}')
    result = model.predict(image)
    records.append(dict(expected=expected, source=origin, file=str(path), **result))
    x = 12 + 244*i
    canvas[88:312, x:x+224] = image
    color = (45,110,20) if result['label']==expected else (30,30,190)
    for text, y, shade in [(origin,77,(40,40,40)), (f'Expected: {expected}',337,(40,40,40)),
                            (f"{result['label']} {result['score']*100:.2f}%",361,color)]:
        cv2.putText(canvas,text,(x,y),cv2.FONT_HERSHEY_SIMPLEX,.5,shade,1,cv2.LINE_AA)
cv2.putText(canvas, 'Scores are model outputs, not guarantees of correctness.',
            (12,391),cv2.FONT_HERSHEY_SIMPLEX,.5,(60,60,60),1,cv2.LINE_AA)
out=Path(args.output)
out.mkdir(parents=True,exist_ok=True)
if not cv2.imwrite(str(out/'pi-result-panel.png'),canvas):
    raise RuntimeError('Failed to save result panel')
(out/'pi-result-panel.json').write_text(json.dumps(records,indent=2))
print(json.dumps(records),flush=True)
cv2.imshow('A4 model 2 - recorded Pi webcam results',canvas)
until = time.monotonic() + args.seconds
while time.monotonic() < until:
    if cv2.waitKey(100) & 255 == ord('q'):
        break
cv2.destroyAllWindows()
