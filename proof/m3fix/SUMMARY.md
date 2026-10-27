# Tellolo M3 fixes — Oct 27 2026 (IST). Real Meta calls: 30 (2 runs x [2 Spark + 10 Image + 3 ASR]), all OK.
1 Fresh titles: PASS — EN "Rosie Hops on a Rainy Day" -> "Rosie Splashes by the River"; HI "मोती और नदी" -> "मोती की सैर" (Spark told earlier titles for that child; app appends (n) only if it still repeats — not needed).
2 Per-child sessions: PASS — real_*/8_parent_summary_this_child.png shows only demo-asha / demo-kabir; older sessions tagged OLD TEST / MOCK under ?all=1 (9_summary_all_tagged.png); nothing deleted.
3 'Pip is' mishearing: PASS — seed heroes Rosie / मोती; 4 clean reads (2 per language) had 0 flags.
4 Demo seed: PASS — static/seed.json, ./demo.sh + /?demo=en|hi, or profile buttons.
5 README: PASS — setup, models, free credits, privacy, licence TBD.
Note: EN planted read also flagged "the" (end of recording heard as "K."); stop-word filter added afterwards so function words no longer become next-story words (next_words_after_stopword_fix.txt).
