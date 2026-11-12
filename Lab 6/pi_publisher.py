"""Pi sensor station -> MQTT. One role per run; all three sensors can share the Qwiic chain.

--role water  Adafruit I2C rotary encoder (seesaw, 0x36). Clockwise tips the watering
              can and pours; counter-clockwise tips it back.
--role mulch  SparkFun Qwiic Joystick (0x20). Moving it left and right spreads mulch.
--role sun    SparkFun Qwiic Button (0x6F). Hold the button for sunlight.
"""
import argparse
import json
import time
import paho.mqtt.client as mqtt
from common import MAX_MULCH, ROLES, mqtt_arguments, prefix

TILT_STEP = 10       # tilt gained per encoder click: ten clicks from upright to fully tipped
STICK_DEADBAND = 15  # joystick counts (of 1023) ignored as jitter, so a still stick sends nothing
STICK_PER_MULCH = 100  # joystick travel per unit of mulch: one full sweep is about 10 units


def open_screen(enabled):
    """Return show(rgb, text) for the Mini PiTFT, or a no-op if it is off or not fitted."""
    if not enabled:
        return lambda rgb, text: None
    try:
        import board
        import digitalio
        from adafruit_rgb_display import st7789
        from PIL import Image, ImageDraw, ImageFont
        backlight = digitalio.DigitalInOut(board.D22)
        backlight.switch_to_output(value=True)
        # CE0 at 24 MHz is what this Pi's screen answers to (checked with a colour test).
        tft = st7789.ST7789(board.SPI(), cs=digitalio.DigitalInOut(board.CE0),
                            dc=digitalio.DigitalInOut(board.D25), rst=None, baudrate=24000000,
                            width=135, height=240, x_offset=53, y_offset=40, rotation=90)
    except Exception as error:
        print(f"No Mini PiTFT ({error}); running without a screen.", flush=True)
        return lambda rgb, text: None
    image = Image.new("RGB", (240, 135))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    shown = None

    def show(rgb, text):
        nonlocal shown
        if (rgb, text) != shown:  # redrawing the screen is slow; only do it on change
            draw.rectangle((0, 0, 240, 135), fill=rgb)
            draw.text((10, 10), text, font=font, fill=(255, 255, 255))
            tft.image(image)
            shown = (rgb, text)

    return show


def turn_text(garden, role):
    if garden.get("mode") == "growing" and garden.get("step") == role:
        return "YOUR TURN"
    return f"wait: {garden.get('step', '...')}"


def water_station(args, garden, show):
    """read() gives {"tilt": 0-100}."""
    import board
    from adafruit_seesaw import neopixel, rotaryio, seesaw
    ss = seesaw.Seesaw(board.I2C(), addr=0x36)
    encoder = rotaryio.IncrementalEncoder(ss)
    pixel = neopixel.NeoPixel(ss, 6, 1, brightness=.3)  # the encoder board's own light
    sign = -1 if args.reverse else 1  # on this encoder, clockwise counts up (checked on the Pi)
    last, tilt = sign * encoder.position, 0

    def read():
        nonlocal last, tilt
        position = sign * encoder.position
        tilt = max(0, min(100, tilt + TILT_STEP * (position - last)))
        last = position
        pixel.fill((0, 0, round(2.55 * tilt)))  # bluer as the can tips further
        show((30, 90, 200) if tilt >= 30 else (40, 60, 80), f"WATER\ntilt {tilt}%\n{turn_text(garden, 'water')}")
        return {"tilt": tilt}

    return read, lambda: pixel.fill((0, 0, 0))


def mulch_station(args, garden, show):
    """read() gives {"amount": 0-10}: how far the stick travelled sideways since the last send."""
    import qwiic_joystick
    stick = qwiic_joystick.QwiicJoystick()
    if not stick.begin():
        raise SystemExit("Qwiic Joystick not found at 0x20. Check the cable and that I2C is enabled.")
    anchor, travel, released, total = stick.get_horizontal(), 0, 0.0, 0

    def read():
        nonlocal anchor, travel, released, total
        x = stick.get_horizontal()  # 0-1023, about 512 at rest
        if abs(x - anchor) >= STICK_DEADBAND:
            travel += abs(x - anchor)
            anchor = x
        amount = 0
        if time.monotonic() - released >= .2:  # at most five mulch messages a second
            amount = min(MAX_MULCH, travel // STICK_PER_MULCH)
            travel -= amount * STICK_PER_MULCH
            if amount:
                released = time.monotonic()
                total += amount
        show((150, 105, 60), f"MULCH\nspread {total}\n{turn_text(garden, 'mulch')}")
        return {"amount": amount}

    return read, lambda: None


def sun_station(args, garden, show):
    """read() gives {"on": bool}."""
    import qwiic_button
    button = qwiic_button.QwiicButton()
    if not button.begin():
        raise SystemExit("Qwiic Button not found at 0x6F. Check the cable and that I2C is enabled.")
    lit = None

    def light(level):
        nonlocal lit
        if level != lit:
            lit = level
            try:  # the LED is a nicety; a driver hiccup must not stop the station
                button.LED_on(level) if level else button.LED_off()
            except Exception as error:
                print(f"Button LED unavailable: {error}", flush=True)

    def read():
        on = bool(button.is_button_pressed())
        my_turn = garden.get("mode") == "growing" and garden.get("step") == "sun"
        # Bright while held; a slow blink when it is this station's turn.
        light(255 if on else 40 if my_turn and int(time.monotonic() * 2) % 2 else 0)
        show((230, 160, 20) if on else (80, 70, 40), f"SUN\n{'shining' if on else 'off'}\n{turn_text(garden, 'sun')}")
        return {"on": on}

    return read, lambda: light(0)


STATIONS = {"water": water_station, "mulch": mulch_station, "sun": sun_station}
IDLE = {"water": {"tilt": 0}, "mulch": {"amount": 0}, "sun": {"on": False}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mqtt_arguments(parser)
    parser.add_argument("--role", choices=ROLES, required=True)
    parser.add_argument("--sensor-only", action="store_true", help="Read the real sensor without connecting to MQTT")
    parser.add_argument("--no-screen", action="store_true", help="Leave the Mini PiTFT alone (use when running two roles at once)")
    parser.add_argument("--reverse", action="store_true", help="water: swap the encoder's direction if clockwise does not pour")
    args = parser.parse_args()

    garden = {}  # latest garden state heard from the laptop, filled in by on_message
    show = open_screen(not args.no_screen)
    read, close = STATIONS[args.role](args, garden, show)
    root = prefix(args.team)
    topic = f"{root}/{args.role}"
    idle = {**IDLE[args.role], "from": "pi"}
    client = None
    try:
        if not args.sensor_only:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{args.team}-pi-{args.role}")
            client.username_pw_set(args.username, args.password)
            client.will_set(topic, json.dumps(idle))  # if this Pi dies, the can tips back / the sun goes in
            client.reconnect_delay_set(min_delay=1, max_delay=10)

            def on_connect(client, userdata, flags, reason_code, properties):
                print(f"MQTT: {reason_code}", flush=True)
                if not reason_code.is_failure:
                    client.subscribe(f"{root}/state")
                    print(f"MQTT subscribed  {root}/state", flush=True)

            def on_message(client, userdata, message):
                try:
                    data = json.loads(message.payload)
                except (ValueError, UnicodeError):
                    return
                if isinstance(data, dict):
                    if data.get("step") != garden.get("step") or data.get("mode") != garden.get("mode"):
                        print(f"MQTT in   {message.topic} mode={data.get('mode')} step={data.get('step')} round={data.get('cycle', 0) + 1}", flush=True)
                    garden.clear()
                    garden.update(data)

            client.on_connect = on_connect
            client.on_message = on_message
            client.on_connect_fail = lambda c, u: print("Broker unavailable; retrying. Check network/host/port.", flush=True)
            client.connect_async(args.broker, args.mqtt_port, keepalive=15)
            client.loop_start()
        print(f"Station {args.role}: publishing to {topic}. Ctrl+C to stop.", flush=True)
        sent, sent_at = None, 0
        while True:
            reading = {**read(), "from": "pi"}
            now = time.monotonic()
            event = reading.get("amount", 0) > 0                      # mulch: every spread counts, even a repeat
            changed = "amount" not in reading and reading != sent    # water and sun: a new position or press
            if event or changed or now - sent_at >= 1:               # otherwise once a second as a heartbeat
                text = json.dumps(reading)
                status = "sensor only"
                if client:
                    status = "MQTT reconnecting"
                    if client.is_connected():
                        status = "sent" if client.publish(topic, text).rc == mqtt.MQTT_ERR_SUCCESS else "send failed"
                if event or changed:
                    print(f"MQTT out  {topic} {text} | {status}", flush=True)
                sent, sent_at = reading, now
            time.sleep(.05)
    except KeyboardInterrupt:
        print("\nStopping station.")
    finally:
        if client:
            if client.is_connected():
                try:
                    client.publish(topic, json.dumps(idle), qos=1).wait_for_publish(timeout=2)
                except RuntimeError:
                    pass
            client.disconnect()
            client.loop_stop()
        close()
        show((0, 0, 0), "")


if __name__ == "__main__":
    main()
