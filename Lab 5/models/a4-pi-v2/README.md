# A4 model 2: Pi shelf camera

Trained/exported 2026-11-10 with Teachable Machine Standard image / TensorFlow
Lite Quantized. Actual training counts: **184 WORK, 163 VIDEO, 200 NEUTRAL**.
The separate Kiyo baseline is retained in [a4-kiyo-v1](../a4-kiyo-v1/README.md).

- [model.tflite](model.tflite): 793,176 bytes; SHA-256
  `aa7bf8402ce755014114dbbc298ee6f3b08e404507235dde72af2735c6f3a513`.
- [labels.txt](labels.txt): `0 WORK`, `1 VIDEO`, `2 NEUTRAL`.
- Pi deployment: `/home/ne8ula/a4-shelf-watcher/a4-pi-v2/`.
- Camera: USB webcam attached to Pi, index 0, actual 640 x 480 capture.
- Preprocessing: top crop `640:400:0:0`; INTER_AREA resize to 224 x 140;
  42 black rows above and below; BGR to RGB. Input `uint8 [1,224,224,3]`,
  quantization scale 0.007843137718737125 / zero point 127. Supply RGB bytes.
- Output: uint8, scale 0.00390625 / zero point 0. Dequantized values are model
  scores, not calibrated guarantees. Maximum representable score is 99.609375%.
- Pi runtime used for A4: Python 3.11 environment `~/venv-tml`, NumPy 1.26.4,
  OpenCV 4.11.0, tflite-runtime 2.14.0. Custom inference uses the interpreter
  directly; the stock example uses teachable-machine-lite 1.2.0.2.
- Editable project backup and full training captures remain in ignored local
  `data/processed/pi-training-v2/` and `data/raw/pi-v2/`.

[Training and export evidence](../../README.md#a4-teachable-machine).
[Manual video/log evaluation](../../README.md#a4-teachable-machine):
94.7% on 872 labeled frames in one recording, with 25 transitions excluded.
Bright fullscreen video and a different wallpaper exposed failures. This model also drives the finished Shelf Watcher interaction.

For a headless diagnostic run on the Pi (no VNC preview needed):

```bash
cd ~/a4-shelf-watcher
source ~/venv-tml/bin/activate
python scripts/a4_camera.py live \
  --model models/a4-pi-v2/model.tflite \
  --labels models/a4-pi-v2/labels.txt \
  --crop 640:400:0:0 \
  --seconds 60 --fps 2 \
  --output runs/manual-check
```

This diagnostic command saves predictions and selected images. With one monitor,
minimize the SSH/VNC window during capture so it does not replace the test scene.
