from __future__ import annotations
"""GitHub 연동: each browser signs in to its own GitHub account, then pushes the download bundle as one commit.

Sign-in: GITHUB_CLIENT_ID identifies this app (an OAuth App with device flow on — not a user account, not a
secret). Each browser gets an opaque session id (cookie, see routes_github) and approves its own short code on
github.com/login/device. Tokens, logins and pending codes live only in this process, per session — never in the
project store, an event, a log or a response. Idle sessions expire after SESSION_TTL and at most MAX_SESSIONS
are kept (the least recently used goes first), so memory stays bounded.

Push: the Git Data API (blobs → tree → commit → ref), so each push is one commit whose tree is exactly the
bundle (files dropped from the bundle disappear from the repo). A missing repo under the signed-in account is
created private with an initial commit; an existing empty repo gets one first through the contents API.
"""

import base64
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from secrets import token_urlsafe
from typing import Any

import httpx

from app.config import read_env

API = "https://api.github.com"
DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
SCOPE = "repo"
USER_AGENT = "planning-automation"
REPO_PART = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
SESSION_COOKIE = "gh_session"
SESSION_TTL = 12 * 3600  # seconds a session may sit unused
MAX_SESSIONS = 500
NOT_CONFIGURED = "운영자가 GitHub 연동을 켜지 않았어요. 내려받기(zip)로 받아 주세요."
NOT_CONNECTED = "GitHub 계정이 연결되지 않았어요. 먼저 「GitHub 연결」로 내 계정을 연결해 주세요."
SIGNED_OUT = "GitHub 연결이 끊겼어요. 다시 연결해 주세요."


class GitHubError(RuntimeError):
    """A failure the client can read (Korean message)."""


class GitHubSignedOut(GitHubError):
    """The calling browser has no usable GitHub sign-in."""


@dataclass
class _Session:
    seen: float
    token: str | None = None
    login: str | None = None
    pending: dict[str, Any] | None = None


class GitHubClient:
    def __init__(self, env_file: Path | None = None, transport: httpx.BaseTransport | None = None,
                 clock: Callable[[], float] = time.monotonic, max_sessions: int = MAX_SESSIONS,
                 session_ttl: float = SESSION_TTL) -> None:
        self._env_file = env_file
        self._transport = transport
        self._clock = clock
        self._max_sessions = max_sessions
        self._ttl = session_ttl
        self._lock = threading.RLock()
        self._sessions: OrderedDict[str, _Session] = OrderedDict()  # least recently used first

    # --- sessions ---------------------------------------------------------------------------------
    def session(self, sid: str | None) -> str:
        """The live session for this id (refreshed), or a new one when the id is missing, unknown or expired.
        Only ids this server issued are accepted, so a client cannot pick its own."""
        with self._lock:
            now = self._clock()
            while self._sessions:
                oldest_id, oldest = next(iter(self._sessions.items()))
                if now - oldest.seen < self._ttl:
                    break
                del self._sessions[oldest_id]
            if sid and sid in self._sessions:
                self._sessions[sid].seen = now
                self._sessions.move_to_end(sid)
                return sid
            new_id = token_urlsafe(32)
            self._sessions[new_id] = _Session(seen=now)
            while len(self._sessions) > self._max_sessions:
                self._sessions.popitem(last=False)
            return new_id

    def _get(self, sid: str) -> _Session:
        # A session evicted mid-request reads as signed out; writes to the stand-in are dropped.
        return self._sessions.get(sid) or _Session(seen=self._clock())

    def secrets(self) -> tuple[str, ...]:
        """Tokens that must never leave in a pushed file."""
        with self._lock:
            return tuple(s.token for s in self._sessions.values() if s.token)

    # --- sign-in ----------------------------------------------------------------------------------
    def _client_id(self) -> str | None:
        return read_env("GITHUB_CLIENT_ID", self._env_file)

    def status(self, sid: str) -> dict[str, Any]:
        with self._lock:
            s = self._get(sid)
            connected = bool(s.token and s.login)
            pending = s.pending
            return {
                "configured": bool(self._client_id()),
                "connected": connected,
                "login": s.login if connected else None,
                "pending": None if not pending else {
                    "user_code": pending["user_code"], "verification_uri": pending["verification_uri"],
                    "interval": pending["interval"], "expires_in": max(0, int(pending["expires_at"] - self._clock()))},
            }

    def start(self, sid: str) -> dict[str, Any]:
        client_id = self._client_id()
        if not client_id:
            raise GitHubError(NOT_CONFIGURED)
        body = self._form(DEVICE_CODE_URL, {"client_id": client_id, "scope": SCOPE})
        if "device_code" not in body:
            raise GitHubError(f"GitHub 기기 인증을 시작하지 못했어요: {body.get('error_description') or body.get('error')}")
        with self._lock:
            self._get(sid).pending = {
                "device_code": body["device_code"], "user_code": body["user_code"],
                "verification_uri": body.get("verification_uri", "https://github.com/login/device"),
                "interval": int(body.get("interval", 5)),
                "expires_at": self._clock() + int(body.get("expires_in", 900)), "next_at": 0.0}
        return self.status(sid)

    def poll(self, sid: str) -> dict[str, Any]:
        """Ask GitHub once whether the code was approved (never faster than the interval GitHub gave)."""
        with self._lock:
            s = self._get(sid)
            pending = s.pending
            if not pending or self._clock() < pending["next_at"]:
                return self.status(sid)
            if self._clock() >= pending["expires_at"]:
                s.pending = None
                raise GitHubError("코드 유효 시간이 지났어요. 다시 연결해 주세요.")
            pending["next_at"] = self._clock() + pending["interval"]
            client_id = self._client_id() or ""
        body = self._form(TOKEN_URL, {"client_id": client_id, "device_code": pending["device_code"],
                                      "grant_type": DEVICE_GRANT})
        error = body.get("error")
        if body.get("access_token"):
            token = str(body["access_token"])
            login = self._user(token)  # outside the lock: other browsers keep working meanwhile
            with self._lock:
                if s.pending is pending:
                    s.token, s.login, s.pending = token, login, None
            return self.status(sid)
        with self._lock:
            if error == "slow_down":
                pending["interval"] += 5
            elif error in ("expired_token", "access_denied"):
                s.pending = None
                raise GitHubError("연결을 취소했어요." if error == "access_denied" else "코드 유효 시간이 지났어요. 다시 연결해 주세요.")
            elif error != "authorization_pending":
                s.pending = None
                raise GitHubError(f"GitHub 연결에 실패했어요: {body.get('error_description') or error}")
        return self.status(sid)

    def disconnect(self, sid: str) -> dict[str, Any]:
        with self._lock:
            s = self._get(sid)
            s.token, s.login, s.pending = None, None, None
        return self.status(sid)

    # --- push -------------------------------------------------------------------------------------
    def push(self, sid: str, repo: str, files: Mapping[str, str | bytes], message: str,
             private: bool = True) -> dict[str, Any]:
        if not self._client_id():
            raise GitHubError(NOT_CONFIGURED)
        with self._lock:
            s = self._get(sid)
            token, login = s.token, s.login
        if not (token and login):
            raise GitHubSignedOut(NOT_CONNECTED)
        owner, _, name = repo.strip().rpartition("/")
        owner = owner or login
        if not (REPO_PART.match(owner) and REPO_PART.match(name)) or name in (".", ".."):
            raise GitHubError("저장소 이름은 영문·숫자·-·_·. 만 쓸 수 있어요. 예: flower-plan 또는 my-org/flower-plan")
        path = f"/repos/{owner}/{name}"
        info, created = self._call(token, "GET", path, ok=(200, 404)), False
        if info is None:
            if owner.lower() != login.lower():
                raise GitHubError(f"{owner}/{name} 저장소가 없거나 권한이 없어요. 다른 계정·조직 저장소는 먼저 만들어 두세요.")
            info = self._call(token, "POST", "/user/repos", {"name": name, "private": private, "auto_init": True,
                                                              "description": "0to1(영일) 결과물"})
            created = True
        branch = str(info.get("default_branch") or "main")
        parent = self._head(token, path, branch)
        tree = [{"path": p, "mode": "100644", "type": "blob",
                 "sha": self._call(token, "POST", f"{path}/git/blobs",
                                   {"content": _b64(content), "encoding": "base64"})["sha"]}
                for p, content in files.items()]
        tree_sha = self._call(token, "POST", f"{path}/git/trees", {"tree": tree})["sha"]
        commit = self._call(token, "POST", f"{path}/git/commits",
                            {"message": message, "tree": tree_sha, "parents": [parent]})
        self._call(token, "PATCH", f"{path}/git/refs/heads/{branch}", {"sha": commit["sha"]})
        url = str(info.get("html_url") or f"https://github.com/{owner}/{name}")
        return {"repo": f"{owner}/{name}", "url": url, "branch": branch, "commit": commit["sha"],
                "commit_url": f"{url}/commit/{commit['sha']}", "created": created, "files": len(files)}

    def _head(self, token: str, path: str, branch: str) -> str:
        """The branch tip; an empty repo first gets an initial commit (blobs cannot be made in an empty repo)."""
        ref = self._call(token, "GET", f"{path}/git/ref/heads/{branch}", ok=(200, 404, 409))
        if ref is None:
            self._call(token, "PUT", f"{path}/contents/.gitkeep", {"message": "저장소 시작", "content": "", "branch": branch})
            ref = self._call(token, "GET", f"{path}/git/ref/heads/{branch}")
        return str(ref["object"]["sha"])

    # --- http -------------------------------------------------------------------------------------
    def _user(self, token: str) -> str:
        return str(self._call(token, "GET", "/user")["login"])

    def _forget(self, token: str) -> None:
        """GitHub rejected this token: sign out every session holding it."""
        with self._lock:
            for s in self._sessions.values():
                if s.token == token:
                    s.token, s.login = None, None

    def _form(self, url: str, data: Mapping[str, str]) -> dict[str, Any]:
        try:
            with httpx.Client(transport=self._transport, timeout=30) as http:
                res = http.post(url, data=dict(data), headers={"Accept": "application/json", "User-Agent": USER_AGENT})
        except httpx.HTTPError as exc:
            raise GitHubError(f"GitHub 에 연결하지 못했어요: {type(exc).__name__}") from exc
        try:
            return dict(res.json())
        except ValueError as exc:
            raise GitHubError(f"GitHub 응답을 읽지 못했어요 (HTTP {res.status_code})") from exc

    def _call(self, token: str, method: str, path: str, body: Mapping[str, Any] | None = None,
              ok: tuple[int, ...] = (200, 201)) -> Any:
        """JSON call with the session's token. A status in `ok` other than 200/201 returns None (e.g. 404 = missing)."""
        headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER_AGENT}
        try:
            with httpx.Client(transport=self._transport, timeout=60) as http:
                res = http.request(method, f"{API}{path}", json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise GitHubError(f"GitHub 에 연결하지 못했어요: {type(exc).__name__}") from exc
        if res.status_code == 401:
            self._forget(token)
            raise GitHubSignedOut(SIGNED_OUT)
        if res.status_code in ok and res.status_code not in (200, 201):
            return None
        if res.status_code not in (200, 201):
            detail = _message(res)
            if res.status_code == 403:
                raise GitHubError(f"GitHub 권한이 없어요(repo 권한 필요): {detail}")
            raise GitHubError(f"GitHub 요청이 실패했어요 (HTTP {res.status_code}): {detail}")
        return res.json()


def _b64(content: str | bytes) -> str:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return base64.b64encode(data).decode("ascii")


def _message(res: httpx.Response) -> str:
    try:
        return str(res.json().get("message") or "")
    except ValueError:
        return ""
