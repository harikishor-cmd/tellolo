"""End-to-end proof. usage: python3 tests/e2e.py mock|meta  -> proof/<mode>/"""
import hashlib, json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
mode = sys.argv[1]; os.environ["TELLOLO_PROVIDER"] = mode
import pipeline, align
from providers import get_provider
from PIL import Image, ImageDraw, ImageFont
P = get_provider(); OUTD = os.path.join(HERE, "proof", mode); os.makedirs(OUTD, exist_ok=True)
SIDE = os.path.join(HERE, "samples", "mock_transcripts.json")
TW = {"en": ["river", "basket", "through"], "hi": ["नदी", "टोकरी", "पेड़"]}
SUBS = {"en": ["banana", "dog"], "hi": ["केला", "कुत्ता"]}
VOICE = {"en": "en-us", "hi": "hi"}
def tts(text, lang, slow=False):
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "a.wav"); subprocess.run(["espeak-ng", "-v", VOICE[lang], "-s", "120" if slow else "150", "-w", f, text], check=True)
        return pipeline.to_wav(open(f, "rb").read())
rep = {"mode": mode, "stories": {}, "asr": {}}
for lang in ["en", "hi"]:
    s = pipeline.make_story(lang, "beginner", TW[lang], ["animals", "rivers"], P)
    full = " ".join(pg["text"] for pg in s["pages"])
    rep["stories"][lang] = {"id": s["id"], "title": s["title"], "pages": len(s["pages"]), "trouble_words": TW[lang],
        "trouble_words_used": s["trouble_words_used"], "devanagari": lang != "hi" or any("\u0900" <= c <= "\u097f" for c in full), "text": [p["text"] for p in s["pages"]]}
    toks = align.toks(full); n = len(toks)
    i1, i2, i3 = n // 5, n // 2, (4 * n) // 5
    spoken = list(toks); spoken[i1] = SUBS[lang][0]; spoken[i3] = SUBS[lang][1]; del spoken[i2]
    planted = [(i1, "substituted"), (i2, "missed"), (i3, "substituted")]
    clean_wav, err_wav = tts(full, lang), tts(" ".join(spoken), lang, slow=True)
    for name, w in [("clean", clean_wav), ("errors", err_wav)]: open(os.path.join(OUTD, f"{lang}_{name}.wav"), "wb").write(w)
    if mode == "mock":  # mock 'hears' exactly what TTS was told to say
        m = json.load(open(SIDE)) if os.path.exists(SIDE) else {}
        m[hashlib.sha256(err_wav).hexdigest()] = " ".join(spoken); json.dump(m, open(SIDE, "w"), ensure_ascii=False)
    res = {}
    for name, w in [("clean", clean_wav), ("errors", err_wav)]:
        heard = P.transcribe(w, lang, full); r = align.flags(full, heard); r["heard"] = heard; res[name] = r
    caught = [{"index": i, "word": toks[i], "planted": k, "flag": res["errors"]["words"][i]["status"], "heard": res["errors"]["words"][i]["heard"]} for i, k in planted]
    rep["asr"][lang] = {"clean_error_rate": res["clean"]["error_rate"], "clean_heard": res["clean"]["heard"],
        "clean_flags": [w for w in res["clean"]["words"] if w["status"] != "correct"], "clean_insertions": res["clean"]["insertions"],
        "planted": caught, "planted_caught": sum(c["flag"] != "correct" for c in caught),
        "errors_read_extra_flags": res["errors"]["errors"] - 3, "errors_heard": res["errors"]["heard"]}
# images for the English story -> contact sheet
sid = rep["stories"]["en"]["id"]; s = pipeline.make_images(sid, P); d = os.path.join(pipeline.OUT, sid)
ims = [Image.open(os.path.join(d, f)).convert("RGB").resize((512, 341)) for f in ["page1.png"] + [f"page{i}.png" for i in range(1, 6)]]
sheet = Image.new("RGB", (3 * 512 + 40, 2 * 381 + 30), "white"); dr = ImageDraw.Draw(sheet)
for k, im in enumerate(ims):
    x, y = 10 + (k % 3) * 522, 10 + (k // 3) * 391; sheet.paste(im, (x, y + 30)); dr.text((x, y + 8), "PAGE 1 (= reference)" if k == 0 else f"PAGE {k}", fill="black")
sheet.save(os.path.join(OUTD, "contact_sheet.png")); rep["contact_sheet"] = f"proof/{mode}/contact_sheet.png"; rep["story_for_browser"] = sid
open(os.path.join(OUTD, "browser_page1.wav"), "wb").write(tts(s["pages"][0]["text"], "en"))
if mode == "meta":
    from providers import meta; rep["meta_calls"] = meta.CALLS
json.dump(rep, open(os.path.join(OUTD, "e2e.json"), "w"), ensure_ascii=False, indent=1)
for l, a in rep["asr"].items(): print(l, "clean_err", a["clean_error_rate"], "caught", a["planted_caught"], "/3", "tw", rep["stories"][l]["trouble_words_used"])
print("story", sid, rep.get("meta_calls"))
