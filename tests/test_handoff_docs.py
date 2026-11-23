from __future__ import annotations
"""Hand-off documents built from the shared source (no model call): AGENTS.md for a coding AI and a one-page
proposal summary for a decision maker. Both ship in the download bundle."""

from pathlib import Path

from app.export import bundle_files
from app.handoff_docs import agents_md, proposal_md, size_class, task_order
from tests.pipeline_helpers import build, to_cp4


def req(rid: str, deps: list[str]) -> dict[str, object]:
    return {"id": rid, "depends_on": deps}


def test_task_order_follows_dependencies_and_survives_cycles() -> None:
    reqs = [req("REQ-01", ["REQ-03"]), req("REQ-02", []), req("REQ-03", ["REQ-02"])]
    assert [r["id"] for r in task_order(reqs)] == ["REQ-02", "REQ-03", "REQ-01"]
    cycle = [req("REQ-01", ["REQ-02"]), req("REQ-02", ["REQ-01"]), req("REQ-03", [])]
    assert sorted(r["id"] for r in task_order(cycle)) == ["REQ-01", "REQ-02", "REQ-03"]


def test_size_class_states_its_basis() -> None:
    assert size_class(3, 2, 0)[0] == "작음"
    assert size_class(12, 5, 1)[0] == "보통"
    label, basis = size_class(25, 9, 3)
    assert label == "큼" and "요구사항 25건" in basis and "화면 9개" in basis and "연계 시스템 3개" in basis


def test_bundle_carries_agents_md_and_proposal(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp4(orch, ws)
    source = ws.source
    files = bundle_files(source)
    assert files["AGENTS.md"] == agents_md(source) and files["제안요약.md"] == proposal_md(source)
    assert "AGENTS.md" in files["README.txt"] and "제안요약.md" in files["README.txt"]

    agents = files["AGENTS.md"]
    first = source["requirements"][0]
    assert "## 하지 말 것" in agents and "서울 밖 배송" in agents  # scope out of the flower memo
    assert f"TASK-01 · {first['id']}" in agents or "TASK-01 ·" in agents
    assert first["acceptance"]["then"] in agents
    assert any(t["id"] in agents for t in source["tests"])
    assert "prototype.html" in agents and "source.json" in agents

    proposal = files["제안요약.md"]
    for heading in ("## 문제", "## 범위", "## 규모", "## 결정이 필요한 것"):
        assert heading in proposal
    assert f"요구사항 {len(source['requirements'])}건" in proposal


def _source_with_cycle() -> dict[str, object]:
    acc = {"given": "g", "when": "w", "then": "t"}
    reqs = [
        {"id": "REQ-01", "title": "수집", "statement": "s", "acceptance": acc, "status": "확정", "depends_on": []},
        {"id": "REQ-02", "title": "발송", "statement": "s", "acceptance": acc, "status": "확정", "depends_on": ["REQ-01", "REQ-03"]},
        {"id": "REQ-03", "title": "시간대", "statement": "s", "acceptance": acc, "status": "확정", "depends_on": ["REQ-02"]},
    ]
    tests = [{"id": "TC-01", "title": "공통", "expected": "e", "requirement_refs": ["REQ-02", "REQ-03"]},
             {"id": "TC-02", "title": "수집만", "expected": "e", "requirement_refs": ["REQ-01"]}]
    return {"requirements": reqs, "tests": tests}


def test_mutual_dependencies_are_named_not_contradicted() -> None:
    text = agents_md(_source_with_cycle())  # order: REQ-01, REQ-03, REQ-02 (REQ-02 and REQ-03 need each other)
    assert "서로 기대는 요구사항" in text and "REQ-02 ↔ REQ-03" in text
    second = text.split("### TASK-02")[1].split("### TASK-03")[0]
    assert "REQ-03" in second.splitlines()[0] and "함께 만들 것(서로 기대고 있음): REQ-02" in second
    assert "먼저 끝나야 하는 것: REQ-02" not in second  # never a "first" that comes later
    third = text.split("### TASK-03")[1]
    assert "먼저 끝나야 하는 것: REQ-01, REQ-03" in third


def test_each_test_is_listed_in_full_once() -> None:
    text = agents_md(_source_with_cycle())
    assert text.count("TC-01 공통") == 1
    assert "TC-01(TASK-02에서 확인)" in text


def _source_with_open_values() -> dict[str, object]:
    """A family-alert source with one assumed answer, one open requirement, a reused product and a linked system."""
    acc = {"given": "g", "when": "w", "then": "t"}
    reqs = [
        {"id": "REQ-01", "title": "Cozi 연결", "statement": "s", "acceptance": acc, "status": "확정", "depends_on": [],
         "change": "연계", "system_refs": ["SYS-01"]},
        {"id": "REQ-02", "title": "기록 보관", "statement": "기록을 1년 보관한다", "acceptance": acc, "status": "가정",
         "depends_on": [], "decision_refs": ["DEC-02"]},
        {"id": "REQ-03", "title": "원인 값 출처", "statement": "원인 값을 받는다", "acceptance": acc, "status": "미결",
         "depends_on": []},
    ]
    tests = [
        {"id": "TC-01", "title": "불러오기", "inputs": "기념일 2건", "expected": "목록에 2건", "status": "확정",
         "requirement_refs": ["REQ-01"]},
        {"id": "TC-02", "title": "보관 기간", "inputs": "366일 지난 기록", "expected": "삭제됨", "status": "가정",
         "requirement_refs": ["REQ-02"]},
        {"id": "TC-03", "title": "원인 표시", "inputs": "원인 코드 7", "expected": "원인 문구", "status": "미결",
         "requirement_refs": ["REQ-03"]},
    ]
    decisions = [
        {"id": "DEC-01", "kind": "build_or_buy", "alternative_ref": "ALT-01", "chosen": "Cozi + 모자란 부분만", "status": "확정"},
        {"id": "DEC-02", "topic": "기록 보관 기간", "chosen": "1년 | 매일 삭제", "status": "가정", "answer_kind": "unknown"},
    ]
    screens = [{"id": "SCR-01", "title": "알림 보내기", "elements": [
        {"name": "받을 사람", "kind": "select", "description": "그룹 구성원 중 본인을 뺀 사람", "input_rule": "필수"},
        {"name": "제목", "kind": "input", "input_rule": "1~30자"}]}]
    return {"requirements": reqs, "tests": tests, "decisions": decisions, "screens": screens,
            "alternatives": [{"id": "ALT-01", "name": "Cozi", "covers": "공유 캘린더", "lacks": "읽음 확인"}],
            "systems": [{"id": "SYS-01", "name": "주문관리", "about": "연결 방법: 주문 조회 API"}],
            "scope": [{"systems": [{"system_ref": "SYS-01", "name": "주문관리", "fit": "연계", "what": "주문 상태를 받는다"}]}]}


def test_open_values_are_gathered_as_constants() -> None:
    text = agents_md(_source_with_open_values())
    table = text.split("## 정해지지 않은 값")[1].split("\n## ")[0]
    row = next(line for line in table.splitlines() if "DEC_02" in line)
    assert "1년 \\| 매일 삭제" in row and "가정" in row and "REQ-02" in row  # pipe in a value is escaped
    header = next(line for line in table.splitlines() if line.startswith("| 상수 이름"))
    assert row.count(" | ") == header.count(" | ")  # same column count as the header row
    assert any("REQ_03" in line and "미정" in line for line in table.splitlines())
    assert "DEC_01" not in table and "REQ_01" not in table  # settled values stay out


def test_tests_show_input_expected_and_undecidable() -> None:
    text = agents_md(_source_with_open_values())
    tc3 = text.split("TC-03 원인 표시")[1].split("###")[0]
    assert "입력: 원인 코드 7" in tc3 and "기대: 원인 문구" in tc3
    assert "판정 불가" in tc3 and "REQ-03" in tc3 and "통과 조건으로 쓰지 않는다" in tc3
    tc2 = text.split("TC-02 보관 기간")[1].split("###")[0]
    assert "가정값 기준" in tc2 and "DEC_02" in tc2
    assert "판정" not in text.split("TC-01 불러오기")[1].split("###")[0]


def test_data_and_links_section() -> None:
    text = agents_md(_source_with_open_values())
    part = text.split("## 데이터·연동")[1].split("\n## ")[0]
    assert "받을 사람" in part and "그룹 구성원 중 본인을 뺀 사람" in part and "제목(1~30자)" in part
    assert "SYS-01 주문관리" in part and "주문 상태를 받는다" in part and "주문 조회 API" in part and "REQ-01" in part
    assert "Cozi" in part and "공유 캘린더" in part and "읽음 확인" in part


def test_one_system_twice_lists_requirements_by_kind() -> None:
    src = _source_with_open_values()
    src["requirements"].append({"id": "REQ-04", "title": "취소 상태", "statement": "s", "status": "확정", "depends_on": [],
                                "acceptance": {}, "change": "기능 추가", "system_refs": ["SYS-01"]})
    src["scope"][0]["systems"].append({"system_ref": "SYS-01", "name": "주문관리", "fit": "기능 추가", "what": "취소 상태 추가"})
    part = agents_md(src).split("### 외부 연동")[1]
    link, add = (next(l for l in part.splitlines() if f"· {k}:" in l) for k in ("연계", "기능 추가"))
    assert link.endswith("REQ-01") and add.endswith("REQ-04")
    assert part.count("주문 조회 API") == 1  # the system's own description only once


def test_code_values_are_pulled_from_the_sentence() -> None:
    from app.handoff_docs import code_values
    assert code_values("오전 8시~오후 9시에만 보내고 밤 판정 건은 다음 날 아침에 발송") == "08:00~21:00"
    assert code_values("출고 후 48시간이 지나도 배송 완료가 아니면 안내 (현행 가정)") == "48h"
    assert code_values("배송 관련 문의만, 기준은 하루 80건 (현행 가정)") == "80건"
    assert code_values("밤 9시부터 아침 8시 사이에는 보내지 않고 30분 안에 다시 시도") == "21:00~08:00 · 30m"
    assert code_values("법무 확인 전까지 취소 기능 보류") == ""


def test_constants_table_has_a_code_value_column_and_boundary_note() -> None:
    src = _source_with_open_values()
    src["decisions"][1]["chosen"] = "기록을 1년 보관하고 매일 오전 3시에 삭제"
    text = agents_md(src)
    table = text.split("## 정해지지 않은 값")[1].split("\n## ")[0]
    header = next(line for line in table.splitlines() if line.startswith("| 상수 이름"))
    assert "코드값" in header
    row = next(line for line in table.splitlines() if "DEC_02" in line)
    assert "1년 · 03:00" in row and row.count(" | ") == header.count(" | ")
    assert "경계" in table  # inclusive or not is read from the sentence


def test_data_section_lists_data_and_interface_requirements() -> None:
    src = _source_with_open_values()
    src["requirements"] += [
        {"id": "REQ-05", "title": "발송 이력", "statement": "주문 번호·발송 시각·결과를 저장한다", "category": "DAR",
         "acceptance": {}, "status": "확정", "depends_on": []},
        {"id": "REQ-06", "title": "택배 수집", "statement": "택배사 정보를 하루 2회 받는다", "category": "INR",
         "acceptance": {}, "status": "확정", "depends_on": []}]
    part = agents_md(src).split("## 데이터·연동")[1].split("\n## ")[0]
    assert "### 저장할 데이터" in part and "REQ-05 발송 이력: 주문 번호·발송 시각·결과를 저장한다" in part
    assert "### 연동 요구사항" in part and "REQ-06 택배 수집: 택배사 정보를 하루 2회 받는다" in part


def test_undecidable_test_carries_a_temporary_behaviour() -> None:
    tc3 = agents_md(_source_with_open_values()).split("TC-03 원인 표시")[1].split("###")[0]
    assert "임시 동작" in tc3 and "skip" in tc3 and "REQ-03" in tc3


def test_a_reused_requirement_says_not_to_build_it_again() -> None:
    src = _source_with_open_values()
    src["systems"].append({"id": "SYS-02", "name": "꽃님 정기구독", "about": "0to1로 만든 서비스",
                           "features": [{"id": "SYS-02/REQ-02", "title": "배송 지역 서울 한정"}]})
    src["requirements"].append({"id": "REQ-04", "title": "선물 배송지 서울 한정", "statement": "s", "status": "확정",
                                "depends_on": [], "acceptance": {}, "change": "재사용", "system_refs": ["SYS-02"],
                                "feature_refs": ["SYS-02/REQ-02"]})
    block = agents_md(src).split("REQ-04 선물 배송지 서울 한정")[1].split("### TASK-")[0]
    line = next(l for l in block.splitlines() if l.startswith("- 기존 시스템:"))
    assert "재사용" in line and "새로 만들지 않는다" in line and "SYS-02/REQ-02 배송 지역 서울 한정" in line
