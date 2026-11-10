import json
import threading
import unittest
import urllib.error
import urllib.request

from scdash.server import make_server
from scdash.state import DashboardState
from scdash.status import parse_status


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = DashboardState()
        cls.httpd = make_server("127.0.0.1", 0, cls.state)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return r.status, r.headers.get("Content-Type"), r.read()

    def test_index(self):
        code, ctype, body = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"SC-Dash", body)

    def test_api(self):
        code, ctype, body = self.get("/api/state")
        self.assertIn("application/json", ctype)
        data = json.loads(body)
        self.assertIn("stats", data)
        self.assertIn("feeds", data)
        self.assertIn("missions", data)

    def test_static_assets(self):
        for p in ("/app.js", "/style.css", "/links.json", "/fonts/rajdhani-700.woff2"):
            self.assertEqual(self.get(p)[0], 200, p)

    def test_path_traversal_blocked(self):
        for p in ("/../server.py", "/%2e%2e/server.py", "/..%2fserver.py"):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self.get(p)
            self.assertEqual(cm.exception.code, 404)


class StatusParseTests(unittest.TestCase):
    def test_parse(self):
        s = parse_status({
            "summaryStatus": "disrupted",
            "systems": [
                {"name": "Platform", "status": "operational", "unresolvedIssues": []},
                {"name": "Persistent Universe", "status": "disrupted", "unresolvedIssues": [{"x": 1}]},
            ],
        })
        self.assertEqual(s["summary"], "disrupted")
        self.assertEqual(s["systems"][1], {"name": "Persistent Universe", "status": "disrupted", "issues": 1})


if __name__ == "__main__":
    unittest.main()
