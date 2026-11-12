# Hardware and software

| Component | Use in the finished system |
|---|---|
| Raspberry Pi 4 | Camera capture, classifier, reminder timing, and display control |
| USB webcam | Optical view of the physical monitor from the shelf |
| Adafruit 1.14-inch miniPiTFT, 240 × 135 | Happy, angry, asleep, and uncertain expressions |
| Leviathan V2 speaker | Spoken reminders over Bluetooth |
| Cardboard enclosure | Holds the expression display and webcam together as a companion |
| Monitor and computer | Work, video, and neutral scenes for training and testing |
| Phone camera | Physical demonstrations with speaker audio |

The speaker remains separate from the enclosure. The webcam, face, cable openings,
and interior are shown in the [finished-build photos](../README.md#part-2--finished-system-in-use).
No servo or printed enclosure is used in this build.

## Software

The recorded platform is Raspberry Pi 4 with Debian 12 Bookworm, aarch64, and
Python 3.11.2. The application uses OpenCV, TensorFlow Lite, Pillow, Adafruit
Blinka/RGB display, and PulseAudio/PipeWire playback. Part A also explores
PyTorch/MobileNet, MediaPipe, and Ollama/Moondream. Teachable Machine is used
for training and export.

[Final launch instructions](part2-run.md) · [Display setup](part-b-display.md) ·
[Audio experiments](part-b-run.md) · [Course dependency reference](../requirements.upstream.txt)

The course dependency reference is not a lockfile for the final installation.
