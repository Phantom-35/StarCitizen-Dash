"""Tiny HTTP server: static files + one JSON endpoint."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from scdash.state import DashboardState

log = logging.getLogger(__name__)

MAX_WAIT = 25.0  # seconds a long poll may be held open

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")


def make_handler(state: DashboardState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SC-Dash"
        protocol_version = "HTTP/1.1"  # keep-alive: no new TCP connection for every poll
        timeout = 60  # drop idle keep-alive connections (e.g. closed dashboard window)

        def log_message(self, fmt, *args):  # keep the console quiet
            log.debug("%s - %s", self.address_string(), fmt % args)

        def _send(self, code: int, body: bytes, ctype: str, cache: str = "no-store") -> None:
            self.send_response(code)
            if code != 204:  # "No Content" must not carry entity headers
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            url = urlparse(self.path)
            path = url.path
            if path == "/api/state":
                # The dashboard polls every 2 s; answer with an empty 204 while nothing changed.
                query = parse_qs(url.query)
                since = query.get("since", [""])[0]
                if since and since == state.token:
                    # Long poll: hold the request until something happens (max. MAX_WAIT s),
                    # so new events reach the dashboard immediately instead of on the next poll.
                    try:
                        wait = min(MAX_WAIT, max(0.0, float(query.get("wait", ["0"])[0])))
                    except ValueError:
                        wait = 0.0
                    if not (wait and state.wait_for_change(since, wait)):
                        return self._send(204, b"", "application/json; charset=utf-8")
                body = json.dumps(state.snapshot(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                return self._send(200, body, "application/json; charset=utf-8")
            if path == "/":
                path = "/index.html"

            full = os.path.normpath(os.path.join(WEB_DIR, path.lstrip("/")))
            if not full.startswith(WEB_DIR + os.sep) or not os.path.isfile(full):
                return self._send(404, b"not found", "text/plain; charset=utf-8")
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("json"):
                ctype += "; charset=utf-8"
            cache = "public, max-age=604800, immutable" if full.endswith(".woff2") else "no-store"
            with open(full, "rb") as fh:
                return self._send(200, fh.read(), ctype, cache)

    return Handler


def make_server(host: str, port: int, state: DashboardState) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    httpd.daemon_threads = True
    return httpd
