from __future__ import annotations
"""S1 audio: format/size checks, Liner speech-to-text over HTTP, transcript stored as SRC marked 음성."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.audio import MAX_AUDIO_BYTES, AudioFileError, check_audio
from app.config import Settings
from app.liner import LinerClient
from app.main import create_app
from tests.fake_liner import FakeLiner
from tests.flower_script import SEARCH_BODY, flower_outputs, memo_chunks

MP3 = b"ID3\x04\x00" + b"\x00" * 64
TRANSCRIPT = "배송은 토요일에만 해요. 일시정지는 꼭 넣어 주세요."


@pytest.mark.parametrize("name, data, fmt", [
    ("a.mp3", MP3, "MP3"), ("a.wav", b"RIFF\x00\x00\x00\x00WAVEfmt ", "WAV"), ("a.flac", b"fLaC\x00", "FLAC"),
    ("a.ogg", b"OggS\x00", "OGG"), ("a.webm", b"\x1a\x45\xdf\xa3\x00", "WebM"), ("a.m4a", b"\x00\x00\x00\x20ftypM4A ", "M4A")])
def test_supported_formats_are_detected_from_content(name: str, data: bytes, fmt: str) -> None:
    assert check_audio(name, data) == fmt


@pytest.mark.parametrize("name, data, word", [
    ("a.mp3", b"", "빈 파일"), ("a.txt", MP3, "형식"), ("memo", MP3, "확장자 없음"), ("a.mp3", b"hello world", "음성 파일로")])
def test_bad_files_get_korean_reasons(name: str, data: bytes, word: str) -> None:
    with pytest.raises(AudioFileError, match=word):
        check_audio(name, data)


def test_over_25mib_is_refused() -> None:
    with pytest.raises(AudioFileError, match="25MB"):
        check_audio("a.mp3", MP3 + b"\x00" * MAX_AUDIO_BYTES)


def client_for(tmp_path: Path, env_file: Path, **fake_kwargs) -> tuple[TestClient, FakeLiner]:
    fake = FakeLiner(flower_outputs(memo_chunks()), search_body=SEARCH_BODY, **fake_kwargs)
    settings = Settings(db_path=tmp_path / "audio.sqlite3", env_file=env_file)
    app = create_app(settings, liner=LinerClient(env_file=env_file, transport=fake.transport()))
    return TestClient(app), fake


def new_project(client: TestClient) -> str:
    return "/api/projects/" + client.post("/api/projects", json={"name": "꽃님", "mode": "real"}).json()["id"]


def test_audio_transcript_becomes_marked_sources(tmp_path: Path, key_env: Path) -> None:
    key_env.write_text(key_env.read_text(encoding="utf-8") + "LINER_STT_MODEL=openai/gpt-transcribe\n", encoding="utf-8")
    client, fake = client_for(tmp_path, key_env, transcript=TRANSCRIPT)
    base = new_project(client)
    response = client.post(f"{base}/input/audio?filename=회의.mp3", content=MP3)
    assert response.status_code == 200 and response.json()["text"] == TRANSCRIPT
    project = client.get(base).json()
    assert project["source"]["sources"] == []  # nothing stored before the G3 check of /input
    assert [e["type"] for e in project["source"]["events"]].count("liner_transcription") == 1
    assert TRANSCRIPT not in str(project["source"]["events"])  # the event keeps size/length only
    assert client.post(f"{base}/input", json={"chunks": ["꽃집 정기구독 앱을 만들고 싶어요."], "audio": True}).status_code == 202
    sources = client.get(base).json()["source"]["sources"]
    typed = [s for s in sources if s["chunk"] == 1]
    spoken = [s for s in sources if s.get("origin") == "audio"]
    assert typed and "origin" not in typed[0]
    assert [s["text"] for s in spoken] == ["배송은 토요일에만 해요.", "일시정지는 꼭 넣어 주세요."]
    assert all(s["origin_note"] == "음성에서 받아 적음" and s["raw"] and s["audio_file"] == "회의.mp3" for s in spoken)


def test_audio_errors_are_korean(tmp_path: Path, key_env: Path) -> None:
    client, fake = client_for(tmp_path, key_env)
    base = new_project(client)
    bad = client.post(f"{base}/input/audio?filename=memo.txt", content=b"hello")
    assert bad.status_code == 400 and "형식" in bad.json()["detail"]
    no_model = client.post(f"{base}/input/audio?filename=a.mp3", content=MP3)
    assert no_model.status_code == 409 and "LINER_STT_MODEL" in no_model.json()["detail"]
    missing = client.post(f"{base}/input", json={"chunks": [], "audio": True})
    assert missing.status_code == 409 and "음성" in missing.json()["detail"]
    empty = client.post(f"{base}/input", json={"chunks": ["  "]})
    assert empty.status_code == 422
    assert fake.requests == []


def test_sensitive_transcript_is_blocked_then_masked_without_a_second_call(tmp_path: Path, key_env: Path) -> None:
    key_env.write_text(key_env.read_text(encoding="utf-8") + "LINER_STT_MODEL=m\n", encoding="utf-8")
    client, fake = client_for(tmp_path, key_env, transcript="제 번호는 010-1234-5678 이에요. 배송은 토요일.")
    base = new_project(client)
    client.post(f"{base}/input/audio?filename=a.mp3", content=MP3)
    blocked = client.post(f"{base}/input", json={"chunks": [], "audio": True}).json()
    assert blocked["blocked"] is True and client.get(base).json()["source"]["sources"] == []
    assert client.post(f"{base}/input", json={"chunks": [], "audio": True, "mask": True}).json()["blocked"] is False
    sources = client.get(base).json()["source"]["sources"]
    assert "010-1234-5678" not in str(sources) and sources[0]["origin"] == "audio"
    assert sum(1 for r in fake.requests if r.url.path.endswith("/audio/transcriptions")) == 1


def test_flow_preview_is_isolated(tmp_path: Path, key_env: Path) -> None:
    from tests.test_p1_api import to_cp3

    client, _ = client_for(tmp_path, key_env)
    base = to_cp3(client)
    response = client.get(f"{base}/flow/preview")
    assert response.status_code == 200
    assert "connect-src 'none'" in response.headers["content-security-policy"]
    assert 'sandbox="allow-scripts"' in response.text and "cdn.jsdelivr.net" not in response.text
    # The phone-screen kit belongs to the prototype only: on the chart it cut the page to a phone's width.
    assert "proto-kit" not in response.text


# --- review fix 7: the size limit applies while the body streams in -----------------------------------
def test_chunked_upload_over_the_limit_without_content_length_gets_413(tmp_path: Path, key_env: Path) -> None:
    client, fake = client_for(tmp_path, key_env)
    pid = client.post("/api/projects", json={"name": "x", "mode": "real"}).json()["id"]

    def body():
        yield MP3
        for _ in range(27):
            yield b"\x00" * 1_048_576

    response = client.post(f"/api/projects/{pid}/input/audio?filename=a.mp3", content=body())
    assert response.status_code == 413 and "25MB" in response.json()["detail"]
    assert fake.requests == []


def test_reading_stops_as_soon_as_the_limit_is_passed() -> None:
    import asyncio

    from app.audio import AudioTooLargeError, read_limited

    pulled = []

    async def stream():
        for i in range(40):
            pulled.append(i)
            yield b"\x00" * 1_048_576

    with pytest.raises(AudioTooLargeError):
        asyncio.run(read_limited(stream(), MAX_AUDIO_BYTES))
    assert len(pulled) == 26  # 25 MiB fit; the 26th chunk passes the limit and reading stops there
