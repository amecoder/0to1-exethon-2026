from __future__ import annotations
"""A scripted GitHub on httpx.MockTransport: device flow, /user, repos and the Git Data API. No network."""

import base64
import json
from typing import Any

import httpx

TOKEN = "gho_fake_token_123"  # the first account's token


class FakeGitHub:
    """Device code N signs in as logins[N] (the last one repeats), each account with its own token."""

    def __init__(self, login: str = "kim", pending_polls: int = 1, repos: dict[str, dict[str, Any]] | None = None,
                 deny: bool = False, logins: tuple[str, ...] = ()) -> None:
        self.logins = logins or (login,)
        self.tokens = {name: TOKEN if i == 0 else f"gho_fake_token_{name}" for i, name in enumerate(self.logins)}
        self._pending_polls = pending_polls  # authorization_pending answers before the token, per device code
        self._pending: dict[str, int] = {}
        self._codes = 0
        self._deny = deny
        # "owner/name" -> {"private", "head" (sha or None = empty), "files" {path: bytes}, "default_branch"}
        self.repos: dict[str, dict[str, Any]] = dict(repos or {})
        self.requests: list[tuple[str, str, Any]] = []
        self.revoked = False
        self._objects: dict[str, Any] = {}
        self._n = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def calls(self, method: str, fragment: str) -> list[Any]:
        return [body for m, path, body in self.requests if m == method and fragment in path]

    def _sha(self, obj: Any) -> str:
        self._n += 1
        sha = f"sha{self._n:04d}"
        self._objects[sha] = obj
        return sha

    def _handle(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        body: Any = None
        if request.content:
            raw = request.content.decode("utf-8")
            body = json.loads(raw) if raw.startswith("{") else dict(httpx.QueryParams(raw))
        self.requests.append((request.method, str(url), body))
        if url.host == "github.com":
            return self._oauth(url.path, body)
        by_header = {f"Bearer {token}": name for name, token in self.tokens.items()}
        login = by_header.get(request.headers.get("authorization", ""))
        if login is None or self.revoked:
            return httpx.Response(401, json={"message": "Bad credentials"})
        return self._api(login, request.method, url.path, body)

    def _oauth(self, path: str, body: dict[str, str]) -> httpx.Response:
        if path == "/login/device/code":
            assert body["scope"] == "repo"
            n, self._codes = self._codes, self._codes + 1
            code = f"dev-{n}"
            self._pending[code] = self._pending_polls
            return httpx.Response(200, json={"device_code": code, "user_code": f"ABCD-{1234 + n}",
                                             "verification_uri": "https://github.com/login/device",
                                             "expires_in": 900, "interval": 5})
        assert body["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"
        if self._deny:
            return httpx.Response(200, json={"error": "access_denied"})
        code = body["device_code"]
        if self._pending[code] > 0:
            self._pending[code] -= 1
            return httpx.Response(200, json={"error": "authorization_pending"})
        login = self.logins[min(int(code.removeprefix("dev-")), len(self.logins) - 1)]
        return httpx.Response(200, json={"access_token": self.tokens[login], "token_type": "bearer", "scope": "repo"})

    def _api(self, login: str, method: str, path: str, body: Any) -> httpx.Response:
        if path == "/user":
            return httpx.Response(200, json={"login": login})
        if method == "POST" and path == "/user/repos":
            full = f"{login}/{body['name']}"
            init = self._sha({"tree": {"README.md": b"init"}, "parents": []})
            self.repos[full] = {"private": body["private"], "head": init, "files": {"README.md": b"init"},
                                "default_branch": "main"}
            return httpx.Response(201, json=self._repo_json(full))
        parts = path.split("/")  # /repos/{o}/{n}/...
        full = f"{parts[2]}/{parts[3]}"
        repo = self.repos.get(full)
        if repo is None:
            return httpx.Response(404, json={"message": "Not Found"})
        rest = "/".join(parts[4:])
        if not rest:
            return httpx.Response(200, json=self._repo_json(full))
        if rest.startswith("git/ref/heads/"):
            if repo["head"] is None:
                return httpx.Response(409, json={"message": "Git Repository is empty."})
            return httpx.Response(200, json={"object": {"sha": repo["head"]}})
        if method == "PUT" and rest.startswith("contents/"):
            repo["head"] = self._sha({"tree": {rest[len("contents/"):]: b""}, "parents": []})
            return httpx.Response(201, json={"commit": {"sha": repo["head"]}})
        if repo["head"] is None:
            return httpx.Response(409, json={"message": "Git Repository is empty."})
        if rest == "git/blobs":
            return httpx.Response(201, json={"sha": self._sha(base64.b64decode(body["content"]))})
        if rest == "git/trees":
            tree = {e["path"]: self._objects[e["sha"]] for e in body["tree"]}
            return httpx.Response(201, json={"sha": self._sha(tree)})
        if rest == "git/commits":
            assert body["parents"] == [repo["head"]]
            return httpx.Response(201, json={"sha": self._sha({"tree": self._objects[body["tree"]],
                                                               "message": body["message"]})})
        if method == "PATCH" and rest.startswith("git/refs/heads/"):
            repo["head"] = body["sha"]
            repo["files"] = self._objects[body["sha"]]["tree"]
            repo["message"] = self._objects[body["sha"]]["message"]
            repo["pushed_by"] = login
            return httpx.Response(200, json={"object": {"sha": body["sha"]}})
        return httpx.Response(404, json={"message": f"unhandled {method} {path}"})

    def _repo_json(self, full: str) -> dict[str, Any]:
        repo = self.repos[full]
        return {"full_name": full, "private": repo["private"], "default_branch": repo["default_branch"],
                "html_url": f"https://github.com/{full}"}
