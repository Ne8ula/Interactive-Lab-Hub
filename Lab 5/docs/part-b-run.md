# Transfer files and run audio experiments

From the repository root in Windows PowerShell:

```powershell
Compress-Archive -Path scripts,models,assets -DestinationPath "$env:TEMP\shelf-watcher-pi.zip" -Force
scp "$env:TEMP\shelf-watcher-pi.zip" ne8ula@vaultpi.local:~/part-b-pi.zip
```

In the Pi terminal, using the existing installation:

```bash
cd ~/a4-shelf-watcher
source ~/venv-tml/bin/activate
python -m zipfile -e ~/part-b-pi.zip .
pactl get-default-sink
python scripts/b1_shelf_watcher.py --mode voice --audio-test
```

Connect the speaker and select it as the default output. Playback uses `paplay` or `pw-play`.

```bash
# Experiment 1: triple beeps, 5-second trigger, no cooldown.
python scripts/b1_shelf_watcher.py --mode beep --seconds 180

# Experiment 2: voice, 15-second trigger and cooldown.
python scripts/b1_shelf_watcher.py --mode voice --persistence 15 --cooldown 15 --seconds 180

# Experiment 3: voice and display with the same timing.
python scripts/b1_shelf_watcher.py --mode voice --display mini-pitft --persistence 15 --cooldown 15 --seconds 180
```

Ctrl+C stops and saves a run. Logs and silent camera videos go in `runs/part-b/`.

[Final companion launch](part2-run.md) · [Display setup](part-b-display.md) · [Experiment results](../README.md#part-b-shelf-watcher-interaction)
