"""Local-only integration check. Requires optional amqtt, no course broker or hardware.

Run from the project root: python tests/mqtt_smoke.py
"""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amqtt.broker import Broker
import paho.mqtt.client as mqtt
from app import connect_mqtt, create_app
from state import GardenState


async def until(predicate, description):
    for _ in range(100):
        if predicate():
            return
        await asyncio.sleep(.05)
    raise AssertionError(description)


async def main():
    broker = Broker({"listeners":{"default":{"type":"tcp","bind":"127.0.0.1:18883"}},
                     "plugins":{"amqtt.plugins.authentication.AnonymousAuthPlugin":{"allow_anonymous":True}}})
    await broker.start()
    now = [0.0]  # hand-driven clock so meters move only when the test says so
    state, connection = GardenState(clock=lambda: now[0]), {"connected":False}
    args = SimpleNamespace(team="localtest",broker="127.0.0.1",mqtt_port=18883,username="",password="")
    sender = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    sender.connect_async("127.0.0.1",18883,15)
    sender.loop_start()
    receiver = None
    topic = "IDD/localtest/garden"
    send = lambda role, payload: sender.publish(f"{topic}/{role}", json.dumps(payload))
    snap = state.snapshot

    async def hold(role, payload, key):
        """Send the same input twice a second until its meter is full."""
        for tick in range(1, 9):  # small steps, so a slow delivery cannot make the station look silent
            now[0] += .5
            send(role, payload)
            await until(lambda: snap()["meter"] >= 12 * tick, f"{role} meter did not reach {12 * tick}")
            await asyncio.sleep(.05)
        assert snap()[key], f"{role} input not shown as active"

    try:
        await until(sender.is_connected, "test publisher did not connect")
        sent = sender.publish(f"{topic}/water",json.dumps({"tilt":100}),qos=1,retain=True)
        await until(sent.is_published, "retained seed not acknowledged")
        receiver = connect_mqtt(args,state,connection)
        await until(lambda: connection["connected"], "display did not connect")
        await asyncio.sleep(.2)
        assert snap()["active"] == 0, "an old retained message must not count as a live station"
        send("water", {"tilt":100})
        await until(lambda: snap()["stations"]["water"], "water station not seen")
        sender.publish(f"{topic}/water", "invalid JSON")
        sender.publish(f"{topic}/water", "[]")
        sender.publish(f"{topic}/water", json.dumps({"tilt":500}))
        sender.publish("IDD/otherteam/garden/sun", json.dumps({"on":True}))
        await hold("water", {"tilt":100}, "pouring")
        send("water", {"tilt":0})
        await until(lambda: snap()["step"] == "mulch", "tipping the can back did not finish the water step")
        for _ in range(3):
            send("mulch", {"amount":10})
        await until(lambda: snap()["step"] == "sun", "mulch did not finish")
        send("sun", {"on":True})
        await until(lambda: snap()["sun"], "sun not seen")
        await hold("sun", {"on":True}, "sun")
        send("sun", {"on":False})
        await until(lambda: snap()["cycle"] == 1, "letting go of the sun did not finish the round")
        api = create_app(state,connection,"localtest").test_client().get("/api/state").json
        assert (api["mode"], api["cycle"], api["step"]) == ("growing", 1, "water"), api
        counts = {name.rsplit("/", 1)[1]: entry["count"] for name, entry in api["topics"].items()}
        assert counts["water"] >= 9 and counts["mulch"] == 3 and counts["sun"] >= 9, counts
        assert any(not line["ok"] for line in api["log"]) or counts["water"] >= 12, "rejected messages should be counted and shown"
        now[0] += 2
        send("sun", {"on":True})
        await until(lambda: snap()["sun"], "out-of-turn sun not seen")
        assert snap()["mode"] == "withered", "sun out of turn did not wither the plant"
        print("PASS: local MQTT -> rules -> HTTP; one full round in order, then a wither; retained/malformed/foreign messages ignored")
    finally:
        sender.disconnect()
        sender.loop_stop()
        if receiver:
            receiver.disconnect()
            receiver.loop_stop()
        await broker.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
