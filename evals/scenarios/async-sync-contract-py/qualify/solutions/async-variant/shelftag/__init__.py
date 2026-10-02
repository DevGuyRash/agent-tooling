"""Shelf-label text for the Marktgasse co-op's stores. The stable API is documented in docs/api.md."""
from .label import Item, LabelError, label_text, label_text_async

__all__ = ["Item", "LabelError", "label_text", "label_text_async"]
__version__ = "1.5.0"
