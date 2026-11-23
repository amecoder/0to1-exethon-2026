from __future__ import annotations
"""FR-01: split pasted chunks into sentence-level source items (SRC-).

`raw` is the sentence exactly as pasted (G4 keeps it); `text` drops a leading messenger timestamp
such as "**[월 오전 10:15]** " so every sentence reads the same way regardless of its position.
"""

import re
from collections.abc import Sequence
from typing import Any

_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+")
_SEPARATOR = re.compile(r"^[-=*_\s]{3,}$")
_TIMESTAMP = re.compile(r"^(?:\*\*)?\[[^\]\n]{1,30}\](?:\*\*)?\s*")


def src_id(n: int) -> str:
    return f"SRC-{n:02d}"


def split_sentences(chunks: Sequence[str]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for chunk_no, chunk in enumerate(chunks, start=1):
        for line in chunk.splitlines():
            line = line.strip()
            if not line or _SEPARATOR.match(line):
                continue
            stamp = _TIMESTAMP.match(line)
            prefix = stamp.group(0) if stamp else ""
            sentences = [s.strip() for s in _SENTENCE_END.split(line[len(prefix):]) if s.strip()]
            for index, sentence in enumerate(sentences):
                raw = f"{prefix}{sentence}" if index == 0 else sentence
                sources.append({"id": src_id(len(sources) + 1), "text": sentence, "raw": raw, "chunk": chunk_no})
    return sources
