from __future__ import annotations
"""A project's name (D1, 11-20): what the client sees, and what a service built with 0to1 is called in the
systems list of the company's next requests. The systems list splits a line into name and description on ':' or
' — ', so a name never keeps those."""

import re

NAME_MAX = 40  # 제안값 (D1) — long enough for 「꽃님 정기구독 선물하기」, short for one line of a list
_SPLITTERS = re.compile(r"\s*[:：]\s*")
_DASH = re.compile(r"\s+[—–-]\s+")
_SPACE = re.compile(r"\s+")


def clean_name(text: str) -> str:
    """One line, no list separators, at most NAME_MAX characters; '' when nothing is left."""
    name = _DASH.sub("-", _SPLITTERS.sub(" ", _SPACE.sub(" ", text)))
    return _SPACE.sub(" ", name).strip()[:NAME_MAX].strip()
