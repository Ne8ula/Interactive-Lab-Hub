"""Run an isolated copy of the supplied example for a bounded evidence capture."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone

source = Path('/home/ne8ula/lab5-a1/Interactive-Lab-Hub/Lab 5')
out = Path('/home/ne8ula/a4-shelf-watcher/stock-check')
out.mkdir(exist_ok=False)
hashes = {}
for name in ('tml_example.py', 'model.tflite', 'labels.txt'):
    shutil.copy2(source/name, out/name)
    hashes[name] = hashlib.sha256((out/name).read_bytes()).hexdigest()
receipt = dict(started_utc=datetime.now(timezone.utc).isoformat(),
               source=str(source), hashes=hashes, seconds=30,
               note='Unmodified supplied script in isolated folder; camera scene is the monitor, not a staged Phone/Zooming test.')
with (out/'stock-output.txt').open('w') as log:
    try:
        result = subprocess.run(['/home/ne8ula/venv-tml/bin/python','-u','tml_example.py'],
            cwd=out, stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ,'DISPLAY':':0','XAUTHORITY':'/home/ne8ula/.Xauthority'},timeout=30)
        receipt['exit_code'] = result.returncode
    except subprocess.TimeoutExpired:
        receipt['stopped_by'] = 'Scheduled 30-second timeout'
receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
(out/'receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
