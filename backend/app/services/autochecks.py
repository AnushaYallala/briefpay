"""Automatic checks on a submission (SPEC 7.3): code only, no LLM. Every check returns PASS, FAIL or ERROR.

FAIL means we looked and the work is not there. ERROR means we could not look (network down, GitHub rate limit, blocked URL):
it is never counted as a pass, and never as proof of failure either. The caller decides what ERROR means.
"""
import base64
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

from app.services.safe_fetch import FetchBlocked, FetchFailed, SafeFetcher

GITHUB_API = "https://api.github.com"
REPO_URL = re.compile(r"^https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$")
SHA = re.compile(r"^[0-9a-fA-F]{7,40}$")
PATH_OK = re.compile(r"^[A-Za-z0-9._@+ /-]{1,200}$")
VIEWPORT = re.compile(r"<meta\b[^>]*\bname\s*=\s*[\"']viewport[\"'][^>]*>", re.I)


@dataclass
class CheckResult:
    check_type: str
    result: str                      # PASS | FAIL | ERROR
    input: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)
    requirement_code: str | None = None

    @property
    def passed(self) -> bool:
        return self.result == "PASS"


def parse_repo(repo_url: str) -> tuple[str, str] | None:
    m = REPO_URL.match((repo_url or "").strip())
    return (m.group(1), m.group(2)) if m else None


def join_site(base: str, path: str) -> str:
    """The deployed URL plus a path from the BRD. The path can never change the host."""
    parts = urlsplit(base)
    if not path.startswith("/") or "//" in path[:2] or "\\" in path:
        raise FetchBlocked("a page path must start with a single /")
    return f"{parts.scheme}://{parts.netloc}{path}"


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def visible_text(html: str) -> str:
    p = _Text()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001  broken markup must not break a check
        pass
    return normalise(" ".join(p.parts))


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


class AutoChecker:
    """Runs the checks through one SafeFetcher for sites and one (host-locked) SafeFetcher for GitHub."""

    def __init__(self, site: SafeFetcher, github: SafeFetcher | None = None, github_token: str = ""):
        self.site = site
        self.github = github or SafeFetcher(allowed_hosts={"api.github.com"}, transport=site.transport, resolver=site.resolver)
        self.token = github_token

    # ---- website ----
    def _page(self, deployed_url: str, path: str):
        return self.site.get(join_site(deployed_url, path))

    def url_reachable(self, deployed_url: str, path: str = "/", requirement_code: str | None = None) -> CheckResult:
        inp = {"deployed_url": deployed_url, "path": path}
        try:
            r = self._page(deployed_url, path)
        except (FetchBlocked, FetchFailed) as e:
            return CheckResult("URL_REACHABLE", "ERROR", inp, {"error": str(e)}, requirement_code)
        ok = 200 <= r.status < 300
        return CheckResult("URL_REACHABLE", "PASS" if ok else "FAIL", inp, {"status": r.status, "redirects": len(r.redirects)}, requirement_code)

    def page_contains(self, deployed_url: str, path: str, text: str, requirement_code: str | None = None) -> CheckResult:
        inp = {"deployed_url": deployed_url, "path": path, "text": text}
        try:
            r = self._page(deployed_url, path)
        except (FetchBlocked, FetchFailed) as e:
            return CheckResult("PAGE_CONTAINS", "ERROR", inp, {"error": str(e)}, requirement_code)
        if not 200 <= r.status < 300:
            return CheckResult("PAGE_CONTAINS", "FAIL", inp, {"status": r.status, "found": False}, requirement_code)
        found = normalise(text) in visible_text(r.text) and bool(normalise(text))
        return CheckResult("PAGE_CONTAINS", "PASS" if found else "FAIL", inp, {"status": r.status, "found": found}, requirement_code)

    def mobile_viewport(self, deployed_url: str, path: str = "/", requirement_code: str | None = None) -> CheckResult:
        inp = {"deployed_url": deployed_url, "path": path}
        try:
            r = self._page(deployed_url, path)
        except (FetchBlocked, FetchFailed) as e:
            return CheckResult("MOBILE_VIEWPORT", "ERROR", inp, {"error": str(e)}, requirement_code)
        tag = VIEWPORT.search(r.text) if 200 <= r.status < 300 else None
        ok = bool(tag) and "width=device-width" in re.sub(r"\s+", "", tag.group(0).lower())
        return CheckResult("MOBILE_VIEWPORT", "PASS" if ok else "FAIL", inp, {"status": r.status, "viewport": bool(tag)}, requirement_code)

    # ---- GitHub ----
    def _gh(self, path: str):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return self.github.get(f"{GITHUB_API}{path}", headers)

    def _gh_result(self, check_type, inp, path, requirement_code=None, ok_when=None):
        try:
            r = self._gh(path)
        except (FetchBlocked, FetchFailed) as e:
            return CheckResult(check_type, "ERROR", inp, {"error": str(e)}, requirement_code), None
        if r.status == 404:
            return CheckResult(check_type, "FAIL", inp, {"status": 404}, requirement_code), None
        if r.status in (403, 429) or r.status >= 500 or r.status == 401:  # rate limit / outage / bad token: we did not learn anything
            return CheckResult(check_type, "ERROR", inp, {"status": r.status}, requirement_code), None
        try:
            return None, json.loads(r.text)
        except ValueError:
            return CheckResult(check_type, "ERROR", inp, {"error": "GitHub sent something unreadable"}, requirement_code), None

    def repo_public(self, repo_url: str) -> CheckResult:
        inp = {"repo_url": repo_url}
        repo = parse_repo(repo_url)
        if repo is None:
            return CheckResult("REPO_PUBLIC", "FAIL", inp, {"error": "not a github.com/owner/repo URL"})
        early, data = self._gh_result("REPO_PUBLIC", inp, f"/repos/{repo[0]}/{repo[1]}")
        if early:
            return early
        public = isinstance(data, dict) and data.get("private") is False
        return CheckResult("REPO_PUBLIC", "PASS" if public else "FAIL", inp, {"private": (data or {}).get("private")})

    def commit_exists(self, repo_url: str, commit_sha: str) -> CheckResult:
        inp = {"repo_url": repo_url, "commit_sha": commit_sha}
        repo = parse_repo(repo_url)
        if repo is None or not SHA.match(commit_sha or ""):
            return CheckResult("COMMIT_EXISTS", "FAIL", inp, {"error": "bad repo URL or commit id"})
        early, data = self._gh_result("COMMIT_EXISTS", inp, f"/repos/{repo[0]}/{repo[1]}/commits/{commit_sha.lower()}")
        if early:
            return early
        sha = (data or {}).get("sha", "") if isinstance(data, dict) else ""
        return CheckResult("COMMIT_EXISTS", "PASS" if sha.lower().startswith(commit_sha.lower()) else "FAIL", inp, {"sha": sha})

    def file_at_commit(self, repo_url: str, commit_sha: str, path: str, requirement_code: str | None = None) -> tuple[CheckResult, str | None]:
        """FILE_EXISTS, plus the file's text (for the snippet cross-check) when it is a small text file."""
        inp = {"repo_url": repo_url, "commit_sha": commit_sha, "path": path}
        repo = parse_repo(repo_url)
        clean = (path or "").strip().lstrip("/")
        if repo is None or not SHA.match(commit_sha or "") or not PATH_OK.match(clean) or any(seg in ("..", ".") for seg in clean.split("/")):
            return CheckResult("FILE_EXISTS", "FAIL", inp, {"error": "bad repo URL, commit id or path"}, requirement_code), None
        early, data = self._gh_result("FILE_EXISTS", inp, f"/repos/{repo[0]}/{repo[1]}/contents/{quote(clean)}?ref={commit_sha.lower()}", requirement_code)
        if early:
            return early, None
        if not isinstance(data, dict) or data.get("type") != "file":
            return CheckResult("FILE_EXISTS", "FAIL", inp, {"type": data.get("type") if isinstance(data, dict) else "directory"}, requirement_code), None
        text = None
        if data.get("encoding") == "base64" and isinstance(data.get("content"), str):
            try:
                text = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            except ValueError:
                text = None
        return CheckResult("FILE_EXISTS", "PASS", inp, {"size": data.get("size")}, requirement_code), text


def snippet_in_file(snippet: str, file_text: str) -> bool:
    """SPEC 7.3 step 3: a pasted snippet that cites a repo path must really be in that file (whitespace ignored)."""
    needle = normalise(snippet)
    return bool(needle) and needle in normalise(file_text)
