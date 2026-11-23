from __future__ import annotations
"""S1 attachments: images and documents the client adds to the request, checked before anything is sent.

Liner limits (docs, verified 2026-11-18): the router (LINER_MODEL) takes image parts — JPEG, PNG, GIF, WEBP up to
5 MB each. Routers do not take PDF; a catalog model (LINER_FILE_MODEL, default google/gemini-3.8-flash) takes
`file` parts, inline data up to 20 MB per request. Text files are read here and cost no call.
"""

import base64
import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import read_env
from app.korean import josa

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
MAX_ATTACHMENT_BYTES = MAX_PDF_BYTES  # the largest kind: the stream stops past this
MAX_ATTACHMENTS = 5
DEFAULT_FILE_MODEL = "google/gemini-3.8-flash"
PURPOSES = ("memo", "systems")
NOTES = {"image": "이미지에서 옮겨 적음", "document": "문서에서 옮겨 적음"}
ALLOWED = "이미지(PNG·JPG·GIF·WEBP), PDF, 글 파일(TXT·MD·CSV·TSV)"

_EXTENSIONS = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".gif": "gif", ".webp": "webp", ".pdf": "pdf",
               ".txt": "text", ".md": "text", ".csv": "text", ".tsv": "text"}
_MEDIA = {"png": "image/png", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf"}
_LIMITS = {"image": (MAX_IMAGE_BYTES, "이미지", "5MB"), "pdf": (MAX_PDF_BYTES, "PDF", "15MB"),
           "text": (MAX_TEXT_BYTES, "글 파일", "1MB")}

MEMO_PROMPT = ("첨부에 적힌 글자와 내용을 빠짐없이 한국어로 옮겨 적어라. 표는 줄마다 '칸: 값'으로, 화면 캡처나 손그림이면 "
               "보이는 화면 구성(제목·입력 칸·버튼·순서)을 위에서 아래로 적어라. 보이지 않는 내용은 지어내지 마라.")
SYSTEMS_PROMPT = ("회사가 이미 운영하는 시스템을 찾아 시스템마다 이름과 하는 일(가진 데이터·연결 방법)을 적어라. "
                  "첨부에 없는 시스템은 지어내지 마라.")
MEMO_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["text"],
               "properties": {"text": {"type": "string"}}}
SYSTEMS_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["systems"],
    "properties": {"systems": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["name", "about"],
        "properties": {"name": {"type": "string"}, "about": {"type": "string"}}}}}}
REQUESTS = {"memo": ("attachment_text", MEMO_SCHEMA, MEMO_PROMPT),
            "systems": ("attachment_systems", SYSTEMS_SCHEMA, SYSTEMS_PROMPT)}


class AttachmentError(ValueError):
    """The attachment cannot be read (message is shown to the client as is)."""


@dataclass(frozen=True)
class Attachment:
    format: str  # png | jpeg | gif | webp | pdf | text

    @property
    def kind(self) -> str:
        """What the client sees and what the sources are marked with: image or document."""
        return "image" if self.format in ("png", "jpeg", "gif", "webp") else "document"

    @property
    def group(self) -> str:
        return "image" if self.kind == "image" else self.format


def sniff(data: bytes) -> str | None:
    """Binary format from the first bytes (magic numbers), or None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:5] == b"%PDF-":
        return "pdf"
    return None


def check_attachment(filename: str, data: bytes) -> Attachment:
    """Return the detected format, or raise AttachmentError with a Korean reason."""
    if not data:
        raise AttachmentError("빈 파일이에요. 첨부할 파일을 다시 골라 주세요")
    ext = Path(filename).suffix.lower()
    expected = _EXTENSIONS.get(ext)
    if expected is None:
        raise AttachmentError(f"읽을 수 없는 파일 형식이에요({ext or '확장자 없음'}). {ALLOWED}만 올릴 수 있어요")
    found = Attachment(expected)
    limit, label, shown = _LIMITS[found.group]
    if len(data) > limit:
        raise AttachmentError(f"파일이 너무 커요({len(data) / 1_048_576:.1f}MB). {josa(label, '은/는')} {shown} 이하만 올릴 수 있어요")
    sniffed = sniff(data)
    if expected == "text":
        if sniffed is not None or b"\x00" in data[:4096]:
            raise AttachmentError("파일 내용이 글 파일로 보이지 않아요. TXT·MD·CSV·TSV 파일인지 확인해 주세요")
    elif sniffed != expected:
        raise AttachmentError(f"파일 내용이 확장자({ext})와 달라요. 파일이 손상되지 않았는지 확인해 주세요")
    return found


def decode_text(data: bytes) -> str:
    """UTF-8 (with or without BOM) first, then cp949 (Korean Windows files)."""
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return data.decode(encoding).replace("\r\n", "\n").strip()
        except UnicodeDecodeError:
            continue
    raise AttachmentError("글자를 읽을 수 없는 파일이에요. UTF-8 이나 한글(CP949)로 저장한 파일인지 확인해 주세요")


def data_part(found: Attachment, filename: str, data: bytes) -> dict[str, Any]:
    """The image or file content part of a chat message (OpenAI-compatible shapes, Liner docs)."""
    url = f"data:{_MEDIA[found.format]};base64,{base64.b64encode(data).decode()}"
    if found.kind == "image":
        return {"type": "image_url", "image_url": {"url": url}}
    return {"type": "file", "file": {"filename": filename, "file_data": url}}


def file_model(env_file: Path | None) -> str:
    return read_env("LINER_FILE_MODEL", env_file) or DEFAULT_FILE_MODEL


def system_lines(systems: Any) -> list[str]:
    """Model answer {systems: [{name, about}]} → 「이름: 하는 일」 lines for the 「우리 시스템 목록」 box."""
    lines = []
    for item in systems if isinstance(systems, list) else []:
        name = str(item.get("name", "")).strip() if isinstance(item, dict) else ""
        about = str(item.get("about", "")).strip() if isinstance(item, dict) else ""
        if name:
            lines.append(f"{name}: {about}" if about else name)
    return lines


def text_systems(filename: str, text: str) -> list[str]:
    """CSV/TSV: first column is the name, the other columns become 「헤더: 값」. Other text: its lines as they are."""
    suffix = Path(filename).suffix.lower()
    if suffix not in (".csv", ".tsv"):
        return [line.strip() for line in text.splitlines() if line.strip()]
    rows = [r for r in csv.reader(io.StringIO(text), delimiter="\t" if suffix == ".tsv" else ",") if any(c.strip() for c in r)]
    if not rows:
        return []
    header, body = rows[0], rows[1:]
    lines = []
    for row in body:
        name = row[0].strip() if row else ""
        parts = []
        for i, value in enumerate(row[1:], start=1):
            head = header[i].strip() if i < len(header) else ""
            if value.strip():
                parts.append(f"{head}: {value.strip()}" if head else value.strip())
        about = ", ".join(parts)
        if name:
            lines.append(f"{name}: {about}" if about else name)
    return lines
