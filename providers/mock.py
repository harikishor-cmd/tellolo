"""Mock provider: deterministic, no network, no key."""
import hashlib, io, json, os
from PIL import Image, ImageDraw
from .base import Provider
SIDECAR = os.path.join(os.path.dirname(__file__), "..", "samples", "mock_transcripts.json")
EN = ["{c} the little fox found a {w0} under the old tree.", "She showed the {w0} to her friend, a {w1} who lived by the river.",
      "Together they walked to the {w2} to find out who lost it.", "The {w1} said the {w2} was too far, but {c} kept going.",
      "At sunset they found the owner, and everyone shared a {w0} and laughed."]
HI = ["{c} नाम की छोटी लोमड़ी को पुराने पेड़ के नीचे एक {w0} मिला।", "उसने {w0} अपने दोस्त {w1} को दिखाया जो नदी के पास रहता था।",
      "दोनों {w2} की ओर चल पड़े ताकि पता चले कि वह किसका है।", "{w1} ने कहा कि {w2} बहुत दूर है, पर {c} चलती रही।",
      "शाम को उन्हें मालिक मिल गया, और सबने मिलकर {w0} बाँटा और खूब हँसे।"]
class MockProvider(Provider):
    name = "mock"
    def story(self, lang, level, trouble_words, interests, hero=None, avoid_titles=()):
        w = (list(trouble_words) + ["ball", "frog", "hill"])[:3]
        c = (hero.split(",")[0].split()[0] if hero else ("टिंकी" if lang == "hi" else "Tinku"))
        tpl = HI if lang == "hi" else EN
        return {"title": f"{c} and the {w[0]}" + (f" ({len(avoid_titles)+1})" if avoid_titles else ""), "language": lang, "level": level, "trouble_words": w, "interests": list(interests),
                "character": {"name": c, "look": "a small orange fox with a blue scarf"},
                "pages": [{"text": t.format(c=c, w0=w[0], w1=w[1], w2=w[2]), "scene": f"scene {i+1}"} for i, t in enumerate(tpl)]}
    def _img(self, label, seed):
        im = Image.new("RGB", (768, 512), (255, 244, 220)); d = ImageDraw.Draw(im)
        d.ellipse((300, 180, 470, 350), fill=(240, 140, 40)); d.rectangle((330, 330, 440, 350), fill=(40, 90, 200))
        d.text((20, 20), f"MOCK image: {label}"[:90], fill=(0, 0, 0)); b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
    def reference_image(self, character, style): return self._img("reference " + character["name"], 0)
    def first_page_image(self, character, scene, style):
        import time; time.sleep(float(os.environ.get('MOCK_IMAGE_DELAY', 0))); return self._img(scene, 1)
    def page_image(self, ref_png, character, scene, style):
        import time; time.sleep(float(os.environ.get('MOCK_IMAGE_DELAY', 0))); return self._img(scene, 1)
    def transcribe(self, wav_bytes, lang, expected_text):
        h = hashlib.sha256(wav_bytes).hexdigest()
        if os.path.exists(SIDECAR):
            m = json.load(open(SIDECAR))
            if h in m: return m[h]
        if os.environ.get("MOCK_READ_ERRORS"):  # deterministic 'imperfect reader': swap the longest word, drop the 2nd-longest
            ws = expected_text.split(); order = sorted(range(len(ws)), key=lambda i: -len(ws[i].strip('.,!?।')))
            if len(ws) > 3: ws[order[0]] = "banana"; ws[order[1]] = ""
            return " ".join(w for w in ws if w)
        return expected_text  # mock: a perfect read
