"""Tellolo M1 local web app (stdlib server). Run ./run.sh -> http://localhost:8010"""
import hmac, json, os, re, shutil, sys, traceback
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline
from providers import get_provider
ST = os.path.join(pipeline.HERE, "static")
PASS = os.environ.get("TELLOLO_PASSCODE", "")
MAX_JSON, MAX_AUDIO = 16_000, 2_000_000  # bytes; 60 s of browser opus is well under 1 MB
HDRS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"}
def problem():
    """Why the server can't do real work, or None. Drives /healthz so a bad deploy shows up on Render."""
    if os.environ.get("TELLOLO_PROVIDER", "mock").lower() == "meta" and not os.environ.get("META_API_KEY"): return "META_API_KEY not set"
    if not shutil.which("ffmpeg"): return "ffmpeg not on PATH"
    if os.environ.get("RENDER") and not PASS: return "TELLOLO_PASSCODE not set (required when hosted)"
class H(BaseHTTPRequestHandler):
    timeout = 15  # a client that stalls mid-request can't hold a thread forever
    def log_message(self, fmt, *a):  # no query strings in logs: they carry child ids
        sys.stderr.write("%s %s %s\n" % (self.command, self.path.split("?")[0], a[1] if len(a) > 1 else ""))
    def _send(self, code, body, ct="application/json"):
        if not isinstance(body, bytes): body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(body)))
        for k, v in HDRS.items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)
    def _q(self, k):
        m = re.search(r"[?&]" + k + r"=([\w-]+)", self.path); return m and m[1]
    def _authed(self):
        """Every API call needs the X-Tellolo-Pass header. Browsers can't send a custom header cross-site without a
        CORS preflight (which we never allow), so this also blocks CSRF. When TELLOLO_PASSCODE is set it must match."""
        got = self.headers.get("X-Tellolo-Pass")
        if os.environ.get("RENDER") and not PASS:
            self._send(503, {"error": "Server not configured (no passcode).", "retryable": False}); return False
        if got is None or (PASS and not hmac.compare_digest(got.encode(), PASS.encode())):
            self._send(401, {"error": "Passcode needed.", "passcode": True, "retryable": False}); return False
        return True
    def do_HEAD(self):
        ok = self.path.split("?")[0] in ("/", "/healthz")
        self.send_response(200 if ok else 404); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", "0"); self.end_headers()
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/healthz":
            p = problem(); return self._send(503 if p else 200, (p or "ok").encode(), "text/plain")
        if path == "/": path = "/index.html"
        if path == "/summary": path = "/summary.html"
        if path.startswith("/api/") and not self._authed(): return
        try:
            if path == "/api/info": return self._send(200, {"provider": get_provider().name})
            if path.startswith("/api/story/"): return self._send(200, pipeline.load(path.rsplit("/", 1)[1], self._q("child")))
            if path == "/api/summary":
                c = self._q("child"); everyone = self._q("all") == "1" and self.client_address[0] == "127.0.0.1" and not os.environ.get("RENDER")
                rows = pipeline.summary(everyone, c) if (c or everyone) else []  # no child -> nothing; all=1 only on a local run
                for r in rows: r["child_name"] = pipeline.child_name(r.get("child"))
                return self._send(200, {"child": c, "child_name": pipeline.child_name(c), "rows": rows})
            if path.startswith("/api/"): return self.send_error(404)
        except Exception as e: return self._err(e)
        f = os.path.realpath(os.path.join(ST, path.lstrip("/")))
        if os.path.commonpath([f, ST]) != ST or not os.path.isfile(f): return self.send_error(404)
        if path.startswith("/out/") and not f.endswith(".png"): return self.send_error(404)  # runtime story data is API-only
        ct = {"html": "text/html; charset=utf-8", "png": "image/png", "js": "text/javascript", "json": "application/json"}.get(f.rsplit(".", 1)[-1], "application/octet-stream")
        self._send(200, open(f, "rb").read(), ct)
    def do_POST(self):
        if not self._authed(): return
        cl = self.headers.get("Content-Length", "")
        n = int(cl) if cl.isdigit() else -1
        if not 0 <= n <= (MAX_AUDIO if self.path == "/api/read" else MAX_JSON):
            self.close_connection = True; return self._send(413, {"error": "That request is too big.", "retryable": False})
        body = self.rfile.read(n); ct = self.headers.get("Content-Type", "")
        try:
            if self.path == "/api/read":
                if not ct.startswith("multipart/form-data"): raise ValueError("expected a recording")
                msg = BytesParser(policy=default).parsebytes(b"Content-Type: " + ct.encode() + b"\r\n\r\n" + body)
                f = {p.get_param("name", header="content-disposition"): p.get_payload(decode=True) for p in msg.iter_parts()}
                child = f["child"].decode() if f.get("child") else None
                return self._send(200, pipeline.read_page(f["id"].decode(), int(f["page"]), f["audio"], child=child))
            if not ct.startswith("application/json"): raise ValueError("expected JSON")
            j = json.loads(body)
            if not isinstance(j, dict): raise ValueError("expected a JSON object")
            if self.path == "/api/story":
                return self._send(200, pipeline.make_story(j.get("lang"), j.get("level", "beginner"), j.get("trouble_words"), j.get("interests", []), child=j.get("child"), hero=j.get("hero")))
            if self.path == "/api/images":
                sid = j["id"]; pipeline.load(sid, j.get("child")); return self._send(202, {"id": sid, "status": "running" if pipeline.start_images(sid) else "already started"})
            if self.path == "/api/profile":
                return self._send(200, pipeline.save_profile(j["child"], j.get("name")))
            if self.path == "/api/forget":
                return self._send(200, pipeline.forget(j["child"]))
            if self.path == "/api/next":
                return self._send(200, pipeline.make_next_story(j["id"], child=j.get("child")))
            self.send_error(404)
        except Exception as e: self._err(e)
    def _err(self, e):
        from providers.meta import MetaError
        if isinstance(e, MetaError): return self._send(502, {"error": str(e), "retryable": e.retryable})
        if isinstance(e, (ValueError, KeyError, IndexError, TypeError)): return self._send(400, {"error": f"Bad request: {e}"[:200], "retryable": False})
        traceback.print_exc(); self._send(500, {"error": "Something went wrong on the server; please try again.", "retryable": True})
if __name__ == "__main__":
    if os.environ.get("RENDER"): os.environ.setdefault("TELLOLO_PROVIDER", "meta")
    for d in ("data", os.path.join("static", "out")): os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), d), exist_ok=True)
    pipeline.purge()
    port = int(os.environ.get("PORT", 8010)); host = os.environ.get("HOST") or ("0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    print(f"Tellolo on http://{host}:{port} provider={os.environ.get('TELLOLO_PROVIDER', 'mock')} passcode={'on' if PASS else 'off'}", flush=True)
    if problem(): print("WARNING:", problem(), flush=True)
    srv = ThreadingHTTPServer((host, port), H); srv.daemon_threads = True
    print("listening", flush=True); srv.serve_forever()
