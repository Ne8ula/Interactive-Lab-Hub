# A4 Kiyo baseline v1

Trained and exported from Teachable Machine on 2026-11-10. This is the first
custom model, before retraining for the Pi webcam's actual shelf position.

| Field | Verified value |
|---|---|
| Model | `model.tflite`, 793176 bytes |
| Export | TensorFlow Lite, Quantized |
| Labels in output order | 0 WORK; 1 VIDEO; 2 NEUTRAL |
| Browser sample counts | 156 WORK; 160 VIDEO; 160 NEUTRAL |
| Training camera | Razer Kiyo V2, optical recordings |
| Prepared training images | 640×480 source; crop `600:340:20:65`; FFmpeg aspect-fit and black padding to 224×224 |
| Independent test samples | None in this training dataset |
| Input | `[1,224,224,3]`, uint8 RGB; scale 0.007843137718737125, zero point 127 |
| Output | uint8; scale 0.00390625, zero point 0 |
| Pi environment | Python 3.11 venv; tflite-runtime 2.14.0; NumPy 1.26.4; opencv-python 4.11.0.86 |

Model SHA-256:
`c6f5bb6820df847393111e9923dd1f5c969faab0859b57bde1a580cca869c44a`

Labels SHA-256:
`47e8d70e3cbadcb0e451c76ddf7a5a0a448dea7f9ca5475b5cb35bb9e43db59b`

The initial Pi diagnostic used the full 640×480 image, OpenCV INTER_AREA
aspect-fit resizing and black padding, then BGR-to-RGB conversion. The model
accepts RGB bytes directly; output scores are dequantized with the recorded
scale and zero point. Scores are not calibrated correctness probabilities.

[Actual Pi result and limitations](../../README.md#a4-teachable-machine).
