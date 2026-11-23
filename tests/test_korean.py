from __future__ import annotations

import pytest

from app.korean import josa


@pytest.mark.parametrize(("word", "pair", "expected"), [
    ("요구사항", "을/를", "요구사항을"), ("화면", "이/가", "화면이"), ("프로토타입", "을/를", "프로토타입을"),
    ("시안", "은/는", "시안은"), ("메모", "을/를", "메모를"), ("REQ-01", "을/를", "REQ-01을"),
    ("REQ-02", "을/를", "REQ-02를"), ("CHG-03", "이/가", "CHG-03이"), ("v2", "으로/로", "v2로"),
    ("v3", "으로/로", "v3으로"), ("v1", "으로/로", "v1로"), ("서울", "으로/로", "서울로"),
    ("합의 위반", "으로/로", "합의 위반으로"), ("PM", "와/과", "PM과"), ("QA", "와/과", "QA와"), ("", "을/를", "을(를)"),
])
def test_josa_picks_the_particle_by_the_last_sound(word: str, pair: str, expected: str) -> None:
    assert josa(word, pair) == expected
