"""Real adult human voice (LibriSpeech, CC BY 4.0) through Chrome's fake mic -> real Voice Transcribe. usage: human_voice.py port
Page 1 expected text has 1 planted word change ('apostle'->'teacher') so the reader's correct audio should flag it; page 2 is a clean match."""
import json, os, sys, wave
from playwright.sync_api import sync_playwright
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); port = sys.argv[1]
C = json.load(open(os.path.join(HERE, "samples/librispeech/clips.json")))["clips"]
sc = lambda t: t.capitalize().replace("mister quilter", "Mister Quilter") + "."
pages = [sc(c["text"]) for c in C] + ["The end."]
pages[0] = pages[0].replace("apostle", "teacher")
sid = "librispeech-human-voice"; d = os.path.join(HERE, "static/out", sid); os.makedirs(d, exist_ok=True)
json.dump({"id": sid, "title": "Human voice test (LibriSpeech 1272-128104, CC BY 4.0)", "language": "en", "level": "adult", "trouble_words": [], "character": {"name": "", "look": ""},
           "pages": [{"text": t, "scene": ""} for t in pages], "parent": None}, open(os.path.join(d, "story.json"), "w"), indent=1)
if os.path.exists(os.path.join(d, "reads.json")): os.remove(os.path.join(d, "reads.json"))
OUT = os.path.join(HERE, "proof/m2/human_voice"); os.makedirs(OUT, exist_ok=True); res = []
for page, clip in [(0, 0), (1, 1)]:
    wav = os.path.join(HERE, "samples/librispeech", C[clip]["file"]); w = wave.open(wav); dur = w.getnframes() / w.getframerate()
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", f"--use-file-for-fake-audio-capture={wav}%noloop"])
        pg = b.new_page(viewport={"width": 1000, "height": 700}); pg.goto(f"http://127.0.0.1:{port}/?id={sid}"); pg.wait_for_selector(f"#rec{page}")
        pg.click(f"#rec{page}"); pg.wait_for_timeout(int(dur * 1000) + 1500); pg.click(f"#rec{page}")
        pg.wait_for_function(f"document.getElementById('r{page}').textContent.includes('error')", timeout=120000)
        r = {"page": page + 1, "librispeech_id": C[clip]["id"], "speaker": C[clip]["speaker_id"], "expected": pages[page], "reference_transcript": C[clip]["text"],
             "result": pg.inner_text(f"#r{page}"), "flags": pg.eval_on_selector_all(f"#t{page} .w", "els=>els.filter(e=>!e.className.includes('correct')).map(e=>[e.textContent,e.className.replace('w ','')])")}
        pg.locator("#pages .page").nth(page).screenshot(path=os.path.join(OUT, f"page{page+1}.png")); b.close(); res.append(r); print(r)
json.dump(res, open(os.path.join(OUT, "human_voice.json"), "w"), indent=1)
