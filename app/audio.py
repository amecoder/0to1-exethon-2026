from __future__ import annotations
"""S1 audio upload checks before anything is sent to Liner speech-to-text.

Liner limits (docs "Audio transcriptions"): up to 25 MiB (26,214,400 bytes); WAV, MP3, FLAC, M4A, OGG, WebM,
detected from the file contents. We check the same rules here so a wrong file never costs a call.
"""

from collections.abc import AsyncIterator

MAX_AUDIO_BYTES = 26_214_400
FORMATS = ("WAV", "MP3", "FLAC", "M4A", "OGG", "WebM")
_EXTENSIONS = {".wav": "WAV", ".mp3": "MP3", ".flac": "FLAC", ".m4a": "M4A", ".mp4": "M4A", ".ogg": "OGG",
               ".oga": "OGG", ".opus": "OGG", ".webm": "WebM"}


class AudioFileError(ValueError):
    """The uploaded audio cannot be transcribed (message is shown to the client as is)."""


class AudioTooLargeError(AudioFileError):
    """The upload passed the size limit while it was still streaming in."""


async def read_limited(chunks: AsyncIterator[bytes], limit: int) -> bytes:
    """Collect a streamed body, stopping as soon as more than `limit` bytes arrived (Content-Length or not)."""
    parts: list[bytes] = []
    total = 0
    async for chunk in chunks:
        total += len(chunk)
        if total > limit:
            raise AudioTooLargeError("파일이 너무 커요. 25MB 이하로 잘라서 올려 주세요")
        parts.append(chunk)
    return b"".join(parts)


def sniff(data: bytes) -> str | None:
    """Audio format from the first bytes (magic numbers), or None."""
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "WAV"
    if data[:4] == b"fLaC":
        return "FLAC"
    if data[:4] == b"OggS":
        return "OGG"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "WebM"
    if data[4:8] == b"ftyp":
        return "M4A"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "MP3"
    return None


def check_audio(filename: str, data: bytes) -> str:
    """Return the detected format, or raise AudioFileError with a Korean reason."""
    allowed = ", ".join(FORMATS)
    if not data:
        raise AudioFileError("빈 파일이에요. 회의 녹음 파일을 다시 골라 주세요")
    if len(data) > MAX_AUDIO_BYTES:
        mib = len(data) / 1_048_576
        raise AudioFileError(f"파일이 너무 커요({mib:.1f}MB). 25MB 이하로 잘라서 올려 주세요")
    dot = filename.rfind(".")
    ext = filename[dot:].lower() if dot >= 0 else ""
    if ext not in _EXTENSIONS:
        raise AudioFileError(f"받아 적을 수 없는 파일 형식이에요({ext or '확장자 없음'}). {allowed} 파일만 올릴 수 있어요")
    found = sniff(data)
    if found is None:
        raise AudioFileError(f"파일 내용이 음성 파일로 보이지 않아요. {allowed} 파일인지 확인해 주세요")
    return found
