import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from execution_logging import run_logged
from execution_replay import replan
from product_pipeline import run as solve
from scheduler import EXAMPLE

ROOT = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def send(self, code, obj, kind="application/json"):
        content = (json.dumps(obj) if kind == "application/json" else obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.path.startswith("/static/"):
            base = (ROOT / "static").resolve()
            path = (ROOT / unquote(urlsplit(self.path).path).lstrip("/")).resolve()
            if not path.is_relative_to(base) or not path.is_file():
                return self.send(404, {"error": "Not found"})
            content = path.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            )
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if self.path == "/":
            self.send(200, (ROOT / "dashboard.html").read_text(encoding="utf-8"), "text/html")
        elif self.path == "/example":
            self.send(200, EXAMPLE)
        elif self.path == "/evidence":
            report = json.loads((ROOT / "artifacts/shipping/benchmark.json").read_text())
            demo = ROOT / "artifacts/shipping/quantum_demo.json"
            if demo.exists():
                report["cases"].append(json.loads(demo.read_text()))
            self.send(200, report)
        elif self.path == "/presentation":
            self.send(200, (ROOT / "docs/DEMO.md").read_text(encoding="utf-8"), "text/plain")
        else:
            self.send(404, {"error": "Not found"})

    def do_POST(self):
        if self.path not in ("/solve", "/replan"):
            return self.send(404, {"error": "Not found"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2000000:
                raise ValueError("Request size must be between 1 and 2000000 bytes")
            request = json.loads(self.rfile.read(size))
            if not isinstance(request, dict):
                raise ValueError("Scenario must be a JSON object")
            self.send(
                200, run_logged(self.path, request, replan if self.path == "/replan" else solve)
            )
        except (ValueError, KeyError, TypeError) as e:
            self.send(400, {"error": str(e)})
        except Exception:
            self.send(500, {"error": "Solver or validation failed; no schedule accepted."})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    print(f"Planner: http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
