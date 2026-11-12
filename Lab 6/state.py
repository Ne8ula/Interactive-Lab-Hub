"""One plant, three carers. Water, mulch, sun, in that order, three times, makes it bloom.

Anything done out of turn withers the plant and the group starts over.
"""
import threading
import time
from common import MAX_MULCH, ROLES, SOURCES

CYCLES = 3          # rounds of water -> mulch -> sun needed to bloom
POUR_TILT = 30      # the can pours once it is tipped this far (0-100)
WATER_RATE = 25     # meter points per second at full tilt: about 4 s to fill
SUN_RATE = 25       # meter points per second while the sun is held: 4 s
MULCH_GAIN = 4      # meter points per unit of rubbing: 25 units to fill
GRACE = 1.5         # seconds after a step changes before out-of-turn input counts
STALE = 3           # a station silent this long is treated as idle and away
WITHER_SECONDS = 5  # how long the withered plant is shown before a fresh start
BLOOM_SECONDS = 20  # how long the flower is shown before a new seed


class GardenState:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.tilt, self.sun_on = 0, False
        self.seen = {role: None for role in ROLES}
        self.source = {role: None for role in ROLES}  # "pi" or "phone", once heard
        self.mulched_at = None
        self.at = clock()
        self._reset(self.at)

    # --- internals: call with the lock held ---

    def _reset(self, now):
        self.mode, self.cycle, self.step, self.meter, self.since, self.reason = "growing", 0, 0, 0.0, now, None

    def _fresh(self, role, now):
        return self.seen[role] is not None and now - self.seen[role] < STALE

    def _pouring(self, now):
        return self._fresh("water", now) and self.tilt >= POUR_TILT

    def _sunny(self, now):
        return self._fresh("sun", now) and self.sun_on

    def _next(self, now):
        self.step, self.meter, self.since = self.step + 1, 0.0, now
        if self.step == len(ROLES):
            self.step, self.cycle = 0, self.cycle + 1
            if self.cycle == CYCLES:
                self.mode = "bloomed"

    def _wither(self, action, now):
        self.reason = f"{action.title()} came when it was time to {ROLES[self.step]}."
        self.mode, self.since = "withered", now

    def _advance(self, now):
        """Apply the inputs held since the last call. Run before changing any input."""
        dt = min(now - self.at, 1)  # shortcut: a gap longer than 1 s credits only 1 s; fine while the display polls
        self.at = now
        pouring, sunny = self._pouring(now), self._sunny(now)
        if self.mode != "growing":
            shown = WITHER_SECONDS if self.mode == "withered" else BLOOM_SECONDS
            if now - self.since >= shown and not pouring and not sunny:
                self._reset(now)  # only once everyone has let go
            return
        role = ROLES[self.step]
        if now - self.since >= GRACE:
            if pouring and role != "water":
                return self._wither("water", now)
            if sunny and role != "sun":
                return self._wither("sun", now)
        if role == "water":
            if pouring:
                self.meter = min(100, self.meter + WATER_RATE * self.tilt / 100 * dt)
            elif self.meter >= 100:
                self._next(now)  # full, and the can is tipped back
        elif role == "sun":
            if sunny:
                self.meter = min(100, self.meter + SUN_RATE * dt)
            elif self.meter >= 100:
                self._next(now)  # full, and the button is released

    # --- station messages ---

    def _heard(self, role, source, now):
        self.seen[role] = now
        self.source[role] = source if source in SOURCES else None

    def water(self, tilt, source=None):
        if type(tilt) is not int or not 0 <= tilt <= 100:
            return False
        now = self.clock()
        with self.lock:
            self._advance(now)
            self.tilt = tilt
            self._heard("water", source, now)
        return True

    def sun(self, on, source=None):
        if type(on) is not bool:
            return False
        now = self.clock()
        with self.lock:
            self._advance(now)
            self.sun_on = on
            self._heard("sun", source, now)
        return True

    def mulch(self, amount, source=None):
        """amount 0 is a heartbeat: the station is here but nobody is spreading."""
        if type(amount) is not int or not 0 <= amount <= MAX_MULCH:
            return False
        now = self.clock()
        with self.lock:
            self._advance(now)
            self._heard("mulch", source, now)
            if amount and self.mode == "growing":
                self.mulched_at = now
                if ROLES[self.step] == "mulch":
                    self.meter = min(100, self.meter + MULCH_GAIN * amount)
                    if self.meter >= 100:
                        self._next(now)
                elif now - self.since >= GRACE:
                    self._wither("mulch", now)
        return True

    # --- display ---

    def _hint(self, pouring, sunny):
        if self.mode == "bloomed":
            return "It bloomed! Three rounds of water, mulch and sun, all in order."
        if self.mode == "withered":
            wait = " and ".join(["stop the water"] * pouring + ["let go of the sun"] * sunny)
            return self.reason + (f" To start again, {wait}." if wait else " Starting over.")
        role, full = ROLES[self.step], self.meter >= 100
        phone = self.source[role] == "phone"  # the wording follows whichever device holds this role
        if role == "water":
            if full:
                return f"That's enough water. {'Slide the bar' if phone else 'Turn the dial'} back to stop pouring."
            return f"Water first. {'Slide the bar right' if phone else 'Turn the dial clockwise'} to tip the can."
        if role == "mulch":
            return f"Now mulch. {'Rub the phone screen' if phone else 'Move the joystick left and right'} to spread it."
        return "Enough sun. Let go of the button." if full else "Now sun. Hold the button down."

    def snapshot(self):
        now = self.clock()
        with self.lock:
            self._advance(now)
            pouring, sunny = self._pouring(now), self._sunny(now)
            stations = {role: self._fresh(role, now) for role in ROLES}
            return {"mode": self.mode, "cycle": self.cycle, "cycles": CYCLES, "step": ROLES[self.step],
                    "meter": round(self.meter), "tilt": self.tilt if stations["water"] else 0,
                    "pouring": pouring, "sun": sunny,
                    "mulching": self.mulched_at is not None and now - self.mulched_at < .6,
                    "reason": self.reason, "hint": self._hint(pouring, sunny),
                    "stations": stations, "sources": dict(self.source), "active": sum(stations.values())}
