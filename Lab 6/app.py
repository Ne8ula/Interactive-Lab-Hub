"""Laptop garden display and phone relay. Run --demo for a labeled offline preview."""
import argparse
import atexit
from collections import deque
import json
import logging
import threading
import time
import uuid
from flask import Flask, abort, jsonify, render_template, request
import paho.mqtt.client as mqtt
from common import MAX_MULCH, ROLES, mqtt_arguments, prefix
from state import GardenState

log = logging.getLogger("garden")

# What a phone may send for each role, checked before anything is published.
PHONE_FIELDS = {"water": ("tilt", lambda v: type(v) is int and 0 <= v <= 100),
                "mulch": ("amount", lambda v: type(v) is int and 0 <= v <= MAX_MULCH),
                "sun": ("on", lambda v: type(v) is bool)}


def new_connection():
    """Shared record of the MQTT link: status, a count per topic, and recent messages for the display."""
    return {"connected": False, "topics": {}, "log": deque(maxlen=12)}


def autopilot(state):
    """Demo only: play a perfect run so the display can be previewed without stations."""
    now = state.snapshot()
    full = now["meter"] >= 100
    state.water(80 if now["mode"] == "growing" and now["step"] == "water" and not full else 0, "phone")
    state.sun(now["mode"] == "growing" and now["step"] == "sun" and not full, "phone")
    state.mulch(2 if now["mode"] == "growing" and now["step"] == "mulch" else 0, "phone")


def create_app(state, connection, team, demo=False, publish=None):
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/state")
    def current_state():
        if demo:
            autopilot(state)
        result = state.snapshot()
        result.update(team=team, demo=demo, mqtt_connected=connection["connected"],
                      topics=connection.get("topics", {}), log=list(connection.get("log", ())))
        response = jsonify(result)
        response.headers["Cache-Control"] = "no-store"
        return response

    # A phone can stand in for any station. The laptop publishes what it sends to the
    # broker on the same topic a Pi would use; it only reaches the garden through the subscription.
    @app.get("/phone/<role>")
    def phone_page(role):
        if role not in ROLES:
            abort(404)
        return render_template("phone.html", role=role)

    @app.post("/api/phone/<role>")
    def phone_message(role):
        if role not in ROLES:
            abort(404)
        field, valid = PHONE_FIELDS[role]
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not valid(data.get(field)):
            abort(400)
        if not publish or not publish(role, {field: data[field], "from": "phone"}):
            abort(503)
        return "", 204

    return app


def connect_mqtt(args, state, connection):
    root = prefix(args.team)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"garden-display-{uuid.uuid4().hex[:10]}")
    client.username_pw_set(args.username, args.password)
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    handlers = {"water": lambda d: state.water(d.get("tilt"), d.get("from")),
                "mulch": lambda d: state.mulch(d.get("amount"), d.get("from")),
                "sun": lambda d: state.sun(d.get("on"), d.get("from"))}

    def on_connect(client, userdata, flags, reason_code, properties):
        connection["connected"] = not reason_code.is_failure
        if reason_code.is_failure:
            log.error("MQTT connection refused: %s", reason_code)
            return
        client.subscribe([(f"{root}/{role}", 0) for role in ROLES])
        log.info("MQTT connected; subscribed to %s/{%s}", root, ",".join(ROLES))

    def on_disconnect(client, userdata, flags, reason_code, properties):
        connection["connected"] = False
        log.warning("MQTT disconnected: %s; reconnecting automatically", reason_code)

    def on_message(client, userdata, message):
        # Old retained messages are never evidence of someone acting now.
        if message.retain or len(message.payload) > 4096:
            return
        head, _, role = message.topic.rpartition("/")
        if head != root or role not in handlers:
            return
        text = message.payload.decode("utf-8", "replace")[:120]
        try:
            data = json.loads(message.payload)
        except (ValueError, UnicodeError):
            data = None
        ok = isinstance(data, dict) and handlers[role](data)
        # Evidence trail: count every message; show and print one only when it differs from
        # the last on its topic, so once-a-second heartbeats do not bury the real changes.
        topic = connection.setdefault("topics", {}).setdefault(message.topic, {"count": 0, "last": None})
        topic["count"] += 1
        if text != topic["last"]:
            topic["last"] = text
            connection.setdefault("log", deque(maxlen=12)).append(
                {"time": time.strftime("%H:%M:%S"), "topic": message.topic, "payload": text, "ok": bool(ok)})
            log.info("MQTT in   %s %s%s", message.topic, text, "" if ok else "   (rejected)")

    def on_connect_fail(client, userdata):
        log.warning("Broker unavailable; retrying. Check network, host and port.")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.on_connect_fail = on_connect_fail
    client.connect_async(args.broker, args.mqtt_port, keepalive=15)
    client.loop_start()
    return client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mqtt_arguments(parser)
    parser.add_argument("--demo", action="store_true", help="Offline simulated preview, not lab evidence")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)  # not 5000: macOS AirPlay Receiver holds it
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # keep the terminal for MQTT traffic
    state, connection = GardenState(), new_connection()
    publish = None
    if not args.demo:
        client = connect_mqtt(args, state, connection)
        atexit.register(lambda: (client.disconnect(), client.loop_stop()))
        root = prefix(args.team)

        last_out = {}

        def publish(role, payload):
            text = json.dumps(payload)
            sent = client.is_connected() and client.publish(f"{root}/{role}", text).rc == mqtt.MQTT_ERR_SUCCESS
            if sent and last_out.get(role) != text:  # print changes, not every heartbeat
                last_out[role] = text
                log.info("MQTT out  %s/%s %s   (for a phone)", root, role, text)
            return sent

        def broadcast():
            """Tell the stations whose turn it is, so the Pi can show it on its own hardware."""
            while True:
                time.sleep(.5)
                if client.is_connected():
                    now = state.snapshot()
                    client.publish(f"{root}/state",
                                   json.dumps({key: now[key] for key in ("mode", "cycle", "step", "meter", "hint")}))

        threading.Thread(target=broadcast, daemon=True).start()
    log.info("Open http://localhost:%s | mode: %s", args.port, "DEMO / simulated" if args.demo else "live stations")
    create_app(state, connection, args.team, args.demo, publish).run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
