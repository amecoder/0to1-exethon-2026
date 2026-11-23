from __future__ import annotations
"""S1 attachments: images and documents become original sentences (SRC) marked with where they came from."""

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.attachments import (
    MAX_IMAGE_BYTES, MAX_PDF_BYTES, MAX_TEXT_BYTES, AttachmentError, check_attachment, decode_text, text_systems,
)
from app.config import Settings
from app.liner import CHAT_URL, LinerClient
from app.main import create_app
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs, memo_chunks

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64
IMAGE_TEXT = "화면 제목: 정기구독 신청. 입력 칸: 받는 요일. 버튼: 신청하기."
PDF_TEXT = "배송 지역: 서울. 결제는 매달 1일에 해요."


@pytest.mark.parametrize("name, data, fmt, kind", [
    ("a.png", PNG, "png", "image"), ("a.JPG", JPEG, "jpeg", "image"), ("a.jpeg", JPEG, "jpeg", "image"),
    ("a.gif", b"GIF89a\x00\x00", "gif", "image"), ("a.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ", "webp", "image"),
    ("a.pdf", PDF, "pdf", "document"), ("a.txt", "메모".encode(), "text", "document"),
    ("a.md", b"# t", "text", "document"), ("a.csv", b"a,b", "text", "document"), ("a.tsv", b"a\tb", "text", "document")])
def test_kind_is_detected_from_extension_and_content(name: str, data: bytes, fmt: str, kind: str) -> None:
    found = check_attachment(name, data)
    assert (found.format, found.kind) == (fmt, kind)


@pytest.mark.parametrize("name, data, word", [
    ("a.png", b"", "빈 파일"), ("a.docx", PNG, "형식"), ("memo", PNG, "확장자 없음"),
    ("a.png", PDF, "확장자"), ("a.pdf", PNG, "확장자"), ("a.txt", PNG, "글 파일")])
def test_bad_files_get_korean_reasons(name: str, data: bytes, word: str) -> None:
    with pytest.raises(AttachmentError, match=word):
        check_attachment(name, data)


@pytest.mark.parametrize("name, head, limit, mb", [
    ("a.png", PNG, MAX_IMAGE_BYTES, "5MB"), ("a.pdf", PDF, MAX_PDF_BYTES, "15MB"), ("a.txt", b"a", MAX_TEXT_BYTES, "1MB")])
def test_size_limits_per_kind(name: str, head: bytes, limit: int, mb: str) -> None:
    with pytest.raises(AttachmentError, match=mb):
        check_attachment(name, head + b"a" * limit)


def test_text_decodes_utf8_then_cp949() -> None:
    assert decode_text("배송은 토요일".encode("utf-8")) == "배송은 토요일"
    assert decode_text("배송은 토요일".encode("cp949")) == "배송은 토요일"


def test_csv_systems_without_a_model() -> None:
    csv_text = "이름,하는 일,연결\n주문관리,주문 상태를 가짐,REST API\n알림톡,,\n"
    assert text_systems("s.csv", csv_text) == ["주문관리: 하는 일: 주문 상태를 가짐, 연결: REST API", "알림톡"]
    assert text_systems("s.txt", "주문관리: 주문\n\n알림톡: 발송\n") == ["주문관리: 주문", "알림톡: 발송"]


# --- API -----------------------------------------------------------------------------------------------
def outputs() -> dict:
    return {**flower_outputs(memo_chunks()),
            "attachment_text": [lambda p: {"text": PDF_TEXT if has_file(p) else IMAGE_TEXT}],
            "attachment_systems": [{"systems": [{"name": "주문관리", "about": "주문 상태를 가짐"},
                                                {"name": "알림톡", "about": "카카오 알림톡 발송"}]}]}


def has_file(payload: dict) -> bool:
    return any(part.get("type") == "file" for part in payload["messages"][-1]["content"])


def client_for(tmp_path: Path, env_file: Path, chat: dict | None = None) -> tuple[TestClient, FakeLiner]:
    fake = FakeLiner(chat or outputs(), search_body=SEARCH_BODY)
    settings = Settings(db_path=tmp_path / "attach.sqlite3", env_file=env_file)
    app = create_app(settings, liner=LinerClient(env_file=env_file, transport=fake.transport()))
    return TestClient(app), fake


def new_project(client: TestClient) -> str:
    return "/api/projects/" + client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]


def upload(client: TestClient, base: str, name: str, data: bytes, purpose: str = "memo"):
    return client.post(f"{base}/input/attachment?filename={name}&purpose={purpose}", content=data)


def test_image_goes_to_the_router_model_as_an_image_part(tmp_path: Path, key_env: Path) -> None:
    client, fake = client_for(tmp_path, key_env)
    base = new_project(client)
    response = upload(client, base, "화면.png", PNG)
    assert response.status_code == 200
    assert response.json() == {"filename": "화면.png", "kind": "image", "text": IMAGE_TEXT, "chars": len(IMAGE_TEXT)}
    [payload] = fake.chat_payloads("attachment_text")
    assert payload["model"] == "test-model"
    text_part, image_part = payload["messages"][-1]["content"]
    assert text_part["type"] == "text" and "지어내지 마라" in text_part["text"]
    assert image_part == {"type": "image_url",
                          "image_url": {"url": "data:image/png;base64," + base64.b64encode(PNG).decode()}}
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert client.get(base).json()["source"]["sources"] == []  # nothing stored before /input


def test_pdf_goes_to_the_file_model_as_a_file_part(tmp_path: Path, key_env: Path) -> None:
    client, fake = client_for(tmp_path, key_env)
    base = new_project(client)
    response = upload(client, base, "기획.pdf", PDF)
    assert response.status_code == 200 and response.json()["text"] == PDF_TEXT
    assert response.json()["kind"] == "document"
    [payload] = fake.chat_payloads("attachment_text")
    assert payload["model"] == "google/gemini-3.8-flash"
    file_part = payload["messages"][-1]["content"][1]
    assert file_part == {"type": "file", "file": {
        "filename": "기획.pdf", "file_data": "data:application/pdf;base64," + base64.b64encode(PDF).decode()}}


def test_file_model_comes_from_env(tmp_path: Path, key_env: Path) -> None:
    key_env.write_text(key_env.read_text(encoding="utf-8") + "LINER_FILE_MODEL=other/pdf-model\n", encoding="utf-8")
    client, fake = client_for(tmp_path, key_env)
    upload(client, new_project(client), "a.pdf", PDF)
    assert fake.chat_payloads("attachment_text")[0]["model"] == "other/pdf-model"


def test_text_file_needs_no_liner_call(tmp_path: Path, key_env: Path) -> None:
    client, fake = client_for(tmp_path, key_env)
    response = upload(client, new_project(client), "메모.txt", "배송은 토요일에만 해요.".encode("cp949"))
    assert response.status_code == 200
    assert response.json() == {"filename": "메모.txt", "kind": "document", "text": "배송은 토요일에만 해요.", "chars": 13}
    assert fake.requests == []


def test_systems_from_csv_and_from_an_image(tmp_path: Path, key_env: Path) -> None:
    client, fake = client_for(tmp_path, key_env)
    base = new_project(client)
    csv_body = "이름,하는 일\n주문관리,주문 상태\n".encode()
    from_csv = upload(client, base, "시스템.csv", csv_body, "systems").json()
    assert from_csv == {"filename": "시스템.csv", "kind": "document", "lines": ["주문관리: 하는 일: 주문 상태"]}
    assert fake.requests == []
    from_image = upload(client, base, "구성도.png", PNG, "systems").json()
    assert from_image["lines"] == ["주문관리: 주문 상태를 가짐", "알림톡: 카카오 알림톡 발송"]
    assert fake.chat_names == ["attachment_systems"]
    # systems are not kept for /input
    assert client.post(f"{base}/input", json={"chunks": [], "attachments": True}).status_code == 409


def test_input_with_attachments_stores_marked_sources(tmp_path: Path, key_env: Path) -> None:
    client, _ = client_for(tmp_path, key_env)
    base = new_project(client)
    upload(client, base, "화면.png", PNG)
    upload(client, base, "기획.pdf", PDF)
    assert client.post(f"{base}/input", json={"chunks": [], "attachments": True}).status_code == 202
    sources = client.get(base).json()["source"]["sources"]
    images = [s for s in sources if s.get("origin") == "image"]
    docs = [s for s in sources if s.get("origin") == "document"]
    assert images and all(s["origin_note"] == "이미지에서 옮겨 적음" and s["attachment_file"] == "화면.png" for s in images)
    assert docs and all(s["origin_note"] == "문서에서 옮겨 적음" and s["attachment_file"] == "기획.pdf" for s in docs)
    assert len(images) + len(docs) == len(sources)


def test_reupload_replaces_and_delete_removes(tmp_path: Path, key_env: Path) -> None:
    client, _ = client_for(tmp_path, key_env)
    base = new_project(client)
    upload(client, base, "a.txt", "첫 번째 글.".encode())
    upload(client, base, "a.txt", "두 번째 글.".encode())
    upload(client, base, "b.txt", "지울 글.".encode())
    assert client.delete(f"{base}/input/attachment?filename=b.txt").status_code == 200
    assert client.delete(f"{base}/input/attachment?filename=b.txt").status_code == 404
    client.post(f"{base}/input", json={"chunks": ["메모 한 줄."], "attachments": True})
    texts = [s["text"] for s in client.get(base).json()["source"]["sources"]]
    assert texts == ["메모 한 줄.", "두 번째 글."]


def test_at_most_five_attachments(tmp_path: Path, key_env: Path) -> None:
    client, _ = client_for(tmp_path, key_env)
    base = new_project(client)
    for i in range(5):
        assert upload(client, base, f"{i}.txt", b"a.").status_code == 200
    sixth = upload(client, base, "5.txt", b"a.")
    assert sixth.status_code == 400 and "5개" in sixth.json()["detail"]


def test_sensitive_attachment_is_blocked_then_masked(tmp_path: Path, key_env: Path) -> None:
    client, fake = client_for(tmp_path, key_env)
    base = new_project(client)
    upload(client, base, "카드.txt", "결제 카드는 1234-5678-9012-3456 이에요.".encode())
    blocked = client.post(f"{base}/input", json={"chunks": [], "attachments": True}).json()
    assert blocked["blocked"] is True and client.get(base).json()["source"]["sources"] == []
    assert client.post(f"{base}/input", json={"chunks": [], "attachments": True, "mask": True}).json()["blocked"] is False
    sources = client.get(base).json()["source"]["sources"]
    assert "1234-5678-9012-3456" not in str(sources) and sources[0]["origin"] == "document"


def test_model_output_is_masked_before_returning(tmp_path: Path, key_env: Path) -> None:
    chat = {**outputs(), "attachment_text": [{"text": "카드 1234-5678-9012-3456 로 결제."}]}
    client, _ = client_for(tmp_path, key_env, chat)
    base = new_project(client)
    text = upload(client, base, "a.png", PNG).json()["text"]
    assert "1234-5678-9012-3456" not in text and "[카드번호 가림]" in text
    assert any(e["type"] == "guardrail" and e["data"]["id"] == "G3" and e["data"]["outcome"] == "masked"
               for e in client.get(base).json()["source"]["events"])


def test_events_keep_no_data_or_text(tmp_path: Path, key_env: Path) -> None:
    client, _ = client_for(tmp_path, key_env)
    base = new_project(client)
    upload(client, base, "화면.png", PNG)
    upload(client, base, "기획.pdf", PDF)
    events = client.get(base).json()["source"]["events"]
    read = [e for e in events if e["type"] == "liner_attachment"]
    assert len(read) == 2
    assert read[0]["data"]["filename"] == "화면.png" and read[0]["data"]["kind"] == "image"
    assert read[0]["data"]["bytes"] == len(PNG) and read[0]["data"]["chars"] == len(IMAGE_TEXT)
    dumped = str(events)
    for secret in (base64.b64encode(PNG).decode()[:16], base64.b64encode(PDF).decode()[:16], IMAGE_TEXT, PDF_TEXT):
        assert secret not in dumped


def test_errors_are_korean(tmp_path: Path, key_env: Path) -> None:
    client, fake = client_for(tmp_path, key_env)
    base = new_project(client)
    bad = upload(client, base, "a.docx", PNG)
    assert bad.status_code == 400 and "형식" in bad.json()["detail"]
    fake_ext = upload(client, base, "a.png", PDF)
    assert fake_ext.status_code == 400 and "확장자" in fake_ext.json()["detail"]
    big = upload(client, base, "a.png", PNG + b"\x00" * MAX_IMAGE_BYTES)
    assert big.status_code == 400 and "5MB" in big.json()["detail"]
    huge = upload(client, base, "a.pdf", PDF + b"\x00" * MAX_PDF_BYTES)
    assert huge.status_code == 413 and "15MB" in huge.json()["detail"]
    missing = client.post(f"{base}/input", json={"chunks": [], "attachments": True})
    assert missing.status_code == 409 and "첨부" in missing.json()["detail"]
    assert client.post(f"{base}/input", json={"chunks": []}).status_code == 422
    assert fake.requests == []
    assert CHAT_URL  # the router URL is the only one attachments use


def test_the_size_message_uses_the_right_particle() -> None:
    """11-22: 「이미지은 5MB」 was printed; the particle follows the last sound."""
    with pytest.raises(AttachmentError, match="이미지는 5MB 이하만"):
        check_attachment("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024 + 1))
    with pytest.raises(AttachmentError, match="PDF는 15MB 이하만"):
        check_attachment("a.pdf", b"%PDF-1.4" + b"0" * (15 * 1024 * 1024 + 1))
