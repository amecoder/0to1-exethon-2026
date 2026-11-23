from __future__ import annotations
"""S6 product pictures from the Liner Images API, embedded into the prototype as small data URIs.

The developer agent may ask for up to MAX_IMAGES pictures (`images: [{slot, prompt}]`) and marks where they
go with <img data-img="slot">. After the HTML has passed G6, each picture is generated, downscaled to a
IMAGE_WIDTH-wide JPEG (a 1024² PNG is ~2 MB of base64) and written into that tag's src. Pictures are optional:
no LINER_IMAGE_MODEL, a failure or the G7 cap leaves a 참고 notice and the kit's placeholder stays.
"""

import base64
import io
import re
from collections.abc import Mapping
from typing import Any

from PIL import Image

from app.config import LinerKeyMissingError
from app.liner import LinerAPIError, LinerConfigError
from app.limits import LimitReachedError
from app.agent_runner import ToolNotAllowedError

MAX_IMAGES = 3
IMAGE_WIDTH = 480
JPEG_QUALITY = 80
NOTICE_PREFIX = "상품 이미지"
_SLOT = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_IMG = re.compile(r"<img\b[^>]*>", re.I)
_SLOT_ATTR = re.compile(r"""\bdata-img\s*=\s*(['"])([^'"]+)\1""", re.I)
_SRC_ATTR = re.compile(r"""\s+src\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_DATA_URI = re.compile(r"""\bsrc\s*=\s*(['"])data:image/[a-z+]+;base64,([A-Za-z0-9+/=]+)\1""", re.I)


def image_slots(html: str) -> list[str]:
    return [m.group(2) for tag in _IMG.findall(html) for m in [_SLOT_ATTR.search(tag)] if m]


def requested_images(output: Mapping[str, Any], html: str) -> list[dict[str, str]]:
    """The agent's requests whose slot is a tag in the HTML: unique, valid, first MAX_IMAGES."""
    asked = output.get("images")
    if not isinstance(asked, list):
        return []
    present, seen, out = set(image_slots(html)), set(), []
    for item in asked:
        if not isinstance(item, Mapping):
            continue
        slot, prompt = str(item.get("slot", "")).strip(), str(item.get("prompt", "")).strip()
        if _SLOT.match(slot) and prompt and slot in present and slot not in seen:
            seen.add(slot)
            out.append({"slot": slot, "prompt": prompt})
    return out[:MAX_IMAGES]


def downscale(b64: str) -> str:
    """Base64 image → IMAGE_WIDTH-wide JPEG data URI (never wider than the original)."""
    with Image.open(io.BytesIO(base64.b64decode(b64))) as img:
        rgb = img.convert("RGB")
        width = min(IMAGE_WIDTH, rgb.width)
        height = max(1, round(rgb.height * width / rgb.width))
        small = rgb.resize((width, height), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    small.save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def embed_images(html: str, pictures: Mapping[str, str]) -> str:
    """Put each data URI into its <img data-img="slot"> (any existing src on that tag is replaced)."""
    def swap(match: re.Match[str]) -> str:
        tag = match.group(0)
        slot = _SLOT_ATTR.search(tag)
        uri = pictures.get(slot.group(2)) if slot else None
        if not uri or not uri.startswith("data:image/"):
            return tag
        bare = _SRC_ATTR.sub("", tag)
        return bare[:4] + f' src="{uri}"' + bare[4:]
    return _IMG.sub(swap, html)


def extract_images(html: str) -> dict[str, bytes]:
    """Embedded pictures by slot (for the zip export)."""
    out: dict[str, bytes] = {}
    for tag in _IMG.findall(html):
        slot, data = _SLOT_ATTR.search(tag), _DATA_URI.search(tag)
        if slot and data:
            out[slot.group(2)] = base64.b64decode(data.group(2))
    return out


def add_images(ctx: Any, html: str, requests: list[dict[str, str]]) -> tuple[str, str | None]:
    """Generate the requested pictures in order. Returns (html, 참고 notice or None)."""
    if not requests:
        return html, None
    pictures: dict[str, str] = {}
    failed: list[str] = []
    for req in requests:
        try:
            body = ctx.runner.image("developer", req["slot"], req["prompt"])
            pictures[req["slot"]] = downscale(body["data"][0]["b64_json"])
        except ToolNotAllowedError as exc:
            return html, f"{NOTICE_PREFIX}: 사진을 만들 도구가 없어 그림으로 채웠어요 ({exc})"
        except LinerConfigError:
            return html, (f"{NOTICE_PREFIX}: LINER_IMAGE_MODEL 이 설정되지 않아 사진 자리를 그림으로 채웠어요"
                          "(참고 — .env 에 LINER_IMAGE_MODEL=qwen/qwen-image-2.1-turbo)")
        except LimitReachedError:
            failed += [r["slot"] for r in requests if r["slot"] not in pictures and r["slot"] not in failed]
            break
        except (LinerAPIError, LinerKeyMissingError, OSError, ValueError, KeyError, IndexError):
            failed.append(req["slot"])
    notice = None
    if failed:
        notice = (f"{NOTICE_PREFIX} {len(failed)}장을 만들지 못해 그림 자리로 두었어요(참고): {', '.join(failed)}")
    return embed_images(html, pictures), notice
