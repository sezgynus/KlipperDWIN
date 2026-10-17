"""Opt-in network HTTP mirror and virtual encoder for Petrel.

Only the existing DWIN emulator is rendered. This server never owns GPIO,
serial, Moonraker, or UI state. Wheel/press travel through the normal UI queue.
When enabled, the viewer listens on all IPv4 interfaces by default; no
authentication is provided, so callers with network access control the UI.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from ipaddress import IPv4Address, IPv4Network
import json
import logging
import re
import subprocess
from threading import Lock, Thread
from time import monotonic

# Inline page is an immutable asset; no JS libraries or CDN requests required.
PAGE = "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>Petrel Remote Display</title>\n<style>\n  :root { color-scheme: dark; font-family: system-ui, sans-serif; }\n  body { background:#151719; color:#e8e8e8; margin:0; min-height:100vh; display:flex; flex-direction:column; align-items:center; gap:12px; }\n  header { padding:18px 12px 0; text-align:center; }\n  h1 { font-size:20px; font-weight:600; margin:0; }\n  p { font-size:13px; color:#a5acb1; margin:8px 0 0; }\n  #screen { display:block; width:min(272px, calc((100dvh - 216px)*272/480), calc(100vw - 32px)); height:auto; aspect-ratio:272/480; background:#090909; border:3px solid #555e68; border-radius:5px; object-fit:contain; image-rendering:auto; user-select:none; -webkit-user-drag:none; }\n  #status { font-size:12px; min-height:17px; color:#a5acb1; }\n  .view { display:flex; flex-direction:column; align-items:center; gap:9px; outline:none; touch-action:none; }\n  .controls { display:flex; gap:8px; width:min(272px, calc(100vw - 32px)); }\n  .controls button { flex:1; min-height:44px; border:1px solid #697580; border-radius:6px; background:#29313a; color:#e8e8e8; font:inherit; cursor:pointer; touch-action:manipulation; }\n  .controls button:hover { background:#394653; }\n  .controls button:active { background:#4b5e70; }\n  .controls button:focus-visible { outline:2px solid #8fc9ff; outline-offset:2px; }\n</style>\n</head>\n<body>\n<header><h1>Petrel Remote Display</h1>\n<p>Mouse wheel / CCW / CW = rotate · Middle click / Enter = press</p><p><a href=\"/maintenance-report.json\" download=\"maintenance-report.json\" style=\"color:#8fc9ff\">Download last diagnostic report</a> · <a href=\"/maintenance-test-trace.zip\" download=\"maintenance-test-trace.zip\" style=\"color:#8fc9ff\">Download test recording</a></p></header>\n<main id=\"view\" class=\"view\" tabindex=\"0\" aria-label=\"Virtual LCD\">\n<img id=\"screen\" alt=\"Petrel LCD live view\" draggable=\"false\" />\n<div class=\"controls\" role=\"group\" aria-label=\"Encoder controls\">\n<button type=\"button\" data-kind=\"rotate\" data-value=\"1\" aria-label=\"Rotate counterclockwise\">CCW</button>\n<button type=\"button\" data-kind=\"press\" aria-label=\"Press encoder\">Enter</button>\n<button type=\"button\" data-kind=\"rotate\" data-value=\"-1\" aria-label=\"Rotate clockwise\">CW</button>\n</div>\n<span id=\"status\" role=\"status\">Connecting…</span>\n</main>\n<script>\n(() => {\n  \"use strict\";\n  const view = document.getElementById(\"view\");\n  const screen = document.getElementById(\"screen\");\n  const status = document.getElementById(\"status\");\n  let wheel = 0, pending = 0, sending = false;\n  let alive = true;\n  function delay(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }\n  async function send(kind, value) {\n    try {\n      const response = await fetch(\"/input\", {\n        method:\"POST\", cache:\"no-store\", credentials:\"same-origin\",\n        headers:{\"Content-Type\":\"application/json\",\"X-Petrel-Remote\":\"1\"},\n        body:JSON.stringify(kind === \"press\" ? {kind} : {kind,value})\n      });\n      if (!response.ok) status.textContent = \"Input rejected (\"+response.status+\")\";\n    } catch {\n      status.textContent = \"Remote connection unavailable\";\n    }\n  }\n  async function drain() {\n    if (sending) return;\n    sending = true;\n    while (pending !== 0 && alive) {\n      const step = Math.max(-6, Math.min(6, pending));\n      pending -= step;\n      await send(\"rotate\", step);\n      await delay(35);\n    }\n    sending = false;\n  }\n  document.querySelectorAll(\".controls button\").forEach(button => {\n    button.addEventListener(\"click\", () => {\n      if (button.dataset.kind === \"press\") {\n        void send(\"press\");\n      } else {\n        pending = Math.max(-24, Math.min(24, pending + Number(button.dataset.value)));\n        void drain();\n      }\n    });\n  });\n  view.addEventListener(\"wheel\", event => {\n    event.preventDefault();\n    const pixels = event.deltaY * (event.deltaMode === 1 ? 33 : event.deltaMode === 2 ? 500 : 1);\n    wheel += pixels;\n    const steps = Math.trunc(wheel / 100);\n    if (steps) {\n      wheel -= steps * 100;\n      pending = Math.max(-24, Math.min(24, pending - steps));\n      void drain();\n    }\n  }, {passive:false});\n  view.addEventListener(\"mousedown\", event => {\n    if (event.button !== 1) return;\n    event.preventDefault();\n    void send(\"press\");\n  });\n  view.addEventListener(\"auxclick\", event => {\n    if (event.button === 1) event.preventDefault();\n  });\n  view.addEventListener(\"contextmenu\", event => event.preventDefault());\n  async function refresh() {\n    if (!alive) return;\n    if (document.hidden) { setTimeout(refresh, 850); return; }\n    const frame = new Image();\n    frame.onload = () => {\n      screen.src = frame.src;\n      status.textContent = \"Live · mouse wheel / middle click\";\n      setTimeout(refresh, 250);\n    };\n    frame.onerror = () => {\n      status.textContent = \"Waiting for LCD frame…\";\n      setTimeout(refresh, 800);\n    };\n    frame.src = \"/frame.jpg?t=\" + Date.now();\n  }\n  window.addEventListener(\"pagehide\", () => { alive = false; pending = 0; });\n  refresh();\n})();\n</script>\n</body>\n</html>"
DEFAULT_PORT = 8088
DEFAULT_HOST = "0.0.0.0"
MAX_EVENT_BYTES = 96
TAILSCALE_CGNAT = IPv4Network("100.64.0.0/10")


def resolve_bind_host(host):
    """Choose only an explicitly local address or the current Tailscale IP.

    Do not accept wildcards, arbitrary LAN interfaces, or externally supplied
    addresses. Fail closed when Tailscale is unavailable, never fall back
    to listening on all interfaces.
    """
    if host in ("127.0.0.1", "0.0.0.0"):
        return host
    if host != "tailscale":
        raise ValueError("Remote host must be 0.0.0.0, tailscale, or 127.0.0.1")
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True,
            check=True, timeout=3)
        address = result.stdout.strip()
        ip = IPv4Address(address)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise RuntimeError("Tailscale IPv4 unavailable; remote display not started") from error
    if ip not in TAILSCALE_CGNAT:
        raise RuntimeError("Tailscale returned an address outside 100.64.0.0/10")
    return str(ip)


class _HTTP(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class RemoteDisplayServer:
    """Idle when disabled; image conversion only for a requesting browser."""

    def __init__(self, emulator, enqueue, port=DEFAULT_PORT, host=DEFAULT_HOST, report_provider=None, trace_provider=None):
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("Invalid remote display port")
        if not callable(enqueue):
            raise ValueError("Input callback must be callable")
        self.host = resolve_bind_host(host)
        self.emulator = emulator
        self.enqueue = enqueue
        self.report_provider = report_provider
        self.trace_provider = trace_provider
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
                if parent.host == "0.0.0.0":
                    # The listener is intentionally reachable from all IPv4
                    # interfaces. Accept the address/hostname used by each
                    # caller, but reject malformed Host or incorrect port.
                    valid = (len(host) <= 270 and re.fullmatch(
                        r"[A-Za-z0-9_.-]+:" + str(parent.port), host) is not None)
                    allowed = (host,) if valid else ()
                else:
                    allowed = (parent.host + ":" + str(parent.port),)
                    if parent.host == "127.0.0.1":
                        allowed += ("localhost:" + str(parent.port),)
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
                elif self.path == "/maintenance-test-trace.zip":
                    # TEMPORARY MAINTENANCE TEST TRACE: existing trust boundary.
                    try:
                        raw = parent.trace_provider() if callable(parent.trace_provider) else None
                        if raw is None:
                            self.reply(404,b"Start test recording from Maintenance first")
                        elif not isinstance(raw,bytes) or len(raw)>10*1024*1024:
                            self.reply(503,b"Test recording unavailable")
                        else:
                            self.reply(200,raw,"application/zip")
                    except (OSError,ValueError,TypeError):
                        self.reply(503,b"Test recording unavailable")
                elif self.path == "/maintenance-report.json":
                    try:
                        raw = parent.report_provider() if callable(parent.report_provider) else None
                        if raw is None:
                            self.reply(404,b"Export a diagnostic report first")
                        elif not isinstance(raw,bytes) or len(raw)>65536:
                            self.reply(503,b"Diagnostic report unavailable")
                        else:
                            self.reply(200,raw,"application/json; charset=utf-8")
                    except (OSError,ValueError,TypeError):
                        self.reply(503,b"Diagnostic report unavailable")
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

        self.http = _HTTP((self.host, port), Handler)
        self.port = self.http.server_address[1]
        self.thread = Thread(target=self.http.serve_forever,
                             kwargs={"poll_interval": 0.15},
                             daemon=True, name="petrel-remote-http")
        self.thread.start()
        logging.info("Petrel Remote Display available on http://%s:%d", self.host, self.port)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)
