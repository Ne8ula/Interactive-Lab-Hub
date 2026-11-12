"""Score recorded predictions against manually reviewed, inclusive frame intervals."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    folder = args.folder
    with (folder / 'predictions.csv').open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    with (folder / 'annotations.csv').open(newline='', encoding='utf-8-sig') as f:
        intervals = list(csv.DictReader(f))
    assert [int(r['frame']) for r in rows] == list(range(len(rows))), 'Missing/duplicate frames'
    labels = ('WORK', 'VIDEO', 'NEUTRAL')
    expected = {}
    for interval in intervals:
        a, b = int(interval['start_frame']), int(interval['end_frame'])
        assert 0 <= a <= b < len(rows)
        for frame in range(a, b + 1):
            assert frame not in expected, 'Overlapping annotations'
            expected[frame] = (interval['expected'], interval['scene'])
    assert len(expected) == len(rows), 'Unannotated frames'
    matrix = {label: {pred: 0 for pred in labels} for label in labels}
    mistakes = []
    for row in rows:
        frame = int(row['frame'])
        truth, scene = expected[frame]
        assert row['prediction'] in labels
        row.update(expected=truth, scene=scene,
                   correct='' if truth == 'TRANSITION' else str(truth == row['prediction']))
        if truth in labels:
            matrix[truth][row['prediction']] += 1
            if truth != row['prediction']:
                mistakes.append(frame)
    scored = sum(sum(v.values()) for v in matrix.values())
    correct = sum(matrix[x][x] for x in labels)
    segments = []
    for interval in intervals:
        a, b = int(interval['start_frame']), int(interval['end_frame'])
        subset = rows[a:b+1]
        segments.append(dict(interval, frames=len(subset),
            video_start_seconds=float(subset[0]['video_seconds']),
            video_end_exclusive_seconds=round((b + 1) / 5, 3),
            prediction_counts=dict(Counter(r['prediction'] for r in subset)),
            correct=None if interval['expected'] == 'TRANSITION' else
                sum(r['prediction'] == interval['expected'] for r in subset),
            label_switches=sum(x['prediction'] != y['prediction'] for x, y in zip(subset, subset[1:]))))
    by_class = {x: dict(frames=sum(matrix[x].values()), correct=matrix[x][x],
                       recall=matrix[x][x]/sum(matrix[x].values())) for x in labels}
    switches = sum(x['prediction'] != y['prediction'] for x, y in zip(rows, rows[1:]))
    same_truth_switches = sum(x['prediction'] != y['prediction'] and
        x['expected'] == y['expected'] and x['expected'] != 'TRANSITION'
        for x, y in zip(rows, rows[1:]))
    result = dict(total_frames=len(rows), scored_frames=scored, excluded_transition_frames=len(rows)-scored,
        correct=correct, accuracy=correct/scored, confusion_matrix=matrix, by_class=by_class,
        all_prediction_counts=dict(Counter(r['prediction'] for r in rows)),
        total_label_switches=switches, same_expected_class_label_switches=same_truth_switches,
        wrong_frames=mistakes, wrong_at_score_ge_95=sum(float(rows[i]['score_percent']) >= 95 for i in mistakes),
        segments=segments,
        source_sha256={name:hashlib.sha256((folder/name).read_bytes()).hexdigest()
                       for name in ('predictions.csv','annotations.csv')},
        method='Manual interval labels: camera-only images reviewed every 5 frames (1 second), with every frame inspected around identified class boundaries. Class labels interpolated within continuous scenes. White documents were labeled WORK and wallpaper with a small terminal was labeled NEUTRAL. Predictions were not used to choose labels. Frame-weighted descriptive results for this one correlated recording; no generalization estimate.')
    (folder/'summary.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    with (folder/'scored-predictions.csv').open('w', newline='', encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({k:v for k,v in result.items() if k not in ('segments','wrong_frames')},indent=2))


if __name__ == '__main__':
    main()
