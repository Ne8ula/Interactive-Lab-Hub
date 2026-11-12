"""Shared protocol settings. No hardware imports."""
import argparse
import os
import re

# The care routine, in the order it must happen. Each role is one station.
# On the Pi: water = rotary encoder, mulch = joystick, sun = button.
ROLES = ("water", "mulch", "sun")
# Who sent a message: a Pi sensor station, or a phone page relayed by the laptop.
SOURCES = ("pi", "phone")
MAX_MULCH = 10  # most mulch one message may carry


def team_name(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", value):
        raise argparse.ArgumentTypeError("Use 1–40 letters, digits, underscores or hyphens")
    return value


def mqtt_arguments(parser):
    parser.add_argument("--team", type=team_name, default="xiong-lab6")
    parser.add_argument("--broker", default=os.getenv("MQTT_BROKER", "farlab.infosci.cornell.edu"))
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--username", default=os.getenv("MQTT_USERNAME", "idd"))
    parser.add_argument("--password", default=os.getenv("MQTT_PASSWORD", "device@theFarm"))


def prefix(team):
    return f"IDD/{team}/garden"
