"""M3 demo flow in headless Chrome with screenshots of every step. usage: m3_flow.py <lang en|hi> <label> <port> [mode]
consent -> profile -> story (progressive pictures, timed) -> read p1 (2 planted errors) + p2 (clean) via fake mic (gTTS adult synthetic voice)
-> flags -> next story from tricky words -> parent summary."""
import json, os, subprocess, sys, time, traceback, wave
from playwright.sync_api import sync_playwright
lang, label, port = sys.argv[1], sys.argv[2], sys.argv[3]; U = f"http://127.0.0.1:{port}"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D = os.path.join(HERE, "proof", "m3fix2", label); os.makedirs(D, exist_ok=True)
GT = "/tmp/gt/bin/python"; SUB = {"en": "banana", "hi": "केला"}
res = {"lang": lang, "label": label, "steps": {}, "timings_s": {}, "ok": False}
def shot(pg, name): pg.screenshot(path=os.path.join(D, name + ".png"))
def tts(text, out):
    mp3 = out[:-4] + ".mp3"; subprocess.run([GT, "-c", "import sys;from gtts import gTTS;gTTS(sys.argv[1],lang=sys.argv[2]).save(sys.argv[3])", text, lang, mp3], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", mp3, "-ac", "1", "-ar", "16000", out], check=True); os.remove(mp3)
    w = wave.open(out); return w.getnframes() / w.getframerate()
def launch(p, wav=None):
    a = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] + ([f"--use-file-for-fake-audio-capture={wav}%noloop"] if wav else [])
    b = p.chromium.launch(args=a); pg = b.new_page(viewport={"width": 1000, "height": 1250}); return b, pg
def wait_imgs(pg, key):
    pg.wait_for_function("window.__t && window.__t.firstSeenMs>0", timeout=180000); res["timings_s"][key + "_first_page"] = round(pg.evaluate("window.__t.firstSeenMs") / 1000, 1)
    pg.wait_for_function("window.__t.allMs>0 || document.getElementById('result').innerText.includes('didn')", timeout=300000)
    res["timings_s"][key + "_all_pages"] = round((pg.evaluate("window.__t.allMs") or 0) / 1000, 1)
def read(p, sid, page, text, name):
    wav = os.path.join(D, name + ".wav"); dur = tts(text, wav); b, pg = launch(p, wav)
    pg.goto(U); pg.evaluate("localStorage.tellolo_consent='test'"); pg.goto(f"{U}/?id={sid}"); pg.wait_for_selector("#s-book:not(.hidden)")
    for _ in range(page): pg.click("#nextp")
    pg.click("#rec"); pg.wait_for_timeout(int(dur * 1000) + 1200); t = time.time(); pg.click("#rec")
    pg.wait_for_function("document.getElementById('text').querySelector('.correct,.substituted,.missed') || document.getElementById('result').innerText.includes('⚠')", timeout=120000)
    res["timings_s"][name + "_check"] = round(time.time() - t, 1); return b, pg
try:
    with sync_playwright() as p:
        b, pg = launch(p); pg.goto(U + "/?demo=" + lang); pg.wait_for_selector("#s-consent:not(.hidden)"); shot(pg, "1_consent")
        pg.check("#agree"); t = time.time(); pg.click("#consentGo")
        try: pg.wait_for_selector("#s-wait:not(.hidden)", timeout=3000); shot(pg, "3_writing_from_seed")
        except Exception: res["steps"]["writing_screen"] = "too fast to capture"
        pg.wait_for_selector("#s-book:not(.hidden)", timeout=300000); res["timings_s"]["story"] = round(time.time() - t, 1)
        s = pg.evaluate("story"); res["steps"]["story1"] = {"child": s.get("child"), "hero": s.get("hero"), "character": s["character"]["name"], "id": s["id"], "title": s["title"], "trouble_words": s["trouble_words"], "used": s["trouble_words_used"], "pages": [x["text"] for x in s["pages"]],
            "devanagari": any("\u0900" <= c <= "\u097f" for c in s["pages"][0]["text"])}
        wait_imgs(pg, "story1"); shot(pg, "4_story_page1"); b.close()
        ws = s["pages"][0]["text"].split(); hero = (s.get("hero") or "").split(",")[0].split()[0]; nm = s["character"]["name"]
        order = sorted([i for i in range(len(ws)) if hero not in ws[i] and ws[i].strip(".,!?।") not in nm], key=lambda i: -len(ws[i].strip(".,!?।")))
        res["steps"]["planted"] = {"substituted": ws[order[0]], "missed": ws[order[1]]}; ws[order[0]] = SUB[lang] + ws[order[0]][len(ws[order[0]].rstrip(".,!?।")):]; ws[order[1]] = ""
        spoken = " ".join(w for w in ws if w); res["steps"]["spoken_page1"] = spoken
        b, pg = read(p, s["id"], 0, spoken, "read_p1_errors"); shot(pg, "5_flags_page1")
        res["steps"]["flags_p1"] = pg.eval_on_selector_all("#text .w", "e=>e.map(x=>[x.textContent,x.className.replace('w ','')])"); res["steps"]["result_p1"] = pg.inner_text("#result")
        pg.locator("#text .substituted, #text .missed").first.click(); res["steps"]["tap_to_hear"] = pg.evaluate("window.__spoken"); b.close()
        b, pg = read(p, s["id"], 1, s["pages"][1]["text"], "read_p2_clean"); shot(pg, "6_flags_page2_clean")
        res["steps"]["flags_p2_nonclean"] = pg.eval_on_selector_all("#text .w:not(.correct)", "e=>e.map(x=>[x.textContent,x.className.replace('w ','')])"); res["steps"]["result_p2"] = pg.inner_text("#result")
        t = time.time(); pg.click("#nextStory"); pg.wait_for_function(f"story && story.id!='{s['id']}' && !document.getElementById('s-book').classList.contains('hidden')", timeout=300000)
        res["timings_s"]["next_story"] = round(time.time() - t, 1); s2 = pg.evaluate("story")
        res["steps"]["story2"] = {"id": s2["id"], "title": s2["title"], "trouble_words": s2["trouble_words"], "used": s2["trouble_words_used"], "parent": s2["parent"], "pages": [x["text"] for x in s2["pages"]]}
        wait_imgs(pg, "story2"); shot(pg, "7_next_story"); b.close()
        res["steps"]["fresh_title"] = s2["title"].strip().lower() != s["title"].strip().lower() and not s2.get("title_fixed_by_app")
        b, pg = read(p, s2["id"], 0, s2["pages"][0]["text"], "read_story2_p1_clean"); shot(pg, "7b_story2_p1_clean")
        res["steps"]["story2_p1_nonclean"] = pg.eval_on_selector_all("#text .w:not(.correct)", "e=>e.map(x=>[x.textContent,x.className.replace('w ','')])"); b.close()
        b, pg = launch(p); pg.goto(f"{U}/summary?child={s['child']}"); pg.wait_for_selector(".card"); pg.wait_for_timeout(500); pg.screenshot(path=os.path.join(D, "8_parent_summary_this_child.png"), full_page=True)
        res["steps"]["summary"] = pg.inner_text("main")[:1200]; res["steps"]["fresh_browser_heading"] = pg.inner_text("#hello")
        res["steps"]["fresh_browser_localStorage_profile"] = pg.evaluate("localStorage.tellolo_profile||null")
        pg.goto(U + "/summary?all=1"); pg.wait_for_selector(".card"); pg.wait_for_timeout(500); pg.screenshot(path=os.path.join(D, "9_summary_all_tagged.png"), full_page=True); b.close()
    res["ok"] = True
except Exception as e:
    res["error"] = traceback.format_exc()[-1500:]
json.dump(res, open(os.path.join(D, "flow.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: res[k] for k in ("ok", "timings_s")}, ensure_ascii=False), res.get("error", "")[-600:])
