"""Tellolo M1 local web app (stdlib server). Run ./run.sh -> http://localhost:8010"""
import json, os, re, sys, traceback
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline
from providers import get_provider
ST = os.path.join(pipeline.HERE, "static")
class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ct="application/json"):
        if not isinstance(body, bytes): body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_HEAD(self):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", "0"); self.end_headers()
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/healthz": return self._send(200, b"ok", "text/plain")
        if path == "/": path = "/index.html"
        if path == "/api/info": return self._send(200, {"provider": get_provider().name})
        if path == "/summary": path = "/summary.html"
        try:
            if path.startswith("/api/story/"): return self._send(200, pipeline.load(path.rsplit("/", 1)[1]))
            if path == "/api/summary":
                c = (re.search(r"child=([\w-]+)", self.path) or [None, None])[1]
                rows = pipeline.summary("all=1" in self.path, c)
                for r in rows: r["child_name"] = pipeline.child_name(r.get("child"))
                return self._send(200, {"child": c, "child_name": pipeline.child_name(c), "rows": rows})
        except Exception as e: return self._err(e)
        f = os.path.realpath(os.path.join(ST, path.lstrip("/")))
        if not f.startswith(ST) or not os.path.isfile(f): return self.send_error(404)
        ct = {"html": "text/html; charset=utf-8", "png": "image/png", "js": "text/javascript", "json": "application/json"}.get(f.rsplit(".", 1)[-1], "application/octet-stream")
        self._send(200, open(f, "rb").read(), ct)
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            if self.path == "/api/story":
                j = json.loads(body); tw = [w.strip() for w in j["trouble_words"] if w.strip()]
                return self._send(200, pipeline.make_story(j["lang"], j.get("level", "beginner"), tw, j.get("interests", []), child=j.get("child"), hero=j.get("hero")))
            if self.path == "/api/images":
                sid = json.loads(body)["id"]; pipeline.load(sid); pipeline.start_images(sid); return self._send(202, {"id": sid, "status": "running"})
            if self.path == "/api/profile":
                j = json.loads(body); return self._send(200, pipeline.save_profile(j["child"], j.get("name")))
            if self.path == "/api/next":
                return self._send(200, pipeline.make_next_story(json.loads(body)["id"]))
            if self.path == "/api/read":
                msg = BytesParser(policy=default).parsebytes(b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body)
                f = {p.get_param("name", header="content-disposition"): p.get_payload(decode=True) for p in msg.iter_parts()}
                return self._send(200, pipeline.read_page(f["id"].decode(), int(f["page"]), f["audio"]))
            self.send_error(404)
        except Exception as e: self._err(e)
    def _err(self, e):
        from providers.meta import MetaError
        if isinstance(e, MetaError): return self._send(502, {"error": str(e), "retryable": e.retryable})
        if isinstance(e, (ValueError, KeyError, FileNotFoundError)): return self._send(400, {"error": f"Bad request: {e}"[:300], "retryable": False})
        traceback.print_exc(); self._send(500, {"error": "Something went wrong on the server; please try again.", "retryable": True})
if __name__ == "__main__":
    if os.environ.get("RENDER"): os.environ.setdefault("TELLOLO_PROVIDER", "meta")
    for d in ("data", os.path.join("static", "out")): os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), d), exist_ok=True)
    port = int(os.environ.get("PORT", 8010)); host = os.environ.get("HOST") or ("0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    print(f"Tellolo on http://{host}:{port} provider={os.environ.get('TELLOLO_PROVIDER', 'mock')}", flush=True)
    srv = ThreadingHTTPServer((host, port), H); srv.daemon_threads = True
    print("listening", flush=True); srv.serve_forever()
