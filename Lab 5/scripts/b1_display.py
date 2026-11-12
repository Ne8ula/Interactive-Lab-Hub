"""Faces for the confirmed Adafruit 1.14-inch 135x240 mini PiTFT.

Pin configuration follows Adafruit's Python Stats example:
https://learn.adafruit.com/adafruit-mini-pitft-135x240-color-tft-add-on-for-raspberry-pi/python-stats
Local PNG previews are design previews, not hardware evidence.
"""
import argparse
import math
import sys
import time
from pathlib import Path


FACES = {'WORK': 'happy', 'VIDEO': 'angry', 'NEUTRAL': 'asleep'}


def face_for_prediction(label, score, threshold=.85):
    if not math.isfinite(score) or score < threshold:
        return 'uncertain'
    return FACES.get(label, 'uncertain')


def render_face(face):
    from PIL import Image, ImageDraw

    image = Image.new('RGB', (240, 135), (4, 8, 14))
    draw = ImageDraw.Draw(image)
    color = {'happy': '#7af0bd', 'angry': '#ff765f', 'asleep': '#97b9ff',
             'uncertain': '#ded8ae', 'error': '#ff765f'}[face]
    if face == 'happy':
        draw.arc((43, 28, 95, 77), 190, 350, fill=color, width=7)
        draw.arc((145, 28, 197, 77), 190, 350, fill=color, width=7)
        draw.arc((77, 54, 163, 112), 10, 170, fill=color, width=7)
        draw.ellipse((33, 76, 49, 83), fill='#31594b')
        draw.ellipse((191, 76, 207, 83), fill='#31594b')
    elif face == 'angry':
        draw.line([(45, 30), (95, 47)], fill=color, width=8)
        draw.line([(145, 47), (195, 30)], fill=color, width=8)
        draw.rounded_rectangle((64, 52, 83, 75), radius=7, fill=color)
        draw.rounded_rectangle((157, 52, 176, 75), radius=7, fill=color)
        draw.arc((82, 87, 158, 120), 200, 340, fill=color, width=6)
    elif face == 'asleep':
        draw.arc((43, 35, 95, 67), 10, 170, fill=color, width=6)
        draw.arc((145, 35, 197, 67), 10, 170, fill=color, width=6)
        draw.ellipse((112, 85, 128, 102), outline=color, width=4)
        for x, y, size in [(183, 16, 11), (202, 6, 17)]:
            draw.line([(x,y), (x+size,y), (x,y+size), (x+size,y+size)], fill=color, width=3)
    else:
        for x in (70, 170):
            if face == 'error':
                draw.line([(x-12,38),(x+12,62)],fill=color,width=5)
                draw.line([(x+12,38),(x-12,62)],fill=color,width=5)
            else:
                draw.ellipse((x-9,40,x+9,61),outline=color,width=4)
        draw.line([(96,98),(144,98)],fill=color,width=5)
        if face == 'uncertain':
            draw.arc((111,59,129,77),180,450,fill=color,width=3)
            draw.line([(120,75),(120,80)],fill=color,width=3)
            draw.ellipse((118,85,122,89),fill=color)
    return image


class MiniPitft:
    def __init__(self, rotation=90):
        import board
        import digitalio
        from adafruit_rgb_display.st7789 import ST7789

        self.rotation, self.current = rotation, None
        self.resources = []
        self.device = self.backlight = None
        self.images = {name: render_face(name) for name in ['happy','angry','asleep','uncertain','error']}
        try:
            spi = board.SPI()
            self.resources.append(spi)
            cs = digitalio.DigitalInOut(board.CE0)
            self.resources.append(cs)
            dc = digitalio.DigitalInOut(board.D25)
            self.resources.append(dc)
            self.backlight = digitalio.DigitalInOut(board.D22)
            self.resources.append(self.backlight)
            self.backlight.switch_to_output(value=False)
            self.device = ST7789(spi, cs=cs, dc=dc, rst=None, baudrate=24000000,
                                 width=135, height=240, x_offset=53, y_offset=40)
            self.show('uncertain')
            self.backlight.value = True
        except BaseException:
            self.close()
            raise

    def show(self, face):
        if face == self.current:
            return False
        self.device.image(self.images[face], self.rotation)
        self.current = face
        return True

    def close(self):
        if self.backlight is not None:
            try:
                self.backlight.value = False
            except Exception as error:
                print(f'Backlight cleanup: {error}', file=sys.stderr)
        for resource in reversed(self.resources):
            try:
                resource.deinit()
            except Exception as error:
                print(f'Display cleanup: {error}', file=sys.stderr)
        self.resources = []
        self.backlight = self.device = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--test', action='store_true', help='Cycle real display through happy, angry, asleep')
    choice.add_argument('--preview-dir', type=Path, help='Save local PNG design previews without GPIO access')
    parser.add_argument('--rotation', type=int, choices=[90,270], default=90)
    args = parser.parse_args()
    if args.preview_dir:
        args.preview_dir.mkdir(parents=True,exist_ok=True)
        for face in ['happy','angry','asleep','uncertain','error']:
            render_face(face).save(args.preview_dir/f'{face}.png')
        print('Saved design previews; no hardware was accessed.')
        return
    display = MiniPitft(args.rotation)
    try:
        for face in ['happy','angry','asleep']:
            print('Showing:',face,flush=True)
            display.show(face)
            time.sleep(3)
    finally:
        display.close()
    print('Display test commands completed. Confirm the three faces appeared correctly.')


if __name__ == '__main__':
    main()
