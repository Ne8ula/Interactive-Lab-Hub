# Launch Shelf Watcher

Use the existing Raspberry Pi installation with the webcam, miniPiTFT, and Bluetooth speaker connected. Close other camera programs.

From Windows PowerShell:

```powershell
ssh ne8ula@vaultpi.local
```

In the Pi terminal:

```bash
cd ~/a4-shelf-watcher
source ~/venv-tml/bin/activate
python scripts/b1_shelf_watcher.py --mode voice --audio-test
python scripts/b1_shelf_watcher.py --mode voice --display mini-pitft --persistence 10 --cooldown 7 --threshold 0.85 --start-delay 10 --seconds 300
```

The audio test plays all three clips. Select the speaker as the Pi's default output if needed. The final command starts after 10 seconds and runs for up to five minutes; Ctrl+C stops and saves it.

VIDEO must remain at or above 85% for 10 seconds. Reminders start at least 7 seconds apart and never overlap. Add `--display-rotation 270` if the face is upside down.

Runs save predictions, events, settings, and a silent camera video under `runs/part-b/`. Use a phone recording to capture speaker audio.

[Transfer files and audio commands](part-b-run.md) · [Display setup](part-b-display.md) · [Finished demonstration](../README.md#part-2--finished-system-in-use)
