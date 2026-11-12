# Shared Garden setup

## Laptop (Windows PowerShell)

Run from the `lab6-shared-garden` folder. Install once with Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-server.txt
```

Launch the automatic offline preview:

```powershell
.\.venv\Scripts\python.exe app.py --demo
```

Open http://localhost:5000. Stop with Ctrl+C.

For live play through MQTT, launch this instead:

```powershell
.\.venv\Scripts\python.exe app.py --host 0.0.0.0
```

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

- `http://localhost:5000/phone/water`
- `http://localhost:5000/phone/mulch`
- `http://localhost:5000/phone/sun`

On a phone, replace `localhost` with the laptop's Wi-Fi IPv4 address from `ipconfig`. Use the same network and allow Python through the laptop firewall. Assign each role to only one device.

The laptop and Pi default to team `xiong-lab6`; use the same `--team` value on both if changing it. Stop the Part B server first if it is using port 5000, or choose another port with `--port 5002`.

## Software checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Optional local MQTT check:

```powershell
.\.venv\Scripts\python.exe -m pip install "amqtt>=0.12,<0.13"
.\.venv\Scripts\python.exe tests/mqtt_smoke.py
```

Build details, photos, videos and testing status are in the [main README](../README.md).
