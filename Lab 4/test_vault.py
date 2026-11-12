"""Offline integration checks. Faked devices do not verify physical hardware."""
import argparse
import contextlib
import io
import sys
import types
import unittest
from unittest.mock import Mock, patch

import vault


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.now > 1.4:
            raise KeyboardInterrupt


class Encoder:
    def __init__(self, clock):
        self.clock = clock
        self.close = Mock()

    @property
    def position(self):
        t = self.clock.now
        return -(3 * (t >= 0.06) + (t >= 0.36) + 4 * (t >= 0.66))


class Button:
    def __init__(self, clock):
        self.clock = clock
        self.close = Mock()

    @property
    def value(self):
        return not (1.0 <= self.clock.now < 1.15)


class Electrode:
    def __init__(self, clock):
        self.clock = clock

    @property
    def value(self):
        t = self.clock.now
        return any(start <= t < start + 0.15 for start in (0.10, 0.40, 0.70))


class Servo:
    def __init__(self):
        self.commands = []

    @property
    def angle(self):
        return self.commands[-1] if self.commands else None

    @angle.setter
    def angle(self, value):
        self.commands.append(value)


class IntegrationTests(unittest.TestCase):
    def exercise(self, no_servo=False, display_failure=False, gpio=False):
        clock = Clock()
        servo, tft, oled, pixel = Servo(), Mock(), Mock(), Mock()
        if gpio:
            pixel = None
        encoder, button = Encoder(clock), Button(clock)
        board = types.ModuleType("board")
        board.I2C = Mock(return_value=object())
        states = []

        def render(model, swapped):
            states.append(model.state)
            if display_failure and model.state == "OPEN":
                raise OSError("simulated disconnected display")
            return model.state, model.state

        args = argparse.Namespace(test=None, servo_angle=None, demo=False,
                                  no_servo=no_servo, code="314", swap_inputs=False,
                                  locked_angle=60, open_angle=120, touch_board="qwiic",
                                  encoder="gpio" if gpio else "qt", reverse_encoder=False)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {"board": board}))
            stack.enter_context(patch.object(vault, "time", clock))
            stack.enter_context(patch.object(vault, "make_tft", return_value=(tft, object())))
            stack.enter_context(patch.object(vault, "make_oled", return_value=oled))
            maker = stack.enter_context(patch.object(vault, "make_servo", return_value=(object(), servo)))
            stack.enter_context(patch.object(vault, "make_encoder",
                                           return_value=(encoder, button, pixel)))
            stack.enter_context(patch.object(vault, "make_touch", return_value=[Electrode(clock)]))
            stack.enter_context(patch.object(vault, "render", side_effect=render))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            with self.assertRaises(OSError if display_failure else KeyboardInterrupt):
                vault.hardware(args)
        if gpio:
            encoder.close.assert_called_once()
            button.close.assert_called_once()
        return servo.commands, states, maker.call_count, tft, oled, pixel

    def test_touch_encoder_unlock_relock_and_shutdown(self):
        commands, states, calls, tft, oled, pixel = self.exercise()
        self.assertEqual(commands, [60, 120, 60, None])
        self.assertEqual(calls, 1)
        self.assertIn("OPEN", states)
        self.assertEqual(states[-1], "LOCKED")
        self.assertEqual(tft.image.call_count, oled.image.call_count)
        self.assertEqual(oled.show.call_count, oled.image.call_count)
        pixel.fill.assert_called_with((0, 0, 0))

    def test_no_servo_does_not_initialize_zio(self):
        commands, states, calls, *_ = self.exercise(no_servo=True)
        self.assertEqual(commands, [])
        self.assertEqual(calls, 0)
        self.assertIn("OPEN", states)

    def test_display_failure_releases_servo(self):
        commands, *_ = self.exercise(display_failure=True)
        self.assertEqual(commands[-1], None)
        self.assertIn(120, commands)

    def test_gpio_encoder_without_neopixel(self):
        commands, states, *_ = self.exercise(gpio=True)
        self.assertEqual(commands, [60, 120, 60, None])
        self.assertIn("OPEN", states)

    def test_qwiic_button_reports_presses_and_missing_board(self):
        device = Mock()
        device.is_button_pressed.return_value = True
        module = types.ModuleType("qwiic_button")
        module.QwiicButton = Mock(return_value=device)
        with patch.dict(sys.modules, {"qwiic_button": module}):
            [button] = vault.make_touch(None, "qwiic")
            self.assertTrue(button.value)
            device.begin.return_value = False
            with self.assertRaises(OSError):
                vault.make_touch(None, "qwiic")

    def test_gpio_adapter_preserves_button_polarity_and_encoder_direction(self):
        device = types.SimpleNamespace(steps=3, is_pressed=True, close=Mock())
        self.assertEqual(-vault.GPIOEncoder(device).position, 3)
        self.assertFalse(vault.GPIOButton(device).value)
        device.is_pressed = False
        self.assertTrue(vault.GPIOButton(device).value)

    def test_qt_encoder_ignores_failed_position_read(self):
        device = types.SimpleNamespace(position=-5)
        encoder = vault.QTEncoder(device)
        self.assertEqual(encoder.position, -5)
        device.position = -2**31
        self.assertEqual(encoder.position, -5)


if __name__ == "__main__":
    unittest.main()
