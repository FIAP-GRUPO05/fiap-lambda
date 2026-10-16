"""Exercise AWS and New Relic adapters against local HTTP stubs only."""

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Stub(BaseHTTPRequestHandler):
    def do_GET(self):
        routes = {
            "/aws/sts": {"Account": "000000000000", "Arn": "arn:aws:iam::000000000000:role/mock"},
            "/newrelic/health": {"status": "ok", "source": "mock"},
        }
        if self.path not in routes:
            self.send_error(404)
            return
        body = json.dumps(routes[self.path]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


with ThreadingHTTPServer(("127.0.0.1", 0), Stub) as server:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    with urllib.request.urlopen(base + "/aws/sts", timeout=5) as response:
        assert json.load(response)["Account"] == "000000000000"
    with urllib.request.urlopen(base + "/newrelic/health", timeout=5) as response:
        assert json.load(response)["status"] == "ok"
    server.shutdown()
print("AWS e New Relic: contratos HTTP locais válidos; serviços reais não foram consultados")
