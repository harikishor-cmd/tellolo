"""Meta Model API provider. Endpoints/models verified by real calls in build/day1-test and
build/readalong-test (Oct 26-27 2026) and docs at dev.meta.ai. Key: env META_API_KEY only,
server-side; never logged."""
import base64, json, os, re, time, requests
from .base import Provider
BASE = os.environ.get("META_API_BASE", "https://api.meta.ai/v1")
TEXT_MODEL = os.environ.get("META_TEXT_MODEL", "muse-spark-1.3")
IMAGE_MODEL = os.environ.get("META_IMAGE_MODEL", "muse-image-1.0")
ASR_MODEL = os.environ.get("META_ASR_MODEL", "muse-voice-transcribe-1.0")
LANG = {"en": "English", "hi": "Hindi"}
RETRIES = int(os.environ.get("META_RETRIES", 3)); BACKOFF = float(os.environ.get("META_BACKOFF", 1.5)); TIMEOUT = int(os.environ.get("META_TIMEOUT", 180))
class MetaError(RuntimeError):
    def __init__(self, msg, status, retryable): super().__init__(msg); self.status, self.retryable = status, retryable
CALLS = []  # (endpoint, status) only; no payloads, no key

class MetaProvider(Provider):
    name = "meta"
    def __init__(self):
        if not os.environ.get("META_API_KEY"):
            raise RuntimeError("META_API_KEY not set; use TELLOLO_PROVIDER=mock")
    def _h(self, json_ct=True):
        h = {"Authorization": "Bearer " + os.environ["META_API_KEY"]}
        if json_ct: h["Content-Type"] = "application/json"
        return h
    def _post(self, ep, **kw):
        """POST with retry/backoff on 429/5xx/timeouts; raises MetaError with a readable message (never the key)."""
        last = None
        for attempt in range(1, RETRIES + 1):
            try:
                r = requests.post(BASE + ep, timeout=TIMEOUT, **kw)
            except (requests.Timeout, requests.ConnectionError) as e:
                CALLS.append((ep, type(e).__name__)); last = f"network problem ({type(e).__name__})"
            else:
                CALLS.append((ep, r.status_code))
                if r.status_code == 200:
                    try: return r.json()
                    except ValueError: last = "Meta sent an unreadable reply"
                elif r.status_code in (401, 403): raise MetaError(f"Meta rejected the API key ({r.status_code}). Check META_API_KEY on the server.", r.status_code, False)
                elif r.status_code == 400: raise MetaError(f"Meta refused the request (400): {r.text[:200]}", 400, False)
                elif r.status_code == 429 or r.status_code >= 500:
                    last = f"Meta is busy or erroring ({r.status_code})"
                    ra = r.headers.get("Retry-After")
                    if ra and ra.isdigit() and attempt < RETRIES: time.sleep(min(int(ra), 30)); continue
                else: raise MetaError(f"Meta error {r.status_code}: {r.text[:200]}", r.status_code, False)
            if attempt < RETRIES: time.sleep(BACKOFF * 2 ** (attempt - 1))
        raise MetaError(f"{last}; gave up after {RETRIES} tries on {ep}. Try again in a minute.", None, True)
    def story(self, lang, level, trouble_words, interests, hero=None, avoid_titles=()):
        L = LANG[lang]; script = " in Devanagari script" if lang == "hi" else ""
        p = (f"Write an original 5-page children's read-aloud story in {L}{script} for reading level '{level}'. "
             f"Child's interests: {', '.join(interests) or 'animals'}. Each of these trouble words must appear exactly as written at least once: {', '.join(trouble_words)}. " +
             (f"The main character is {hero}. " if hero else "One main character (an animal). ") +
             (f"The title must be new and different from these earlier titles: {'; '.join(avoid_titles)}. " if avoid_titles else "") +
             "1-2 short sentences per page, no dialogue quotes. Reply with JSON only: "
             '{"title": str, "character": {"name": str, "look": str (English, precise visual description: species, colours, clothing)}, '
             '"pages": [{"text": str, "scene": str (English illustration prompt)}] (exactly 5)}')
        if os.environ.get("TELLOLO_LOG_PROMPTS"):  # test hook: prompt text only (no key, no headers)
            with open(os.environ["TELLOLO_LOG_PROMPTS"], "a") as f: f.write(json.dumps({"prompt": p}, ensure_ascii=False) + "\n")
        j = self._post("/chat/completions", headers=self._h(), json={"model": TEXT_MODEL, "messages": [{"role": "user", "content": p}]})
        c = j["choices"][0]["message"]["content"]; c = c[c.find("{"): c.rfind("}") + 1]
        try: s = json.loads(c)
        except ValueError: raise MetaError("Muse Spark returned a story that wasn't valid JSON; try again.", 200, True)
        if len(s.get("pages", [])) != 5: raise MetaError(f"Muse Spark returned {len(s.get('pages', []))} pages, not 5; try again.", 200, True)
        s.update(language=lang, level=level, trouble_words=list(trouble_words), interests=list(interests)); return s
    def _img(self, ep, body):
        body.update(model=IMAGE_MODEL, n=1, output_format="png", reasoning_strength="low", size="1536x1024",
                    tool_enablement={"enable_web_search": False, "enable_shell": False, "enable_image_search": False})
        return base64.b64decode(self._post("/images/" + ep, headers=self._h(), json=body)["data"][0]["b64_json"])
    def reference_image(self, character, style):
        return self._img("generations", {"prompt": f"{style} Character reference sheet: full-body front and side view of {character['name']}, {character['look']}. Plain white background."})
    def first_page_image(self, character, scene, style):
        return self._img("generations", {"prompt": f"{style} Main character: {character['name']}, {character['look']}. Show the character clearly, full body. Scene: {scene}"})
    def page_image(self, ref_png, character, scene, style):
        ref = "data:image/png;base64," + base64.b64encode(ref_png).decode()
        return self._img("edits", {"images": [{"image_url": ref}], "prompt": f"{style} The image shows {character['name']}, {character['look']}. Keep the character exactly as in the reference (species, colours, clothing). Scene: {scene}"})
    def transcribe(self, wav_bytes, lang, expected_text):
        req = {"mode": "PUSH_TO_TALK", "model": ASR_MODEL, "audioEncoding": "WAV", "languageBias": [LANG[lang]]}
        j = self._post("/asr/transcribe", headers=self._h(False), files={"request": (None, json.dumps(req), "application/json"), "audio": ("page.wav", wav_bytes, "audio/wav")})
        return j["transcript"]
