"""Swappable model layer. TELLOLO_PROVIDER=mock|meta (default mock). Built Oct 27 2026."""
import os
def get_provider(name=None):
    name = (name or os.environ.get("TELLOLO_PROVIDER", "mock")).lower()
    if name == "meta":
        from .meta import MetaProvider
        return MetaProvider()
    from .mock import MockProvider
    return MockProvider()
