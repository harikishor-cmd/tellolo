"""Retry/backoff + error messages against a local fake Meta server (no real calls, dummy key)."""
import json, os, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
PLAN = []
class F(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0))); code = PLAN.pop(0) if PLAN else 200
        if code == "sleep": time.sleep(3); code = 200
        body = json.dumps({"transcript": "hello there"} if code == 200 else {"error": "fake"}).encode()
        self.send_response(code)
        if code == 429: self.send_header("Retry-After", "1")
        self.end_headers(); self.wfile.write(body)
srv = ThreadingHTTPServer(("127.0.0.1", 8099), F); threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ.update(META_API_BASE="http://127.0.0.1:8099", META_API_KEY="dummy-not-a-real-key", META_BACKOFF="0.2", META_TIMEOUT="1", TELLOLO_DATA=tempfile.mkdtemp())  # own budget file
from providers import meta
P = meta.MetaProvider(); res = []
def case(name, plan, expect_ok, call=lambda: P.transcribe(b"RIFF", "en", "")):
    PLAN[:] = plan; meta.CALLS.clear(); t = time.time()
    try: out = call(); ok, msg = True, out
    except meta.MetaError as e: ok, msg = False, str(e) + (" [maybe billed]" if e.maybe_billed else "")
    r = {"case": name, "server_plan": plan, "attempts": [c[1] for c in meta.CALLS], "ok": ok, "message": msg, "seconds": round(time.time() - t, 2), "pass": ok == expect_ok}
    res.append(r); print(r)
case("503 then 503 then 200 -> recovers", [503, 503, 200], True)
case("429 with Retry-After then 200 -> recovers", [429, 200], True)
case("timeout then 200 -> recovers", ["sleep", 200], True)
case("500 x3 -> gives up with clear message", [500, 500, 500], False)
case("401 -> no retry, key message", [401], False)
case("400 -> no retry", [400], False)
img = lambda: P._post("/images/edits", once=True, json={})
case("image timeout -> no retry (Meta may already have billed it)", ["sleep", 200], False, img)
case("image 500 -> no retry (may be billed)", [500, 200], False, img)
case("image 429 then 200 -> retried (429 means no work was done)", [429, 200], True, img)
meta.BUDGET, keep = 0, meta.BUDGET
case("daily budget used up -> refused before any call", [200], False)
meta.BUDGET = keep
json.dump(res, open(os.path.join(HERE, "proof", "m2", "retry_test.json"), "w"), indent=1)
print("ALL PASS" if all(r["pass"] for r in res) else "FAIL")
