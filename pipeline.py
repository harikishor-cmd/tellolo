import json, os, shutil, subprocess, tempfile, threading, time, unicodedata, uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from providers import get_provider, DATA
import align
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(DATA, "stories")  # outside static/: served only through the API
STYLE = "Stylised children's picture-book illustration, flat gouache colours, soft outlines, warm palette, no text."
LOCK = threading.RLock()
IMAGES = ThreadPoolExecutor(2)  # at most 2 stories drawing at once; more requests queue
FFMPEG = threading.BoundedSemaphore(int(os.environ.get("TELLOLO_FFMPEG_MAX", 2))); FFMPEG_WAIT = 20  # seconds to wait for a free slot
KEEP_HOURS = float(os.environ.get("TELLOLO_KEEP_HOURS", 0))  # 0 = keep forever (local); render.yaml sets 24
_W = json.load(open(os.path.join(HERE, "static", "words.json")))
NFC = lambda w: unicodedata.normalize("NFC", w.strip())
PRACTICE = {lang: {NFC(w) for w in ws} for lang, ws in _W["practice"].items()}
INTERESTS = {k: v["en"] for k, v in _W["interests"].items()}
HEROES = {p["hero"] for p in json.load(open(os.path.join(HERE, "static", "seed.json")))["profiles"].values()}
def new_id(): return uuid.uuid4().hex  # 128-bit, for stories, children and sessions
def is_id(x): return isinstance(x, str) and len(x) == 32 and all(c in "0123456789abcdef" for c in x)
def letters(w, n=24): return isinstance(w, str) and 0 < len(w) <= n and all(unicodedata.category(c)[0] in "LM" for c in w)
def clean_prompt(s, n):
    """Model-written text that goes back into an image prompt: letters, digits, spaces and . , ' - only, length-capped."""
    s = "".join(c if unicodedata.category(c)[0] in "LMN" or c in " .,'-" else " " for c in str(s or ""))
    return " ".join(s.split())[:n]
def _dump(obj, f):
    """Write-then-rename so readers never see a half-written file."""
    tmp = f"{f}.{uuid.uuid4().hex[:6]}.tmp"
    with open(tmp, "w") as fh: json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, f)
def _read(f):
    with open(f) as fh: return json.load(fh)
def to_wav(data):
    """Browser audio (webm/ogg/mp4/wav) -> 16 kHz mono WAV via ffmpeg, first 60 s only, at most TELLOLO_FFMPEG_MAX at once.
    Only audio-container demuxers and local files are allowed, so a crafted 'recording' (HLS/concat playlist) can't make ffmpeg fetch URLs or read files."""
    if not FFMPEG.acquire(timeout=FFMPEG_WAIT): raise ValueError("Tellolo is busy; please try again in a moment.")
    try:
        with tempfile.TemporaryDirectory() as d:
            i, o = os.path.join(d, "in"), os.path.join(d, "out.wav"); open(i, "wb").write(data)
            try:
                r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-protocol_whitelist", "file", "-format_whitelist", "matroska,webm,ogg,wav,mov,mp4",
                                    "-i", i, "-t", "60", "-ac", "1", "-ar", "16000", o], capture_output=True, timeout=30)
            except subprocess.TimeoutExpired: raise ValueError("That recording took too long to read; please record again.") from None
            if r.returncode or not os.path.exists(o): raise ValueError("Couldn't read that recording; please record again.")
            return open(o, "rb").read()
    finally: FFMPEG.release()
def _save(s):
    with LOCK: _dump(s, os.path.join(OUT, s["id"], "story.json"))
def load(sid):
    f = os.path.join(OUT, sid if is_id(sid) else "x", "story.json")
    if not is_id(sid) or not os.path.exists(f): raise ValueError("story not found")
    with LOCK: return _read(f)
def _stories():
    for sid in os.listdir(OUT) if os.path.isdir(OUT) else []:
        f = os.path.join(OUT, sid, "story.json")
        if is_id(sid) and os.path.exists(f): yield sid, _read(f)
def child_titles(child): return [s.get("title", "") for _, s in _stories() if child and s.get("child") == child]
def make_story(lang, level, trouble_words, interests, provider=None, parent=None, child=None, hero=None, from_story=False):
    """child: profile id (sessions are kept per child). hero: fixed main character from the demo seed. Titles never repeat for a child.
    Practice words and interests must come from static/words.json; from_story=True (next story) instead takes words from the child's
    own last story, which only need to be plain letters."""
    if lang not in PRACTICE: raise ValueError("language must be en or hi")
    if level not in ("beginner", "intermediate"): raise ValueError("level must be beginner or intermediate")
    if hero is not None and hero not in HEROES: raise ValueError("hero must be one of the demo heroes")
    if not isinstance(trouble_words, list) or not isinstance(interests, list) or len(trouble_words) > 3 or len(interests) > 3: raise ValueError("up to 3 words and 3 interests")
    if not all(isinstance(x, str) for x in trouble_words + interests): raise ValueError("words must be text")
    trouble_words = list(dict.fromkeys(NFC(w) for w in trouble_words if w.strip()))
    if not all(letters(w) if from_story else w in PRACTICE[lang] for w in trouble_words): raise ValueError("practice words must come from the word list")
    if not all(k in INTERESTS for k in interests): raise ValueError("interests must come from the list")
    interests = [INTERESTS[k] for k in dict.fromkeys(interests)]
    p = provider or get_provider(); old = child_titles(child)
    s = p.story(lang, level, trouble_words, interests, hero, old)
    if s["title"].strip().lower() in {x.strip().lower() for x in old}:
        s["title"] = f"{s['title']} ({len(old) + 1})"; s["title_fixed_by_app"] = True
    s["child"] = child; s["hero"] = hero; s["created"] = time.strftime("%Y%m%d-%H%M%S")
    s["id"] = new_id(); s["provider"] = p.name; s["parent"] = parent
    full = " ".join(pg["text"] for pg in s["pages"]); s["trouble_words_used"] = [w for w in trouble_words if w in full]
    with LOCK:  # the child may have been deleted while Meta was writing: then drop the story
        if child is not None:
            d = _profiles()
            if child not in d: raise ValueError("this child's data was deleted")
            d[child]["at"] = time.time(); _dump(d, PROFILES)
        os.makedirs(os.path.join(OUT, s["id"]), exist_ok=True); _save(s)
    return s
def _needs(s, i):
    """A page still to draw: no picture yet, and its last failure was not one Meta may have billed."""
    e = s["images"]["errors"].get(str(i))
    return not s["pages"][i-1].get("image") and not (e and e.get("maybe_billed"))
def make_images(sid, provider=None, workers=4):
    """Page 1 is generated first and becomes the character reference; pages 2-5 run in parallel as edits.
    story.json is updated as each page lands, so the UI can poll /api/story/<id> and show pages progressively.
    A page is never requested again once drawn or once a failure may have been billed; deleting the story stops further requests."""
    p = provider or get_provider(); d = os.path.join(OUT, sid); f = os.path.join(d, "story.json"); t0 = time.time()
    with LOCK:
        s = load(sid); s.setdefault("images", {"timings": {}, "errors": {}}).update(status="running", started=t0); _save(s)
    ch = s["character"]; ch = {"name": clean_prompt(ch.get("name"), 40), "look": clean_prompt(ch.get("look"), 200)}
    scene = lambda i: clean_prompt(s["pages"][i-1].get("scene"), 300)
    alive = lambda: os.path.exists(f)
    def put(i, png):
        with LOCK:
            if not alive(): return
            open(os.path.join(d, f"page{i}.png"), "wb").write(png)
            cur = _read(f); cur["pages"][i-1]["image"] = f"/out/{sid}/page{i}.png"
            cur["images"]["timings"][str(i)] = round(time.time() - t0, 1); cur["images"]["errors"].pop(str(i), None); _dump(cur, f)
    def fail(i, e):
        with LOCK:
            if not alive(): return
            billed = getattr(e, "maybe_billed", True)  # unknown failures count as possibly billed
            cur = _read(f); cur["images"]["errors"][str(i)] = {"msg": str(e)[:200], "maybe_billed": billed}; _dump(cur, f)
    def one(i, call):
        if not alive(): return None
        try: png = call(); put(i, png); return png
        except Exception as e: fail(i, e)
    first = open(os.path.join(d, "page1.png"), "rb").read() if s["pages"][0].get("image") else None
    if first is None and _needs(s, 1): first = one(1, lambda: p.first_page_image(ch, scene(1), STYLE))
    if first is not None:
        todo = [i for i in range(2, 6) if _needs(s, i)]
        with ThreadPoolExecutor(workers) as ex: list(ex.map(lambda i: one(i, lambda: p.page_image(first, ch, scene(i), STYLE)), todo))
    with LOCK:
        if not alive(): return None
        cur = _read(f); left = [i for i in range(1, 6) if not cur["pages"][i-1].get("image")]
        cur["images"].update(status="error" if left else "done", total_s=round(time.time() - t0, 1),
                             retryable=any(_needs(cur, i) for i in left) and bool(cur["pages"][0].get("image") or _needs(cur, 1)))
        _dump(cur, f)
    return cur
def start_images(sid):
    """Draw a story's pictures. Returns False (and spends nothing) if they are queued, drawing, done, or nothing is left that can
    be retried without risking a second charge. A run stuck for 10 minutes (e.g. the server restarted mid-run) may restart."""
    with LOCK:
        s = load(sid); im = s.setdefault("images", {"timings": {}, "errors": {}})
        if im.get("status") in ("queued", "running") and time.time() - im.get("started", 0) < 600: return False
        if not any(_needs(s, i) for i in range(1, 6)) or not (s["pages"][0].get("image") or _needs(s, 1)): return False
        im.update(status="queued", started=time.time()); im.setdefault("timings", {}); im.setdefault("errors", {}); _save(s)
    IMAGES.submit(make_images, sid); return True
def clean_word(w): return "".join(c for c in w if unicodedata.category(c)[0] in "LMN")
def read_page(sid, page, audio, provider=None, story=None):
    p = provider or get_provider(); s = story or load(sid)
    if not 0 <= page < len(s["pages"]): raise ValueError("no such page")
    p.check_budget()  # don't spend ffmpeg time on a reading Meta will refuse
    exp = s["pages"][page]["text"]
    heard = p.transcribe(to_wav(audio), s["language"], exp)
    r = align.flags(exp, heard); r.update(expected=exp, heard=heard, page=page, provider=p.name, at=time.strftime("%Y-%m-%d %H:%M"))
    r["flagged"] = [clean_word(w["display"]) for w in r["words"] if w["status"] != "correct"]
    with LOCK:  # the transcript goes back to the browser only; just the tricky words are kept
        if not os.path.exists(os.path.join(OUT, sid)): raise ValueError("story not found")
        f = os.path.join(OUT, sid, "reads.json"); reads = _read(f) if os.path.exists(f) else {}
        reads[str(page)] = {k: r[k] for k in ("errors", "error_rate", "flagged", "at", "provider")}; _dump(reads, f)
    return r
def reads(sid):
    f = os.path.join(OUT, sid, "reads.json"); return _read(f) if os.path.exists(f) else {}
STOP = {"the", "and", "was", "are", "his", "her", "she", "for", "with", "has", "had", "but", "you", "they", "this", "that", "है", "था", "थी", "थे", "के", "की", "का", "में", "और", "वह", "को", "से", "पर", "भी", "एक"}
def next_words(sid, n=3):
    """Trouble words for the next story: this session's flagged words (most often missed first), then any
    original trouble words not yet read correctly. Very short function words (<=2 letters) are skipped."""
    s = load(sid); names = {clean_word(x).lower() for x in (s.get("character", {}).get("name", "") + " " + (s.get("hero") or "").split(",")[0]).split()}
    c = Counter(w for r in reads(sid).values() for w in r["flagged"] if len(w) > 2 and w.lower() not in names and w.lower() not in STOP and letters(w))
    words = [w for w, _ in c.most_common()]
    for w in s.get("trouble_words", []):
        if w not in words and len(words) < n: words.append(w)
    return words[:n]
def make_next_story(sid, provider=None):
    s = load(sid); w = next_words(sid); keys = {v: k for k, v in INTERESTS.items()}
    return make_story(s["language"], s["level"], w, [keys[x] for x in s.get("interests", []) if x in keys], provider,
                      parent=sid, child=s.get("child"), hero=s.get("hero"), from_story=True)
def summary(child):
    """One child's stories, newest first."""
    out = []
    for sid, s in sorted(_stories(), key=lambda x: x[1].get("created", ""), reverse=True):
        if not child or s.get("child") != child: continue
        r = reads(sid); rates = [x["error_rate"] for x in r.values()]
        out.append({"id": sid, "title": s.get("title"), "language": s.get("language"), "trouble_words": s.get("trouble_words"), "parent": s.get("parent"),
                    "pages_read": len(r), "mode": "real" if s.get("provider") == "meta" else "MOCK", "child": child, "created": s.get("created"),
                    "avg_error_rate": round(sum(rates) / len(rates), 3) if rates else None,
                    "flagged": sorted({w for x in r.values() for w in x["flagged"]}), "next_words": next_words(sid) if r else []})
    return out

PROFILES = os.path.join(DATA, "profiles.json")  # {child: {name, session, at}}; never sent to Meta
def _profiles(): return _read(PROFILES) if os.path.exists(PROFILES) else {}
def owns(child, session):
    if not (is_id(child) and is_id(session)): return False
    with LOCK: return _profiles().get(child, {}).get("session") == session
def new_child(session, name):
    """The server picks the child id and ties it to the browser session that asked."""
    if not is_id(session): raise ValueError("no session")
    child = new_id(); _set(child, name, session); return {"child": child, "name": (name or "").strip()[:40]}
def _set(child, name, session):
    with LOCK:
        os.makedirs(DATA, exist_ok=True); d = _profiles()
        d[child] = {"name": (name or "").strip()[:40], "session": session, "at": time.time()}; _dump(d, PROFILES)
def rename(child, name, session):
    if not owns(child, session): raise ValueError("child not found")
    _set(child, name, session); return {"child": child, "name": (name or "").strip()[:40]}
def children(session):
    with LOCK: return [{"child": c, "name": v.get("name")} for c, v in _profiles().items() if is_id(session) and v.get("session") == session]
def child_name(child):
    if not child: return None
    with LOCK: return _profiles().get(child, {}).get("name")
def forget(child, session=None):
    """Delete everything kept for one child: their stories, pictures, reading results and name. A story still being written
    is then dropped when Meta answers (make_story), and no further pictures are requested for deleted stories (make_images)."""
    if session is not None and not owns(child, session): raise ValueError("child not found")
    gone = 0
    with LOCK:
        for sid, s in list(_stories()):
            if s.get("child") == child: shutil.rmtree(os.path.join(OUT, sid)); gone += 1
        d = _profiles()
        if d.pop(child, None) is not None: _dump(d, PROFILES)
    return {"child": child, "stories_deleted": gone}
def purge():
    """Delete stories and names untouched for TELLOLO_KEEP_HOURS (off when 0). Runs at start and on a timer (app.py)."""
    if not KEEP_HOURS: return
    cut = time.time() - KEEP_HOURS * 3600
    with LOCK:
        for sid in os.listdir(OUT) if os.path.isdir(OUT) else []:
            d = os.path.join(OUT, sid)
            if os.path.isdir(d) and os.path.getmtime(d) < cut: shutil.rmtree(d)
        p = _profiles(); keep = {k: v for k, v in p.items() if v.get("at", 0) >= cut}
        if keep != p: _dump(keep, PROFILES)
