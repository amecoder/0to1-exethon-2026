from __future__ import annotations
"""Intake triage on S1: code pre-check, one Liner model call per round, code rules on the verdict, the endpoint."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.intake_triage import SCHEMA_NAME, merge_verdict, precheck
from app.liner import CHAT_URL, DECISIONS_URL, LinerClient
from app.main import create_app
from tests.fake_liner import FakeLiner
from tests.test_policy import purpose
from tests.flower_script import SEARCH_BODY, flower_outputs, memo_chunks

REQUEST = "저희 꽃집 정기구독 앱을 만들고 싶어요. 고객이 일주일에 한 번 꽃을 받는 거예요."
FULL = {"who": "꽃집 단골 고객과 사장", "pain": "구독 주문을 전화로 받아 자주 빠뜨림",
        "done": "고객이 앱에서 구독을 신청하고 사장이 주문 목록을 본다"}


def model_out(case: str, **slots: str) -> dict[str, Any]:
    filled = {"who": "", "pain": "", "done": "", **slots}
    questions = [{"slot": s, "question": f"{s} 질문이에요?"} for s, v in filled.items() if not v]
    return {"case": case, "reason": f"{case} 이유", **filled, "questions": questions}


# --- precheck ------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["", "   ", "ㅁㄴㅇㄹ", "ㅁㄴㅇㄹ ㅁㄴㅇㄹ ㅋㅋㅋ", "ㅇㅁ", "꽃배달앱", "?!?!...",
                                  "아아아아아아아아아아아아", "앱 앱 앱 앱 앱 앱 앱"])
def test_precheck_catches_garbage_without_a_call(text: str) -> None:
    verdict = precheck(text)
    assert verdict is not None and verdict.case == "garbled" and verdict.reason
    assert verdict.questions == ()


@pytest.mark.parametrize("text", [REQUEST, "앱 만들어 주세요", "앱만들어주세요",  # no spaces is still a (thin) request
                                   "Build a booking web app for our clinic staff"])
def test_precheck_lets_real_text_through(text: str) -> None:
    assert precheck(text) is None


# --- merge_verdict -------------------------------------------------------------------------------
def test_ok_with_an_empty_slot_becomes_insufficient() -> None:
    verdict = merge_verdict({**model_out("ok", who=FULL["who"], pain=FULL["pain"]), "questions": []})
    assert verdict.case == "insufficient"
    assert verdict.missing() == ("done",)
    assert [q.slot for q in verdict.questions] == ["done"] and verdict.questions[0].question


def test_insufficient_with_every_slot_becomes_ok() -> None:
    verdict = merge_verdict(model_out("insufficient", **FULL))
    assert verdict.case == "ok" and verdict.questions == () and verdict.missing() == ()


def test_insufficient_asks_only_about_empty_slots() -> None:
    out = model_out("insufficient", who=FULL["who"])
    out["questions"] = [*out["questions"], {"slot": "who", "question": "이미 찬 칸 질문"}]
    verdict = merge_verdict(out)
    assert [q.slot for q in verdict.questions] == ["pain", "done"]
    assert verdict.questions[0].question == "pain 질문이에요?"


def test_cannot_stays_cannot_and_asks_nothing() -> None:
    verdict = merge_verdict(model_out("cannot", who="이삿짐 옮길 사람"))
    assert verdict.case == "cannot" and verdict.questions == () and verdict.reason == "cannot 이유"


def test_unknown_case_is_a_bad_answer() -> None:
    with pytest.raises(ValueError):
        merge_verdict({**model_out("ok", **FULL), "case": "maybe"})


# --- endpoint ------------------------------------------------------------------------------------
def client_for(tmp_path: Path, env_file: Path, triage: list[Any], **fake_kw: Any) -> tuple[TestClient, FakeLiner, str]:
    fake = FakeLiner({**flower_outputs(memo_chunks()), SCHEMA_NAME: triage}, search_body=SEARCH_BODY, **fake_kw)
    settings = Settings(db_path=tmp_path / "triage.sqlite3", env_file=env_file)
    client = TestClient(create_app(settings, liner=LinerClient(env_file=env_file, transport=fake.transport())))
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    return client, fake, f"/api/projects/{pid}"


def triage_events(client: TestClient, base: str) -> list[dict[str, Any]]:
    return [e for e in client.get(base).json()["source"]["events"] if e["type"] == "intake_triage"]


def test_ok_round_returns_slots_and_records_one_event(tmp_path: Path, key_env: Path) -> None:
    client, fake, base = client_for(tmp_path, key_env, [model_out("ok", **FULL)])
    response = client.post(f"{base}/input/triage", json={"chunks": [REQUEST]})
    assert response.status_code == 200
    body = response.json()
    assert body["case"] == "ok" and body["slots"] == FULL and body["questions"] == [] and body["blocked"] is False
    assert fake.chat_names == [SCHEMA_NAME]
    project = client.get(base).json()
    assert project["source"]["sources"] == [] and project["source"]["meta"]["pipeline"]["stage"] == "S1"
    [event] = triage_events(client, base)
    assert event["actor"] == "coordinator" and event["data"]["case"] == "ok" and event["data"]["missing"] == []


def test_insufficient_round_asks_and_the_answers_reach_the_model(tmp_path: Path, key_env: Path) -> None:
    client, fake, base = client_for(tmp_path, key_env, [model_out("insufficient", who=FULL["who"]),
                                                        model_out("ok", **FULL)])
    first = client.post(f"{base}/input/triage", json={"chunks": [REQUEST]}).json()
    assert first["case"] == "insufficient" and [q["slot"] for q in first["questions"]] == ["pain", "done"]
    assert first["slots"]["who"] == FULL["who"] and first["slots"]["pain"] == ""
    answers = [{"slot": "pain", "question": "pain 질문이에요?", "answer": "전화 주문을 자주 빠뜨려요"},
               {"slot": "done", "question": "done 질문이에요?", "answer": "앱으로 신청받으면 끝이에요"}]
    second = client.post(f"{base}/input/triage", json={"chunks": [REQUEST], "answers": answers}).json()
    assert second["case"] == "ok"
    sent = fake.chat_payloads(SCHEMA_NAME)[1]["messages"][-1]["content"]
    assert "전화 주문을 자주 빠뜨려요" in sent and REQUEST in sent
    events = triage_events(client, base)
    assert [e["data"]["case"] for e in events] == ["insufficient", "ok"]
    assert events[0]["data"]["missing"] == ["pain", "done"]


def test_cannot_round_gives_the_reason(tmp_path: Path, key_env: Path) -> None:
    client, _, base = client_for(tmp_path, key_env, [model_out("cannot")])
    body = client.post(f"{base}/input/triage", json={"chunks": ["토요일에 이삿짐 옮겨 줄 사람 두 명 보내 주세요"]}).json()
    assert body["case"] == "cannot" and body["reason"] == "cannot 이유" and body["questions"] == []


def test_garbled_text_is_judged_without_any_liner_call(tmp_path: Path, key_env: Path) -> None:
    client, fake, base = client_for(tmp_path, key_env, [model_out("ok", **FULL)])
    body = client.post(f"{base}/input/triage", json={"chunks": ["ㅁㄴㅇㄹ"]}).json()
    assert body["case"] == "garbled" and body["reason"]
    assert fake.requests == []
    [event] = triage_events(client, base)
    assert event["data"]["by"] == "code"


def test_sensitive_text_is_blocked_before_liner(tmp_path: Path, key_env: Path) -> None:
    client, fake, base = client_for(tmp_path, key_env, [model_out("ok", **FULL)])
    text = f"{REQUEST} 문의는 010-1234-5678 로 주세요"
    body = client.post(f"{base}/input/triage", json={"chunks": [text]}).json()
    assert body["blocked"] is True and body["guard"] == "G3" and "전화번호" in body["kinds"]
    assert fake.requests == []
    masked = client.post(f"{base}/input/triage", json={"chunks": [text], "mask": True}).json()
    assert masked["case"] == "ok"
    sent = [r for r in fake.requests if str(r.url) == CHAT_URL][0].content.decode()
    assert "1234-5678" not in sent


def test_sensitive_answer_is_blocked_too(tmp_path: Path, key_env: Path) -> None:
    client, fake, base = client_for(tmp_path, key_env, [model_out("ok", **FULL)])
    answers = [{"slot": "who", "question": "누가 쓰나요?", "answer": "사장님 010-1234-5678"}]
    body = client.post(f"{base}/input/triage", json={"chunks": [REQUEST], "answers": answers}).json()
    assert body["blocked"] is True and fake.requests == []


def test_liner_failure_is_an_error_to_retry_not_a_failed_pipeline(tmp_path: Path, key_env: Path) -> None:
    client, _, base = client_for(tmp_path, key_env, ["not json"])
    response = client.post(f"{base}/input/triage", json={"chunks": [REQUEST]})
    assert response.status_code == 502 and "다시" in response.json()["detail"]
    assert client.get(base).json()["source"]["meta"]["pipeline"]["status"] == "awaiting_input"


def test_triage_only_on_s1_awaiting_input(tmp_path: Path, key_env: Path) -> None:
    client, _, base = client_for(tmp_path, key_env, [model_out("ok", **FULL)])
    assert client.post(f"{base}/input", json={"chunks": memo_chunks()}).status_code == 202
    response = client.post(f"{base}/input/triage", json={"chunks": [REQUEST]})
    assert response.status_code == 409


def test_answers_chunk_reaches_the_team_as_a_source(tmp_path: Path, key_env: Path) -> None:
    client, _, base = client_for(tmp_path, key_env, [model_out("ok", **FULL)])
    chunk = "접수 대화에서 받은 답:\n- 무엇이 불편한가요? → 전화 주문을 자주 빠뜨려요"
    assert client.post(f"{base}/input", json={"chunks": [*memo_chunks(), chunk]}).status_code == 202
    texts = [s["text"] for s in client.get(base).json()["source"]["sources"]]
    assert any("전화 주문을 자주 빠뜨려요" in t for t in texts)


# --- G9 on a refused or thin request (11-22: a harmful request was told only 「맡을 수 없어요」) -----------------
GAMBLING = "불법 도박 사이트 회원을 모으는 앱을 만들어 주세요. 운영자가 회원에게 베팅을 권하는 기능이 필요해요."


def with_decisions(env_file: Path) -> Path:
    env_file.write_text(env_file.read_text(encoding="utf-8") + "LINER_DECISION_MODEL=m\n", encoding="utf-8")
    return env_file


def decision_calls(fake: FakeLiner) -> int:
    return sum(1 for r in fake.requests if str(r.url) == DECISIONS_URL)


def g9_events(client: TestClient, base: str) -> list[dict[str, Any]]:
    return [e["data"] for e in client.get(base).json()["source"]["events"]
            if e["type"] == "guardrail" and e["data"]["id"] == "G9"]


def test_harmful_request_the_model_refused_says_why(tmp_path: Path, key_env: Path) -> None:
    client, fake, base = client_for(tmp_path, with_decisions(key_env), [model_out("cannot")],
                                    decision=purpose("illegal", 0.9))
    body = client.post(f"{base}/input/triage", json={"chunks": [GAMBLING]}).json()
    assert body["blocked"] is True and body["guard"] == "G9" and body["kinds"] == []
    assert "불법 행위" in body["message"]
    [g9] = g9_events(client, base)
    assert g9["outcome"] == "blocked" and g9["category"] == "illegal"
    assert client.get(base).json()["source"]["sources"] == []


def test_harmless_refusal_stays_a_refusal(tmp_path: Path, key_env: Path) -> None:
    client, _, base = client_for(tmp_path, with_decisions(key_env), [model_out("cannot")],
                                 decision=purpose("ok", 0.05))
    body = client.post(f"{base}/input/triage", json={"chunks": ["토요일에 이삿짐 옮겨 줄 사람 두 명 보내 주세요"]}).json()
    assert body["blocked"] is False and body["case"] == "cannot"
    assert [e["outcome"] for e in g9_events(client, base)] == ["passed"]


def test_harmful_thin_request_is_refused_before_asking_more(tmp_path: Path, key_env: Path) -> None:
    client, _, base = client_for(tmp_path, with_decisions(key_env), [model_out("insufficient", who="회원")],
                                 decision=purpose("illegal", 0.9))
    body = client.post(f"{base}/input/triage", json={"chunks": [GAMBLING]}).json()
    assert body["blocked"] is True and body["guard"] == "G9"


def test_ok_and_garbled_rounds_add_no_decision_call(tmp_path: Path, key_env: Path) -> None:
    client, fake, base = client_for(tmp_path, with_decisions(key_env), [model_out("ok", **FULL)],
                                    decision=purpose("illegal", 0.9))
    assert client.post(f"{base}/input/triage", json={"chunks": [REQUEST]}).json()["case"] == "ok"
    assert client.post(f"{base}/input/triage", json={"chunks": ["ㅋㅋㅋㅋㅋㅋ"]}).json()["case"] == "garbled"
    assert decision_calls(fake) == 0  # ok goes on to /input, where G9 runs anyway


def test_without_decision_model_a_refusal_is_unchanged(tmp_path: Path, key_env: Path) -> None:
    client, _, base = client_for(tmp_path, key_env, [model_out("cannot")])
    body = client.post(f"{base}/input/triage", json={"chunks": [GAMBLING]}).json()
    assert body["blocked"] is False and body["case"] == "cannot"
    assert [e["outcome"] for e in g9_events(client, base)] == ["skipped"]
