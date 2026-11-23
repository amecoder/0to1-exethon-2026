from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.checks import review
from app.export import build_bundle
from app.limits import calls_used
from app.liner import IMAGES_URL, LinerAPIError
from app.prototype import PREVIEW_CSP, sanitize
from app.prototype_images import (
    IMAGE_WIDTH, MAX_IMAGES, downscale, embed_images, extract_images, requested_images,
)
from tests.flower_script import PROTOTYPE_HTML, prototype_output
from tests.pipeline_helpers import build, events, to_cp4

MODEL = "qwen/qwen-image-2.1-turbo"
SLOTS = '<img data-img="hero" alt="꽃다발"><img data-img="box" alt="상자" src="https://cdn.example.com/x.png">'
HTML = PROTOTYPE_HTML.replace("</body>", f"{SLOTS}</body>")


def with_images(*images: dict[str, str]) -> dict:
    return {**prototype_output(HTML), "images": list(images)}


def image_env(key_env: Path) -> Path:
    key_env.write_text(key_env.read_text(encoding="utf-8") + f"LINER_IMAGE_MODEL={MODEL}\n", encoding="utf-8")
    return key_env


def png(width: int, height: int) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 80, 120)).save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_downscale_makes_a_small_jpeg_data_uri() -> None:
    uri = downscale(png(1024, 1024))
    assert uri.startswith("data:image/jpeg;base64,")
    img = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
    assert img.format == "JPEG" and img.size == (IMAGE_WIDTH, IMAGE_WIDTH)


def test_requested_images_keeps_slots_in_the_html_and_at_most_three() -> None:
    html = "".join(f'<img data-img="s{i}">' for i in range(5))
    asked = [{"slot": f"s{i}", "prompt": f"사진 {i}"} for i in range(5)] + [{"slot": "nope", "prompt": "x"}]
    assert [r["slot"] for r in requested_images({"images": asked}, html)] == ["s0", "s1", "s2"] == \
        [f"s{i}" for i in range(MAX_IMAGES)]
    assert requested_images({}, html) == [] and requested_images({"images": "bad"}, html) == []


def test_embed_and_extract_round_trip_and_g6_still_blocks_http() -> None:
    uri = downscale(png(64, 48))
    out = embed_images(f"<html><body>{SLOTS}</body></html>", {"hero": uri})
    assert f'src="{uri}"' in out and extract_images(out) == {"hero": base64.b64decode(uri.split(",", 1)[1])}
    checked = sanitize(out)
    assert checked.valid and "cdn.example.com" not in checked.html and uri in checked.html
    assert "img-src data:" in PREVIEW_CSP


def test_s6_generates_images_embeds_them_and_logs_without_base64(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, image_env(key_env), {"prototype": [with_images(
        {"slot": "hero", "prompt": "하얀 배경의 분홍 장미 꽃다발 사진"}, {"slot": "box", "prompt": "꽃 상자 사진"})]})
    to_cp4(orch, ws)
    bodies = fake.payloads(IMAGES_URL)
    assert [b["prompt"] for b in bodies] == ["하얀 배경의 분홍 장미 꽃다발 사진", "꽃 상자 사진"]
    assert all(b["model"] == MODEL and b["resolution"] == "1K" for b in bodies)
    proto = ws.items("prototype")[-1]
    assert set(extract_images(proto["html"])) == {"hero", "box"} and "cdn.example.com" not in proto["html"]
    logged = events(ws, "liner_image")
    assert [e["data"]["slot"] for e in logged] == ["hero", "box"]
    assert logged[0]["data"]["model"] == MODEL and logged[0]["data"]["cost"] == 0.0184
    assert logged[0]["data"]["duration_ms"] >= 0 and "base64" not in json.dumps(logged)
    assert calls_used(ws.log.events) == len(fake.requests)
    zf = zipfile.ZipFile(io.BytesIO(build_bundle(approve(orch, ws))))
    assert {"images/hero.jpg", "images/box.jpg"} <= set(zf.namelist())


def approve(orch, ws) -> dict:  # noqa: ANN001
    orch.confirm("CP4", True, "발주사")
    return ws.source


def test_no_image_model_skips_with_a_notice(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, key_env, {"prototype": [with_images({"slot": "hero", "prompt": "꽃"})]})
    to_cp4(orch, ws)
    assert fake.payloads(IMAGES_URL) == [] and events(ws, "liner_image") == []
    proto = ws.items("prototype")[-1]
    assert "LINER_IMAGE_MODEL" in proto["image_notice"] and extract_images(proto["html"]) == {}
    notices = [w["id"] for w in review(ws.source, "CP4")["notices"]]
    assert "prototype.images:PROTO-01" in notices


def test_late_failure_in_a_200_body_is_a_notice_not_a_stop(repo_root: Path, key_env: Path) -> None:
    orch, ws, _ = build(repo_root, image_env(key_env), {"prototype": [with_images({"slot": "hero", "prompt": "꽃"})]},
                        image_error=True)
    to_cp4(orch, ws)
    assert ws.pipeline["status"] == "awaiting_confirmation"
    assert events(ws, "liner_image")[0]["data"]["error"]
    assert ws.items("prototype")[-1]["image_notice"]


def test_image_prompt_with_personal_data_is_not_sent(repo_root: Path, key_env: Path) -> None:
    orch, ws, fake = build(repo_root, image_env(key_env))
    with pytest.raises(LinerAPIError) as caught:
        orch._ctx.runner.image("developer", "hero", "010-1234-5678 로 연락하는 꽃집 간판")
    assert caught.value.kind == "blocked_sensitive"
    assert fake.payloads(IMAGES_URL) == [] and events(ws, "liner_image") == []
    g3 = [e["data"] for e in events(ws, "guardrail") if e["data"]["id"] == "G3"]
    assert g3 and g3[-1]["outcome"] == "blocked" and "010-1234-5678" not in json.dumps(g3)


def test_photo_bytes_never_go_to_agents_and_do_not_trip_g3(repo_root: Path, key_env: Path) -> None:
    """Real photos are noisy base64 that the G3 key pattern matches; agents get a placeholder instead."""
    import os

    from app.guardrails import DATA_URI_PLACEHOLDER
    from app.liner import outgoing_labels
    from app.schemas import CONSUMER_FEEDBACK

    noisy = "data:image/jpeg;base64," + base64.b64encode(os.urandom(3000)).decode()
    assert outgoing_labels({"html": f'<img src="{noisy}">'}) == []
    assert outgoing_labels({"html": f'<img src="{noisy}"> sk_live_{"a1" * 12}'}) == ["API 키"]  # keys still caught
    orch, ws, fake = build(repo_root, key_env)
    to_cp4(orch, ws)
    proto = ws.items("prototype")[-1]
    ws.write("developer", "prototype", {**proto, "html": proto["html"].replace("</body>", f'<img src="{noisy}"></body>')})
    orch._ctx.runner.ask("consumer", "프로토타입을 눌러 보세요", "consumer_feedback", CONSUMER_FEEDBACK)
    sent = fake.chat_payloads("consumer_feedback")[-1]["messages"][-1]["content"]
    assert DATA_URI_PLACEHOLDER in sent and noisy.split(",", 1)[1][:40] not in sent
