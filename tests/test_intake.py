from __future__ import annotations

from app.intake import split_sentences
from tests.flower_script import memo_chunks


def test_messenger_timestamp_is_stripped_from_text_but_kept_in_raw() -> None:
    sources = split_sentences(["**[월 오전 10:13]** 고객이 일주일에 한 번 꽃을 받는 거예요. 사이즈는 S, M 두 가지고요."])
    assert [s["text"] for s in sources] == ["고객이 일주일에 한 번 꽃을 받는 거예요.", "사이즈는 S, M 두 가지고요."]
    assert sources[0]["raw"] == "**[월 오전 10:13]** 고객이 일주일에 한 번 꽃을 받는 거예요."
    assert sources[1]["raw"] == "사이즈는 S, M 두 가지고요."


def test_plain_lines_have_identical_text_and_raw() -> None:
    (only,) = split_sentences(["배송은 토요일이에요."])
    assert only["text"] == only["raw"] == "배송은 토요일이에요."


def test_flower_memo_texts_never_carry_timestamps() -> None:
    sources = split_sentences(memo_chunks())
    assert all("**[" not in s["text"] for s in sources)
    joined = "\n".join(memo_chunks())
    assert all(s["raw"] in joined for s in sources)
    assert any(s["raw"].startswith("**[월 오후 2:40]**") for s in sources)


def test_line_with_only_a_timestamp_is_skipped() -> None:
    assert split_sentences(["**[월 오전 10:12]**", "다음 문장."])[0]["text"] == "다음 문장."
