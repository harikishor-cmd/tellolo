"""Headless browser: open story, record page 1 with fake mic (TTS wav), screenshot. usage: browser.py mode story_id port"""
import os, sys, json, wave
from playwright.sync_api import sync_playwright
mode, sid, port = sys.argv[1], sys.argv[2], sys.argv[3]; D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "proof", mode)
wav = os.path.join(D, "browser_page1.wav"); w = wave.open(wav); dur = w.getnframes() / w.getframerate()
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", f"--use-file-for-fake-audio-capture={wav}%noloop", "--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page(viewport={"width": 1000, "height": 1400}); pg.goto(f"http://127.0.0.1:{port}/?id={sid}")
    pg.wait_for_selector("#rec0"); pg.click("#rec0"); pg.wait_for_timeout(int(dur * 1000) + 1500); pg.click("#rec0")
    pg.wait_for_function("document.getElementById('r0').textContent.includes('error')", timeout=120000)
    print(pg.inner_text("#r0")); pg.screenshot(path=os.path.join(D, "browser.png"), full_page=False); b.close()
