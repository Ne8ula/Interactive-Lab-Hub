"""A4 optical sample capture and TFLite diagnostics; not the Part B robot.

Capture and inference share crop/resize/padding. Raw camera images stay beside
processed samples for auditing. A dataset split is an operator choice, not proof
of independence. Use separate scenes/sessions for evaluation.
"""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np


def stamp():
    return datetime.now(timezone.utc).isoformat()


def prepare(frame, crop):
    height, width = frame.shape[:2]
    if crop:
        w, h, x, y = map(int, crop.split(':'))
        if min(w, h) <= 0 or min(x, y) < 0 or x+w > width or y+h > height:
            raise ValueError(f'Crop {crop} outside {width}x{height}')
        frame = frame[y:y+h, x:x+w]
    height, width = frame.shape[:2]
    scale = min(224 / width, 224 / height)
    w, h = max(1, int(width*scale)), max(1, int(height*scale))
    resized = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
    result = np.zeros((224, 224, 3), np.uint8)
    x, y = (224-w)//2, (224-h)//2
    result[y:y+h, x:x+w] = resized
    return result


def save_image(path, image):
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f'Failed to save {path}')


def open_camera(args):
    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f'Cannot open camera {args.camera}')
    return cap


def capture(args):
    session = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = Path(args.output) / args.split / args.label / (session+'-'+args.scene)
    raw, processed = folder / 'raw', folder / 'processed'
    raw.mkdir(parents=True)
    processed.mkdir()
    receipt = dict(status='started', started_utc=stamp(), label=args.label,
                   split=args.split, scene=args.scene, crop=args.crop,
                   camera_index=args.camera, requested_size=[args.width,args.height],
                   requested_seconds=args.seconds, requested_samples_per_second=args.fps,
                   preprocessing='BGR camera; crop; aspect-fit INTER_AREA; black pad 224x224; PNG',
                   frames=[], note='Optical captures; adjacent frames are correlated.')
    cap = None
    try:
        cap = open_camera(args)
        start = time.monotonic()
        next_save = start
        while time.monotonic()-start < args.seconds:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError('Camera read failed')
            now = time.monotonic()
            if now < next_save:
                continue
            image = prepare(frame, args.crop)
            index = len(receipt['frames'])
            filename = f'{index:04d}.png'
            save_image(raw / filename, frame)
            save_image(processed / filename, image)
            receipt['actual_size'] = [frame.shape[1],frame.shape[0]]
            receipt['frames'].append(dict(file=filename, utc=stamp(), elapsed=now-start))
            print(f'{args.label} {index+1} {folder}', flush=True)
            next_save = now + 1/args.fps
            if args.preview:
                cv2.imshow('A4 processed capture',image)
                if cv2.waitKey(1) & 255 == 27:
                    break
        receipt['status'] = 'complete'
    except BaseException as error:
        receipt['status'] = 'failed'
        receipt['error'] = str(error)
        raise
    finally:
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        receipt['finished_utc'] = stamp()
        receipt['frame_count'] = len(receipt['frames'])
        (folder/'capture.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')


class Model:
    def __init__(self, model, labels):
        from tflite_runtime.interpreter import Interpreter
        self.engine = Interpreter(model_path=model)
        self.engine.allocate_tensors()
        self.input = self.engine.get_input_details()[0]
        self.output = self.engine.get_output_details()[0]
        self.labels = [re.sub(r'^\d+\s+', '', s.strip()) for s in
                       Path(labels).read_text(encoding='utf-8-sig').splitlines() if s.strip()]
        if list(self.input['shape']) != [1,224,224,3]:
            raise ValueError(f"Unsupported input shape: {self.input['shape']}")
        if int(np.prod(self.output['shape'])) != len(self.labels):
            raise ValueError('Model output count and label count differ')

    def describe(self):
        return dict(labels=self.labels,
                    input_shape=self.input['shape'].tolist(),
                    input_dtype=str(self.input['dtype']),
                    input_quantization=self.input['quantization'],
                    output_dtype=str(self.output['dtype']),
                    output_quantization=self.output['quantization'])

    def predict(self, image):
        rgb = cv2.cvtColor(image,cv2.COLOR_BGR2RGB)
        dtype = self.input['dtype']
        if dtype == np.uint8:
            # Teachable Machine Quantized image export accepts RGB bytes.
            pixels = rgb
        elif dtype == np.float32:
            pixels = rgb.astype(np.float32)/127.5-1.0
        else:
            raise ValueError(f'Unverified input type {dtype}; inspect export first')
        self.engine.set_tensor(self.input['index'], pixels[None])
        start = time.perf_counter()
        self.engine.invoke()
        elapsed = time.perf_counter()-start
        scores = self.engine.get_tensor(self.output['index']).reshape(-1)
        if np.issubdtype(scores.dtype,np.integer):
            scale, zero = self.output['quantization']
            if scale <= 0:
                raise ValueError('Missing output quantization scale')
            scores = (scores.astype(np.float32)-zero)*scale
        index = int(np.argmax(scores))
        return dict(label=self.labels[index],score=float(scores[index]),
                    scores=dict(zip(self.labels,map(float,scores))),invoke_seconds=elapsed)


def run(args):
    model = Model(args.model,args.labels)
    out = Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    session = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    metadata = dict(utc=stamp(),model_sha256=hashlib.sha256(Path(args.model).read_bytes()).hexdigest(),
                    crop=args.crop,model=model.describe(), mode=args.mode,
                    note='invoke_seconds excludes capture, preprocessing, file I/O and display.')
    (out/(session+'-metadata.json')).write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps(metadata),flush=True)
    cap = None
    try:
        with (out/(session+'-predictions.jsonl')).open('w',encoding='utf-8') as log:
            if args.mode == 'images':
                files = sorted(p for p in Path(args.images).rglob('*')
                               if p.suffix.lower() in ('.png','.jpg','.jpeg'))
                if not files:
                    raise ValueError('No images found')
                for path in files:
                    image = cv2.imread(str(path))
                    if image is None or image.shape[:2] != (224,224):
                        raise ValueError(f'Expected already processed 224x224 image: {path}')
                    result = dict(utc=stamp(),file=str(path),**model.predict(image))
                    log.write(json.dumps(result)+'\n')
                    print(json.dumps(result),flush=True)
            else:
                cap = open_camera(args)
                start, next_sample = time.monotonic(), 0
                count = 0
                while time.monotonic()-start < args.seconds:
                    ok, raw = cap.read()
                    if not ok:
                        raise RuntimeError('Camera read failed')
                    now = time.monotonic()
                    if now < next_sample:
                        continue
                    image = prepare(raw,args.crop)
                    result = dict(utc=stamp(),elapsed=now-start,**model.predict(image))
                    log.write(json.dumps(result)+'\n')
                    log.flush()
                    print(json.dumps(result),flush=True)
                    save_image(out/'latest-raw.png',raw)
                    save_image(out/'latest-input.png',image)
                    if count % 10 == 0:
                        save_image(out/f'{session}-{count:04d}.png',image)
                    count += 1
                    next_sample = time.monotonic()+1/args.fps
                    if args.preview:
                        view = raw.copy()
                        cv2.putText(view,f"{result['label']} {result['score']:.3f}",
                                    (10,30),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,255,0),2)
                        cv2.imshow('A4 live classifier',view)
                        cv2.imshow('A4 processed model input',image)
                        if cv2.waitKey(1) & 255 == 27:
                            break
    finally:
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['capture','live','images'])
    parser.add_argument('--camera',type=int,default=0)
    parser.add_argument('--width',type=int,default=640)
    parser.add_argument('--height',type=int,default=480)
    parser.add_argument('--crop',default='',help='w:h:x:y; empty uses full frame')
    parser.add_argument('--seconds',type=float,default=10)
    parser.add_argument('--fps',type=float,default=2)
    parser.add_argument('--output',required=True)
    parser.add_argument('--label',choices=['WORK','VIDEO','NEUTRAL'])
    parser.add_argument('--split',choices=['train','test','calibration'],default='calibration')
    parser.add_argument('--scene',default='scene')
    parser.add_argument('--model',default='model.tflite')
    parser.add_argument('--labels',default='labels.txt')
    parser.add_argument('--images')
    parser.add_argument('--preview',action='store_true')
    args = parser.parse_args()
    if args.seconds <= 0 or args.fps <= 0:
        parser.error('seconds and fps must be positive')
    if args.mode == 'capture' and not args.label:
        parser.error('capture requires --label')
    if args.mode == 'images' and not args.images:
        parser.error('images requires --images')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.scene):
        parser.error('scene must contain only letters, numbers, underscores or hyphens')
    capture(args) if args.mode == 'capture' else run(args)


if __name__ == '__main__':
    main()
