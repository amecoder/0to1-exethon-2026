from __future__ import annotations
"""The Korean font bundled for the PDF documents and the wireframe pictures (11-22).

Nanum Gothic, SIL Open Font License 1.1 (app/data/fonts/OFL.txt), from github.com/google/fonts ofl/nanumgothic.
A character the font cannot draw would print as an empty box, so `printable` swaps it first.
"""

import unicodedata
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont

FONT_DIR = Path(__file__).resolve().parent / "data" / "fonts"
REGULAR = FONT_DIR / "NanumGothic-Regular.ttf"
BOLD = FONT_DIR / "NanumGothic-Bold.ttf"
FAMILY = "NanumGothic"
SUBSTITUTES = {"▾": "▼", "−": "-", "✓": "v", "✔": "v", "✗": "x", "✘": "x"}
UNKNOWN = "?"


@lru_cache(maxsize=1)
def _glyphs() -> frozenset[int]:
    return frozenset(TTFont(REGULAR).getBestCmap() or {})


def _drawable(text: str) -> bool:
    glyphs = _glyphs()
    return all(ord(ch) in glyphs for ch in text)


def printable(text: str) -> str:
    """Text the bundled font can draw: a missing character becomes its listed substitute, else its NFKC form
    (① → 1, ℃ → °C), else '?'. Line breaks stay; other whitespace becomes a space."""
    out = []
    for ch in text:
        if ch == "\n" or _drawable(ch):
            out.append(ch)
        elif ch.isspace():
            out.append(" ")
        elif ch in SUBSTITUTES:
            out.append(SUBSTITUTES[ch])
        else:
            folded = unicodedata.normalize("NFKC", ch)
            out.append(folded if folded != ch and _drawable(folded) else UNKNOWN)
    return "".join(out)
