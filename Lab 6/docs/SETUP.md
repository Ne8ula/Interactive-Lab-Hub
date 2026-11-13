# Shared Garden setup

## Laptop (macOS)

Run from the `Lab 6` folder. Install once with Python 3.9 or newer:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-server.txt
```

Launch the automatic offline preview:

```bash
.venv/bin/python app.py --demo
```

Open http://localhost:5001. Stop with Ctrl+C.

For live play through MQTT, launch this instead:

```bash
.venv/bin/python app.py --host 0.0.0.0
```

On Windows, use `py -3.12 -m venv .venv` and `.\.venv\Scripts\python.exe` in place of `.venv/bin/python`.

The default port is 5001 because macOS AirPlay Receiver holds 5000.

## User-test layout: Pi 4 + Pi 5 + phone + Mac

| Device | Job | Command or page |
|---|---|---|
| Mac | Display | `.venv/bin/python app.py --host 0.0.0.0`, then http://localhost:5001 full screen |
| Pi 5 | Water station (encoder) | `sudo systemctl stop piscreen.service`, then `.venv/bin/python pi_publisher.py --role water` |
| Pi 4 | Mulch station (joystick) | `.venv/bin/python pi_publisher.py --role mulch` |
| Phone | Sun station | `http://<Mac IP>:5001/phone/sun` |

Any role can go on any device, one device per role. The Pis only need internet access to reach the course broker; they do not need to see the Mac. The phone does need to reach the Mac, so both must be on the same Wi-Fi. If that Wi-Fi blocks device-to-device traffic, put the Mac and the phone on a phone hotspot.

On the Pi 5, `piscreen.service` owns the Mini PiTFT until it is stopped. `pi_publisher.py` picks the screen's chip select by board: CE0 on a Pi 4, D5 on a Pi 5, where the kernel holds CE0.

## Pi station

Copy `common.py`, `pi_publisher.py` and `requirements-pi.txt` into a `lab6-shared-garden` folder on the Pi. Enable I2C and SPI with `sudo raspi-config`, then install:

```bash
cd ~/lab6-shared-garden
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements-pi.txt
```

Power off before connecting sensors through the Mini PiTFT's Qwiic port.

| Role | Sensor | I2C address |
|---|---|---|
| `water` | Adafruit seesaw rotary encoder | `0x36` |
| `mulch` | SparkFun Qwiic Joystick | `0x20` |
| `sun` | SparkFun Qwiic Button | `0x6F` |

Run one station, replacing `water` with `mulch` or `sun` as needed:

```bash
.venv/bin/python pi_publisher.py --role water
```

Add `--sensor-only` to test without MQTT, or `--no-screen` if not using the PiTFT. When running multiple roles on one Pi, use separate terminals and give only one process access to the screen.

## Browser stations

With the live server running, open any unused roles in browser tabs or on phones:

- `http://localhost:5001/phone/water`
- `http://localhost:5001/phone/mulch`
- `http://localhost:5001/phone/sun`

On a phone, replace `localhost` with the Mac's Wi-Fi address from `ipconfig getifaddr en0`. Use the same network and allow Python through the laptop firewall. Assign each role to only one device.

The laptop and Pi default to team `xiong-lab6`; use the same `--team` value on both if changing it. Choose another port with `--port 5002` if 5001 is taken.

## Software checks

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Optional local MQTT check:

```bash
.venv/bin/python -m pip install "amqtt>=0.12,<0.13"
.venv/bin/python tests/mqtt_smoke.py
```

Build details, photos, videos and testing status are in the [main README](../README.md).
