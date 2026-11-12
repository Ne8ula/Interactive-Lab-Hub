import unittest
from state import BLOOM_SECONDS, CYCLES, GRACE, WITHER_SECONDS, GardenState
from app import create_app


class GardenTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.state = GardenState(clock=lambda: self.now)

    def hold(self, seconds, tilt=0, sun=False):
        """Both Pis keep reporting these inputs for a while, four times a second."""
        for _ in range(round(seconds * 4)):
            self.now += .25
            self.assertTrue(self.state.water(tilt))
            self.assertTrue(self.state.sun(sun))
        return self.state.snapshot()

    def round_in_order(self):
        self.hold(5, tilt=100)
        self.hold(.5)
        for _ in range(3):
            self.state.mulch(10)
        self.hold(5, sun=True)
        return self.hold(.5)

    def test_water_fills_only_while_pouring_and_ends_when_tipped_back(self):
        self.assertEqual(self.hold(3, tilt=20)["meter"], 0)        # not tipped far enough
        now = self.hold(5, tilt=100)
        self.assertEqual((now["meter"], now["step"], now["pouring"]), (100, "water", True))
        self.assertIn("Turn the dial back", now["hint"])
        self.assertEqual(self.hold(.5)["step"], "mulch")

    def test_half_tilt_pours_at_half_speed(self):
        self.assertEqual(self.hold(4.25, tilt=50)["meter"], 50)  # the first quarter second passes before the first report

    def test_three_rounds_in_order_bloom_then_a_new_seed(self):
        for done in range(1, CYCLES + 1):
            now = self.round_in_order()
            self.assertEqual(now["cycle"], done)
        self.assertEqual(now["mode"], "bloomed")
        self.assertEqual(self.hold(BLOOM_SECONDS + 1)["mode"], "growing")
        self.assertEqual(self.state.snapshot()["cycle"], 0)

    def test_sun_out_of_turn_withers_and_loses_progress(self):
        self.round_in_order()
        self.hold(GRACE + .5)                       # round 2, time to water
        now = self.hold(.5, sun=True)
        self.assertEqual((now["mode"], now["reason"]), ("withered", "Sun came when it was time to water."))
        now = self.hold(WITHER_SECONDS + 1)
        self.assertEqual((now["mode"], now["cycle"], now["step"]), ("growing", 0, "water"))

    def test_water_and_mulch_out_of_turn_wither(self):
        self.hold(GRACE + .5)
        self.state.mulch(3)
        self.assertEqual(self.state.snapshot()["reason"], "Mulch came when it was time to water.")
        self.setUp()
        self.hold(5, tilt=100)
        self.hold(GRACE + .5)                       # time to mulch
        self.assertEqual(self.hold(.5, tilt=100)["reason"], "Water came when it was time to mulch.")

    def test_grace_period_forgives_trailing_input(self):
        self.state.mulch(5)                         # the very start
        self.assertEqual(self.state.snapshot()["mode"], "growing")
        self.hold(5, tilt=100)
        self.hold(.5)
        for _ in range(4):                          # one rub more than needed
            self.state.mulch(10)
        now = self.state.snapshot()
        self.assertEqual((now["mode"], now["step"]), ("growing", "sun"))

    def test_withered_plant_waits_until_everyone_lets_go(self):
        self.hold(GRACE + .5, sun=True)
        now = self.hold(WITHER_SECONDS + 2, sun=True)
        self.assertEqual(now["mode"], "withered")
        self.assertIn("let go", now["hint"])
        self.assertEqual(self.hold(.5)["mode"], "growing")

    def test_a_silent_station_stops_pouring(self):
        self.state.water(100)
        for _ in range(20):
            self.now += .25
            now = self.state.snapshot()
        self.assertFalse(now["pouring"])
        self.assertFalse(now["stations"]["water"])
        self.assertLess(now["meter"], 100)

    def test_reject_malformed_messages(self):
        for bad in (True, 101, -1, "5", 2.5, None):
            self.assertFalse(self.state.water(bad), bad)
        for bad in (1, 0, "on", None):
            self.assertFalse(self.state.sun(bad), bad)
        for bad in (11, -1, True, "1", 1.5, None):
            self.assertFalse(self.state.mulch(bad), bad)
        self.assertEqual(self.state.snapshot()["active"], 0)

    def test_hints_and_labels_follow_whichever_device_holds_a_role(self):
        self.state.water(0, "pi")
        now = self.state.snapshot()
        self.assertEqual(now["sources"], {"water": "pi", "mulch": None, "sun": None})
        self.assertIn("Turn the dial clockwise", now["hint"])
        self.state.water(0, "phone")
        self.assertIn("Slide the bar right", self.state.snapshot()["hint"])
        self.state.water(0, "toaster")              # an unknown sender is accepted but not labelled
        self.assertIsNone(self.state.snapshot()["sources"]["water"])
        self.hold(5, tilt=100)
        self.hold(.5)
        self.assertIn("joystick", self.state.snapshot()["hint"])
        self.state.mulch(0, "phone")
        self.assertIn("Rub the phone screen", self.state.snapshot()["hint"])

    def test_phone_routes_publish_only_valid_messages_with_their_origin(self):
        sent = []
        client = create_app(self.state, {"connected": True}, "test", publish=lambda r, p: sent.append((r, p)) or True).test_client()
        good = {"water": {"tilt": 60}, "mulch": {"amount": 0}, "sun": {"on": True}}
        bad = {"water": [{"tilt": 101}, {"tilt": True}, {"on": True}], "mulch": [{"amount": 11}, {"amount": False}, {}],
               "sun": [{"on": 1}, {"on": "yes"}, [True]]}
        for role in good:
            self.assertEqual(client.get(f"/phone/{role}").status_code, 200)
            self.assertEqual(client.post(f"/api/phone/{role}", json=good[role]).status_code, 204)
            for payload in bad[role]:
                self.assertEqual(client.post(f"/api/phone/{role}", json=payload).status_code, 400, payload)
        self.assertEqual(client.get("/phone/fire").status_code, 404)
        self.assertEqual(client.post("/api/phone/fire", json={"on": True}).status_code, 404)
        self.assertEqual(sent, [(role, {**payload, "from": "phone"}) for role, payload in good.items()])
        offline = create_app(self.state, {"connected": False}, "test").test_client()
        self.assertEqual(offline.post("/api/phone/sun", json={"on": True}).status_code, 503)
        self.assertEqual(self.state.snapshot()["active"], 0)  # nothing bypasses MQTT

    def test_http_live_and_demo_are_distinct(self):
        client = create_app(self.state, {"connected": False}, "test").test_client()
        self.assertEqual(client.get("/").status_code, 200)
        response = client.get("/api/state")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertFalse(response.json["demo"])
        self.assertIn("Water first", response.json["hint"])
        demo = create_app(GardenState(), {"connected": False}, "test", True).test_client()
        self.assertTrue(demo.get("/api/state").json["demo"])
        self.assertTrue(demo.get("/api/state").json["pouring"])  # the autopilot starts by watering


if __name__ == "__main__":
    unittest.main()
