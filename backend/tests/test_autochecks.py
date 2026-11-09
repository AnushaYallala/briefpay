"""SSRF-safe fetcher and the automatic checks (T-32). No test touches the network: httpx.MockTransport plays the internet."""
import base64
import json

import httpx
import pytest

from app.services import autochecks as ac
from app.services.safe_fetch import MAX_BYTES, FetchBlocked, FetchFailed, SafeFetcher, is_public

PUBLIC = "93.184.216.34"
HOSTS = {"site.example": [PUBLIC], "other.example": ["93.184.216.35"], "api.github.com": ["140.82.112.5"]}


def resolver(host, port):
    if host not in HOSTS:
        raise OSError("no such host")
    return HOSTS[host]


class Net:
    """A scripted internet: handler(request) -> httpx.Response. Remembers every request that was really sent."""

    def __init__(self, handler):
        self.handler, self.sent = handler, []

    def __call__(self, request):
        self.sent.append(request)
        return self.handler(request)


def fetcher(handler, **kw):
    net = Net(handler)
    return SafeFetcher(resolver=kw.pop("resolver", resolver), transport=httpx.MockTransport(net), **kw), net


def ok(body="<html>hi</html>", status=200, **headers):
    return lambda req: httpx.Response(status, text=body, headers=headers)


# =============================== which addresses count as public ===============================

@pytest.mark.parametrize("address", ["8.8.8.8", "93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"])
def test_public_addresses_are_allowed(address):
    assert is_public(address)


@pytest.mark.parametrize("address", [
    "127.0.0.1", "127.1.2.3", "10.0.0.5", "172.16.0.1", "172.31.255.255", "192.168.1.1", "169.254.169.254", "100.64.0.1",
    "0.0.0.0", "224.0.0.1", "255.255.255.255", "192.0.2.1", "198.18.0.1",
    "::1", "::", "fe80::1", "fc00::1", "fd12:3456::1", "ff02::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254",
    "2002:7f00:1::", "2001:0:4136:e378:8000:63bf:3fff:fdd2", "not an address", "",
])
def test_private_loopback_link_local_and_disguised_addresses_are_refused(address):
    assert not is_public(address)


# =============================== URL rules ===============================

@pytest.mark.parametrize("url", [
    "http://site.example/", "ftp://site.example/", "file:///etc/passwd", "gopher://site.example/", "javascript:alert(1)",
    "https://user:pw@site.example/", "https://user@site.example/", "https://site.example:8443/", "https://site.example:80/",
    "https://localhost/", "https://127.0.0.1/", "http://localhost:8000/", "https://[::1]/", "https:///nohost", "//site.example/",
    "https://site.example/ with space", "https://site.example/\r\nX: y", "https://site.example/\x00", "", "   ", "https://",
])
def test_these_urls_are_never_contacted(url):
    f, net = fetcher(ok())
    with pytest.raises((FetchBlocked, FetchFailed)):
        f.get(url)
    assert net.sent == []


def test_a_name_that_resolves_to_a_private_address_is_never_contacted():
    HOSTS["evil.example"] = ["10.0.0.7"]
    HOSTS["mixed.example"] = [PUBLIC, "169.254.169.254"]
    HOSTS["v6.example"] = ["::ffff:192.168.0.1"]
    try:
        for host in ("evil.example", "mixed.example", "v6.example"):
            f, net = fetcher(ok())
            with pytest.raises(FetchBlocked):
                f.get(f"https://{host}/")
            assert net.sent == []
    finally:
        for host in ("evil.example", "mixed.example", "v6.example"):
            HOSTS.pop(host, None)


def test_an_ip_literal_to_a_private_address_is_refused_and_a_public_one_is_allowed():
    f, net = fetcher(ok(), resolver=lambda h, p: [h])
    for bad in ("https://10.1.1.1/", "https://169.254.169.254/latest/meta-data/", "https://[fe80::1]/", "https://2130706433/", "https://0x7f.1/"):
        with pytest.raises((FetchBlocked, FetchFailed, OSError)):
            f.get(bad)
    assert net.sent == []
    assert f.get("https://93.184.216.34/").status == 200


def test_an_unresolvable_name_is_a_failure_not_a_block():
    f, _ = fetcher(ok())
    with pytest.raises(FetchFailed):
        f.get("https://nowhere.example/")


def test_localhost_is_allowed_only_when_dev_mode_says_so():
    f, net = fetcher(ok(), allow_local=True)
    assert f.get("http://localhost:3000/x").status == 200 and f.get("http://127.0.0.1:8080/").status == 200
    assert len(net.sent) == 2
    with pytest.raises(FetchBlocked):
        f.get("http://169.254.169.254/")        # dev mode opens localhost only, not the private ranges
    with pytest.raises(FetchBlocked):
        f.get("http://10.0.0.1/")


def test_the_host_allow_list_blocks_other_hosts():
    f, net = fetcher(ok(), allowed_hosts={"api.github.com"})
    assert f.get("https://api.github.com/x").status == 200
    with pytest.raises(FetchBlocked):
        f.get("https://site.example/")
    assert len(net.sent) == 1


# =============================== connection is pinned to the checked address ===============================

def test_the_request_goes_to_the_resolved_address_with_the_real_host_name():
    f, net = fetcher(ok())
    f.get("https://site.example/a/b?x=1")
    req = net.sent[0]
    assert req.url.host == PUBLIC and req.url.path == "/a/b" and req.url.query == b"x=1"
    assert req.headers["host"] == "site.example"
    assert req.extensions["sni_hostname"] == "site.example"
    assert "cookie" not in req.headers


def test_a_second_dns_answer_cannot_change_where_the_request_goes():
    answers = iter([[PUBLIC], ["10.0.0.9"]])
    f, net = fetcher(ok(), resolver=lambda h, p: next(answers))
    f.get("https://site.example/")
    assert net.sent[0].url.host == PUBLIC       # we asked DNS once and used that answer


def test_cookies_set_by_a_site_are_not_sent_back():
    def handler(req):
        return httpx.Response(200, text="x", headers={"set-cookie": "s=1"}) if not req.headers.get("cookie") else httpx.Response(500)
    f, net = fetcher(handler)
    f.get("https://site.example/")
    f.get("https://site.example/")
    assert all("cookie" not in r.headers for r in net.sent)


# =============================== redirects ===============================

def redirect_to(location, status=302):
    return lambda req: httpx.Response(status, headers={"location": location})


def test_redirects_are_followed_and_each_one_is_rechecked():
    pages = {"/a": redirect_to("/b")(None), "/b": redirect_to("https://other.example/c")(None)}
    f, net = fetcher(lambda req: pages.get(req.url.path) or httpx.Response(200, text="end"))
    r = f.get("https://site.example/a")
    assert r.status == 200 and r.text == "end" and len(r.redirects) == 2 and len(net.sent) == 3
    assert net.sent[2].headers["host"] == "other.example"


@pytest.mark.parametrize("target", [
    "http://site.example/", "https://169.254.169.254/latest/meta-data/", "https://127.0.0.1/", "http://localhost/", "file:///etc/passwd",
    "https://user:pw@site.example/", "https://site.example:6379/", "https://[::1]/",
])
def test_a_redirect_into_a_forbidden_place_is_refused_before_it_is_followed(target):
    f, net = fetcher(redirect_to(target))
    with pytest.raises((FetchBlocked, FetchFailed)):
        f.get("https://site.example/")
    assert len(net.sent) == 1


def test_a_redirect_to_a_name_that_resolves_privately_is_refused():
    HOSTS["inside.example"] = ["192.168.0.10"]
    try:
        f, net = fetcher(redirect_to("https://inside.example/admin"))
        with pytest.raises(FetchBlocked):
            f.get("https://site.example/")
        assert len(net.sent) == 1
    finally:
        HOSTS.pop("inside.example")


def test_more_than_three_redirects_fail():
    f, net = fetcher(redirect_to("/again"))
    with pytest.raises(FetchFailed, match="redirects"):
        f.get("https://site.example/")
    assert len(net.sent) == 4          # the first request plus three redirects, then stop


def test_exactly_three_redirects_are_fine():
    n = [0]

    def handler(req):
        n[0] += 1
        return httpx.Response(302, headers={"location": "/next"}) if n[0] <= 3 else httpx.Response(200, text="done")
    f, _ = fetcher(handler)
    assert f.get("https://site.example/").text == "done"


def test_a_redirect_without_a_location_is_just_a_response():
    f, _ = fetcher(lambda req: httpx.Response(302))
    assert f.get("https://site.example/").status == 302


def test_headers_for_one_host_are_not_sent_to_another_after_a_redirect():
    def handler(req):
        return httpx.Response(302, headers={"location": "https://other.example/x"}) if req.headers["host"] == "site.example" else httpx.Response(200)
    f, net = fetcher(handler)
    f.get("https://site.example/", {"Authorization": "Bearer secret"})
    assert net.sent[0].headers["authorization"] == "Bearer secret"
    assert "authorization" not in net.sent[1].headers


# =============================== limits ===============================

def test_a_body_over_the_cap_is_refused_even_without_a_content_length():
    f, _ = fetcher(lambda req: httpx.Response(200, content=b"x" * (MAX_BYTES + 1)))
    with pytest.raises(FetchFailed, match="large"):
        f.get("https://site.example/")


def chunks(total, size=100_000):
    def gen():
        sent = 0
        while sent < total:
            n = min(size, total - sent)
            sent += n
            yield b"x" * n
    return gen()


def test_a_streamed_body_with_no_length_is_cut_off_at_the_cap():
    f, _ = fetcher(lambda req: httpx.Response(200, content=chunks(MAX_BYTES * 3)))
    with pytest.raises(FetchFailed, match="large"):
        f.get("https://site.example/")
    f, _ = fetcher(lambda req: httpx.Response(200, content=chunks(MAX_BYTES)))
    assert len(f.get("https://site.example/").body) == MAX_BYTES


def test_a_relative_redirect_stays_on_the_host_that_sent_it():
    def handler(req):
        if req.headers["host"] == "site.example":
            return httpx.Response(302, headers={"location": "https://other.example/start"})
        if req.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, text="ok")
    f, net = fetcher(handler)
    r = f.get("https://site.example/")
    assert r.status == 200 and net.sent[2].headers["host"] == "other.example" and net.sent[2].url.path == "/final"


def test_a_body_exactly_at_the_cap_is_accepted():
    f, _ = fetcher(lambda req: httpx.Response(200, content=b"x" * MAX_BYTES))
    assert len(f.get("https://site.example/").body) == MAX_BYTES


def test_a_huge_declared_length_is_refused_up_front():
    f, _ = fetcher(lambda req: httpx.Response(200, content=b"x", headers={"content-length": str(MAX_BYTES * 50)}))
    with pytest.raises(FetchFailed, match="large"):
        f.get("https://site.example/")


def test_timeouts_and_connection_errors_are_failures_not_crashes():
    def boom(exc):
        def handler(req):
            raise exc
        return handler
    for exc in (httpx.ConnectTimeout("t"), httpx.ReadTimeout("t"), httpx.ConnectError("c"), httpx.RemoteProtocolError("p")):
        f, _ = fetcher(boom(exc))
        with pytest.raises(FetchFailed):
            f.get("https://site.example/")


def test_the_overall_deadline_is_respected():
    f, net = fetcher(ok(), timeout=0)
    with pytest.raises(FetchFailed, match="timed out"):
        f.get("https://site.example/")
    assert net.sent == []                      # an expired deadline sends nothing at all


# =============================== website checks ===============================

def site(pages):
    def handler(req):
        body = pages.get(req.url.path)
        return httpx.Response(404, text="nope") if body is None else httpx.Response(200, text=body)
    f, net = fetcher(handler)
    return ac.AutoChecker(f), net


def test_url_reachable_passes_on_2xx_fails_on_404_and_errors_when_unreachable():
    c, _ = site({"/": "x", "/stay": "y"})
    assert c.url_reachable("https://site.example", "/stay").result == "PASS"
    r = c.url_reachable("https://site.example", "/missing")
    assert (r.result, r.detail["status"]) == ("FAIL", 404)
    gone = ac.AutoChecker(fetcher(ok(), resolver=lambda h, p: (_ for _ in ()).throw(OSError()))[0])
    assert gone.url_reachable("https://site.example").result == "ERROR"


def test_url_reachable_treats_a_blocked_url_as_an_error_with_a_reason():
    c, net = site({})
    r = c.url_reachable("http://site.example")
    assert r.result == "ERROR" and "https" in r.detail["error"] and net.sent == []


def test_a_page_path_cannot_point_somewhere_else():
    c, net = site({"/": "x"})
    for path in ("//evil.example/x", "https://evil.example/", "\\\\evil.example", "stay"):
        assert c.url_reachable("https://site.example", path).result == "ERROR"
    assert net.sent == []
    assert ac.join_site("https://site.example/deep/path?q=1", "/stay") == "https://site.example/stay"


def test_page_contains_reads_visible_text_ignoring_case_spacing_and_markup():
    html = "<html><head><title>T</title><script>var secret='Sea Breeze'</script></head><body><h1>Sea\n  <b>Breeze</b> Homestay</h1></body></html>"
    c, _ = site({"/stay": html})
    assert c.page_contains("https://site.example", "/stay", "sea breeze HOMESTAY").result == "PASS"
    # text that exists only inside a script or a comment is not on the page
    html2 = "<body><script>Sea Breeze</script><style>.a{content:'Sea Breeze'}</style><!-- Sea Breeze --></body>"
    c2, _ = site({"/stay": html2})
    assert c2.page_contains("https://site.example", "/stay", "Sea Breeze").result == "FAIL"


def test_page_contains_fails_on_a_missing_page_and_on_empty_search_text():
    c, _ = site({"/stay": "Sea Breeze"})
    assert c.page_contains("https://site.example", "/nope", "Sea Breeze").detail["status"] == 404
    assert c.page_contains("https://site.example", "/stay", "   ").result == "FAIL"
    assert c.page_contains("https://site.example", "/stay", "Mountain View").result == "FAIL"


def test_page_contains_survives_broken_html():
    c, _ = site({"/": "<div><p>Hello <b>World</div></p><<>>&amp; Sea &#38; Sky"})
    assert c.page_contains("https://site.example", "/", "Hello World").result == "PASS"
    assert c.page_contains("https://site.example", "/", "sea & sky").result == "PASS"


@pytest.mark.parametrize("meta,expected", [
    ('<meta name="viewport" content="width=device-width, initial-scale=1">', "PASS"),
    ("<meta name='viewport' content='width = device-width,initial-scale=1'>", "PASS"),
    ('<META NAME="viewport" CONTENT="width=device-width">', "PASS"),
    ('<meta name="viewport" content="width=1024">', "FAIL"),
    ('<meta name="description" content="width=device-width">', "FAIL"),
    ("", "FAIL"),
])
def test_mobile_viewport(meta, expected):
    c, _ = site({"/": f"<html><head>{meta}</head></html>"})
    assert c.mobile_viewport("https://site.example").result == expected


# =============================== GitHub checks ===============================

SHA40 = "a" * 40


def github(routes):
    """routes: {path: (status, json)}; records requests."""
    def handler(req):
        key = req.url.path + (f"?{req.url.query.decode()}" if req.url.query else "")
        hit = routes.get(key)
        if hit is None:
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(hit[0], json=hit[1])
    f, net = fetcher(handler)
    return ac.AutoChecker(f), net


def test_repo_url_parsing_is_strict():
    assert ac.parse_repo("https://github.com/anu/velugu-cove") == ("anu", "velugu-cove")
    assert ac.parse_repo("https://github.com/anu/velugu.cove.git/") == ("anu", "velugu.cove")
    for bad in ("http://github.com/a/b", "https://gitlab.com/a/b", "https://github.com/a", "https://github.com/a/b/tree/main",
                "https://github.com.evil.example/a/b", "https://github.com/a/b?x=1", "https://user@github.com/a/b", "https://github.com/../b",
                "https://github.com/a/b c", "", None):
        assert ac.parse_repo(bad) is None


def test_repo_public():
    c, net = github({"/repos/anu/site": (200, {"private": False})})
    assert c.repo_public("https://github.com/anu/site").result == "PASS"
    assert net.sent[0].headers["host"] == "api.github.com"
    assert c.repo_public("https://github.com/anu/gone").result == "FAIL"
    private, _ = github({"/repos/anu/site": (200, {"private": True})})
    assert private.repo_public("https://github.com/anu/site").result == "FAIL"
    assert private.repo_public("https://evil.example/anu/site").result == "FAIL"
    odd, _ = github({"/repos/anu/site": (200, {"name": "site"})})        # no "private" field: do not guess
    assert odd.repo_public("https://github.com/anu/site").result == "FAIL"


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_github_trouble_is_an_error_never_a_verdict(status):
    c, _ = github({"/repos/anu/site": (status, {"message": "rate limit"})})
    assert c.repo_public("https://github.com/anu/site").result == "ERROR"


def test_unreadable_github_reply_is_an_error():
    f, _ = fetcher(lambda req: httpx.Response(200, text="<html>not json</html>"))
    assert ac.AutoChecker(f).repo_public("https://github.com/anu/site").result == "ERROR"


def test_commit_exists_needs_the_same_commit_back():
    c, _ = github({f"/repos/anu/site/commits/{SHA40}": (200, {"sha": SHA40})})
    assert c.commit_exists("https://github.com/anu/site", SHA40).result == "PASS"
    assert c.commit_exists("https://github.com/anu/site", SHA40.upper()).result == "PASS"
    assert c.commit_exists("https://github.com/anu/site", "b" * 40).result == "FAIL"
    short, _ = github({"/repos/anu/site/commits/aaaaaaa": (200, {"sha": SHA40})})
    assert short.commit_exists("https://github.com/anu/site", "aaaaaaa").result == "PASS"
    liar, _ = github({f"/repos/anu/site/commits/{SHA40}": (200, {"sha": "c" * 40})})
    assert liar.commit_exists("https://github.com/anu/site", SHA40).result == "FAIL"
    for bad in ("", "main", "../../x", "zzzzzzz", "abc", SHA40 + "a"):
        r = c.commit_exists("https://github.com/anu/site", bad)
        assert r.result == "FAIL"


def content(text, kind="file"):
    return (200, {"type": kind, "size": len(text), "encoding": "base64", "content": base64.encodebytes(text.encode()).decode()})


def test_file_exists_returns_the_file_text_for_the_snippet_check():
    code = "function send() {\n  fetch('/enquiry', {method:'POST'})\n}\n"
    c, net = github({f"/repos/anu/site/contents/src/form.js?ref={SHA40}": content(code)})
    r, text = c.file_at_commit("https://github.com/anu/site", SHA40, "/src/form.js")
    assert r.result == "PASS" and text == code
    assert net.sent[0].url.path == "/repos/anu/site/contents/src/form.js"
    assert ac.snippet_in_file("function send() { fetch('/enquiry', {method:'POST'}) }", text)
    assert not ac.snippet_in_file("fetch('/other')", text)
    assert not ac.snippet_in_file("   ", text)


def test_file_exists_fails_for_missing_files_and_directories():
    c, _ = github({f"/repos/anu/site/contents/src?ref={SHA40}": (200, [{"type": "file"}]),
                   f"/repos/anu/site/contents/link?ref={SHA40}": content("x", kind="symlink")})
    assert c.file_at_commit("https://github.com/anu/site", SHA40, "src")[0].result == "FAIL"
    assert c.file_at_commit("https://github.com/anu/site", SHA40, "link")[0].result == "FAIL"
    assert c.file_at_commit("https://github.com/anu/site", SHA40, "nope.js")[0].result == "FAIL"


@pytest.mark.parametrize("path", ["../secret", "a/../../b", "./x", "a/./b", "a?ref=main", "a#b", "a%2e%2e/b", "", "x" * 300, "a\\b", "a\nb"])
def test_file_paths_cannot_escape_or_inject(path):
    c, net = github({})
    r, text = c.file_at_commit("https://github.com/anu/site", SHA40, path)
    assert r.result == "FAIL" and text is None and net.sent == []


def test_a_github_token_goes_only_to_github_and_is_never_logged_in_results():
    c, net = github({"/repos/anu/site": (200, {"private": False})})
    c.token = "ghp_secret"
    r = c.repo_public("https://github.com/anu/site")
    assert net.sent[0].headers["authorization"] == "Bearer ghp_secret"
    assert "ghp_secret" not in json.dumps(r.__dict__)


def test_the_github_client_cannot_be_pointed_at_another_host():
    c, net = github({})
    with pytest.raises(FetchBlocked):
        c.github.get("https://site.example/repos/x/y")
    assert net.sent == []


@pytest.mark.parametrize("sha", [SHA40 + "\n", "abcdef1\n", "\nabcdef1"])
def test_a_commit_id_with_a_stray_newline_is_not_accepted(sha):
    assert not ac.SHA.match(sha)


def test_a_repo_url_or_path_with_a_trailing_newline_is_not_accepted():
    assert ac.parse_repo("https://github.com/anu/si\nte") is None and ac.parse_repo("https://github.com/anu/site\n/x") is None
    assert ac.parse_repo("  https://github.com/anu/site\n") == ("anu", "site")      # surrounding whitespace is trimmed, never kept
    assert not ac.PATH_OK.match("src/form.js\n")
    from app.schemas.brd import PATH_PATTERN
    assert not PATH_PATTERN.match("/stay\n") and PATH_PATTERN.match("/stay")
