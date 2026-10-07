"""MQTT bridge for the magic mirror.

Publishes state and frame previews; subscribes to commands.

Topics published:
  mirror/status   — retained JSON: {state, sim_mode, online}
  mirror/preview  — JSON: {data: base64_jpeg, ts: unix_ms}
  mirror/prompts  — retained JSON: {MIRROR_PERSONA, BOOTH_AI_PROMPT_SYSTEM, AI_FALLBACK_MESSAGE}

Topics subscribed:
  mirror/cmd      — JSON command payload (see _dispatch)

Requires paho-mqtt. Falls back silently if not installed.
Mosquitto must have a WebSocket listener on MQTT_WS_PORT for browser access:

  listener 1883
  listener 9001
  protocol websockets
"""
import base64
import io
import json
import threading
import time
from typing import Optional

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False


class MQTTBridge:
    PREVIEW_INTERVAL = __import__("config").MQTT_PREVIEW_INTERVAL_SEC
    STATUS_INTERVAL  = 2.0   # seconds between status publishes

    def __init__(self, mirror, host: str = "localhost", port: int = 1883):
        self.mirror = mirror
        self.host = host
        self.port = port
        self.client: Optional[object] = None
        self._running = False

        if not HAS_MQTT:
            return

        self.client = mqtt.Client(client_id="magic-mirror", clean_session=True,
                                  protocol=mqtt.MQTTv311)
        self.client.on_connect    = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message    = self._on_message

    # ------------------------------------------------------------------ hooks

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[MQTT] connected to {self.host}:{self.port}")
            client.subscribe("mirror/cmd")
            self._publish_prompts()
        else:
            print(f"[MQTT] connect failed rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            print(f"[MQTT] unexpected disconnect rc={rc}, will reconnect")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self._dispatch(payload)
        except Exception as e:
            print(f"[MQTT] message error: {e}")

    # --------------------------------------------------------------- dispatch

    def _dispatch(self, payload: dict):
        action = payload.get("action")
        m = self.mirror

        if action == "trigger":
            m._trigger_event.set()
        elif action == "photobooth":
            m._booth_event.set()
        elif action == "power_on":
            m._stop.clear()
        elif action == "power_off":
            m._stop.set()
        elif action == "display_text":
            m._overlay_text  = payload.get("text") or None
            m._overlay_image = None
        elif action == "display_image":
            raw = payload.get("data", "")
            if raw:
                from PIL import Image
                img_bytes = base64.b64decode(raw)
                m._overlay_image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                m._overlay_image = m._overlay_image.resize(
                    (m.matrix.width if hasattr(m.matrix, "width") else __import__("config").TOTAL_WIDTH,
                     m.matrix.height if hasattr(m.matrix, "height") else __import__("config").TOTAL_HEIGHT),
                )
            else:
                m._overlay_image = None
        elif action == "clear_overlay":
            m._overlay_text  = None
            m._overlay_image = None
        elif action == "config":
            import config as cfg
            key   = payload.get("key")
            value = payload.get("value")
            if key and hasattr(cfg, key):
                setattr(cfg, key, value)
                print(f"[MQTT] config {key} = {value!r}")
        elif action == "update_prompts":
            import config as cfg
            allowed = {"MIRROR_PERSONA", "BOOTH_AI_PROMPT_SYSTEM", "AI_FALLBACK_MESSAGE"}
            for k, v in payload.items():
                if k in allowed:
                    setattr(cfg, k, v)
                    print(f"[MQTT] prompt {k} updated")
            self._publish_prompts()

    # --------------------------------------------------------------- publish

    def _publish_prompts(self):
        if not self.client:
            return
        import config as cfg
        payload = json.dumps({
            "MIRROR_PERSONA":         cfg.MIRROR_PERSONA,
            "BOOTH_AI_PROMPT_SYSTEM": cfg.BOOTH_AI_PROMPT_SYSTEM,
            "AI_FALLBACK_MESSAGE":    cfg.AI_FALLBACK_MESSAGE,
        })
        self.client.publish("mirror/prompts", payload, qos=0, retain=True)

    def _publish_loop(self):
        last_status  = 0.0
        last_preview = 0.0

        while self._running:
            now = time.monotonic()

            if now - last_status >= self.STATUS_INTERVAL:
                try:
                    payload = json.dumps({
                        "state":    self.mirror.state.name,
                        "sim_mode": self.mirror.sim_mode,
                        "online":   True,
                    })
                    self.client.publish("mirror/status", payload, qos=0, retain=True)
                except Exception:
                    pass
                last_status = now

            if now - last_preview >= self.PREVIEW_INTERVAL:
                try:
                    frame = self.mirror._latest_frame
                    if frame is not None:
                        import cv2
                        from PIL import Image
                        small = cv2.resize(frame, (320, 240))
                        rgb   = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                        buf   = io.BytesIO()
                        Image.fromarray(rgb).save(buf, format="JPEG", quality=55)
                        b64 = base64.b64encode(buf.getvalue()).decode()
                        self.client.publish("mirror/preview", json.dumps({
                            "data": b64,
                            "ts":   int(time.time() * 1000),
                        }), qos=0, retain=False)
                except Exception:
                    pass
                last_preview = now

            time.sleep(0.25)

    # ----------------------------------------------------------------- public

    def start(self) -> None:
        if not self.client:
            print("[MQTT] paho-mqtt not installed — bridge disabled")
            return
        try:
            self.client.connect_async(self.host, self.port, keepalive=60)
            self.client.loop_start()
            self._running = True
            threading.Thread(target=self._publish_loop, daemon=True,
                             name="mqtt-publish").start()
            print(f"[MQTT] bridge started → {self.host}:{self.port}")
        except Exception as e:
            print(f"[MQTT] start failed: {e}")
            self.client = None

    def stop(self) -> None:
        self._running = False
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
