"""SSRF-safe fetcher (SPEC 7.3). The freelancer chooses the URLs we fetch, so every request is treated as hostile input.

Rules: https only (http only to localhost, and only when `allow_local` is on for dev); no credentials in the URL; port 443
(any port for the localhost dev exception); the host name is resolved here, EVERY address must be a public one, and we then
connect to that exact address (so a DNS answer cannot change between the check and the connection); at most 3 redirects, each
one re-checked from scratch; 10 s overall deadline per request; 2 MB body cap; no cookies; no proxy or environment settings.
Headers meant for one host (a token) are dropped when a redirect leaves that host.
"""
import ipaddress
import socket
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx

MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 10.0
MAX_BYTES = 2_000_000
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


class FetchBlocked(Exception):
    """The URL is not allowed (never contacted)."""


class FetchFailed(Exception):
    """The URL was allowed but could not be fetched (timeout, connection error, too big, too many redirects)."""


@dataclass
class Fetched:
    url: str
    status: int
    headers: dict
    body: bytes
    redirects: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def system_resolver(host: str, port: int) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


def is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.teredo is not None or ip.sixtofour is not None:  # tunnels can wrap a private IPv4 address
            return False
    return ip.is_global and not ip.is_multicast


def _is_local_host(host: str) -> bool:
    return host.lower() in LOCAL_HOSTS


class SafeFetcher:
    def __init__(self, *, allow_local: bool = False, resolver=system_resolver, transport: httpx.BaseTransport | None = None,
                 allowed_hosts: set[str] | None = None, timeout: float = TIMEOUT_SECONDS, max_bytes: int = MAX_BYTES):
        self.allow_local, self.resolver, self.transport = allow_local, resolver, transport
        self.allowed_hosts = {h.lower() for h in allowed_hosts} if allowed_hosts else None
        self.timeout, self.max_bytes = timeout, max_bytes

    # ---- validation ----
    def check_url(self, url: str) -> tuple[str, str, int, str, str | None]:
        """-> (scheme, host, port, path+query, address to connect to). Raises FetchBlocked."""
        if not isinstance(url, str) or len(url) > 2000 or any(ord(c) < 33 or ord(c) == 127 for c in url):
            raise FetchBlocked("not a usable URL")
        parts = urlsplit(url)
        scheme, host = parts.scheme.lower(), (parts.hostname or "").lower()
        if scheme not in ("https", "http") or not host:
            raise FetchBlocked("only https URLs are allowed")
        if parts.username is not None or parts.password is not None or "@" in parts.netloc:
            raise FetchBlocked("credentials in a URL are not allowed")
        try:
            port = parts.port
        except ValueError:
            raise FetchBlocked("bad port") from None
        local = _is_local_host(host)
        if scheme == "http" and not (local and self.allow_local):
            raise FetchBlocked("only https URLs are allowed")
        if local and not self.allow_local:
            raise FetchBlocked("localhost is not allowed")
        if not local and port not in (None, 443):
            raise FetchBlocked("only port 443 is allowed")
        if self.allowed_hosts is not None and host not in self.allowed_hosts:
            raise FetchBlocked(f"host {host} is not on the allow list")
        port = port or (443 if scheme == "https" else 80)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        if local:
            return scheme, host, port, path, host
        try:
            addresses = self.resolver(host, port)
        except OSError:
            raise FetchFailed(f"could not resolve {host}") from None
        if not addresses:
            raise FetchFailed(f"could not resolve {host}")
        bad = [a for a in addresses if not is_public(a)]
        if bad:  # one private answer among public ones is still a rebinding trick: refuse the lot
            raise FetchBlocked(f"{host} resolves to a non-public address")
        return scheme, host, port, path, addresses[0]

    # ---- fetching ----
    def get(self, url: str, headers: dict | None = None) -> Fetched:
        deadline = time.monotonic() + self.timeout
        current, trail, first_host = url, [], (urlsplit(url).hostname or "").lower()
        for hop in range(MAX_REDIRECTS + 1):
            scheme, host, port, path, address = self.check_url(current)
            send_headers = dict(headers or {}) if host == first_host else {}  # never carry a token to another host
            resp = self._once(scheme, host, port, path, address, send_headers, deadline)
            if resp.status in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                trail.append(current)
                current = urljoin(current, resp.headers["location"])
                continue
            resp.url, resp.redirects = current, trail
            return resp
        raise FetchFailed("too many redirects")  # pragma: no cover

    def _once(self, scheme, host, port, path, address, headers, deadline) -> Fetched:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchFailed("timed out")
        netloc = f"[{address}]" if ":" in address else address
        if not _is_local_host(host):
            netloc += f":{port}"
        elif port not in (80, 443):
            netloc += f":{port}"
        target = f"{scheme}://{netloc}{path}"
        send = {"Host": host if port in (80, 443) else f"{host}:{port}", "User-Agent": "BriefPay-Verifier/1.0",
                "Accept": "*/*", "Accept-Encoding": "identity", **{k: v for k, v in headers.items() if k.lower() != "host"}}
        timeout = httpx.Timeout(remaining)
        try:
            with httpx.Client(transport=self.transport, timeout=timeout, follow_redirects=False, trust_env=False, cookies=None) as client:
                with client.stream("GET", target, headers=send, extensions={"sni_hostname": host}) as r:
                    declared = r.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > self.max_bytes:
                        raise FetchFailed("response is too large")
                    body = bytearray()
                    for chunk in r.iter_bytes():
                        body.extend(chunk)
                        if len(body) > self.max_bytes:
                            raise FetchFailed("response is too large")
                        if time.monotonic() > deadline:
                            raise FetchFailed("timed out")
                    return Fetched(url=target, status=r.status_code, headers={k.lower(): v for k, v in r.headers.items()}, body=bytes(body))
        except httpx.TimeoutException:
            raise FetchFailed("timed out") from None
        except httpx.HTTPError as e:
            raise FetchFailed(f"connection failed: {type(e).__name__}") from None
