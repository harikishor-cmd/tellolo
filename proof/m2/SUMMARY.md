# Tellolo M2 proof — Oct 27 2026 (IST). Real Meta calls in M2: 10 (2 Spark, 5 Image, 3 ASR), all 200.
1 Original words in flags: PASS — meta/2_flags_original_words.png ("wakes" missed, "basket." substituted, case/punctuation kept); flow.json flag_spans.
2 Retry/backoff + clear errors: PASS — retry_test.json (6/6: 503,503,200 / 429+Retry-After / timeout recover; 500x3 gives up with message; 401, 400 no retry); UI error + Try again: meta/5_error_message.png.
3 Browser mic, adult voice: PASS as far as the box allows — human_voice/ (real LibriSpeech adult recordings via Chrome fake mic -> real ASR: clean page 0.0%, planted word caught). Real mic on a real device: NEEDS HARI.
4 First page <=15 s: PASS — meta/flow.json first_page_ms_browser 9066 ms (server 8.4 s); all 5 in 23.1 s (page 1 alone took 8.4 s; serial M1 ~60 s). meta/1_first_page_shown.png, meta/contact_sheet_parallel.png.
5 Adaptive loop: PASS — story 1 read with 2 planted errors -> flagged wakes, basket -> story 2 "Pip Has Fun All Day" uses wakes, basket, river (meta/3_next_story.png, flow.json story2).
Extras: tap-to-hear (browser voice, labelled) wired (flow.json tap_to_hear_spoken) but sound not verifiable headless; parent summary meta/4_parent_summary.png.
