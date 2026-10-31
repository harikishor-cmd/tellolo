import json, os, re, shutil, subprocess, tempfile, threading, time, uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from providers import get_provider
import align
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "static", "out")
STYLE = "Stylised children's picture-book illustration, flat gouache colours, soft outlines, warm palette, no text."
LOCK = threading.RLock()
IMAGES = ThreadPoolExecutor(2)  # at most 2 stories drawing at once; more requests queue
KEEP_HOURS = float(os.environ.get("TELLOLO_KEEP_HOURS", 0))  # 0 = keep forever (local); render.yaml sets 24
CHILD = r"[\w-]{4,64}"; WORD = r"[\wऀ-ॿ' -]{1,32}"
HEROES = {p["hero"] for p in json.load(open(os.path.join(HERE, "static", "seed.json")))["profiles"].values()}
_ANY = object()
def _dump(obj, f):
    """Write-then-rename so readers never see a half-written file."""
    tmp = f"{f}.{uuid.uuid4().hex[:6]}.tmp"
    with open(tmp, "w") as fh: json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, f)
def _read(f):
    with open(f) as fh: return json.load(fh)
def to_wav(data):
    """Browser audio (webm/ogg/mp4/wav) -> 16 kHz mono WAV via ffmpeg, first 60 s only.
    Only audio-container demuxers and local files are allowed, so a crafted 'recording' (HLS/concat playlist) can't make ffmpeg fetch URLs or read files."""
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, "in"), os.path.join(d, "out.wav"); open(i, "wb").write(data)
        try:
            r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-protocol_whitelist", "file", "-format_whitelist", "matroska,webm,ogg,wav,mov,mp4",
                                "-i", i, "-t", "60", "-ac", "1", "-ar", "16000", o], capture_output=True, timeout=30)
        except subprocess.TimeoutExpired: raise ValueError("That recording took too long to read; please record again.") from None
        if r.returncode or not os.path.exists(o): raise ValueError("Couldn't read that recording; please record again.")
        return open(o, "rb").read()
def _save(s):
    with LOCK: _dump(s, os.path.join(OUT, s["id"], "story.json"))
def load(sid, child=_ANY):
    """child: when given, the story must belong to that child (None = a story made without a profile)."""
    f = os.path.join(OUT, sid or "x", "story.json")
    if not isinstance(sid, str) or not re.fullmatch(r"[\w-]+", sid) or not os.path.exists(f): raise ValueError("story not found")
    with LOCK: s = _read(f)
    if child is not _ANY and s.get("child") != (child or None): raise ValueError("story not found")
    return s
def child_titles(child):
    t = []
    for sid in os.listdir(OUT):
        f = os.path.join(OUT, sid, "story.json")
        if child and os.path.exists(f):
            j = _read(f)
            if j.get("child") == child: t.append(j.get("title", ""))
    return t
def _words(xs, what, n=3):
    """User text that goes into Meta prompts: a short list of short plain words only."""
    if not isinstance(xs, list) or len(xs) > n or not all(isinstance(x, str) for x in xs): raise ValueError(f"{what}: up to {n} words")
    xs = [x.strip() for x in xs if x.strip()]
    for x in xs:
        if not re.fullmatch(WORD, x): raise ValueError(f"{what}: only letters, up to 32 each")
    return xs
def make_story(lang, level, trouble_words, interests, provider=None, parent=None, child=None, hero=None):
    """child: profile id (sessions are kept per child). hero: fixed main character from the demo seed. Titles never repeat for a child."""
    if lang not in ("en", "hi"): raise ValueError("language must be en or hi")
    if level not in ("beginner", "intermediate"): raise ValueError("level must be beginner or intermediate")
    if child is not None and not (isinstance(child, str) and re.fullmatch(CHILD, child)): raise ValueError("bad child id")
    if hero is not None and hero not in HEROES: raise ValueError("hero must be one of the demo heroes")
    trouble_words, interests = _words(trouble_words, "practice words"), _words(interests, "interests")
    purge()
    p = provider or get_provider(); old = child_titles(child)
    s = p.story(lang, level, trouble_words, interests, hero, old)
    if s["title"].strip().lower() in {x.strip().lower() for x in old}:
        s["title"] = f"{s['title']} ({len(old) + 1})"; s["title_fixed_by_app"] = True
    s["child"] = child; s["hero"] = hero
    s["id"] = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]; s["provider"] = p.name; s["parent"] = parent
    full = " ".join(pg["text"] for pg in s["pages"]); s["trouble_words_used"] = [w for w in trouble_words if w in full]
    os.makedirs(os.path.join(OUT, s["id"]), exist_ok=True); _save(s); return s
def make_images(sid, provider=None, workers=4):
    """Page 1 is generated first and becomes the character reference; pages 2-5 run in parallel as edits.
    story.json is updated as each page lands, so the UI can poll /api/story/<id> and show pages progressively."""
    p = provider or get_provider(); s = load(sid); d = os.path.join(OUT, sid); f = os.path.join(d, "story.json"); t0 = time.time()
    s["images"] = {"status": "running", "started": t0, "timings": {}, "errors": {}}; _save(s)
    def put(i, png):
        open(os.path.join(d, f"page{i}.png"), "wb").write(png)
        with LOCK:
            cur = _read(f)
            cur["pages"][i-1]["image"] = f"/out/{sid}/page{i}.png"; cur["images"]["timings"][str(i)] = round(time.time() - t0, 1)
            _dump(cur, f)
    def fail(i, e):
        with LOCK:
            cur = _read(f); cur["images"]["errors"][str(i)] = str(e)[:200]; _dump(cur, f)
    try:
        first = p.first_page_image(s["character"], s["pages"][0]["scene"], STYLE); put(1, first)
    except Exception as e:
        fail(1, e); first = None
    if first is not None:
        def one(i):
            try: put(i, p.page_image(first, s["character"], s["pages"][i-1]["scene"], STYLE))
            except Exception as e: fail(i, e)
        with ThreadPoolExecutor(workers) as ex: list(ex.map(one, range(2, 6)))
    with LOCK:
        cur = _read(f)
        cur["images"]["status"] = "error" if cur["images"]["errors"] else "done"; cur["images"]["total_s"] = round(time.time() - t0, 1)
        _dump(cur, f)
    return load(sid)
def start_images(sid):
    """Draw a story's pictures once. Returns False (and spends nothing) if they are already queued, drawing or done;
    only a run that ended in errors, or one stuck for 10 minutes (e.g. the server restarted mid-run), may be retried."""
    with LOCK:
        s = load(sid); im = s.get("images", {})
        if im.get("status") == "done" or (im.get("status") in ("queued", "running") and time.time() - im.get("started", 0) < 600): return False
        s["images"] = {"status": "queued", "started": time.time(), "timings": {}, "errors": {}}; _save(s)
    IMAGES.submit(make_images, sid); return True
def clean_word(w): return re.sub(r"[^\wऀ-ॣ०-ॿ]", "", w)
def read_page(sid, page, audio, provider=None, story=None, child=_ANY):
    p = provider or get_provider(); s = story or load(sid, child)
    if not 0 <= page < len(s["pages"]): raise ValueError("no such page")
    exp = s["pages"][page]["text"]
    heard = p.transcribe(to_wav(audio), s["language"], exp)
    r = align.flags(exp, heard); r.update(expected=exp, heard=heard, page=page, provider=p.name, at=time.strftime("%Y-%m-%d %H:%M"))
    r["flagged"] = [clean_word(w["display"]) for w in r["words"] if w["status"] != "correct"]
    with LOCK:  # the transcript goes back to the browser only; just the tricky words are kept
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
    c = Counter(w for r in reads(sid).values() for w in r["flagged"] if len(w) > 2 and w.lower() not in names and w.lower() not in STOP and re.fullmatch(WORD, w))
    words = [w for w, _ in c.most_common()]
    for w in s.get("trouble_words", []):
        if w not in words and len(words) < n: words.append(w)
    return words[:n]
def make_next_story(sid, provider=None, child=_ANY):
    s = load(sid, child); w = next_words(sid)
    return make_story(s["language"], s["level"], w, s.get("interests", ["animals"]), provider, parent=sid, child=s.get("child"), hero=s.get("hero"))
def summary(include_tests=False, child=None):
    """Real (meta) sessions only by default; mock and fixed test stories are hidden unless include_tests."""
    out = []
    for sid in sorted(os.listdir(OUT), reverse=True):
        f = os.path.join(OUT, sid, "story.json")
        if not os.path.exists(f): continue
        s = _read(f); r = reads(sid)
        test = s.get("provider") != "meta"
        if not s.get("child"): test = True  # sessions from before per-child profiles (M1-M3 tests): hidden by default, tagged
        if test and not include_tests: continue
        if child and s.get("child") != child and not include_tests: continue
        rates = [x["error_rate"] for x in r.values()]
        out.append({"id": sid, "title": s.get("title"), "language": s.get("language"), "trouble_words": s.get("trouble_words"), "parent": s.get("parent"),
                    "pages_read": len(r), "mode": ("MOCK" if s.get("provider") != "meta" else "OLD TEST") if test else "real", "child": s.get("child"), "created": sid[:15], "avg_error_rate": round(sum(rates) / len(rates), 3) if rates else None,
                    "flagged": sorted({w for x in r.values() for w in x["flagged"]}), "next_words": next_words(sid) if r else []})
    return out

PROFILES = os.path.join(HERE, "data", "profiles.json")  # not under static/, never sent to Meta
def _profiles(): return _read(PROFILES) if os.path.exists(PROFILES) else {}
def save_profile(child, name):
    if not (isinstance(child, str) and re.fullmatch(CHILD, child)): raise ValueError("bad child id")
    name = (name or "").strip()[:40]
    with LOCK:
        os.makedirs(os.path.dirname(PROFILES), exist_ok=True)
        d = _profiles(); d[child] = {"name": name, "at": time.time()}; _dump(d, PROFILES)
    return {"child": child, "name": name}
def child_name(child):
    if not child: return None
    with LOCK: return _profiles().get(child, {}).get("name")
def forget(child):
    """Delete everything kept for one child: their stories, pictures, reading results and name."""
    if not (isinstance(child, str) and re.fullmatch(CHILD, child)): raise ValueError("bad child id")
    gone = 0
    with LOCK:
        for sid in os.listdir(OUT):
            f = os.path.join(OUT, sid, "story.json")
            if os.path.exists(f) and _read(f).get("child") == child: shutil.rmtree(os.path.join(OUT, sid)); gone += 1
        d = _profiles()
        if d.pop(child, None) is not None: _dump(d, PROFILES)
    return {"child": child, "stories_deleted": gone}
def purge():
    """Delete stories and names older than TELLOLO_KEEP_HOURS (off when 0)."""
    if not KEEP_HOURS: return
    cut = time.time() - KEEP_HOURS * 3600
    with LOCK:
        for sid in os.listdir(OUT):
            d = os.path.join(OUT, sid)
            if os.path.isdir(d) and os.path.getmtime(d) < cut: shutil.rmtree(d)
        p = _profiles(); keep = {k: v for k, v in p.items() if v.get("at", 0) >= cut}
        if keep != p: _dump(keep, PROFILES)
