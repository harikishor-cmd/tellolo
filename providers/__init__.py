"""Swappable model layer. TELLOLO_PROVIDER=mock|meta (default mock). Built Oct 27 2026."""
import os
# Runtime data (stories, pictures, names, Meta budget). Never under static/. Override with TELLOLO_DATA (e.g. a mounted disk).
DATA = os.environ.get("TELLOLO_DATA") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
def get_provider(name=None):
    name = (name or os.environ.get("TELLOLO_PROVIDER", "mock")).lower()
    if name == "meta":
        from .meta import MetaProvider
        return MetaProvider()
    from .mock import MockProvider
    return MockProvider()
