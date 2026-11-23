from __future__ import annotations
"""Role swimlane flow chart: designer output normalization, deterministic SVG, pipeline and bundle."""

import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.export import build_bundle
from app.liner import LinerClient
from app.main import create_app
from app.swimlane import MAX_LANES, MAX_STEPS, normalize_swimlane, swimlane_svg
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs, flower_swimlane, lane_step, screen_spec
from tests.pipeline_helpers import CHUNKS, build, events, to_cp3, to_cp4

SVG_NS = "{http://www.w3.org/2000/svg}"
SCR_MAP = {"S-A": "SCR-01", "S-B": "SCR-02"}
SCREENS = [{"id": "SCR-01", "title": "구독 신청"}, {"id": "SCR-02", "title": "결제 안내"}]


def texts(svg: str) -> list[str]:
    root = ET.fromstring(svg)
    return ["".join(t.itertext()) for t in root.iter(f"{SVG_NS}text")]


# --- normalization --------------------------------------------------------------------------------
def test_normalize_maps_screens_and_keeps_the_flower_flow() -> None:
    lanes, dropped = normalize_swimlane(flower_swimlane(), SCR_MAP)
    assert dropped == []
    assert lanes["lanes"] == ["고객", "앱", "사장"]
    by_id = {s["id"]: s for s in lanes["steps"]}
    assert by_id["c1"]["screen_ref"] == "SCR-01" and by_id["x1"]["screen_ref"] == "SCR-02"
    assert by_id["x1"]["kind"] == "exception" and by_id["x1"]["note"] == "결제 실패"
    assert by_id["x2"]["after"] == ["x1"]


def test_normalize_drops_unknown_lanes_steps_and_screens() -> None:
    raw = {"lanes": ["고객", "고객", " ", "앱"], "steps": [
        lane_step("a", "고객", "신청하기", [], "S-ZZ"),
        lane_step("b", "택배사", "배송하기", ["a"]),  # lane not declared
        lane_step("c", "앱", "결제하기", ["a", "b", "nope"], kind="weird"),
        lane_step("a", "앱", "중복 id", []),
        lane_step("d", "앱", "  ", ["c"]),  # empty label
    ]}
    lanes, dropped = normalize_swimlane(raw, SCR_MAP)
    assert lanes["lanes"] == ["고객", "앱"]
    assert [s["id"] for s in lanes["steps"]] == ["a", "c"]
    assert lanes["steps"][0]["screen_ref"] == ""
    assert lanes["steps"][1]["after"] == ["a"] and lanes["steps"][1]["kind"] == "normal"
    refs = {d["ref"] for d in dropped}
    assert {"S-ZZ", "b", "nope", "택배사"} <= refs


def test_normalize_caps_lanes_and_steps() -> None:
    names = [f"역할{i}" for i in range(8)]
    steps = [lane_step(f"s{i}", names[i % 8], f"단계 {i}", [f"s{i - 1}"] if i else []) for i in range(30)]
    lanes, _ = normalize_swimlane({"lanes": names, "steps": steps}, {})
    assert len(lanes["lanes"]) == MAX_LANES
    assert len(lanes["steps"]) <= MAX_STEPS
    assert all(s["lane"] in lanes["lanes"] for s in lanes["steps"])


def test_normalize_breaks_cycles() -> None:
    raw = {"lanes": ["고객"], "steps": [
        lane_step("a", "고객", "하나", ["c"]), lane_step("b", "고객", "둘", ["a"]), lane_step("c", "고객", "셋", ["b"]),
    ]}
    lanes, dropped = normalize_swimlane(raw, {})
    edges = {(p, s["id"]) for s in lanes["steps"] for p in s["after"]}
    assert len(edges) == 2 and any("순환" in d["reason"] for d in dropped)
    swimlane_svg(lanes, [])  # draws without looping


def test_normalize_without_steps_is_none() -> None:
    assert normalize_swimlane(None, {})[0] is None
    assert normalize_swimlane({"lanes": ["고객"], "steps": []}, {})[0] is None
    assert normalize_swimlane({"lanes": [], "steps": [lane_step("a", "고객", "하나", [])]}, {})[0] is None


# --- drawing --------------------------------------------------------------------------------------
def test_svg_has_every_lane_and_step_label() -> None:
    lanes, _ = normalize_swimlane(flower_swimlane(), SCR_MAP)
    svg = swimlane_svg(lanes, SCREENS)
    shown = [t.replace(" ", "") for t in texts(svg)]  # labels wrap at spaces into separate lines
    for name in lanes["lanes"]:
        assert name in shown
    for step in lanes["steps"]:
        assert step["label"].replace(" ", "") in shown
    assert "결제실패" in shown and any("구독신청" in t for t in shown)
    assert "http" not in svg.replace("http://www.w3.org/2000/svg", "") and "<script" not in svg


def test_exception_arrow_is_dashed_with_its_note() -> None:
    lanes, _ = normalize_swimlane(flower_swimlane(), SCR_MAP)
    root = ET.fromstring(swimlane_svg(lanes, SCREENS))
    arrows = [p for p in root.iter(f"{SVG_NS}path") if p.get("data-to")]
    dashed = {p.get("data-to") for p in arrows if p.get("stroke-dasharray")}
    assert dashed == {"x1", "x3"}
    assert len(arrows) == sum(len(s["after"]) for s in lanes["steps"])


def test_svg_escapes_text() -> None:
    raw = {"lanes": ["<고객&>"], "steps": [lane_step("a", "<고객&>", "<script>alert(1)</script>", [])]}
    lanes, _ = normalize_swimlane(raw, {})
    svg = swimlane_svg(lanes, [])
    assert "<script>" not in svg and "&lt;script&gt;" in svg
    ET.fromstring(svg)


def test_columns_follow_the_order_of_after() -> None:
    lanes, _ = normalize_swimlane(flower_swimlane(), SCR_MAP)
    root = ET.fromstring(swimlane_svg(lanes, SCREENS))
    x = {g.get("data-step"): float(g.get("data-x", "0")) for g in root.iter(f"{SVG_NS}g") if g.get("data-step")}
    assert x["c1"] < x["c2"] < x["a1"] < x["a2"] < x["o1"]
    assert x["a1"] < x["x1"] < x["x2"] < x["x3"]


# --- pipeline and bundle --------------------------------------------------------------------------
def test_pipeline_stores_swimlane_and_bundle_has_the_lanes_file(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, key_env)
    to_cp4(orch, ws)
    (spec,) = ws.items("screen_spec")
    assert spec["swimlane"]["lanes"] == ["고객", "앱", "사장"]
    assert {s["screen_ref"] for s in spec["swimlane"]["steps"]} == {"SCR-01", "SCR-02", ""}
    orch.confirm("CP4", True, "발주사")
    bundle = zipfile.ZipFile(io.BytesIO(build_bundle(ws.source)))
    assert {"user_flow_lanes.html", "user_flow.html"} <= set(bundle.namelist())
    page = bundle.read("user_flow_lanes.html").decode("utf-8")
    assert "결제 실패" in page and "Content-Security-Policy" in page
    assert "user_flow_lanes.html" in bundle.read("README.txt").decode("utf-8")


def test_unknown_swimlane_refs_are_logged(repo_root: Path, key_env: Path) -> None:
    def spec_with_bad_ref(chunks: list[str]) -> dict[str, Any]:
        out = screen_spec(chunks)
        out["swimlane"]["steps"].append(lane_step("z", "고객", "엉뚱한 화면", ["c1"], "S-Q"))
        return out

    orch, ws, _ = build(repo_root, key_env, overrides={"screen_spec": [spec_with_bad_ref(CHUNKS)]})
    to_cp3(orch, ws)
    assert any(e["data"].get("ref") == "S-Q" for e in events(ws, "ref_dropped"))


def test_without_swimlane_nothing_new_appears(repo_root: Path, key_env: Path) -> None:
    plain = {k: v for k, v in screen_spec(CHUNKS).items() if k != "swimlane"}
    orch, ws, _ = build(repo_root, key_env, overrides={"screen_spec": [plain]})
    to_cp4(orch, ws)
    (spec,) = ws.items("screen_spec")
    assert "swimlane" not in spec
    orch.confirm("CP4", True, "발주사")
    names = zipfile.ZipFile(io.BytesIO(build_bundle(ws.source))).namelist()
    assert "user_flow_lanes.html" not in names and "user_flow.html" in names


def test_lanes_preview_route(tmp_path: Path, key_env: Path) -> None:
    fake = FakeLiner(flower_outputs(CHUNKS), search_body=SEARCH_BODY)
    settings = Settings(db_path=tmp_path / "d.sqlite3", env_file=key_env)
    client = TestClient(create_app(settings, liner=LinerClient(env_file=key_env, transport=fake.transport())))
    pid = client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]
    assert client.get(f"/api/projects/{pid}/flow/lanes").status_code == 404
    base = f"/api/projects/{pid}"
    client.post(f"{base}/input", json={"chunks": CHUNKS})
    client.post(f"{base}/confirmations", json={"cp": "CP1", "approved": True})
    for kind in ("unknown", "choice"):
        q = client.get(base).json()["todo"]["question"]
        client.post(f"{base}/answers", json={"question_id": q["id"], "kind": kind, "value": q["options"][0]})
    client.post(f"{base}/answers/submit")
    client.post(f"{base}/confirmations", json={"cp": "CP2", "approved": True})
    res = client.get(f"{base}/flow/lanes")
    assert res.status_code == 200 and res.headers["content-type"].startswith("image/svg+xml")
    assert "Content-Security-Policy" in res.headers and "사장" in res.text


def test_exception_note_is_shown_in_full_on_two_lines() -> None:
    notes = ["밤 9시~아침 8시 야간 제한", "문자도 실패 또는 수신 번호 없음"]  # notes cut at 15 chars in the 2026-11-18 run
    raw = {"lanes": ["고객", "앱"], "steps": [
        lane_step("a", "고객", "주문", []),
        {**lane_step("b", "앱", "발송 보류", ["a"]), "kind": "exception", "note": notes[0]},
        {**lane_step("c", "앱", "담당자 알림", ["a"]), "kind": "exception", "note": notes[1]}]}
    lanes, _ = normalize_swimlane(raw, {})
    shown = [t.replace(" ", "") for t in texts(swimlane_svg(lanes, []))]
    for note in notes:
        assert note.replace(" ", "") in shown


def test_overlong_note_keeps_full_text_as_tooltip() -> None:
    note = "알림톡 실패 후 10분 기다렸다가 문자로 다시 보내고 그래도 실패하면 담당자에게 알림"
    raw = {"lanes": ["앱"], "steps": [lane_step("a", "앱", "발송", []),
                                     {**lane_step("b", "앱", "재발송", ["a"]), "kind": "exception", "note": note}]}
    lanes, _ = normalize_swimlane(raw, {})
    root = ET.fromstring(swimlane_svg(lanes, []))
    assert any(note[:40] in "".join(t.itertext()) for t in root.iter(f"{SVG_NS}title"))
