from __future__ import annotations
"""Korean particles after a variable word (을/를, 이/가, 은/는, 와/과, 으로/로, 이에요/예요).

Picks by the last sound: Hangul by its final consonant, digits by their Korean reading (1 일, 3 삼 …), and
Latin letters by how they are spelled out (L 엘, M 엠, N 엔, R 알 end in a consonant).
"""

HANGUL_START, HANGUL_END = 0xAC00, 0xD7A3
RIEUL = 8  # index of ㄹ among final consonants
DIGIT_FINAL = {"0": "ㅇ", "1": "ㄹ", "2": "", "3": "ㅁ", "4": "", "5": "", "6": "ㄱ", "7": "ㄹ", "8": "ㄹ", "9": ""}
LATIN_FINAL = {"l": "ㄹ", "m": "ㅁ", "n": "ㄴ", "r": "ㄹ"}
AFTER_CONSONANT = ("을", "이", "은", "과", "으로", "이에요")


def _final(word: str) -> str | None:
    """'' for an open syllable, 'ㄹ'/'x' for a final consonant, None when no letter or digit is found."""
    for ch in reversed(word.strip()):
        code = ord(ch)
        if HANGUL_START <= code <= HANGUL_END:
            index = (code - HANGUL_START) % 28
            return "" if index == 0 else ("ㄹ" if index == RIEUL else "x")
        if ch in DIGIT_FINAL:
            return DIGIT_FINAL[ch]
        if ch.isascii() and ch.isalpha():
            return LATIN_FINAL.get(ch.lower(), "")
    return None


def josa(word: str, pair: str) -> str:
    """`word` + the right particle of `pair` ("을/를", "와/과", "으로/로" — either order)."""
    first, second = pair.split("/")
    with_final, without_final = (first, second) if first in AFTER_CONSONANT else (second, first)
    final = _final(word)
    if final is None:
        return f"{word}{with_final}({without_final})"
    if with_final == "으로":
        return word + ("로" if final in ("", "ㄹ") else "으로")
    return word + (with_final if final else without_final)
