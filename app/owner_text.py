from __future__ import annotations
"""Text for the owner-facing documents (BRD, 제안요약): no internal reference numbers inside a sentence.

A parenthesis that holds nothing but IDs — 「(DEC-02·09, TC-09·12)」, 「[SRC-01, SRC-02]」 — is taken out of the
sentence and returned, so the caller can list the references once in an appendix for the development team.
An ID that is part of the sentence itself is left alone: removing it would change what the sentence says.
"""

import re

SCOPE_MARK = "(범위 밖)"
_ID = r"[A-Z]{1,5}-\d+(?:\(범위 밖\))?"
_LIST = rf"{_ID}(?:\s*[·~,]\s*(?:{_ID}|\d+(?:\(범위 밖\))?))*"
_REFS = re.compile(rf"\s*(?:\(\s*{_LIST}\s*\)|\[\s*{_LIST}\s*\])")


def strip_refs(text: str) -> tuple[str, list[str]]:
    """(the text without ID-only parentheses, the references taken out — in reading order)."""
    found = [m.group(0).strip()[1:-1].strip() for m in _REFS.finditer(text)]
    return (_REFS.sub("", text) if found else text), found


def excerpt(text: str, limit: int = 28) -> str:
    """The start of a sentence, to name it in the appendix. A 「(범위 밖)」 mark is never cut in half."""
    plain = " ".join(text.split())
    if len(plain) <= limit:
        return plain
    mark = plain.find(SCOPE_MARK, max(0, limit - len(SCOPE_MARK)))
    cut = mark + len(SCOPE_MARK) if 0 <= mark < limit else limit
    return plain[:cut].rstrip() + "…"
