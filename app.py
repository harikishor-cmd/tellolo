"""Tellolo M1 local web app (stdlib server). Run ./run.sh -> http://localhost:8010"""
import collections, hashlib, hmac, json, os, re, secrets, shutil, sys, threading, time, traceback
from email.parser import BytesParser
from email.policy import default
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline
from providers import get_provider, DATA
ST = os.path.join(pipeline.HERE, "static")
PASS = os.environ.get("TELLOLO_PASSCODE", "")
HOSTED = bool(os.environ.get("RENDER"))
MAX_JSON, MAX_AUDIO = 16_000, 2_000_000  # bytes; 60 s of browser opus is well under 1 MB
MAX_THREADS = int(os.environ.get("TELLOLO_MAX_THREADS", 32))
PURGE_EVERY = float(os.environ.get("TELLOLO_PURGE_EVERY", 900))  # seconds
# (per session, per IP, window seconds). login counts failed passcodes only.
LIMITS = {"story": (8, 20, 3600), "read": (60, 150, 3600), "child": (10, 30, 3600), "login": (None, 5, 900)}
HDRS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; frame-ancestors 'none'; form-action 'none'"}
def _secret():
    """Signs session cookies. Hosted: TELLOLO_SECRET (render.yaml generates one). Local: kept in data/.secret so sessions survive restarts."""
    if os.environ.get("TELLOLO_SECRET"): return os.environ["TELLOLO_SECRET"].encode()
    f = os.path.join(DATA, ".secret")
    if not os.path.exists(f):
        os.makedirs(DATA, exist_ok=True)
        with open(os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as fh: fh.write(secrets.token_hex(32))
    return open(f).read().strip().encode()
SECRET = _secret()
def _sign(sess, ok):  # the passcode is part of what's signed, so changing it logs everyone out
    return hmac.new(SECRET, f"{sess}.{ok}.{PASS if ok == '1' else ''}".encode(), hashlib.sha256).hexdigest()[:32]
def problem():
    """Why the server can't do real work, or None. Drives /healthz so a bad deploy shows up on Render."""
    if os.environ.get("TELLOLO_PROVIDER", "mock").lower() == "meta" and not os.environ.get("META_API_KEY"): return "META_API_KEY not set"
    if not shutil.which("ffmpeg"): return "ffmpeg not on PATH"
    if HOSTED and not PASS: return "TELLOLO_PASSCODE not set (required when hosted)"
    if HOSTED and not os.environ.get("TELLOLO_SECRET"): return "TELLOLO_SECRET not set (required when hosted)"
_HITS, _RL = {}, threading.Lock()  # rate-limit windows: key -> deque of times
def _window(key, per, now):
    q = _HITS.setdefault(key, collections.deque())
    while q and q[0] <= now - per: q.popleft()
    return q
def prune_limits():
    now = time.time()
    with _RL:
        for k in [k for k, q in _HITS.items() if not q or q[-1] <= now - 3600]: del _HITS[k]
class H(BaseHTTPRequestHandler):
    timeout = 15  # a client that stalls mid-request can't hold a thread forever
    def log_message(self, fmt, *a):  # no query strings in logs
        sys.stderr.write("%s %s %s\n" % (self.command, self.path.split("?")[0], a[1] if len(a) > 1 else ""))
    def _send(self, code, body, ct="application/json"):
        if not isinstance(body, bytes): body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(body)))
        for k, v in HDRS.items(): self.send_header(k, v)
        for c in getattr(self, "_cookies", []): self.send_header("Set-Cookie", c)
        self.end_headers(); self.wfile.write(body)
    def _q(self, k):
        m = re.search(r"[?&]" + k + r"=([0-9a-f]{32})(?:&|$)", self.path); return m and m[1]
    def _ip(self):
        """Behind Render's proxy the client is the last X-Forwarded-For entry the proxy added (TELLOLO_PROXY_HOPS from the right)."""
        if HOSTED:
            xff = [x.strip() for x in self.headers.get("X-Forwarded-For", "").split(",") if x.strip()]; hops = int(os.environ.get("TELLOLO_PROXY_HOPS", 1))
            if len(xff) >= hops: return xff[-hops]
        return self.client_address[0]
    def _session(self):
        """Signed cookie 'tl' = <session id>.<passcode ok 0/1>.<hmac>. A missing or forged cookie gets a fresh session."""
        c = SimpleCookie()
        try: c.load(self.headers.get("Cookie", ""))
        except CookieError: pass
        parts = c["tl"].value.split(".") if "tl" in c else []
        if len(parts) == 3 and pipeline.is_id(parts[0]) and parts[1] in ("0", "1") and hmac.compare_digest(parts[2], _sign(parts[0], parts[1])):
            self.sess, ok = parts[0], parts[1]
        else: self.sess, ok = pipeline.new_id(), "0"; self._cookie(ok)
        self.authed = ok == "1" or not PASS
    def _cookie(self, ok):
        self._cookies = [f"tl={self.sess}.{ok}.{_sign(self.sess, ok)}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000" + ("; Secure" if HOSTED else "")]
    def _limit(self, kind, record=True):
        n_s, n_ip, per = LIMITS[kind]; now = time.time()
        keys = [((kind, "ip", self._ip()), n_ip)] + ([((kind, "s", self.sess), n_s)] if n_s else [])
        with _RL:
            qs = [_window(k, per, now) for k, _ in keys]
            if any(len(q) >= n for q, (_, n) in zip(qs, keys, strict=True)): return False
            if record:
                for q in qs: q.append(now)
        return True
    def _api(self):
        """Gate for /api/*: custom header (a cross-site page can't send it without a CORS preflight we never allow), signed session,
        and the passcode when one is set. /api/login is let through so the passcode can be entered."""
        if self.headers.get("X-Tellolo") != "1": self._send(403, {"error": "Missing X-Tellolo header.", "retryable": False}); return False
        if HOSTED and not PASS: self._send(503, {"error": "Server not configured (no passcode).", "retryable": False}); return False
        self._session()
        if not self.authed and self.path != "/api/login": self._send(401, {"error": "Passcode needed.", "passcode": True, "retryable": False}); return False
        return True
    def _story(self, sid):
        s = pipeline.load(sid)
        if not pipeline.owns(s.get("child"), self.sess): raise ValueError("story not found")
        return s
    def do_HEAD(self):
        ok = self.path.split("?")[0] in ("/", "/healthz")
        self.send_response(200 if ok else 404); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", "0"); self.end_headers()
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/healthz":
            p = problem(); return self._send(503 if p else 200, (p or "ok").encode(), "text/plain")
        if path == "/": path = "/index.html"
        if path == "/summary": path = "/summary.html"
        m = re.fullmatch(r"/out/([0-9a-f]{32})/page([1-5])\.png", path)
        if m:  # pictures: only to the session that owns the story (an <img> sends the SameSite cookie, not our header)
            self._session()
            try: ok = self.authed and pipeline.owns(pipeline.load(m[1]).get("child"), self.sess)
            except ValueError: ok = False
            f = os.path.join(pipeline.OUT, m[1], f"page{m[2]}.png")
            if not ok or not os.path.isfile(f): return self.send_error(404)
            return self._send(200, open(f, "rb").read(), "image/png")
        if path.startswith("/api/"):
            if not self._api(): return
            try:
                if path == "/api/info": return self._send(200, {"provider": get_provider().name, "passcode": bool(PASS)})
                if path == "/api/children": return self._send(200, {"children": pipeline.children(self.sess)})
                if path.startswith("/api/story/"): return self._send(200, self._story(path.rsplit("/", 1)[1]))
                if path == "/api/summary":
                    c = self._q("child")
                    if not pipeline.owns(c, self.sess): raise ValueError("child not found")
                    return self._send(200, {"child": c, "child_name": pipeline.child_name(c), "rows": pipeline.summary(c)})
                return self.send_error(404)
            except Exception as e: return self._err(e)
        f = os.path.realpath(os.path.join(ST, path.lstrip("/")))
        legacy = os.path.join(ST, "out")  # where older versions kept runtime data: never served
        if os.path.commonpath([f, ST]) != ST or os.path.commonpath([f, legacy]) == legacy or not os.path.isfile(f): return self.send_error(404)
        ct = {"html": "text/html; charset=utf-8", "png": "image/png", "js": "text/javascript", "json": "application/json"}.get(f.rsplit(".", 1)[-1], "application/octet-stream")
        self._send(200, open(f, "rb").read(), ct)
    def do_POST(self):
        if not self.path.startswith("/api/"): return self.send_error(404)
        if not self._api(): return
        cl = self.headers.get("Content-Length", "")
        n = int(cl) if cl.isdigit() else -1
        if not 0 <= n <= (MAX_AUDIO if self.path == "/api/read" else MAX_JSON):
            self.close_connection = True; return self._send(413, {"error": "That request is too big.", "retryable": False})
        body = self.rfile.read(n); ct = self.headers.get("Content-Type", "")
        busy = lambda: self._send(429, {"error": "Too many requests; please wait a bit and try again.", "retryable": True})
        try:
            if self.path == "/api/read":
                if not ct.startswith("multipart/form-data"): raise ValueError("expected a recording")
                msg = BytesParser(policy=default).parsebytes(b"Content-Type: " + ct.encode() + b"\r\n\r\n" + body)
                f = {p.get_param("name", header="content-disposition"): p.get_payload(decode=True) for p in msg.iter_parts()}
                s = self._story(f["id"].decode())
                if not self._limit("read"): return busy()
                return self._send(200, pipeline.read_page(s["id"], int(f["page"]), f["audio"], story=s))
            if not ct.startswith("application/json"): raise ValueError("expected JSON")
            j = json.loads(body)
            if not isinstance(j, dict): raise ValueError("expected a JSON object")
            if self.path == "/api/login":
                if not PASS: return self._send(200, {"ok": True})
                if not self._limit("login", record=False): return busy()
                if not hmac.compare_digest(str(j.get("passcode", "")).encode(), PASS.encode()):
                    self._limit("login"); return self._send(401, {"error": "That passcode isn't right.", "passcode": True, "retryable": False})
                self._cookie("1"); return self._send(200, {"ok": True})
            if self.path == "/api/child":
                if not self._limit("child"): return busy()
                return self._send(200, pipeline.new_child(self.sess, j.get("name")))
            if self.path == "/api/profile": return self._send(200, pipeline.rename(j.get("child"), j.get("name"), self.sess))
            if self.path == "/api/forget": return self._send(200, pipeline.forget(j.get("child"), self.sess))
            if self.path == "/api/story":
                if not pipeline.owns(j.get("child"), self.sess): raise ValueError("child not found")
                if not self._limit("story"): return busy()
                return self._send(200, pipeline.make_story(j.get("lang"), j.get("level", "beginner"), j.get("trouble_words"), j.get("interests", []), child=j["child"], hero=j.get("hero")))
            if self.path == "/api/next":
                s = self._story(j.get("id"))
                if not self._limit("story"): return busy()
                return self._send(200, pipeline.make_next_story(s["id"]))
            if self.path == "/api/images":
                s = self._story(j.get("id")); return self._send(202, {"id": s["id"], "status": "running" if pipeline.start_images(s["id"]) else "not started"})
            self.send_error(404)
        except Exception as e: self._err(e)
    def _err(self, e):
        from providers.meta import MetaError
        if isinstance(e, MetaError): return self._send(502, {"error": str(e), "retryable": e.retryable})
        if isinstance(e, (ValueError, KeyError, IndexError, TypeError)): return self._send(400, {"error": f"Bad request: {e}"[:200], "retryable": False})
        traceback.print_exc(); self._send(500, {"error": "Something went wrong on the server; please try again.", "retryable": True})
class Server(ThreadingHTTPServer):
    """At most MAX_THREADS requests at once; extra connections wait up to 2 s for a slot, then are dropped."""
    daemon_threads = True
    slots = threading.BoundedSemaphore(MAX_THREADS)
    def process_request(self, request, client_address):
        if not self.slots.acquire(timeout=2): return self.shutdown_request(request)
        try: super().process_request(request, client_address)
        except Exception: self.slots.release(); raise
    def process_request_thread(self, request, client_address):
        try: super().process_request_thread(request, client_address)
        finally: self.slots.release()
def housekeeping():
    while True:
        time.sleep(PURGE_EVERY)
        try: pipeline.purge(); prune_limits()
        except Exception: traceback.print_exc()
if __name__ == "__main__":
    if HOSTED: os.environ.setdefault("TELLOLO_PROVIDER", "meta")
    os.makedirs(pipeline.OUT, exist_ok=True)
    pipeline.purge(); threading.Thread(target=housekeeping, daemon=True).start()
    port = int(os.environ.get("PORT", 8010)); host = os.environ.get("HOST") or ("0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    print(f"Tellolo on http://{host}:{port} provider={os.environ.get('TELLOLO_PROVIDER', 'mock')} passcode={'on' if PASS else 'off'}", flush=True)
    if problem(): print("WARNING:", problem(), flush=True)
    srv = Server((host, port), H)
    print("listening", flush=True); srv.serve_forever()
