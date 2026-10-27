"""M2 end-to-end in headless Chrome: story -> progressive pictures (timed) -> record page 1 (fake mic) -> flags in original words
-> tap-to-hear -> next story from flagged words -> parent summary. usage: m2_flow.py mock|meta port"""
import json, os, subprocess, sys, tempfile, time, wave, requests
from playwright.sync_api import sync_playwright
mode, port = sys.argv[1], sys.argv[2]; HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(HERE, "proof", "m2", mode); os.makedirs(D, exist_ok=True); U = f"http://127.0.0.1:{port}"
t = time.time(); s = requests.post(U + "/api/story", json={"lang": "en", "level": "beginner", "trouble_words": ["river", "basket", "through"], "interests": ["animals"]}, timeout=300).json()
res = {"mode": mode, "story1": {"id": s["id"], "title": s["title"], "trouble_words": s["trouble_words"], "used": s["trouble_words_used"], "seconds": round(time.time() - t, 1), "page1": s["pages"][0]["text"]}}
ws = s["pages"][0]["text"].split(); order = sorted(range(len(ws)), key=lambda i: -len(ws[i].strip(".,!?")))
planted = {"substituted": ws[order[0]], "missed": ws[order[1]]}; ws[order[0]] = "banana"; ws[order[1]] = ""
spoken = " ".join(w for w in ws if w); res["planted"] = planted; res["spoken_by_tts"] = spoken
wav = os.path.join(D, "page1_errors.wav"); subprocess.run(["espeak-ng", "-v", "en-us", "-s", "140", "-w", wav, spoken], check=True)
w = wave.open(wav); dur = w.getnframes() / w.getframerate()
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", f"--use-file-for-fake-audio-capture={wav}%noloop"])
    pg = b.new_page(viewport={"width": 1000, "height": 1300}); pg.goto(f"{U}/?id={s['id']}"); pg.wait_for_selector("#rec0")
    pg.click("#imgs"); pg.wait_for_function("window.__t.firstPageMs>0", timeout=180000)
    res["first_page_ms_browser"] = round(pg.evaluate("window.__t.firstPageMs")); pg.screenshot(path=os.path.join(D, "1_first_page_shown.png"))
    pg.wait_for_function("window.__t.allMs>0 || document.getElementById('status').innerText.includes('failed')", timeout=300000)
    res["all_pages_ms_browser"] = round(pg.evaluate("window.__t.allMs||0")); res["image_status"] = pg.inner_text("#status")
    res["server_image_timings_s"] = requests.get(f"{U}/api/story/{s['id']}").json()["images"]
    pg.click("#rec0"); pg.wait_for_timeout(int(dur * 1000) + 1500); pg.click("#rec0")
    pg.wait_for_function("document.getElementById('r0').textContent.includes('error')", timeout=120000)
    res["read_result"] = pg.inner_text("#r0"); res["flag_spans"] = pg.eval_on_selector_all("#t0 .w", "els=>els.map(e=>[e.textContent,e.className.replace('w ','')])")
    pg.locator("#pages .page").first.scroll_into_view_if_needed(); pg.locator("#pages .page").first.screenshot(path=os.path.join(D, "2_flags_original_words.png"))
    flagged = pg.locator("#t0 .substituted, #t0 .missed").first; flagged.click(); res["tap_to_hear_spoken"] = pg.evaluate("window.__spoken")
    pg.click("#next"); pg.wait_for_function(f"story && story.id!='{s['id']}'", timeout=300000)
    s2 = pg.evaluate("story"); res["story2"] = {"id": s2["id"], "title": s2["title"], "trouble_words": s2["trouble_words"], "used": s2["trouble_words_used"], "parent": s2["parent"], "pages": [x["text"] for x in s2["pages"]]}
    pg.screenshot(path=os.path.join(D, "3_next_story.png"))
    pg.goto(U + "/summary"); pg.wait_for_selector("table"); pg.screenshot(path=os.path.join(D, "4_parent_summary.png")); res["summary_text"] = pg.inner_text("table")[:1500]
    pg.goto(f"{U}/?id=does-not-exist"); pg.wait_for_selector(".err"); res["bad_id_error_shown"] = pg.inner_text("#status"); pg.screenshot(path=os.path.join(D, "5_error_message.png"))
    b.close()
json.dump(res, open(os.path.join(D, "flow.json"), "w"), ensure_ascii=False, indent=1); print(json.dumps(res, ensure_ascii=False, indent=1)[:4000])
