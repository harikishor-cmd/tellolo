class Provider:
    name = "base"
    def check_budget(self):
        """Raise if a paid call would be refused right now (so callers can skip work like ffmpeg first)."""
    def story(self, lang, level, trouble_words, interests, hero=None, avoid_titles=()) -> dict:
        """-> {title, character:{name, look}, pages:[{text, scene}] x5}"""
        raise NotImplementedError
    def reference_image(self, character, style) -> bytes: raise NotImplementedError
    def page_image(self, ref_png, character, scene, style) -> bytes: raise NotImplementedError
    def transcribe(self, wav_bytes, lang, expected_text) -> str: raise NotImplementedError
