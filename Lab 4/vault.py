#!/usr/bin/env python3
"""Pi 4 vault: Mini PiTFT 1.14, SSD1306, Zio, SparkFun Qwiic Button, GPIO encoder.

See docs/setup.md for installation, wiring and staged checks. Code 314 by default.
Press the Qwiic Button to enter; press dial to clear/relock. --swap-inputs reverses
those two actions. --touch-board mpr121 remains for the Part A touch exercise.
--self-test needs no hardware. --demo needs displays but no input boards.
Software tests do not establish physical hardware compatibility or calibration.
"""

import argparse
import time


class Press:
    """One event per stable press; an initially held input must be released."""

    def __init__(self, initial=False, now=0.0):
        self.raw = self.stable = bool(initial)
        self.changed = now

    def update(self, value, now):
        value = bool(value)
        if value != self.raw:
            self.raw, self.changed = value, now
        if self.raw != self.stable and now - self.changed >= 0.05:
            self.stable = self.raw
            return self.stable
        return False


class Vault:
    def __init__(self, code="314"):
        self.code = tuple(map(int, code))
        self.reset()

    def reset(self):
        self.digit = 0
        self.entered = []
        self.state = "LOCKED"
        self.retry_at = 0.0

    def step(self, delta, confirm, reset, now):
        if reset:
            self.reset()
            return
        if self.state == "DENIED" and now >= self.retry_at:
            self.reset()
            return  # Ignore events on this transition.
        if self.state != "LOCKED":
            return
        self.digit = (self.digit + delta) % 10
        if confirm:
            self.entered.append(self.digit)
            self.digit = 0
            if len(self.entered) == len(self.code):
                self.state = "OPEN" if tuple(self.entered) == self.code else "DENIED"
                self.retry_at = now + 1.5

    def lines(self, swapped=False):
        action = "Press dial: enter" if swapped else "Button: enter"
        reset = "Button: relock" if swapped else "Press dial: relock"
        if self.state == "OPEN":
            return ("ACCESS GRANTED", "Close door first", reset, "")
        if self.state == "DENIED":
            return ("ACCESS DENIED", "Try again...", "", "")
        progress = "*" * len(self.entered) + "_" * (len(self.code) - len(self.entered))
        return ("VAULT " + progress, "Digit: " + str(self.digit), action,
                "Button:reset" if swapped else "Press dial:reset")


def self_test():
    def enter(v, digits, now=0):
        for digit in digits:
            v.step(digit - v.digit, True, False, now)

    v = Vault()
    enter(v, [3, 1, 4])
    assert v.state == "OPEN"
    v.step(1, True, False, 1)
    assert v.state == "OPEN" and v.entered == [3, 1, 4]
    v.step(0, False, True, 2)
    assert v.state == "LOCKED" and v.entered == []
    enter(v, [3, 1, 5], 3)
    assert v.state == "DENIED"
    v.step(0, False, False, 4)
    assert v.state == "DENIED"
    v.step(0, False, False, 5)
    assert v.state == "LOCKED" and v.entered == []
    v.step(-1, False, False, 6)
    assert v.digit == 9
    v.step(2, False, False, 7)
    assert v.digit == 1
    v.step(0, True, True, 8)
    assert v.entered == []  # Reset has priority over simultaneous confirm.
    enter(v, [3])
    v.step(0, False, True, 9)
    assert v.entered == []
    p = Press()
    assert not p.update(True, 0.1)
    assert not p.update(False, 0.12)
    assert not p.update(True, 0.14)
    assert p.update(True, 0.21)
    assert not p.update(True, 2)
    assert not p.update(False, 3)
    assert not p.update(False, 3.1)
    assert not p.update(True, 4)
    assert p.update(True, 4.1)
    held = Press(True)
    assert not held.update(True, 1)
    assert not held.update(False, 2)
    assert not held.update(False, 2.1)
    assert not held.update(True, 3)
    assert held.update(True, 3.1)
    assert "Press dial: enter" in Vault().lines(True)
    assert all(len(line) <= 21 for line in Vault().lines())
    print("PASS: correct/wrong codes, retry, reset, wrap, held/bouncing inputs, display mapping.")


COLORS = {"LOCKED": (75, 155, 255), "OPEN": (40, 220, 130), "DENIED": (255, 85, 75)}


def make_tft():
    import board
    import digitalio
    from adafruit_rgb_display import st7789
    backlight = digitalio.DigitalInOut(board.D22)
    backlight.switch_to_output(value=True)
    tft = st7789.ST7789(board.SPI(), cs=digitalio.DigitalInOut(board.CE0),
                       dc=digitalio.DigitalInOut(board.D25), rst=None,
                       baudrate=24000000, width=135, height=240,
                       x_offset=53, y_offset=40, rotation=90)
    return tft, backlight  # Keep GPIO object alive for the lifetime of the screen.


def make_oled(i2c):
    import adafruit_ssd1306
    return adafruit_ssd1306.SSD1306_I2C(128, 32, i2c, addr=0x3C)


def make_servo(i2c):
    from adafruit_servokit import ServoKit
    kit = ServoKit(channels=16, i2c=i2c, address=0x40, frequency=50)
    servo = kit.servo[0]
    # Usual full range for 9g hobby servos (about 180 degrees), NOT a measured MS18 calibration.
    # The earlier 1000-2000 range only gave about half the travel.
    servo.set_pulse_width_range(500, 2500)
    return kit, servo


class GPIOEncoder:
    """Adapt GPIO Zero's event-driven quadrature decoder to our encoder interface."""
    def __init__(self, device):
        self.device = device

    @property
    def position(self):
        return -self.device.steps

    def close(self):
        self.device.close()


class GPIOButton:
    def __init__(self, device):
        self.device = device

    @property
    def value(self):
        return not self.device.is_pressed

    def close(self):
        self.device.close()


def make_encoder(i2c, kind="gpio"):
    if kind == "gpio":
        from gpiozero import Button, RotaryEncoder
        from gpiozero.pins.rpigpio import RPiGPIOFactory
        factory = RPiGPIOFactory()
        encoder = RotaryEncoder(16, 20, max_steps=0, pin_factory=factory)
        try:
            button = Button(21, pull_up=True, pin_factory=factory)
        except BaseException:
            encoder.close()
            raise
        return GPIOEncoder(encoder), GPIOButton(button), None
    from adafruit_seesaw import seesaw, rotaryio, digitalio, neopixel
    ss = seesaw.Seesaw(i2c, addr=0x36)
    ss.pin_mode(24, ss.INPUT_PULLUP)
    return (QTEncoder(rotaryio.IncrementalEncoder(ss)), digitalio.DigitalIO(ss, 24),
            neopixel.NeoPixel(ss, 6, 1, brightness=0.12))


class QTEncoder:
    # The seesaw encoder sporadically returns INT32_MIN on the Pi (seen 2026-11-11); keep the last good position.
    def __init__(self, device):
        self.device, self.last = device, 0

    @property
    def position(self):
        raw = self.device.position
        if raw != -2**31:
            self.last = raw
        return self.last


class QwiicButton:
    def __init__(self, device):
        self.device = device

    @property
    def value(self):
        return self.device.is_button_pressed()


def make_touch(i2c, kind="qwiic"):
    if kind == "qwiic":
        # SparkFun's driver opens the Pi's default I2C bus itself; default address 0x6F.
        import qwiic_button
        device = qwiic_button.QwiicButton()
        if not device.begin():
            raise OSError("SparkFun Qwiic Button not found at I2C 0x6F")
        return [QwiicButton(device)]
    import adafruit_mpr121
    device = adafruit_mpr121.MPR121(i2c, address=0x5A)
    return [device[i] for i in range(12)]


def render(vault, swapped=False):
    """Generate both frames independently of hardware; Pillow is required."""
    from PIL import Image, ImageDraw, ImageFont
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try:
        progress_font, digit_font = ImageFont.truetype(font_path, 30), ImageFont.truetype(font_path, 84)
        state_font, status_font = ImageFont.truetype(font_path, 54), ImageFont.truetype(font_path, 26)
        anchor = "mm"
    except OSError:
        # Bitmap fallback cannot be sized or centred; text is small and offset but still shown.
        progress_font = digit_font = state_font = status_font = ImageFont.load_default()
        anchor = None
    # The TFT shows only progress + digit, or the state; control hints stay in the terminal log.
    color = COLORS[vault.state]
    frame = Image.new("RGB", (240, 135), (10, 16, 25))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, 239, 5), fill=color)
    if vault.state == "LOCKED":
        progress = " ".join("*" * len(vault.entered) + "_" * (len(vault.code) - len(vault.entered)))
        draw.text((120, 30), progress, font=progress_font, fill=color, anchor=anchor)
        draw.text((120, 88), str(vault.digit), font=digit_font, fill="white", anchor=anchor)
    else:
        draw.text((120, 70), vault.state, font=state_font, fill=color, anchor=anchor)
    indicator = Image.new("1", (128, 32))
    ink = ImageDraw.Draw(indicator)
    ink.text((64, 16), vault.state, font=status_font, fill=1, anchor=anchor)
    return frame, indicator


def check_part(args, i2c):
    if args.test in ("tft", "oled"):
        tft, backlight = make_tft() if args.test == "tft" else (None, None)
        oled = make_oled(i2c) if args.test == "oled" else None
        v = Vault()
        for state in ("LOCKED", "OPEN", "DENIED"):
            v.state = state
            frame, indicator = render(v)
            if tft:
                tft.image(frame)
            if oled:
                oled.image(indicator)
                oled.show()
            print(state, flush=True)
            time.sleep(2)
        print("Display sequence finished; verify all three states were visible.")
    elif args.test == "touch":
        touch = make_touch(i2c, args.touch_board)
        last = None
        print("Keep inputs untouched at startup. Press/release each. Ctrl+C to stop.")
        while True:
            first = 0 if args.touch_board == "mpr121" else 1
            active = [i + first for i, pad in enumerate(touch) if pad.value]
            if active != last:
                print("Active inputs:", active, flush=True)
                last = active
            time.sleep(0.05)
    elif args.test == "encoder":
        encoder, button, pixel = make_encoder(i2c, args.encoder)
        last = None
        try:
            while True:
                direction = -1 if args.reverse_encoder else 1
                reading = (-encoder.position * direction, not button.value)
                if reading != last:
                    print("Position, pressed:", reading, flush=True)
                    if pixel is not None:
                        pixel.fill((0, 180, 0) if reading[1] else (0, 0, 180))
                    last = reading
                time.sleep(0.02)
        finally:
            if pixel is not None:
                pixel.fill((0, 0, 0))
            if args.encoder == "gpio":
                encoder.close()
                button.close()


def hardware(args):
    import board
    i2c = board.I2C()
    if args.test:
        check_part(args, i2c)
        return
    if args.servo_angle is not None:
        kit, servo = make_servo(i2c)
        try:
            servo.angle = args.servo_angle
            print("Channel 0 nominal angle:", args.servo_angle, "(hold 3 seconds)", flush=True)
            time.sleep(3)
        finally:
            servo.angle = None
        print("PWM released. Remove power before attaching the pointer or changing wires.")
        return

    # Initialize outputs and inputs before enabling servo movement.
    tft, backlight = make_tft()
    oled = make_oled(i2c)
    servo = pixel = encoder = button = None
    direction = -1 if args.reverse_encoder else 1
    try:
        if not args.demo:
            touch = make_touch(i2c, args.touch_board)
            encoder, button, pixel = make_encoder(i2c, args.encoder)
            now = time.monotonic()
            pad_press = Press(touch[0].value, now)
            dial_press = Press(not button.value, now)
            position = -encoder.position * direction
        if not args.no_servo:
            kit, servo = make_servo(i2c)
        v = Vault(args.code)
        last_lines = last_state = None
        started = time.monotonic()
        print("DEMO: automatic states; no sensor input." if args.demo else
              "Vault running. Code " + args.code + ". Press button to enter; dial press resets.")
        if args.swap_inputs:
            print("SWAPPED: dial press enters; button resets.")
        while True:
            now = time.monotonic()
            if args.demo:
                v.state = ("LOCKED", "OPEN", "DENIED")[int((now - started) // 3) % 3]
            else:
                new_position = -encoder.position * direction
                delta, position = new_position - position, new_position
                pad = pad_press.update(touch[0].value, now)
                dial = dial_press.update(not button.value, now)
                confirm, reset = (dial, pad) if args.swap_inputs else (pad, dial)
                v.step(delta, confirm, reset, now)
            if v.state != last_state:
                if servo is not None:
                    servo.angle = args.open_angle if v.state == "OPEN" else args.locked_angle
                if pixel is not None:
                    pixel.fill(COLORS[v.state])
                last_state = v.state
            lines = v.lines(args.swap_inputs)
            if lines != last_lines:
                frame, indicator = render(v, args.swap_inputs)
                tft.image(frame)
                oled.image(indicator)
                oled.show()
                print(v.state, "|", " | ".join(lines), flush=True)
                last_lines = lines
            time.sleep(0.02)
    finally:
        if servo is not None:
            servo.angle = None
        if pixel is not None:
            pixel.fill((0, 0, 0))
        if args.encoder == "gpio":
            if encoder is not None:
                encoder.close()
            if button is not None:
                button.close()
        print("PWM released. Display may retain its last image. Disconnect power before rewiring.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--swap-inputs", action="store_true")
    parser.add_argument("--code", default="314")
    parser.add_argument("--touch-board", choices=("qwiic", "mpr121"), default="qwiic",
                        help="Confirm input: Qwiic Button (default) or a borrowed MPR121.")
    parser.add_argument("--encoder", choices=("gpio", "qt"), default="gpio")
    parser.add_argument("--reverse-encoder", action="store_true", help="Reverse the dial direction.")
    parser.add_argument("--locked-angle", type=int, default=60)
    parser.add_argument("--open-angle", type=int, default=120)
    parser.add_argument("--reverse-servo", action="store_true", help="Turn the servo the other way.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--test", choices=("tft", "oled", "touch", "encoder"))
    modes.add_argument("--demo", action="store_true", help="Automatic display/servo demo; no inputs.")
    modes.add_argument("--servo-angle", type=int, help="Move channel 0; hold 3 s; release PWM.")
    parser.add_argument("--no-servo", action="store_true", help="Do not initialize the Zio or servo.")
    args = parser.parse_args()
    if len(args.code) != 3 or any(c not in "0123456789" for c in args.code):
        parser.error("--code must be three ASCII digits")
    for angle in (args.locked_angle, args.open_angle, args.servo_angle):
        if angle is not None and not 0 <= angle <= 180:
            parser.error("Angles must be from 0 to 180; this servo cannot turn further")
    if args.no_servo and args.servo_angle is not None:
        parser.error("--no-servo cannot be combined with --servo-angle")
    if args.reverse_servo:  # Mirror around the middle: 0 <-> 180, 90 stays 90.
        args.locked_angle, args.open_angle = 180 - args.locked_angle, 180 - args.open_angle
        if args.servo_angle is not None:
            args.servo_angle = 180 - args.servo_angle
    if args.self_test:
        self_test()
    else:
        try:
            hardware(args)
        except KeyboardInterrupt:
            print("Stopped.")


if __name__ == "__main__":
    main()
