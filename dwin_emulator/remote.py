"""Opt-in localhost-only HTTP mirror and virtual encoder for Petrel.

Only the existing DWIN emulator is rendered. This server never owns GPIO,
serial, Moonraker, or UI state. Wheel/press travel through the normal UI queue.
Access is bound to loopback: use SSH port forwarding for remote access.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import logging
from threading import Lock, Thread
from time import monotonic

# Inline page is an immutable asset; no JS libraries or CDN requests required.
PAGE = "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>Petrel Remote Display</title>\n<style>\n  :root { color-scheme: dark; font-family: system-ui, sans-serif; }\n  body { background:#151719; color:#e8e8e8; margin:0; min-height:100vh; display:flex; flex-direction:column; align-items:center; gap:12px; }\n  header { padding:18px 12px 0; text-align:center; }\n  h1 { font-size:20px; font-weight:600; margin:0; }\n  p { font-size:13px; color:#a5acb1; margin:8px 0 0; }\n  #screen { display:block; width:min(272px, calc((100dvh - 140px)*272/480), calc(100vw - 32px)); height:auto; aspect-ratio:272/480; background:#090909; border:3px solid #555e68; border-radius:5px; object-fit:contain; image-rendering:auto; user-select:none; -webkit-user-drag:none; }\n  #status { font-size:12px; min-height:17px; color:#a5acb1; }\n  .view { display:flex; flex-direction:column; align-items:center; gap:9px; outline:none; touch-action:none; }\n</style>\n</head>\n<body>\n<header><h1>Petrel Remote Display</h1>\n<p>Scroll = encoder rotation · Middle click = encoder press</p></header>\n<main id=\"view\" class=\"view\" tabindex=\"0\" aria-label=\"Virtual LCD\">\n<img id=\"screen\" alt=\"Petrel LCD live view\" draggable=\"false\" />\n<span id=\"status\" role=\"status\">Connecting…</span>\n</main>\n<script>\n(() => {\n  \"use strict\";\n  const view = document.getElementById(\"view\");\n  const screen = document.getElementById(\"screen\");\n  const status = document.getElementById(\"status\");\n  let wheel = 0, pending = 0, sending = false;\n  let alive = true;\n  function delay(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }\n  async function send(kind, value) {\n    try {\n      const response = await fetch(\"/input\", {\n        method:\"POST\", cache:\"no-store\", credentials:\"same-origin\",\n        headers:{\"Content-Type\":\"application/json\",\"X-Petrel-Remote\":\"1\"},\n        body:JSON.stringify(kind === \"press\" ? {kind} : {kind,value})\n      });\n      if (!response.ok) status.textContent = \"Input rejected (\"+response.status+\")\";\n    } catch {\n      status.textContent = \"Remote connection unavailable\";\n    }\n  }\n  async function drain() {\n    if (sending) return;\n    sending = true;\n    while (pending !== 0 && alive) {\n      const step = Math.max(-6, Math.min(6, pending));\n      pending -= step;\n      await send(\"rotate\", step);\n      await delay(35);\n    }\n    sending = false;\n  }\n  view.addEventListener(\"wheel\", event => {\n    event.preventDefault();\n    const pixels = event.deltaY * (event.deltaMode === 1 ? 33 : event.deltaMode === 2 ? 500 : 1);\n    wheel += pixels;\n    const steps = Math.trunc(wheel / 100);\n    if (steps) {\n      wheel -= steps * 100;\n      pending = Math.max(-24, Math.min(24, pending - steps));\n      void drain();\n    }\n  }, {passive:false});\n  view.addEventListener(\"mousedown\", event => {\n    if (event.button !== 1) return;\n    event.preventDefault();\n    void send(\"press\");\n  });\n  view.addEventListener(\"auxclick\", event => {\n    if (event.button === 1) event.preventDefault();\n  });\n  view.addEventListener(\"contextmenu\", event => event.preventDefault());\n  async function refresh() {\n    if (!alive) return;\n    if (document.hidden) { setTimeout(refresh, 850); return; }\n    const frame = new Image();\n    frame.onload = () => {\n      screen.src = frame.src;\n      status.textContent = \"Live · mouse wheel / middle click\";\n      setTimeout(refresh, 250);\n    };\n    frame.onerror = () => {\n      status.textContent = \"Waiting for LCD frame…\";\n      setTimeout(refresh, 800);\n    };\n    frame.src = \"/frame.jpg?t=\" + Date.now();\n  }\n  window.addEventListener(\"pagehide\", () => { alive = false; pending = 0; });\n  refresh();\n})();\n</script>\n</body>\n</html>"
DEFAULT_PORT = 8088
MAX_EVENT_BYTES = 96


class _HTTP(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class RemoteDisplayServer:
    """Idle when disabled; image conversion only for a requesting browser."""

    def __init__(self, emulator, enqueue, port=DEFAULT_PORT):
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("Invalid remote display port")
        if not callable(enqueue):
            raise ValueError("Input callback must be callable")
        self.emulator = emulator
        self.enqueue = enqueue
        self._event_lock = Lock()
        self._last_event = 0.0
        self._closed = False
        parent = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format, *args):
                # No per-frame request logging in the UI's systemd journal.
                return

            def reply(self, status, body=b"", content_type="text/plain; charset=utf-8"):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy",
                                 "default-src 'none'; img-src 'self' data:; "
                                 "connect-src 'self'; style-src 'unsafe-inline'; "
                                 "script-src 'unsafe-inline'; base-uri 'none'; "
                                 "frame-ancestors 'none'")
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def trusted(self):
                # Reject DNS rebinding and cross-origin browser requests.
                host = self.headers.get("Host", "")
                allowed = ("127.0.0.1:" + str(parent.port),
                           "localhost:" + str(parent.port))
                if host not in allowed:
                    self.reply(403, b"Invalid Host")
                    return False
                origin = self.headers.get("Origin")
                if origin is not None and origin not in tuple("http://" + h for h in allowed):
                    self.reply(403, b"Invalid Origin")
                    return False
                return True

            def do_GET(self):
                if not self.trusted():
                    return
                if self.path == "/":
                    self.reply(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
                elif self.path.split("?", 1)[0] == "/frame.jpg":
                    try:
                        # A snapshot is copied under the emulator's lock. JPEG
                        # encoding runs outside that lock and off the UI thread.
                        image, _sequence = parent.emulator.snapshot()
                        output = BytesIO()
                        image.convert("RGB").save(output, "JPEG", quality=80)
                        self.reply(200, output.getvalue(), "image/jpeg")
                    except (RuntimeError, OSError, ValueError):
                        self.reply(503, b"LCD framebuffer unavailable")
                else:
                    self.reply(404, b"Not found")

            def do_POST(self):
                if not self.trusted():
                    return
                if self.path != "/input":
                    self.reply(404, b"Not found")
                    return
                if (self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json"
                        or self.headers.get("X-Petrel-Remote") != "1"):
                    self.reply(415, b"JSON and remote-input header required")
                    return
                try:
                    length = int(self.headers.get("Content-Length", ""))
                except ValueError:
                    self.reply(400, b"Invalid content length")
                    return
                if not 1 <= length <= MAX_EVENT_BYTES:
                    self.reply(413, b"Invalid input length")
                    return
                try:
                    value = json.loads(self.rfile.read(length))
                except (ValueError, UnicodeError):
                    self.reply(400, b"Invalid JSON")
                    return
                if not isinstance(value, dict) or not (
                    (set(value) == {"kind"} and value.get("kind") == "press")
                    or (set(value) == {"kind", "value"}
                        and value.get("kind") == "rotate"
                        and type(value.get("value")) is int
                        and 0 < abs(value["value"]) <= 6)
                ):
                    self.reply(400, b"Unsupported encoder input")
                    return
                with parent._event_lock:
                    if monotonic() - parent._last_event < 0.025:
                        self.reply(429, b"Input rate limited")
                        return
                    try:
                        accepted = bool(parent.enqueue(value["kind"], value.get("value", 1)))
                    except Exception:
                        accepted = False
                    if accepted:
                        parent._last_event = monotonic()
                self.reply(202 if accepted else 409,
                           b"queued" if accepted else b"UI input unavailable")

        self.http = _HTTP(("127.0.0.1", port), Handler)
        self.port = self.http.server_address[1]
        self.thread = Thread(target=self.http.serve_forever,
                             kwargs={"poll_interval": 0.15},
                             daemon=True, name="petrel-remote-http")
        self.thread.start()
        logging.info("Petrel Remote Display available on http://127.0.0.1:%d", self.port)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)
