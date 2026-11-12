# miniPiTFT setup

Adafruit 1.14-inch miniPiTFT, 135 × 240, on Raspberry Pi 4.

## Install on the Pi

After [transferring the files](part-b-run.md), run in the Pi terminal:

```bash
cd ~/a4-shelf-watcher
source ~/venv-tml/bin/activate
python -m zipfile -e ~/part-b-pi.zip .
sudo apt-get update
sudo apt-get install -y libgpiod-dev python3-libgpiod
python -m pip install adafruit-blinka adafruit-circuitpython-rgb-display Pillow RPi.GPIO
sudo raspi-config nonint do_spi 0
sudo shutdown -h now
```

Setup references: [Adafruit Python display setup](https://learn.adafruit.com/adafruit-mini-pitft-135x240-color-tft-add-on-for-raspberry-pi/python-setup)
and [Blinka installation](https://learn.adafruit.com/circuitpython-on-raspberrypi-linux/installing-circuitpython-on-raspberry-pi).
If you previously installed a PiTFT console/kernel driver, follow Adafruit's
instructions to remove its conflicting configuration before using this Python method.

## Attach the display

After shutdown, unplug Pi power. Fit the display's 2x12 socket onto **physical
pins 1-24**, at the pin-1/3.3V end of the Pi's 40-pin header. All 24 socket holes
must align; the remaining 16 Pi pins stay uncovered. Match the board orientation
to [Adafruit's attachment photo](https://learn.adafruit.com/adafruit-mini-pitft-135x240-color-tft-add-on-for-raspberry-pi/python-setup#attaching).
Do not attach or reposition it while powered. Reconnect power and SSH afterward.

The display uses SPI CE0 and GPIO25, with GPIO22 for its backlight.
[Official pinout](https://learn.adafruit.com/adafruit-mini-pitft-135x240-color-tft-add-on-for-raspberry-pi/pinouts).

## Test the screen

```bash
cd ~/a4-shelf-watcher
source ~/venv-tml/bin/activate
ls -l /dev/spidev0.0
python scripts/b1_display.py --test
```

It should show happy, angry, and asleep for three seconds each, then turn the
backlight off. If upside down, rerun with `--rotation 270` and add
`--display-rotation 270` to the launch command. If the test fails,
check the terminal error and SPI configuration before continuing. A successful command alone
does not confirm that the screen looks right.

The tested setup required enabling SPI and releasing Linux's CE0/CE1 claims
using [Adafruit's chip-enable fix](https://learn.adafruit.com/circuitpython-on-raspberrypi-linux/spi-sensors-devices#reassigning-or-disabling-the-spi-chip-enable-lines-3097985), then rebooting.
The experiment runs over SSH; VNC is not needed.


[Launch Shelf Watcher](part2-run.md).
