"""Part B: live Pi classifier with beep or sequential voice reminders."""
import argparse
import csv
import hashlib
import json
import math
import shutil
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def utc():
    return datetime.now(timezone.utc).isoformat()


class Controller:
    def __init__(self, persistence=15, cooldown=60, threshold=.85, max_gap=3):
        self.persistence, self.cooldown = persistence, cooldown
        self.threshold, self.max_gap = threshold, max_gap
        self.video_since = self.last_frame = self.last_reminder = None

    def observe(self, now, label, score, busy=False):
        if self.last_frame is not None and now - self.last_frame > self.max_gap:
            self.video_since = None
        self.last_frame = now
        confident_video = label == 'VIDEO' and math.isfinite(score) and score >= self.threshold
        if not confident_video:
            self.video_since = None
        elif self.video_since is None:
            self.video_since = now
        held = 0 if self.video_since is None else now - self.video_since
        remaining = 0 if self.last_reminder is None else max(0, self.cooldown - (now-self.last_reminder))
        return dict(video_seconds=held, cooldown_seconds=remaining,
                    due=confident_video and held >= self.persistence and remaining == 0 and not busy)

    def mark_started(self, now):
        self.last_reminder = now


class AudioOutput:
    def __init__(self, clips, player=None):
        self.clips = [Path(p) for p in clips]
        if not self.clips or any(not p.is_file() for p in self.clips):
            raise RuntimeError('Missing audio files; transfer assets/audio first.')
        self.player = player or shutil.which('paplay') or shutil.which('pw-play')
        if not self.player:
            raise RuntimeError('Need paplay or pw-play for the Bluetooth/default desktop audio output.')
        self.index = 0
        self.process = None
        self.current = None

    @property
    def busy(self):
        return self.process is not None

    def start(self):
        if self.busy:
            raise RuntimeError('Audio is already playing')
        clip = self.clips[self.index]
        self.process = subprocess.Popen([self.player, str(clip)])
        self.current = clip
        return clip.name

    def poll(self):
        if self.process is None:
            return None
        code = self.process.poll()
        if code is None:
            return None
        name = self.current.name
        self.process = self.current = None
        if code:
            raise RuntimeError(f'Audio player failed for {name}: exit {code}. Check Bluetooth output.')
        self.index = (self.index + 1) % len(self.clips)
        return name

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process = self.current = None


def audio_test(output):
    try:
        for _ in range(len(output.clips)):
            print('Playing:', output.start(), flush=True)
            while output.busy:
                output.poll()
                time.sleep(.05)
            time.sleep(.5)
    finally:
        output.close()
    print('Playback commands completed. Confirm you heard them on the Leviathan V2.')


def run(args, output):
    import cv2 as cv
    from a4_camera import Model, prepare

    model = Model(str(args.model), str(args.labels))
    run_dir = args.output / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-' + args.mode)
    run_dir.mkdir(parents=True, exist_ok=False)
    settings = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    metadata = dict(started_utc=utc(), settings=settings, model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
                    tensors=model.describe(), player=output.player,
                    audio_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.clips},
                    video_note='Silent camera MP4. Phone recording with microphone is needed to demonstrate audible output.',
                    timing_note='MP4 is constant FPS; CSV elapsed_seconds and capture_utc preserve actual capture timing.',
                    status='starting')
    cap = video = display = None
    previous_sigint = None
    stop_requested = False

    def request_stop(signum, frame):
        nonlocal stop_requested
        stop_requested = True

    frame_number = 0
    controller = Controller(args.persistence, args.cooldown, args.threshold, args.max_gap)
    print('Saving to:', run_dir, flush=True)
    try:
        if args.display == 'mini-pitft':
            from b1_display import MiniPitft, face_for_prediction
            display = MiniPitft(args.display_rotation)
        cap = cv.VideoCapture(args.camera)
        cap.set(cv.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            raise RuntimeError('Cannot open Pi webcam. Close other camera scripts.')
        print(f'Starts in {args.start_delay:g}s. Minimize SSH/VNC and show your test scene.', flush=True)
        time.sleep(args.start_delay)
        # Discard frames buffered while the user switches away from the terminal.
        for _ in range(5):
            cap.grab()
        start = time.monotonic()
        metadata['capture_started_utc'] = utc()
        previous_sigint = signal.signal(signal.SIGINT, request_stop)
        with (run_dir/'predictions.csv').open('w', newline='') as log, (run_dir/'events.jsonl').open('w') as events:
            writer = csv.writer(log)
            writer.writerow(['frame','video_seconds','capture_utc','elapsed_seconds','prediction','score_percent',
                             'video_held_seconds','cooldown_remaining_seconds','audio_active','action_started','display_face'])

            def event(kind, **details):
                record = dict(utc=utc(), elapsed_seconds=time.monotonic()-start, event=kind, **details)
                events.write(json.dumps(record)+'\n')
                events.flush()
                print(json.dumps(record), flush=True)

            event('run_started', mode=args.mode)
            if display:
                event('display_changed', face=display.current)
            while not stop_requested and time.monotonic()-start < args.seconds:
                loop_start = time.monotonic()
                finished = output.poll()
                if finished:
                    event('audio_completed', clip=finished)
                ok, frame = cap.read()
                captured, captured_at = utc(), time.monotonic()
                if not ok:
                    event('camera_error')
                    raise RuntimeError('Camera stopped returning frames')
                if frame.shape[:2] != (480,640):
                    raise RuntimeError(f'Unexpected camera size: {frame.shape}')
                result = model.predict(prepare(frame, '640:400:0:0'))
                now = time.monotonic()
                face = ''
                if display:
                    face = face_for_prediction(result['label'], result['score'], args.threshold)
                    if now-captured_at > args.max_gap:
                        face = 'uncertain'
                    if display.show(face):
                        event('display_changed',face=face,trigger_frame=frame_number,prediction=result['label'])
                state = controller.observe(captured_at, result['label'], result['score'], output.busy)
                action = ''
                if state['due'] and now-captured_at <= args.max_gap:
                    action = output.start()
                    controller.mark_started(now)
                    state['cooldown_seconds'] = args.cooldown
                    event('audio_started', clip=action, trigger_frame=frame_number)
                active = output.current.name if output.current else ''
                elapsed = captured_at-start
                recorded = cv.copyMakeBorder(frame,0,96,0,0,cv.BORDER_CONSTANT,value=(0,0,0))
                lines = [f"Frame {frame_number} | {elapsed:.2f}s | {args.mode} | Face: {face or 'off'}",
                         f"{result['label']} {result['score']*100:.2f}% | VIDEO held {state['video_seconds']:.1f}s",
                         f"Cooldown {state['cooldown_seconds']:.1f}s | Audio: {active or 'quiet'}"]
                for i, line in enumerate(lines):
                    cv.putText(recorded,line,(10,505+29*i),cv.FONT_HERSHEY_SIMPLEX,.52,(255,255,255),1,cv.LINE_AA)
                if video is None:
                    video=cv.VideoWriter(str(run_dir/'camera.mp4'),cv.VideoWriter_fourcc(*'mp4v'),args.fps,(640,576))
                    if not video.isOpened():
                        raise RuntimeError('Could not create MP4')
                video.write(recorded)
                writer.writerow([frame_number,f'{frame_number/args.fps:.3f}',captured,f'{elapsed:.3f}',
                                 result['label'],f"{result['score']*100:.4f}",f"{state['video_seconds']:.3f}",
                                 f"{state['cooldown_seconds']:.3f}",active,action,face])
                log.flush()
                frame_number += 1
                time.sleep(max(0,1/args.fps-(time.monotonic()-loop_start)))
            # Let a final short reminder complete before recording the end event.
            deadline = time.monotonic()+10
            while not stop_requested and output.busy and time.monotonic()<deadline:
                finished=output.poll()
                if finished:
                    event('audio_completed',clip=finished)
                time.sleep(.05)
            if stop_requested:
                if output.busy:
                    event('audio_interrupted',clip=output.current.name,reason='user_stop')
                    output.close()
                event('run_stopped_by_user',frames=frame_number)
            elif output.busy:
                raise RuntimeError('Audio player did not finish within 10 seconds')
            else:
                event('run_completed',frames=frame_number)
        metadata['status']='stopped_by_user' if stop_requested else 'complete'
    except KeyboardInterrupt:
        metadata['status']='stopped_by_user'
        print('\nStopped by you.',flush=True)
    except Exception as error:
        metadata.update(status='failed',error=str(error))
        if display:
            try:
                display.show('error')
            except Exception:
                pass
        raise
    finally:
        if previous_sigint is not None:
            signal.signal(signal.SIGINT, previous_sigint)
        output.close()
        if cap is not None:
            cap.release()
        if video is not None:
            video.release()
        if display is not None:
            display.close()
        metadata.update(finished_utc=utc(),frames=frame_number)
        (run_dir/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
        print('Saved:',run_dir,flush=True)


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['beep','voice'],default='voice')
    parser.add_argument('--audio-test',action='store_true')
    parser.add_argument('--display',choices=['none','mini-pitft'],default='none')
    parser.add_argument('--display-rotation',type=int,choices=[90,270],default=90)
    parser.add_argument('--model',type=Path,default=ROOT/'models/a4-pi-v2/model.tflite')
    parser.add_argument('--labels',type=Path,default=ROOT/'models/a4-pi-v2/labels.txt')
    parser.add_argument('--audio-dir',type=Path,default=ROOT/'assets/audio')
    parser.add_argument('--output',type=Path,default=ROOT/'runs/part-b')
    parser.add_argument('--camera',type=int,default=0)
    parser.add_argument('--seconds',type=float,default=180)
    parser.add_argument('--fps',type=float,default=5)
    parser.add_argument('--start-delay',type=float,default=10)
    parser.add_argument('--persistence',type=float,help='VIDEO duration: beep defaults to 5s; voice to 15s')
    parser.add_argument('--cooldown',type=float,help='Seconds between reminders: beep defaults to 0; voice to 60')
    parser.add_argument('--threshold',type=float,default=.85)
    parser.add_argument('--max-gap',type=float,default=3)
    args=parser.parse_args(argv)
    if args.persistence is None:
        args.persistence = 5 if args.mode == 'beep' else 15
    if args.cooldown is None:
        args.cooldown = 0 if args.mode == 'beep' else 60
    if any(not math.isfinite(v) or v<=0 for v in [args.seconds,args.fps,args.persistence,args.max_gap]):
        parser.error('Duration, FPS, persistence, and max-gap must be positive and finite.')
    if not math.isfinite(args.cooldown) or args.cooldown < 0:
        parser.error('Cooldown must be finite and nonnegative; 0 disables cooldown.')
    if not math.isfinite(args.start_delay) or args.start_delay<0 or not 0<=args.threshold<=1:
        parser.error('Invalid start delay or threshold.')
    return args


def main():
    args = parse_args()
    clips=[args.audio_dir/'beep.wav'] if args.mode=='beep' else [args.audio_dir/f'reminder-{i:02d}.wav' for i in (1,2,3)]
    output=AudioOutput(clips)
    if args.audio_test:
        audio_test(output)
    else:
        run(args,output)


if __name__=='__main__':
    main()
