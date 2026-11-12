"""Part B, run 1: the Mini PiTFT's two buttons pick a hue for the course pixel grid.

Used before the APDS-9960 arrived. Run 2 used the course's own pixel_grid_publisher.py.
"""
import argparse
import colorsys
import json
import socket
import time
import uuid
import paho.mqtt.client as mqtt
from common import mqtt_arguments

PIXELGRID_TOPIC = "IDD/pixelgrid/colors"


def local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # UDP connect sends nothing; it only picks the outgoing interface
            return s.getsockname()[0]
    except OSError:
        return "unknown"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mqtt_arguments(parser)
    args = parser.parse_args()

    # Lazy imports keep --help usable on a laptop.
    import board
    import digitalio
    from adafruit_rgb_display import st7789
    from gpiozero import Button
    from PIL import Image, ImageDraw, ImageFont

    down, up = Button(23), Button(24)  # Mini PiTFT buttons, active low
    backlight = digitalio.DigitalInOut(board.D22)
    backlight.switch_to_output(value=True)
    # CE0 at 24 MHz is what this Pi's screen answers to (checked with a colour test).
    tft = st7789.ST7789(board.SPI(), cs=digitalio.DigitalInOut(board.CE0),
                        dc=digitalio.DigitalInOut(board.D25), rst=None, baudrate=24000000,
                        width=135, height=240, x_offset=53, y_offset=40, rotation=90)
    image = Image.new("RGB", (240, 135))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except OSError:
        font = ImageFont.load_default()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(args.username, args.password)
    client.on_connect = lambda c, u, f, reason_code, p: print(f"MQTT: {reason_code}", flush=True)
    client.connect_async(args.broker, args.mqtt_port, keepalive=15)
    client.loop_start()
    mac = ":".join(f"{uuid.getnode():012x}"[i:i + 2] for i in range(0, 12, 2))
    ip = local_ip()
    print(f"Publishing to {PIXELGRID_TOPIC}. Ctrl+C to stop.", flush=True)

    hue, was, shown = 0, (False, False), None
    try:
        while True:
            pressed = (down.is_pressed, up.is_pressed)
            moved = (pressed[1] and not was[1]) - (pressed[0] and not was[0])
            was = pressed
            hue = (hue + 15 * moved) % 360
            rgb = tuple(round(v * 255) for v in colorsys.hsv_to_rgb(hue / 360, 1, 1))
            if rgb != shown:  # redrawing the screen is slow; only do it on change
                draw.rectangle((0, 0, 240, 135), fill=rgb)
                draw.text((12, 12), f"Part B\nhue {hue}", font=font, fill=(0, 0, 0) if sum(rgb) > 384 else (255, 255, 255))
                tft.image(image)
                shown = rgb
            if client.is_connected():
                client.publish(PIXELGRID_TOPIC, json.dumps({"mac": mac, "ip": ip, "r": rgb[0], "g": rgb[1],
                                                            "b": rgb[2], "timestamp": int(time.time())}))
            if moved:
                print(f"hue {hue} rgb {rgb}", flush=True)
            time.sleep(.1)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        client.disconnect()
        client.loop_stop()
        backlight.value = False


if __name__ == "__main__":
    main()
