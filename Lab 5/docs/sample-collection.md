# Collect training samples

Film the physical monitor through the camera used for inference. Keep its position and crop fixed, and vary the screen content between captures.

From the repository root in Windows PowerShell, with FFmpeg installed:

```powershell
.\scripts\Collect-Samples.ps1 -Label WORK -Scene editor
.\scripts\Collect-Samples.ps1 -Label VIDEO -Scene player
.\scripts\Collect-Samples.ps1 -Label NEUTRAL -Scene desktop
```

Close other camera applications first. Each command waits five seconds, records eight seconds, and extracts up to 40 images at five frames per second. The default camera is the Kiyo; use the Pi shelf camera for the final model's training data.

To sample an existing optical recording:

```powershell
.\scripts\Collect-Samples.ps1 -Label VIDEO -Scene player -SourceVideo 'C:\clips\camera-recording.mp4' -StartSeconds 3
```

Use `-Crop 'width:height:x:y'` for a fixed crop and `-Split test` for held-out evaluation captures. Cropping, aspect-fit resizing, and black padding must match inference.

Raw recordings and receipts go in `data/raw/`; training images go in `data/processed/train/`. Upload images into the matching Teachable Machine class. Keep test captures out of training.

[Final model specifications](../models/a4-pi-v2/README.md)
