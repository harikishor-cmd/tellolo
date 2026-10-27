"""Hindi retest with punctuation kept: espeak-ng errored read (normal speed) + gTTS (online, no account) clean & errored. Real Meta calls."""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
os.environ["TELLOLO_PROVIDER"] = "meta"
import pipeline, align
from providers import get_provider, meta
P = get_provider(); D = os.path.join(HERE, "proof", "meta"); r = json.load(open(os.path.join(D, "e2e.json")))
full = " ".join(r["stories"]["hi"]["text"])
# planted on display text: 1st 'छोटी'->'केला'... use story-specific words, keep punctuation
words = full.split(); n = len(words); i1, i2, i3 = n // 5, n // 2, (4 * n) // 5
def core(w): return align.norm(w)
spoken = list(words); tail = lambda w: w[len(w.rstrip("।,")):]
spoken[i1] = "केला" + tail(words[i1]); spoken[i3] = "कुत्ता" + tail(words[i3]); del spoken[i2]
planted = [(core(words[i1]), "substituted"), (core(words[i2]), "missed"), (core(words[i3]), "substituted")]
etext = " ".join(spoken)
def espeak(t):
    with tempfile.TemporaryDirectory() as d:
        f = d + "/a.wav"; subprocess.run(["espeak-ng", "-v", "hi", "-w", f, t], check=True); return pipeline.to_wav(open(f, "rb").read())
def gtts(t):
    with tempfile.TemporaryDirectory() as d:
        f = d + "/a.mp3"; subprocess.run(["/tmp/gt/bin/python", "-c", "import sys;from gtts import gTTS;gTTS(sys.argv[1],lang='hi').save(sys.argv[2])", t, f], check=True); return pipeline.to_wav(open(f, "rb").read())
# map planted words to token indices in full-text tokens
toks = align.toks(full); idx = []
pos = 0
for w in words[: i1]: pos += len(align.toks(w))
idx.append(pos); pos = sum(len(align.toks(w)) for w in words[:i2]); idx.append(pos); pos = sum(len(align.toks(w)) for w in words[:i3]); idx.append(pos)
out = {"errored_text": etext, "planted": planted}
for name, fn, txt in [("espeak_errors", espeak, etext), ("gtts_clean", gtts, full), ("gtts_errors", gtts, etext)]:
    w = fn(txt); open(os.path.join(D, f"hi_{name}.wav"), "wb").write(w)
    heard = P.transcribe(w, "hi", full); f = align.flags(full, heard)
    res = {"heard": heard, "error_rate": f["error_rate"], "insertions": f["insertions"], "flags": [x for x in f["words"] if x["status"] != "correct"]}
    if "errors" in name: res["planted_flags"] = [f["words"][i] for i in idx]; res["caught"] = sum(f["words"][i]["status"] != "correct" for i in idx); res["extra_flags"] = f["errors"] - res["caught"]
    out[name] = res; print(name, res["error_rate"], res.get("caught"), res.get("extra_flags"))
out["calls"] = meta.CALLS; json.dump(out, open(os.path.join(D, "hindi_retry.json"), "w"), ensure_ascii=False, indent=1)
