"""Display decisions tested locally; these tests do not access Pi hardware."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from b1_display import face_for_prediction


class FaceSelectionTests(unittest.TestCase):
    def test_three_requested_class_expressions(self):
        self.assertEqual(face_for_prediction('WORK',.99),'happy')
        self.assertEqual(face_for_prediction('VIDEO',.99),'angry')
        self.assertEqual(face_for_prediction('NEUTRAL',.99),'asleep')

    def test_low_confidence_is_not_mislabeled_as_neutral(self):
        self.assertEqual(face_for_prediction('VIDEO',.84),'uncertain')
        self.assertEqual(face_for_prediction('WORK',.85),'happy')
        self.assertEqual(face_for_prediction('NEUTRAL',float('nan')),'uncertain')
        self.assertEqual(face_for_prediction('unknown',.99),'uncertain')


if __name__=='__main__':
    unittest.main()
