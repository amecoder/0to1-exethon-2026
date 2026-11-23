from __future__ import annotations
"""「우리 시스템 목록」: the client's existing systems, compared in S2 (기능 추가 / 연계) and tagged on requirements."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.liner import LinerClient
from app.main import create_app
from app.systems import MAX_SYSTEMS, REUSE, parse_systems, requirement_features
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, candidates, flower_outputs, problem_scope, src_id
from tests.pipeline_helpers import CHUNKS, build

CATALOG = """
# 우리 시스템
- 주문관리 시스템: 주문 상태와 배송 요일을 갖고 있어요. 주문 조회 API가 있어요.
* 알림톡 발송 — 카카오 알림톡을 보낼 수 있어요
결제 모듈

"""


def with_fit(**fit: Any) -> dict[str, Any]:
    weekly = src_id(CHUNKS, "일주일에 한 번")
    base = {"system_ref": "SYS-01", "fit": "기능 추가", "what": "주문관리에 구독 주기를 추가한다",
            "refs": [weekly], "quote": "일주일에 한 번"}
    return {**problem_scope(CHUNKS), "system_fit": [{**base, **fit}]}


def tagged_candidates(**req: Any) -> dict[str, Any]:
    out = candidates(CHUNKS)
    first = {**out["requirements"][0], **req}
    return {**out, "requirements": [first, *out["requirements"][1:]]}


def test_parse_systems_one_line_each() -> None:
    systems = parse_systems(CATALOG)
    assert [s["id"] for s in systems] == ["SYS-01", "SYS-02", "SYS-03"]
    assert systems[0]["name"] == "주문관리 시스템" and systems[0]["about"].startswith("주문 상태와")
    assert systems[1]["name"] == "알림톡 발송" and systems[1]["about"] == "카카오 알림톡을 보낼 수 있어요"
    assert systems[2] == {"id": "SYS-03", "name": "결제 모듈", "about": "", "raw": "결제 모듈"}
    assert parse_systems("") == [] and parse_systems("  \n# 제목만\n") == []
    many = "\n".join(f"시스템{i}: 설명" for i in range(MAX_SYSTEMS + 5))
    assert len(parse_systems(many)) == MAX_SYSTEMS


def test_systems_reach_fde_and_fit_is_checked(repo_root: Path, key_env: Path) -> None:
    bad = {"system_ref": "SYS-09", "fit": "연계", "what": "없는 시스템", "refs": [], "quote": ""}
    wrong_quote = {"system_ref": "SYS-02", "fit": "연계", "what": "알림톡으로 안내", "refs": [src_id(CHUNKS, "서울만")],
                   "quote": "지어낸 인용"}
    scope_out = with_fit()
    scope_out["system_fit"] += [bad, wrong_quote]
    orch, ws, fake = build(repo_root, key_env, {"problem_scope": [scope_out]})
    orch.ingest(CHUNKS, systems=CATALOG)
    orch.advance()
    assert [s["id"] for s in ws.items("systems")] == ["SYS-01", "SYS-02", "SYS-03"]
    content = fake.chat_payloads("problem_scope")[0]["messages"][-1]["content"]
    assert "주문관리 시스템" in content and "system_fit" in content
    fits = ws.items("scope")[0]["systems"]
    assert [f["system_ref"] for f in fits] == ["SYS-01", "SYS-02"]
    assert fits[0] == {**fits[0], "name": "주문관리 시스템", "fit": "기능 추가", "status": "확인"}
    assert fits[1]["status"] == "미확인"
    details = [e["data"].get("detail", "") for e in ws.source["events"] if e["type"] == "guardrail"]
    assert any("목록에 없는 시스템" in d for d in details)


def test_without_systems_nothing_changes(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env)
    orch.ingest(CHUNKS)
    orch.advance()
    assert ws.items("systems") == ()
    content = fake.chat_payloads("problem_scope")[0]["messages"][-1]["content"]
    assert "우리 시스템" not in content and "systems" not in content
    assert ws.items("scope")[0].get("systems") == []


def test_requirements_keep_known_systems_only(repo_root: Path, key_env: Path) -> None:
    out = tagged_candidates(system_refs=["SYS-01", "SYS-99"], change="기능 추가")
    orch, ws, fake = build(repo_root, key_env, {"problem_scope": [with_fit()], "requirement_candidates": [out]})
    orch.ingest(CHUNKS, systems=CATALOG)
    orch.advance()
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    first, second = ws.items("requirements")[:2]
    assert first["system_refs"] == ["SYS-01"] and first["change"] == "기능 추가"
    assert second["system_refs"] == [] and second["change"] == "신규"
    assert "system_refs" in fake.chat_payloads("requirement_candidates")[0]["messages"][-1]["content"]


def test_change_without_a_system_is_new(repo_root: Path, key_env: Path) -> None:
    out = tagged_candidates(system_refs=["SYS-01"], change="연계")
    orch, ws, _ = build(repo_root, key_env, {"requirement_candidates": [out]})
    orch.ingest(CHUNKS)
    orch.advance()
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    first = ws.items("requirements")[0]
    assert first["system_refs"] == [] and first["change"] == "신규"


def test_input_api_takes_systems(tmp_path: Path, key_env: Path) -> None:
    fake = FakeLiner({**flower_outputs(CHUNKS), "problem_scope": [with_fit()]}, search_body=SEARCH_BODY)
    settings = Settings(db_path=tmp_path / "sys.sqlite3", env_file=key_env)
    client = TestClient(create_app(settings, liner=LinerClient(env_file=key_env, transport=fake.transport())))
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    response = client.post(f"/api/projects/{pid}/input", json={"chunks": CHUNKS, "systems": CATALOG})
    assert response.status_code == 202
    source = client.get(f"/api/projects/{pid}").json()["source"]
    assert [s["name"] for s in source["systems"]][:2] == ["주문관리 시스템", "알림톡 발송"]
    assert source["scope"][0]["systems"][0]["system_ref"] == "SYS-01"


def test_reuse_is_a_fit_of_its_own(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env, {"problem_scope": [with_fit(fit=REUSE, what="주문 조회를 그대로 쓴다")]})
    orch.ingest(CHUNKS, systems=CATALOG)
    orch.advance()
    (fit,) = ws.items("scope")[0]["systems"]
    assert fit["fit"] == REUSE and fit["status"] == "확인"


SERVICE = {"id": "SYS-02", "name": "꽃님 정기구독", "features": [{"id": "SYS-02/REQ-02", "title": "배송 지역 서울 한정"},
                                                            {"id": "SYS-02/REQ-09", "title": "구독 일시정지"}]}


def test_feature_refs_keep_only_features_of_the_systems_the_requirement_names() -> None:
    systems = [{"id": "SYS-01", "name": "꽃집 POS"}, SERVICE]
    raw = {"feature_refs": ["SYS-02/REQ-02", "SYS-02/REQ-99", "REQ-02", "SYS-02/REQ-02"]}
    assert requirement_features(raw, systems, ["SYS-02"]) == ["SYS-02/REQ-02"]
    assert requirement_features(raw, systems, ["SYS-01"]) == []  # not a feature of the named system
    assert requirement_features({"feature_refs": "SYS-02/REQ-02"}, systems, ["SYS-02"]) == []


def test_a_reused_requirement_keeps_its_feature_refs(repo_root: Path, key_env: Path) -> None:
    out = tagged_candidates(system_refs=["SYS-01"], change=REUSE, feature_refs=["SYS-01/REQ-01", "SYS-01/REQ-77"])
    orch, ws, fake = build(repo_root, key_env, {"requirement_candidates": [out]})
    orch.ingest(CHUNKS, services=[{"name": "꽃님 정기구독", "features": [{"id": "REQ-01", "title": "정기구독 신청"}]}])
    orch.advance()
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    first, second = ws.items("requirements")[:2]
    assert first["change"] == REUSE and first["feature_refs"] == ["SYS-01/REQ-01"]
    assert second["feature_refs"] == []
    assert "feature_refs" in fake.chat_payloads("requirement_candidates")[0]["messages"][-1]["content"]


def test_reuse_without_a_real_feature_is_an_addition(repo_root: Path, key_env: Path) -> None:
    out = tagged_candidates(system_refs=["SYS-01"], change=REUSE, feature_refs=["SYS-01/REQ-77"])
    orch, ws, _ = build(repo_root, key_env, {"requirement_candidates": [out]})
    orch.ingest(CHUNKS, systems=CATALOG)
    orch.advance()
    orch.confirm("CP1", True, "발주사")
    orch.advance()
    first = ws.items("requirements")[0]
    assert first["change"] == "기능 추가" and first["feature_refs"] == []  # no 「새로 만들지 않는다」 without a basis


def test_the_reuse_instruction_draws_the_line_at_any_change() -> None:
    from app.systems import TASK_PM_SYSTEMS
    assert "하나도 고치지 않아도" in TASK_PM_SYSTEMS and "기능 추가" in TASK_PM_SYSTEMS
