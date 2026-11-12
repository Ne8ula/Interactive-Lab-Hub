"""Deterministic controller/player checks; no camera or speaker access."""
import sys
import csv
import io
import json
import signal
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from b1_shelf_watcher import AudioOutput, Controller, parse_args, run


class ControllerTests(unittest.TestCase):
    def test_zero_cooldown_repeats_only_after_playback(self):
        controller=Controller(persistence=5,cooldown=0)
        for now in range(5):
            self.assertFalse(controller.observe(now,'VIDEO',.99)['due'])
        self.assertTrue(controller.observe(5,'VIDEO',.99)['due'])
        controller.mark_started(5)
        self.assertFalse(controller.observe(6,'VIDEO',.99,busy=True)['due'])
        self.assertTrue(controller.observe(6.2,'VIDEO',.99,busy=False)['due'])
        self.assertFalse(controller.observe(7,'WORK',.99)['due'])
        for now in range(8,13):
            self.assertFalse(controller.observe(now,'VIDEO',.99)['due'])
        self.assertTrue(controller.observe(13,'VIDEO',.99)['due'])

    def test_persistence_and_cooldown(self):
        controller=Controller()
        for now in range(15):
            self.assertFalse(controller.observe(now,'VIDEO',.99)['due'])
        self.assertTrue(controller.observe(15,'VIDEO',.99)['due'])
        controller.mark_started(15)
        for now in range(16,75):
            self.assertFalse(controller.observe(now,'VIDEO',.99)['due'])
        self.assertTrue(controller.observe(75,'VIDEO',.99)['due'])

    def test_nonvideo_uncertainty_and_nan_reset_timer(self):
        for label,score in [('WORK',.99),('NEUTRAL',.99),('VIDEO',.5),('VIDEO',float('nan'))]:
            controller=Controller()
            for now in range(15):
                controller.observe(now,'VIDEO',.99)
            self.assertFalse(controller.observe(15,label,score)['due'])
            for now in range(16,31):
                self.assertFalse(controller.observe(now,'VIDEO',.99)['due'])
            self.assertTrue(controller.observe(31,'VIDEO',.99)['due'])

    def test_camera_gap_and_busy_output(self):
        controller=Controller()
        for now in range(15):
            controller.observe(now,'VIDEO',.99)
        self.assertEqual(controller.observe(20,'VIDEO',.99)['video_seconds'],0)
        for now in range(21,35):
            controller.observe(now,'VIDEO',.99)
        self.assertFalse(controller.observe(35,'VIDEO',.99,busy=True)['due'])
        self.assertTrue(controller.observe(36,'VIDEO',.99,busy=False)['due'])

    def test_new_video_streak_does_not_cancel_cooldown(self):
        controller=Controller()
        controller.mark_started(0)
        controller.observe(1,'WORK',.99)
        for now in range(2,60):
            self.assertFalse(controller.observe(now,'VIDEO',.99)['due'])
        self.assertTrue(controller.observe(60,'VIDEO',.99)['due'])


class ArgumentTests(unittest.TestCase):
    def test_beep_defaults_and_voice_defaults(self):
        beep=parse_args(['--mode','beep'])
        self.assertEqual((beep.persistence,beep.cooldown),(5,0))
        voice=parse_args(['--mode','voice'])
        self.assertEqual((voice.persistence,voice.cooldown),(15,60))

    def test_explicit_zero_cooldown_is_accepted(self):
        args=parse_args(['--mode','voice','--persistence','5','--cooldown','0'])
        self.assertEqual((args.persistence,args.cooldown),(5,0))

    @patch('sys.stderr')
    def test_negative_cooldown_is_rejected(self,stderr):
        with self.assertRaises(SystemExit):
            parse_args(['--cooldown','-1'])


class RecordingTests(unittest.TestCase):
    def test_stop_during_video_write_finishes_csv_row_and_logs_face(self):
        # Simulated devices: interrupt exactly between MP4 write and CSV write.
        # No Pi/camera/display result is claimed by this regression check.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            model_file=root/'model.tflite'; model_file.write_bytes(b'test model')
            args=parse_args(['--model',str(model_file),'--output',str(root/'runs'),
                             '--start-delay','0','--display','mini-pitft'])
            frame=Mock(); frame.shape=(480,640,3)
            cv=Mock(); cv.VideoCapture.return_value.read.return_value=(True,frame)
            cv.VideoCapture.return_value.isOpened.return_value=True
            writer=cv.VideoWriter.return_value
            writer.isOpened.return_value=True
            writer.write.side_effect=lambda image: signal.getsignal(signal.SIGINT)(signal.SIGINT,None)
            camera_module=Mock()
            camera_module.Model.return_value.describe.return_value={}
            camera_module.Model.return_value.predict.return_value={'label':'WORK','score':.99}
            face_module=Mock()
            face_module.face_for_prediction.return_value='happy'
            display=face_module.MiniPitft.return_value
            display.current='uncertain'; display.show.return_value=True
            output=Mock(); output.player='mock'; output.clips=[]
            output.busy=False; output.current=None; output.poll.return_value=None
            old_handler=signal.getsignal(signal.SIGINT)
            with patch.dict(sys.modules,{'cv2':cv,'a4_camera':camera_module,'b1_display':face_module}), \
                 patch('b1_shelf_watcher.time.sleep'), redirect_stdout(io.StringIO()):
                run(args,output)
            saved=next((root/'runs').iterdir())
            with (saved/'predictions.csv').open(newline='') as f:
                rows=list(csv.DictReader(f))
            meta=json.loads((saved/'metadata.json').read_text())
            events=[json.loads(x) for x in (saved/'events.jsonl').read_text().splitlines()]
            self.assertEqual(writer.write.call_count,len(rows))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['display_face'],'happy')
            self.assertEqual(meta['frames'],1)
            self.assertEqual(meta['status'],'stopped_by_user')
            self.assertEqual(events[-1]['event'],'run_stopped_by_user')
            display.close.assert_called_once()
            self.assertIs(signal.getsignal(signal.SIGINT),old_handler)


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clips=[Path(self.temp.name)/f'{i}.wav' for i in (1,2,3)]
        for path in self.clips:
            path.touch()

    @patch('b1_shelf_watcher.subprocess.Popen')
    def test_sequence_wraps_without_overlap(self,popen):
        process=Mock()
        popen.return_value=process
        output=AudioOutput(self.clips,player='test-player')
        for name in ['1.wav','2.wav','3.wav','1.wav']:
            process.poll.return_value=None
            self.assertEqual(output.start(),name)
            self.assertIsNone(output.poll())
            with self.assertRaises(RuntimeError):
                output.start()
            process.poll.return_value=0
            self.assertEqual(output.poll(),name)
            self.assertFalse(output.busy)
        self.assertEqual(popen.call_count,4)

    @patch('b1_shelf_watcher.subprocess.Popen')
    def test_failed_playback_does_not_advance(self,popen):
        popen.return_value.poll.return_value=1
        output=AudioOutput(self.clips,player='test-player')
        output.start()
        with self.assertRaisesRegex(RuntimeError,'Audio player failed'):
            output.poll()
        self.assertEqual(output.index,0)
        self.assertFalse(output.busy)


if __name__=='__main__':
    unittest.main()
