"""Package completed Pi captures for direct Teachable Machine class uploads.

Keeps raw captures untouched; writes class ZIPs of already processed PNGs and
a provenance manifest. Use a new output folder for each dataset revision.
"""
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', required=True, help='Capture root containing train/')
parser.add_argument('--output', required=True)
args = parser.parse_args()
source, output = Path(args.source), Path(args.output)
receipts = sorted((source / 'train').glob('*/*/capture.json'))
if not receipts:
    raise ValueError('No training capture receipts found')
captures = []
for path in receipts:
    record = json.loads(path.read_text(encoding='utf-8'))
    if record['status'] != 'complete' or record['split'] != 'train':
        raise ValueError(f'Incomplete or non-training capture: {path}')
    if len(record['frames']) != record['frame_count']:
        raise ValueError(f'Frame count mismatch: {path}')
    if record['label'] not in ('WORK', 'VIDEO', 'NEUTRAL'):
        raise ValueError(f'Unknown class: {path}')
    for frame in record['frames']:
        if not (path.parent / 'processed' / frame['file']).is_file():
            raise ValueError(f'Missing frame: {path} {frame}')
    captures.append((path, record))
if {r['label'] for _, r in captures} != {'WORK', 'VIDEO', 'NEUTRAL'}:
    raise ValueError('All three classes must have completed captures')
if len({r['crop'] for _, r in captures}) != 1:
    raise ValueError('Capture crops differ')

output.mkdir(parents=True, exist_ok=False)
manifest = dict(camera='Pi-connected USB webcam, /dev/video0',
                crop=captures[0][1]['crop'],
                preprocessing=captures[0][1]['preprocessing'],
                counts={}, independent_test_images=0,
                note='Adjacent frames are correlated; counts do not measure diversity or accuracy.',
                sessions=[], images=[])
for label in ('WORK', 'VIDEO', 'NEUTRAL'):
    folder = output / label
    folder.mkdir()
    count = 0
    with zipfile.ZipFile(output / (label + '.zip'), 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, record in captures:
            if record['label'] != label:
                continue
            manifest['sessions'].append(dict(session=path.parent.name,
                label=label, frames=record['frame_count'],
                started_utc=record['started_utc'], finished_utc=record['finished_utc']))
            for frame in record['frames']:
                original = path.parent / 'processed' / frame['file']
                name = f'{label.lower()}-{count:04d}.png'
                target = folder / name
                shutil.copyfile(original, target)
                archive.write(target, name)
                manifest['images'].append(dict(file=f'{label}/{name}',
                    source=str(original.relative_to(source)).replace('\\', '/'),
                    sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
                count += 1
    manifest['counts'][label] = count
(output / 'dataset.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(manifest['counts']))
