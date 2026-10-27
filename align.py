"""Word-level flags: known page text vs transcript (Voice Transcribe has no word timestamps)."""
import re, unicodedata
def norm(w):
    w = unicodedata.normalize("NFC", w).replace("\u093c", "").lower()
    return re.sub(r"[^\w\u0900-\u097f]|[\u0964\u0965]", "", w)
def pieces(s):
    """[(original word as written, normalised token)] -- split on spaces/dashes only so punctuation stays with its word."""
    out = []
    for w in re.split(r"[\s\-—]+", s):
        t = norm(w)
        if t: out.append((w, t))
    return out
def toks(s): return [t for _, t in pieces(s)]
def display_words(s): return [w for w in s.split() if norm(w)]
def flags(expected, heard):
    disp = [w for w, _ in pieces(expected)]; a, b = toks(expected), toks(heard)
    # normalise compound splits: if b[j]+b[j+1] matches a word in a, merge
    aset, m, j = set(a), [], 0
    while j < len(b):
        if j + 1 < len(b) and b[j] + b[j + 1] in aset and b[j] not in aset: m.append(b[j] + b[j + 1]); j += 2
        else: m.append(b[j]); j += 1
    b = m; n, k = len(a), len(b)
    D = [[0] * (k + 1) for _ in range(n + 1)]
    for i in range(n + 1): D[i][0] = i
    for j in range(k + 1): D[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, k + 1):
            D[i][j] = min(D[i-1][j] + 1, D[i][j-1] + 1, D[i-1][j-1] + (a[i-1] != b[j-1]))
    i, j, out, ins = n, k, [None] * n, []
    while i or j:
        if i and j and D[i][j] == D[i-1][j-1] + (a[i-1] != b[j-1]):
            out[i-1] = {"word": a[i-1], "display": disp[i-1], "status": "correct" if a[i-1] == b[j-1] else "substituted", "heard": b[j-1]}; i -= 1; j -= 1
        elif i and D[i][j] == D[i-1][j] + 1: out[i-1] = {"word": a[i-1], "display": disp[i-1], "status": "missed", "heard": ""}; i -= 1
        else:
            nb = {b[j-2] if j >= 2 else None, b[j] if j < k else None}
            if b[j-1] not in nb: ins.append(b[j-1])  # ignore ASR neighbour-word repeats
            j -= 1
    errs = sum(1 for o in out if o["status"] != "correct")
    return {"words": out, "insertions": ins[::-1], "errors": errs, "error_rate": round((errs + len(ins)) / max(n, 1), 4)}
