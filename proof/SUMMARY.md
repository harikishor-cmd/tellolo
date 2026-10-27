# Tellolo M1 proof — Oct 27 2026 (IST)
Real Meta calls: 19, all HTTP 200 (2 Spark, 6 Image, 11 ASR incl. 1 from the browser). No spend beyond free credits (~6 images x $0.01 + <2 min audio + 2 Spark calls).
1. Story: PASS. EN "Pip by the Water" + HI (Devanagari) 5 pages each, all 3 trouble words used (meta/e2e.json "stories").
2. Images: PENDING Lead review. meta/contact_sheet.png (reference + 5 pages); own check: otter in blue vest recognisable 5/5.
3. Browser record -> server ASR: PASS. meta/browser.png (headless Chrome, fake mic fed TTS wav, real Voice Transcribe call).
4. Flags: EN espeak: clean 3.9%, planted 3/3 caught (exact types). HI gTTS: clean 0.0%, planted 3/3 caught, 0 extra flags (meta/hindi_retry.json).
   HI espeak-ng (offline): FAIL — clean 12.2%, errored read: first run empty transcript; retry 31.7% with 10 extra flags. espeak's Hindi voice is mispronounced (छोटी->सोटी), not a pipeline bug.
5. Synthetic adult TTS only (espeak-ng, gTTS public endpoint no account); README; no key in any file (grep for literal key value = 0 hits); mock mode runs with no key (mock/).
