# Running the vault

## Parts

- Raspberry Pi 4 with an Adafruit Mini PiTFT 1.14" (135 x 240) on its header
- SparkFun Qwiic OLED 0.91" (128 x 32)
- SparkFun Qwiic Button
- Adafruit I2C QT rotary encoder
- Zio 16 Servo Controller with a 9g servo on channel 0
- Separate 5 V supply for the servo

## Wiring

Qwiic cables, in order: Mini PiTFT -> Zio -> OLED -> Qwiic Button -> rotary encoder.

Servo power: 5 V supply -> barrel-jack screw-terminal adapter -> two-wire JST lead -> the Zio socket marked V+ and GND. Check with a multimeter which wire is positive before plugging it in.

Expected `i2cdetect -y 1` addresses: 0x36 encoder, 0x3C OLED, 0x40 Zio, 0x6F button.

## Install

Enable I2C and SPI in `sudo raspi-config`, then:

```bash
cd ~/lab4-vault
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements-vault.txt
```

## Run

```bash
python -u vault.py --encoder qt --reverse-servo --locked-angle 50 --open-angle 150
```

The code is `314`. Turn the encoder to pick a digit, press the button to enter it, and press the encoder to clear or relock.

## Other commands

| Command | What it does |
|---|---|
| `python vault.py --self-test` | Checks the code logic without any hardware |
| `python -m unittest test_vault.py` | Runs the tests without any hardware |
| `python vault.py --test tft` / `--test oled` | Shows LOCKED, OPEN and DENIED on one screen |
| `python vault.py --test touch` | Prints button presses |
| `python vault.py --test encoder --encoder qt` | Prints encoder position and press |
| `python vault.py --servo-angle 90` | Moves the servo to one angle (0 to 180) for three seconds |
| `python vault.py --no-servo --encoder qt` | Runs the vault without the servo |

Add `--reverse-servo` if the servo turns the wrong way, and `--reverse-encoder` if the digits count the wrong way.

The Part B sensor scripts from the course repository also need `python -m pip install -r requirements-lab4-sensors.txt`.
