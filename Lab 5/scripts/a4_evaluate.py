"""Compare exported models on recorded test captures without changing training data."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

import cv2
from a4_camera import Model, stamp

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--captures', required=True, help='Root containing test class/session folders')
parser.add_argument('--models', nargs='+', required=True, help='Folders with model.tflite and labels.txt')
parser.add_argument('--output', required=True)
args = parser.parse_args()
root = Path(args.captures)
receipts = sorted(root.glob('*/*/capture.json'))
if not receipts:
    raise ValueError('No test captures found')
samples = []
for receipt in receipts:
    capture = json.loads(receipt.read_text())
    if capture['split'] != 'test' or capture['status'] != 'complete':
        raise ValueError(f'Not a completed test capture: {receipt}')
    for frame in capture['frames']:
        path = receipt.parent / 'processed' / frame['file']
        image = cv2.imread(str(path))
        if image is None or image.shape != (224, 224, 3):
            raise ValueError(f'Invalid processed input: {path}')
        samples.append((image, dict(file=path.relative_to(root).as_posix(),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            expected=capture['label'], captured_utc=frame['utc'], crop=capture['crop'],
            session=receipt.parent.name)))

out = Path(args.output)
out.mkdir(parents=True, exist_ok=False)
for model_path in map(Path, args.models):
    model = Model(str(model_path/'model.tflite'), str(model_path/'labels.txt'))
    records = [dict(**meta, **model.predict(image)) for image, meta in samples]
    folder = out / model_path.name
    folder.mkdir()
    (folder/'predictions.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    counts = {}
    for label in model.labels:
        rows = [r for r in records if r['expected'] == label]
        counts[label] = dict(frames=len(rows),
            correct=sum(r['label'] == label for r in rows),
            predictions={name: sum(r['label'] == name for r in rows) for name in model.labels},
            top_score_min=min(r['score'] for r in rows) if rows else None,
            top_score_max=max(r['score'] for r in rows) if rows else None)
    summary = dict(evaluated_utc=stamp(), model=model_path.name,
        model_sha256=hashlib.sha256((model_path/'model.tflite').read_bytes()).hexdigest(),
        tensors=model.describe(), by_expected_class=counts,
        total_frames=len(records), correct_frames=sum(r['label']==r['expected'] for r in records),
        capture_sessions=len(receipts),
        median_invoke_seconds=statistics.median(r['invoke_seconds'] for r in records),
        note='Three short correlated test scenes, not a generalization accuracy estimate. '
             'Ground truth is the operator-selected scene label. Inputs were preprocessed during capture. '
             'Timing excludes image loading and preprocessing. The neutral scene repeats the training wallpaper.')
    (folder/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
