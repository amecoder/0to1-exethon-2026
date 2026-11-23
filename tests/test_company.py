from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.company import COMPANY_DECISION, MAX_ITEMS, SERVICE_NOTE, company_items, service_line
from app.systems import LINE_MAX
from app.config import Settings
from app.liner import RERANK_URL, LinerClient
from app.main import create_app
from app.store import DEFAULT_COMPANY, ProjectStore, empty_source
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, card, flower_outputs
from tests.test_liner_features import add_env
from tests.test_orchestrator import CHUNKS, build, to_cp1


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "company.sqlite3")


def decided(topic: str, chosen: str, **extra: Any) -> dict[str, Any]:
    return {"id": f"DEC-{abs(hash(topic)) % 90 + 10}", "topic": topic, "chosen": chosen, "status": "확정",
            "answered_by": "client", **extra}


def with_decisions(*decisions: dict[str, Any], cp2: bool | None = True) -> dict[str, Any]:
    """A project whose answers are on record; by default its latest CP2 record is approved (D3: only then they carry)."""
    confirmations = [] if cp2 is None else [{"cp": "CP2", "approved": cp2}]
    return {**empty_source(), "decisions": list(decisions), "confirmations": confirmations}


# --- store ---------------------------------------------------------------------------------------
def test_projects_are_listed_only_in_their_own_company(store: ProjectStore) -> None:
    a = store.create_company("꽃집 체인")
    b = store.create_company("동네 세탁소")
    store.create("정기구독", "real", company_id=a["id"])
    store.create("수거 예약", "real", company_id=b["id"])
    assert [p["name"] for p in store.summaries("real", 20, company_id=a["id"])] == ["정기구독"]
    assert [p["name"] for p in store.summaries("real", 20, company_id=b["id"])] == ["수거 예약"]
    assert store.count("real", company_id=a["id"]) == 1
    assert store.get(store.ids()[0])["company_id"] in (a["id"], b["id"])


def test_projects_from_before_companies_move_to_the_default_company(tmp_path: Path) -> None:
    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL, "
                     "created_at TEXT NOT NULL, source_json TEXT NOT NULL)")
        conn.execute("INSERT INTO projects VALUES ('p1', '예전 것', 'real', '2026-11-01T00:00:00+00:00', ?)",
                     (json.dumps(empty_source()),))
    store = ProjectStore(db)
    assert store.get("p1")["company_id"] == DEFAULT_COMPANY
    assert [c["id"] for c in store.companies()] == [DEFAULT_COMPANY]
    assert store.companies()[0]["projects"] == 1


def test_company_profile_is_saved(store: ProjectStore) -> None:
    a = store.create_company("꽃집 체인")
    store.update_company(a["id"], systems="꽃집 POS: 매장 결제", notes="회원 등급은 3단계다")
    got = store.get_company(a["id"])
    assert (got["systems"], got["notes"]) == ("꽃집 POS: 매장 결제", "회원 등급은 3단계다")
    with pytest.raises(KeyError):
        store.update_company("없는회사", systems="", notes="")


def test_past_decisions_come_only_from_confirmed_answers_of_the_same_company(store: ProjectStore) -> None:
    a = store.create_company("꽃집 체인")
    b = store.create_company("동네 세탁소")
    store.create("정기구독", "real", with_decisions(
        decided("결제 수단", "토스로 결제한다"),
        decided("배송 요일", "토요일 일괄", superseded_by="CHG-01"),  # replaced later: not carried
        decided("포장", "친환경 포장", status="가정"),  # filled by default, never chosen
        decided("만들기 전에", "새로 만들기", kind="build_or_buy"),  # this project's build-or-buy call only
    ), company_id=a["id"])
    store.create("수거 예약", "real", with_decisions(decided("수거 시간", "오전만")), company_id=b["id"])
    past = store.past_decisions(a["id"])
    assert [(d["topic"], d["chosen"], d["project"]) for d in past] == [("결제 수단", "토스로 결제한다", "정기구독")]


# --- company items given to the agents ---------------------------------------------------------------
def test_company_items_number_notes_lines_then_past_decisions() -> None:
    profile = {"name": "꽃집 체인", "notes": "# 용어\n- 회원 등급은 3단계다\n\n정기구독은 월 단위다"}
    past = [{"topic": "결제 수단", "chosen": "토스로 결제한다", "project": "정기구독", "decision_id": "DEC-02"}]
    items = company_items(profile, past)
    assert [(i["id"], i["kind"], i["text"]) for i in items] == [
        ("CMP-01", "note", "회원 등급은 3단계다"),
        ("CMP-02", "note", "정기구독은 월 단위다"),
        ("CMP-03", COMPANY_DECISION, "결제 수단 → 토스로 결제한다"),
    ]
    assert items[2]["project"] == "정기구독"


def test_over_the_cap_the_notes_stay_and_the_newest_decisions_win() -> None:
    past = [{"topic": f"주제 {n}", "chosen": f"답 {n}", "project": "p"} for n in range(1, MAX_ITEMS + 6)]
    items = company_items({"notes": "회원 등급은 3단계다"}, past)
    assert len(items) == MAX_ITEMS and items[0]["text"] == "회원 등급은 3단계다"
    assert items[1]["text"] == "주제 7 → 답 7"  # one note takes one of the 40 places
    assert items[-1]["text"] == f"주제 {MAX_ITEMS + 5} → 답 {MAX_ITEMS + 5}"


def test_no_company_material_gives_no_items() -> None:
    assert company_items({"name": "새 회사", "notes": ""}, []) == []


# --- API ---------------------------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path: Path, key_env: Path) -> TestClient:
    liner = LinerClient(env_file=key_env, transport=FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY).transport())
    return TestClient(create_app(Settings(db_path=tmp_path / "api.sqlite3", env_file=key_env), liner=liner))


def test_company_api_creates_lists_and_filters_projects(client: TestClient) -> None:
    a = client.post("/api/companies", json={"name": "꽃집 체인"}).json()
    b = client.post("/api/companies", json={"name": "동네 세탁소"}).json()
    client.post("/api/projects", json={"name": "정기구독", "mode": "real", "company_id": a["id"]})
    client.post("/api/projects", json={"name": "수거 예약", "mode": "real", "company_id": b["id"]})
    listed = client.get(f"/api/projects?company={a['id']}").json()
    assert [p["name"] for p in listed["projects"]] == ["정기구독"] and listed["total"] == 1
    names = {c["name"]: c["projects"] for c in client.get("/api/companies").json()["companies"]}
    assert names == {"기본 회사": 0, "꽃집 체인": 1, "동네 세탁소": 1}


def test_unknown_company_is_refused(client: TestClient) -> None:
    response = client.post("/api/projects", json={"name": "x", "mode": "real", "company_id": "없음"})
    assert response.status_code == 404


def test_company_profile_api_saves_and_blocks_sensitive_text(client: TestClient) -> None:
    a = client.post("/api/companies", json={"name": "꽃집 체인"}).json()
    saved = client.put(f"/api/companies/{a['id']}", json={"systems": "꽃집 POS", "notes": "회원 등급은 3단계다"})
    assert saved.status_code == 200 and saved.json()["notes"] == "회원 등급은 3단계다"
    blocked = client.put(f"/api/companies/{a['id']}", json={"systems": "", "notes": "대표 연락처 010-1234-5678"})
    assert blocked.status_code == 400
    assert client.get(f"/api/companies/{a['id']}").json()["notes"] == "회원 등급은 3단계다"


def test_input_copies_the_company_material_into_the_project(client: TestClient) -> None:
    a = client.post("/api/companies", json={"name": "꽃집 체인"}).json()
    client.put(f"/api/companies/{a['id']}", json={"systems": "", "notes": "회원 등급은 3단계다"})
    project = client.post("/api/projects", json={"name": "정기구독", "mode": "real", "company_id": a["id"]}).json()
    client.post(f"/api/projects/{project['id']}/input", json={"chunks": CHUNKS})
    source = client.get(f"/api/projects/{project['id']}").json()["source"]
    assert [i["text"] for i in source["company"]] == ["회원 등급은 3단계다"]
    assert source["meta"]["company"] == {"id": a["id"], "name": "꽃집 체인"}


# --- S3: findings the company material already answers ----------------------------------------------
COMPANY = [{"id": "CMP-01", "kind": COMPANY_DECISION, "text": "결제 실패 시 → 다음 날 한 번 더 결제한다",
            "project": "정기구독"}]


def run_s3(repo_root: Path, key_env: Path, cards_out: dict[str, Any], company: list[dict[str, Any]]):
    orch, ws, fake = build(repo_root, key_env, {"question_cards": [cards_out]})
    assert orch.ingest(CHUNKS, company=company).blocked is False
    orch.advance()
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    return ws, fake


def test_a_finding_the_company_answered_becomes_a_company_decision_not_a_card(repo_root: Path, key_env: Path) -> None:
    out = {"cards": [card("고객이 요일을 고르나요?", ["고객이 고름", "토요일 일괄"], [])],
           "settled": [{"finding_ref": "FND-02", "company_ref": "CMP-01", "answer": "다음 날 한 번 더 결제한다"}]}
    ws, fake = run_s3(repo_root, key_env, out, COMPANY)
    (dec,) = [d for d in ws.items("decisions") if d.get("kind") == "company"]
    assert dec["chosen"] == "다음 날 한 번 더 결제한다" and dec["company_ref"] == "CMP-01"
    assert dec["finding_refs"] == ["FND-02"] and dec["status"] == "확정"
    assert dec["answer_kind"] == "free_text"  # the PM may word it its own way: CP2's verbatim check skips it
    assert not ws.items("open_items")  # the answered finding is not left as undecided
    sent = fake.chat_payloads("question_cards")[0]
    assert "settled" in sent["response_format"]["json_schema"]["schema"]["properties"]
    assert "CMP-01" in sent["messages"][1]["content"]


def test_a_settled_entry_naming_nothing_real_is_ignored(repo_root: Path, key_env: Path) -> None:
    out = {"cards": [card("고객이 요일을 고르나요?", ["고객이 고름", "토요일 일괄"], [])],
           "settled": [{"finding_ref": "FND-02", "company_ref": "CMP-99", "answer": "지어낸 답"},
                       {"finding_ref": "FND-77", "company_ref": "CMP-01", "answer": "없는 지적"}]}
    ws, _ = run_s3(repo_root, key_env, out, COMPANY)
    assert not [d for d in ws.items("decisions") if d.get("kind") == "company"]
    assert [o["finding_refs"] for o in ws.items("open_items")] == [["FND-02"]]


def test_without_company_material_the_card_call_is_unchanged(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    to_cp1(orch)
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    sent = fake.chat_payloads("question_cards")[0]
    assert "settled" not in sent["response_format"]["json_schema"]["schema"]["properties"]
    assert "company" not in sent["messages"][1]["content"].split("[공유 원본")[0]


# --- services the company already built with 0to1 (company ontology v1) -------------------------------
def built(name_reqs: list[tuple[str, str]], approved: bool = True) -> dict[str, Any]:
    reqs = [{"id": f"REQ-{n:02d}", "title": t, "statement": f"{t} 한다", "status": s, "screens": [f"SCR-{n:02d}"]}
            for n, (t, s) in enumerate(name_reqs, start=1)]
    return {**empty_source(), "requirements": reqs,
            "confirmations": [{"cp": "CP4", "approved": approved}]}


def test_services_are_the_company_projects_confirmed_at_cp4(store: ProjectStore) -> None:
    a = store.create_company("꽃집 체인")
    b = store.create_company("동네 세탁소")
    store.create("꽃님 정기구독", "real", built([("정기구독 신청", "확정"), ("구독 일시정지", "가정"),
                                              ("배송 시간대", "미결")]), company_id=a["id"])
    store.create("아직 검토 중", "real", built([("선물하기", "확정")], approved=False), company_id=a["id"])
    store.create("수거 예약", "real", built([("수거 신청", "확정")]), company_id=b["id"])
    (service,) = store.services(a["id"])
    assert service["name"] == "꽃님 정기구독"
    assert [(f["id"], f["title"]) for f in service["features"]] == [("REQ-01", "정기구독 신청"), ("REQ-02", "구독 일시정지")]
    assert service["features"][0]["screens"] == ["SCR-01"]


def test_a_service_becomes_one_line_of_the_systems_list() -> None:
    service = {"name": "꽃님 정기구독", "features": [{"title": "정기구독 신청"}, {"title": "구독 일시정지"}]}
    assert service_line(service) == f"꽃님 정기구독: {SERVICE_NOTE} · 기능 정기구독 신청, 구독 일시정지"


def test_a_long_feature_list_keeps_the_given_order_until_the_line_is_full() -> None:
    feats = [{"title": f"기능 {n:02d} " + "가" * 20} for n in range(1, 40)]
    line = service_line({"name": "큰 서비스", "features": feats})
    assert len(line) <= LINE_MAX and "기능 01" in line and "기능 39" not in line


def test_input_adds_the_built_services_to_the_systems_list(client: TestClient, tmp_path: Path) -> None:
    a = client.post("/api/companies", json={"name": "꽃집 체인"}).json()
    first = client.post("/api/projects", json={"name": "꽃님 정기구독", "mode": "real", "company_id": a["id"]}).json()
    ProjectStore(tmp_path / "api.sqlite3").save_source(first["id"], built([("정기구독 신청", "확정")]), 0)
    second = client.post("/api/projects", json={"name": "선물하기", "mode": "real", "company_id": a["id"]}).json()
    client.post(f"/api/projects/{second['id']}/input", json={"chunks": CHUNKS, "systems": "꽃집 POS: 매장 결제"})
    systems = client.get(f"/api/projects/{second['id']}").json()["source"]["systems"]
    assert [s["name"] for s in systems] == ["꽃집 POS", "꽃님 정기구독"]
    assert SERVICE_NOTE in systems[1]["raw"] and "정기구독 신청" in systems[1]["raw"]
    detail = client.get(f"/api/companies/{a['id']}").json()
    assert [s["name"] for s in detail["services"]] == ["꽃님 정기구독"]


def test_features_are_ordered_by_how_close_they_are_to_the_request(repo_root: Path, key_env: Path) -> None:
    add_env(key_env, LINER_RERANK_MODEL="cohere/rerank-5-fast")
    orch, ws, fake = build(repo_root, key_env)
    feats = [{"title": f"관계없는 기능 {n} " + "나" * 25} for n in range(12)] + [{"title": "정기구독 결제 실패 처리"}]
    service = {"name": "꽃님 정기구독", "features": feats}
    assert orch.ingest(CHUNKS, services=[service]).blocked is False
    (line,) = [s["raw"] for s in ws.items("systems")]
    assert "정기구독 결제 실패 처리" in line  # the close one made it into the line although it was listed last
    assert fake.payloads(RERANK_URL)  # Liner rerank chose the order


def test_a_service_system_carries_the_ids_of_the_features_on_its_line(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    service = {"name": "꽃님 정기구독", "features": [{"id": "REQ-01", "title": "정기구독 신청"},
                                                  {"id": "REQ-02", "title": "배송 지역 서울 한정"}]}
    orch.ingest(CHUNKS, systems="꽃집 POS: 매장 결제", services=[service])
    pos, built_one = ws.items("systems")
    assert "features" not in pos  # the client's own systems have no feature list
    assert built_one["features"] == [{"id": "SYS-02/REQ-01", "title": "정기구독 신청"},
                                     {"id": "SYS-02/REQ-02", "title": "배송 지역 서울 한정"}]


def test_only_the_features_that_fit_on_the_line_get_an_id(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    feats = [{"id": f"REQ-{n:02d}", "title": f"기능 {n:02d} " + "가" * 20} for n in range(1, 40)]
    orch.ingest(CHUNKS, services=[{"name": "큰 서비스", "features": feats}])
    (system,) = ws.items("systems")
    titles = [f["title"] for f in system["features"]]
    assert titles and all(t in system["raw"] for t in titles)
    assert len(titles) < len(feats) and feats[len(titles)]["title"] not in system["raw"]


LONG = [{"id": f"REQ-{n:02d}", "title": f"기능 {n} " + "나" * 25} for n in range(14)]


@pytest.mark.parametrize("mask", [False, True])
def test_sensitive_text_never_reaches_rerank(repo_root: Path, key_env: Path, mask: bool) -> None:
    add_env(key_env, LINER_RERANK_MODEL="cohere/rerank-5-fast")
    orch, ws, fake = build(repo_root, key_env)
    secret = "담당자 연락처 010-1234-5678"
    res = orch.ingest([*CHUNKS, secret], mask=mask, services=[{"name": "꽃님 정기구독", "features": LONG}])
    assert res.blocked is (not mask)
    assert "010-1234-5678" not in json.dumps(ws.source, ensure_ascii=False)
    assert "010-1234-5678" not in json.dumps(fake.payloads(RERANK_URL), ensure_ascii=False)
    assert bool(fake.payloads(RERANK_URL)) is mask  # a blocked input is not reranked at all


def test_the_call_cap_during_rerank_keeps_the_given_order() -> None:
    from types import SimpleNamespace
    from app.company import ranked_service
    from app.limits import LimitReachedError

    def capped(*_: Any) -> Any:
        raise LimitReachedError("calls", 3, 3, "S1")
    events: list[tuple[Any, ...]] = []
    ctx = SimpleNamespace(runner=SimpleNamespace(rerank=capped), ws=SimpleNamespace(emit=lambda *a: events.append(a)))
    service = {"name": "꽃님 정기구독", "features": LONG}
    assert ranked_service(ctx, "선물하기", service) == service  # type: ignore[arg-type]
    assert events and events[0][2]["check"] == "rerank" and events[0][2]["outcome"] == "skipped"


def test_a_service_whose_name_is_part_of_a_listed_system_still_joins(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    orch.ingest(CHUNKS, systems="주문관리 시스템: 주문 상태", services=[{"name": "주문", "features": [{"id": "REQ-01", "title": "주문하기"}]}])
    assert [s["name"] for s in ws.items("systems")] == ["주문관리 시스템", "주문"]
    orch2, ws2, _ = build(repo_root, key_env)
    orch2.ingest(CHUNKS, systems="주문: 우리가 직접 적은 설명", services=[{"name": "주문", "features": [{"title": "주문하기"}]}])
    assert [s["name"] for s in ws2.items("systems")] == ["주문"]  # the client's own line wins


def test_a_company_name_must_have_text_and_no_personal_data(client: TestClient) -> None:
    assert client.post("/api/companies", json={"name": "   "}).status_code in (400, 422)
    assert client.post("/api/companies", json={"name": "김꽃님 010-1234-5678"}).status_code == 400


def test_an_answer_unrelated_to_its_company_item_is_left_open(repo_root: Path, key_env: Path) -> None:
    out = {"cards": [card("고객이 요일을 고르나요?", ["고객이 고름", "토요일 일괄"], [])],
           "settled": [{"finding_ref": "FND-02", "company_ref": "CMP-01", "answer": "회원 등급은 세 단계로 나눈다"}]}
    ws, _ = run_s3(repo_root, key_env, out, COMPANY)
    assert not [d for d in ws.items("decisions") if d.get("kind") == "company"]
    assert any("FND-02" in o["finding_refs"] for o in ws.items("open_items"))  # still undecided, not closed
    checks = [e["data"] for e in ws.source["events"] if e["type"] == "check_result" and e["data"]["check"] == "company_settled"]
    assert checks and checks[0]["outcome"] == "flagged"


def test_relatedness_is_shared_wording_with_the_company_item() -> None:
    from app.company import RELATED_MIN, relatedness
    text = "일시정지는 최대 얼마 동안 가능하고, 다시 시작은 어떻게 하나요? → 최대 4주까지 정지 가능, 고객이 직접 재개"
    assert relatedness("일시정지는 최대 4주, 고객이 직접 재개하며 기간이 지나면 자동 재개", text) >= RELATED_MIN
    assert relatedness("회원 등급은 세 단계로 나눈다", text) < RELATED_MIN


def test_company_answers_are_shown_as_company_material_not_the_clients() -> None:
    from app.checks import answer_table
    from app.documents.prd import decision_rows
    dec = {"id": "DEC-01", "kind": "company", "topic": "결제 실패", "chosen": "다음 날 한 번 더 결제한다",
           "answer_kind": "free_text", "status": "확정", "answered_by": "company", "company_ref": "CMP-01"}
    source = {**empty_source(), "decisions": [dec]}
    (row,) = answer_table(source)
    assert row["answered_by"] == "company" and row["company_ref"] == "CMP-01"
    (prd,) = decision_rows(source)
    assert prd[-1] == "회사 자료 CMP-01" and "발주사" not in prd[-1]



# --- D3 (11-20): which past answers carry over ----------------------------------------------------------
def test_answers_before_cp2_do_not_carry_over(store: ProjectStore) -> None:
    a = store.create_company("꽃집 체인")
    store.create("시험 삼아", "real", with_decisions(decided("결제 수단", "토스"), cp2=None), company_id=a["id"])
    store.create("반려됨", "real", with_decisions(decided("포장", "친환경"), cp2=False), company_id=a["id"])
    assert store.past_decisions(a["id"]) == []


def test_the_same_question_keeps_the_newest_projects_answer(store: ProjectStore) -> None:
    a = store.create_company("꽃집 체인")
    store.create("1차", "real", with_decisions(decided("결제 수단은?", "토스"), decided("포장", "친환경")), company_id=a["id"])
    store.create("2차", "real", with_decisions(decided("결제 수단은 ?", "카카오페이")), company_id=a["id"])
    past = store.past_decisions(a["id"])
    assert [(d["topic"], d["chosen"], d["project"]) for d in past] == [("포장", "친환경", "1차"), ("결제 수단은 ?", "카카오페이", "2차")]


def test_cards_task_says_to_ask_when_past_decisions_disagree(repo_root: Path, key_env: Path) -> None:
    out = {"cards": [card("고객이 요일을 고르나요?", ["고객이 고름", "토요일 일괄"], [])], "settled": []}
    _, fake = run_s3(repo_root, key_env, out, COMPANY)
    assert "서로 다르게 정했으면" in fake.chat_payloads("question_cards")[0]["messages"][0]["content"] + \
        fake.chat_payloads("question_cards")[0]["messages"][-1]["content"]


# --- D2 (11-20): company material vs. the client's own answer -------------------------------------------
PAY_ANSWER = "다음 날 한 번 더 결제한다"


def test_a_finding_asked_on_a_card_is_not_settled_by_company_material(repo_root: Path, key_env: Path) -> None:
    out = {"cards": [card("고객이 요일을 고르나요?", ["고객이 고름", "토요일 일괄"], [])],  # the card is on FND-01
           "settled": [{"finding_ref": "FND-01", "company_ref": "CMP-01", "answer": PAY_ANSWER}]}
    ws, _ = run_s3(repo_root, key_env, out, COMPANY)
    assert len(ws.items("questions")) == 1
    assert [d for d in ws.items("decisions") if d.get("kind") == "company"] == []
    assert not [o for o in ws.items("open_items") if "FND-01" in o["finding_refs"]]


def test_a_card_over_the_cap_that_company_material_settled_leaves_no_open_item(repo_root: Path, key_env: Path) -> None:
    from app.stage_common import FIRST_ROUND_MAX_CARDS
    cards = [card(f"충돌 질문 {n}", ["가", "나"], []) for n in range(FIRST_ROUND_MAX_CARDS)]
    cards.append(card("결제 실패는?", ["가", "나"], [], finding_refs=["FND-02"]))
    out = {"cards": cards, "settled": [{"finding_ref": "FND-02", "company_ref": "CMP-01", "answer": PAY_ANSWER}]}
    ws, _ = run_s3(repo_root, key_env, out, COMPANY)
    (dec,) = [d for d in ws.items("decisions") if d.get("kind") == "company"]
    assert dec["finding_refs"] == ["FND-02"]
    assert not [o for o in ws.items("open_items") if "FND-02" in o["finding_refs"]]


def company_ctx(repo_root: Path) -> Any:
    from types import SimpleNamespace
    from app.definitions import load_definitions
    from app.workspace import Workspace
    agents, _ = load_definitions(repo_root)
    ws = Workspace(empty_source(), agents)
    ws.add_company(COMPANY, {"id": "c1", "name": "꽃집"})
    return SimpleNamespace(ws=ws)


def finding(fid: str, req: str) -> dict[str, Any]:
    return {"id": fid, "type": "missing_exception", "note": "결제 실패 처리", "requirement_ids": [req], "source_refs": []}


def test_an_s3_rework_does_not_repeat_a_company_decision(repo_root: Path) -> None:
    from app.company import write_settled
    ctx = company_ctx(repo_root)
    write_settled(ctx, [finding("FND-01", "REQ-02")], {"FND-01": ("CMP-01", PAY_ANSWER)})
    done = write_settled(ctx, [finding("FND-03", "REQ-04")], {"FND-03": ("CMP-01", "다음 날 한 번 더 결제한다.")})
    (dec,) = [d for d in ctx.ws.items("decisions") if d.get("kind") == "company"]
    assert done == {"FND-03"} and dec["finding_refs"] == ["FND-01", "FND-03"]
    assert dec["requirement_refs"] == ["REQ-02", "REQ-04"]


def test_another_answer_from_the_same_company_item_is_its_own_decision(repo_root: Path) -> None:
    from app.company import write_settled
    ctx = company_ctx(repo_root)
    write_settled(ctx, [finding("FND-01", "REQ-02")], {"FND-01": ("CMP-01", PAY_ANSWER)})
    write_settled(ctx, [finding("FND-03", "REQ-04")], {"FND-03": ("CMP-01", "결제 실패 시 바로 해지 안내를 보낸다")})
    assert len([d for d in ctx.ws.items("decisions") if d.get("kind") == "company"]) == 2


def test_pm_is_told_the_client_answer_wins_only_with_company_material(repo_root: Path, key_env: Path) -> None:
    for company, told in ((COMPANY, True), ([], False)):
        orch, ws, fake = build(repo_root, key_env)
        orch.ingest(CHUNKS, company=company)
        orch.advance()
        orch.confirm("CP1", True, "발주사")
        orch.advance()
        for q in ws.items("questions"):
            orch.answer(q["id"], "choice", q["options"][0])
        orch.submit_answers()
        orch.advance()
        sent = json.dumps(fake.chat_payloads("requirements_final")[0], ensure_ascii=False)
        assert ("발주사 답을 따르고" in sent) is told


# --- D4 (11-20): the systems list keeps the built services --------------------------------------------
def svc(name: str, n_features: int = 2, long: bool = False) -> dict[str, Any]:
    pad = " 가나다라마바사" * 3 if long else ""
    return {"name": name, "features": [{"id": f"REQ-{k:02d}", "title": f"기능 {k}{pad}"} for k in range(1, n_features + 1)]}


def systems_events(ws: Any) -> list[dict[str, Any]]:
    return [e["data"] for e in ws.source["events"] if e["type"] == "check_result" and e["data"]["check"] == "systems_list"]


def test_services_stay_when_the_client_list_is_full(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    orch.ingest(CHUNKS, systems="\n".join(f"시스템{n}: 설명" for n in range(30)), services=[svc("꽃님 정기구독"), svc("꽃님 클래스")])
    systems = ws.items("systems")
    assert len(systems) == 32 and [s["id"] for s in systems[-2:]] == ["SYS-31", "SYS-32"]
    assert systems[-1]["features"][0]["id"] == "SYS-32/REQ-01"


def test_a_long_client_list_never_cuts_a_service_line(repo_root: Path, key_env: Path) -> None:
    from app.company import service_line
    orch, ws, _ = build(repo_root, key_env)
    lines = "\n".join(f"시스템{n:02d}: " + "설" * 290 for n in range(20))
    service = svc("꽃님 정기구독")
    orch.ingest(CHUNKS, systems=lines, services=[service])
    last = ws.items("systems")[-1]
    assert last["raw"] == service_line(service) and last["features"]


def test_only_the_newest_ten_services_are_listed(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    orch.ingest(CHUNKS, services=[svc(f"서비스 {n}") for n in range(1, 13)])
    assert [s["name"] for s in ws.items("systems")] == [f"서비스 {n}" for n in range(3, 13)]
    (event,) = systems_events(ws)
    assert event["outcome"] == "flagged" and any("서비스 1, 서비스 2" in d for d in event["details"])


def test_client_lines_over_the_cap_are_reported(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    orch.ingest(CHUNKS, systems="\n".join(f"시스템{n}: 설명" for n in range(35)))
    assert len(ws.items("systems")) == 30
    (event,) = systems_events(ws)
    assert any("35줄 중 30줄" in d for d in event["details"])


def test_features_that_did_not_fit_are_counted(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    orch.ingest(CHUNKS, services=[svc("큰 서비스", 20, long=True)])
    (event,) = systems_events(ws)
    assert event["outcome"] == "passed" and any("20개 중" in d for d in event["details"])


def test_nothing_dropped_means_no_event(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    orch.ingest(CHUNKS, systems="POS: 결제\n재고: 수량\n배송: 출고", services=[svc("꽃님 정기구독")])
    assert systems_events(ws) == []


def test_a_service_name_with_a_colon_keeps_its_whole_name(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    orch.ingest(CHUNKS, services=[svc("꽃님: 정기구독")])
    assert ws.items("systems")[0]["name"] == "꽃님 정기구독"


def test_opposite_answers_from_one_company_item_stay_apart(repo_root: Path) -> None:
    """Review (11-21) #1: 「환불 가능」 and 「환불 불가능」 must never be joined as one decision."""
    from app.company import write_settled
    ctx = company_ctx(repo_root)
    write_settled(ctx, [finding("FND-01", "REQ-02"), finding("FND-02", "REQ-03")],
                  {"FND-01": ("CMP-01", "환불 가능"), "FND-02": ("CMP-01", "환불 불가능")})
    decisions = [d for d in ctx.ws.items("decisions") if d.get("kind") == "company"]
    assert sorted(d["chosen"] for d in decisions) == ["환불 가능", "환불 불가능"]


def test_one_round_never_joins_its_own_answers(repo_root: Path) -> None:
    from app.company import write_settled
    ctx = company_ctx(repo_root)
    write_settled(ctx, [finding("FND-01", "REQ-02"), finding("FND-02", "REQ-03")],
                  {"FND-01": ("CMP-01", PAY_ANSWER), "FND-02": ("CMP-01", PAY_ANSWER)})
    assert len([d for d in ctx.ws.items("decisions") if d.get("kind") == "company"]) == 2


def test_dropped_service_names_are_masked(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    orch.ingest(CHUNKS, services=[svc("김사장 010-1234-5678 앱"), *[svc(f"서비스 {n}") for n in range(10)]])
    assert "010-1234-5678" not in json.dumps(ws.source, ensure_ascii=False)
