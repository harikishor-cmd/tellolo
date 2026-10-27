import json, os, re, subprocess, tempfile, threading, time, uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from providers import get_provider
import align
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "static", "out")
STYLE = "Stylised children's picture-book illustration, flat gouache colours, soft outlines, warm palette, no text."
LOCK = threading.Lock()
def to_wav(data):
    """Any browser audio (webm/ogg/wav) -> 16 kHz mono WAV via ffmpeg."""
    with tempfile.TemporaryDirectory() as d:
        i, o = os.path.join(d, "in"), os.path.join(d, "out.wav"); open(i, "wb").write(data)
        r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", i, "-ac", "1", "-ar", "16000", o], capture_output=True)
        if r.returncode or not os.path.exists(o): raise ValueError("Couldn't read that recording; please record again.")
        return open(o, "rb").read()
def _save(s):
    with LOCK: json.dump(s, open(os.path.join(OUT, s["id"], "story.json"), "w"), ensure_ascii=False, indent=1)
def load(sid):
    f = os.path.join(OUT, sid or "x", "story.json")
    if not re.fullmatch(r"[\w-]+", sid or "") or not os.path.exists(f): raise ValueError("story not found")
    with LOCK: return json.load(open(f))
def child_titles(child):
    t = []
    for sid in os.listdir(OUT):
        f = os.path.join(OUT, sid, "story.json")
        if child and os.path.exists(f):
            j = json.load(open(f))
            if j.get("child") == child: t.append(j.get("title", ""))
    return t
def make_story(lang, level, trouble_words, interests, provider=None, parent=None, child=None, hero=None):
    """child: profile id (sessions are kept per child). hero: fixed main character from the demo seed. Titles never repeat for a child."""
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
    p = provider or get_provider(); s = load(sid); d = os.path.join(OUT, sid); t0 = time.time()
    s["images"] = {"status": "running", "started": t0, "timings": {}, "errors": {}}; _save(s)
    def put(i, png):
        open(os.path.join(d, f"page{i}.png"), "wb").write(png)
        with LOCK:
            cur = json.load(open(os.path.join(d, "story.json")))
            cur["pages"][i-1]["image"] = f"/out/{sid}/page{i}.png"; cur["images"]["timings"][str(i)] = round(time.time() - t0, 1)
            json.dump(cur, open(os.path.join(d, "story.json"), "w"), ensure_ascii=False, indent=1)
    def fail(i, e):
        with LOCK:
            cur = json.load(open(os.path.join(d, "story.json"))); cur["images"]["errors"][str(i)] = str(e)[:200]
            json.dump(cur, open(os.path.join(d, "story.json"), "w"), ensure_ascii=False, indent=1)
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
        cur = json.load(open(os.path.join(d, "story.json")))
        cur["images"]["status"] = "error" if cur["images"]["errors"] else "done"; cur["images"]["total_s"] = round(time.time() - t0, 1)
        json.dump(cur, open(os.path.join(d, "story.json"), "w"), ensure_ascii=False, indent=1)
    return load(sid)
def start_images(sid):
    threading.Thread(target=make_images, args=(sid,), daemon=True).start()
def clean_word(w): return re.sub(r"[^\w\u0900-\u0963\u0966-\u097f]", "", w)
def read_page(sid, page, audio, provider=None, story=None):
    p = provider or get_provider(); s = story or load(sid); exp = s["pages"][page]["text"]
    heard = p.transcribe(to_wav(audio), s["language"], exp)
    r = align.flags(exp, heard); r.update(expected=exp, heard=heard, page=page, provider=p.name, at=time.strftime("%Y-%m-%d %H:%M"))
    r["flagged"] = [clean_word(w["display"]) for w in r["words"] if w["status"] != "correct"]
    with LOCK:
        f = os.path.join(OUT, sid, "reads.json"); reads = json.load(open(f)) if os.path.exists(f) else {}
        reads[str(page)] = {k: r[k] for k in ("errors", "error_rate", "flagged", "heard", "at", "provider")}; json.dump(reads, open(f, "w"), ensure_ascii=False, indent=1)
    return r
def reads(sid):
    f = os.path.join(OUT, sid, "reads.json"); return json.load(open(f)) if os.path.exists(f) else {}
STOP = {"the", "and", "was", "are", "his", "her", "she", "for", "with", "has", "had", "but", "you", "they", "this", "that", "है", "था", "थी", "थे", "के", "की", "का", "में", "और", "वह", "को", "से", "पर", "भी", "एक"}
def next_words(sid, n=3):
    """Trouble words for the next story: this session's flagged words (most often missed first), then any
    original trouble words not yet read correctly. Very short function words (<=2 letters) are skipped."""
    s = load(sid); names = {clean_word(x).lower() for x in (s.get("character", {}).get("name", "") + " " + (s.get("hero") or "").split(",")[0]).split()}
    c = Counter(w for r in reads(sid).values() for w in r["flagged"] if len(w) > 2 and w.lower() not in names and w.lower() not in STOP)
    words = [w for w, _ in c.most_common()]
    for w in s.get("trouble_words", []):
        if w not in words and len(words) < n: words.append(w)
    return words[:n]
def make_next_story(sid, provider=None):
    s = load(sid); w = next_words(sid)
    return make_story(s["language"], s["level"], w, s.get("interests", ["animals"]), provider, parent=sid, child=s.get("child"), hero=s.get("hero"))
def summary(include_tests=False, child=None):
    """Real (meta) sessions only by default; mock and fixed test stories are hidden unless include_tests."""
    out = []
    for sid in sorted(os.listdir(OUT), reverse=True):
        f = os.path.join(OUT, sid, "story.json")
        if not os.path.exists(f): continue
        s = json.load(open(f)); r = reads(sid)
        test = s.get("provider") != "meta"
        if not s.get("child"): test = True  # sessions from before per-child profiles (M1-M3 tests): hidden by default, tagged
        if test and not include_tests: continue
        if child and s.get("child") != child and not include_tests: continue
        rates = [x["error_rate"] for x in r.values()]
        out.append({"id": sid, "title": s.get("title"), "language": s.get("language"), "trouble_words": s.get("trouble_words"), "parent": s.get("parent"),
                    "pages_read": len(r), "mode": ("MOCK" if s.get("provider") != "meta" else "OLD TEST") if test else "real", "child": s.get("child"), "created": sid[:15], "avg_error_rate": round(sum(rates) / len(rates), 3) if rates else None,
                    "flagged": sorted({w for x in r.values() for w in x["flagged"]}), "next_words": next_words(sid) if r else []})
    return out

PROFILES = os.path.join(HERE, "data", "profiles.json")  # local only; not under static/, never sent to Meta
def save_profile(child, name):
    if not re.fullmatch(r"[\w-]+", child or ""): raise ValueError("bad child id")
    name = (name or "").strip()[:40]
    with LOCK:
        os.makedirs(os.path.dirname(PROFILES), exist_ok=True)
        d = json.load(open(PROFILES)) if os.path.exists(PROFILES) else {}
        d[child] = {"name": name}; json.dump(d, open(PROFILES, "w"), ensure_ascii=False, indent=1)
    return {"child": child, "name": name}
def child_name(child):
    if not child or not os.path.exists(PROFILES): return None
    with LOCK: return json.load(open(PROFILES)).get(child, {}).get("name")
