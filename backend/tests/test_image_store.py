"""What an upload really is (image_meta), and the two image stores (local disk and Cloudinary)."""
import base64
import hashlib
import json
import time

import httpx
import pytest

from app.config import get_settings
from app.services import image_meta, image_store as ims
from app.services.image_store import CloudinaryImageStore, ImageStoreError, ImageStoreUnavailable, LocalImageStore
from app.services.safe_fetch import SafeFetcher
from tests import imgs

# =============================== image_meta ===============================

@pytest.mark.parametrize("data,expected", [
    (imgs.png(4, 3), ("png", 4, 3)), (imgs.png_header(1600, 900), ("png", 1600, 900)),
    (imgs.jpeg(40, 30), ("jpg", 40, 30)), (imgs.jpeg(1600, 1200), ("jpg", 1600, 1200)),
    (imgs.jpeg(40, 30, exif_bytes=70_000), ("jpg", 40, 30)),                     # a big EXIF block before the frame header
    (imgs.webp_lossy(64, 48), ("webp", 64, 48)), (imgs.webp_lossless(64, 48), ("webp", 64, 48)), (imgs.webp_extended(640, 480), ("webp", 640, 480)),
], ids=lambda v: f"{type(v).__name__}{len(v) if isinstance(v, bytes) else ''}")
def test_real_images_are_recognised_with_their_size(data, expected):
    info = image_meta.sniff(data)
    assert (info.format, info.width, info.height) == expected and info.mime == image_meta.MIME[expected[0]]


@pytest.mark.parametrize("data", [
    b"", b"\x00" * 100, b"GIF89a" + b"\x00" * 50, b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
    b"<html><script>alert(1)</script></html>", b"%PDF-1.4 " + b"x" * 50, b"MZ" + b"\x00" * 60, b"\xff\xd8", b"\x89PNG\r\n\x1a\n",
    imgs.png()[:20], imgs.jpeg()[:15], imgs.webp_lossy()[:20],
    imgs.png_header(0, 5), imgs.png_header(5, 0), imgs.jpeg(0, 10), imgs.jpeg(10, 0), imgs.webp_extended(1, 1)[:28],
    imgs.png_header(13_000, 10), imgs.png_header(10, 13_000), imgs.png_header(8_000, 8_000), imgs.jpeg(9_000, 9_000),            # too wide, too tall, too many pixels
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 30,                                                                      # PNG magic but no IHDR
    b"\xff\xd8\xff\xe0\x00\x10" + b"J" * 14 + b"\x00\x00\x00\x00",                                           # JPEG with no frame header
    b"\xff\xd8" + b"\x00" * 20,                                                                              # JPEG whose first marker is junk
    b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 30,                                                         # WebP without the VP8 start code
    b"RIFF\x00\x00\x00\x00WEBPXXXX" + b"\x00" * 30,
    "text, not bytes", None, 12345,
], ids=lambda v: f"{type(v).__name__}{len(v) if isinstance(v, (bytes, str)) else ''}")
def test_anything_else_is_refused(data):
    assert image_meta.sniff(data) is None


def test_a_polyglot_that_starts_like_an_image_but_is_not_one_is_still_judged_by_its_header():
    html_after_png = imgs.png()[:33] + b"<script>alert(1)</script>"
    assert image_meta.sniff(html_after_png).format == "png"     # the header is all we read; the bytes are only ever served as image/png + nosniff
    assert image_meta.sniff(b"<script>" + imgs.png()) is None


# =============================== public ids ===============================

def test_public_ids_have_one_shape_and_name_their_project():
    pid = ims.new_public_id(42)
    assert ims.PUBLIC_ID.match(pid) and ims.project_of(pid) == 42 and pid.startswith(f"briefpay/{ims.env_label()}/42/")
    assert ims.new_public_id(42) != pid


@pytest.mark.parametrize("bad", [
    "", "briefpay/dev/42/short", "briefpay/dev/42/" + "g" * 32, "briefpay/dev/42/" + "a" * 33, "briefpay/dev/4x/" + "a" * 32,
    "briefpay/dev/42/../" + "a" * 32, "../briefpay/dev/42/" + "a" * 32, "briefpay/dev/42/" + "a" * 32 + "/x", "briefpay/dev/42/" + "a" * 32 + "\n",
    "other/dev/42/" + "a" * 32, "briefpay//42/" + "a" * 32, "/briefpay/dev/42/" + "a" * 32, None,
])
def test_malformed_public_ids_belong_to_no_project(bad):
    assert ims.project_of(bad) is None


def test_a_public_id_from_another_environment_is_not_accepted(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "prod")
    pid = ims.new_public_id(7)
    monkeypatch.setattr(get_settings(), "app_env", "dev")
    assert ims.project_of(pid) is None


# =============================== local store ===============================

@pytest.fixture()
def store(tmp_path):
    return LocalImageStore(tmp_path / "imgs", secret="test-secret", base_url="http://backend.test", max_bytes=50_000)


def test_a_valid_image_is_stored_and_read_back_with_its_metadata_and_hash(store):
    pid = ims.new_public_id(1)
    data = imgs.png(20, 10)
    info = store.write(pid, data)
    assert (info.format, info.bytes, info.width, info.height, info.sha256) == ("png", len(data), 20, 10, hashlib.sha256(data).hexdigest())
    assert store.read_bytes(pid) == data and store.inspect(pid) == info


def test_nothing_is_stored_for_a_bad_upload(store, tmp_path):
    pid = ims.new_public_id(1)
    for data, code in ((b"<svg/>", "NOT_AN_IMAGE"), (b"", "NOT_AN_IMAGE"), (imgs.png(4, 3) + b"x" * 60_000, "IMAGE_TOO_LARGE")):
        with pytest.raises(ImageStoreError) as e:
            store.write(pid, data)
        assert e.value.code == code
    assert store.read_bytes(pid) is None and not list((tmp_path / "imgs").rglob("*")) or not any(p.is_file() for p in (tmp_path / "imgs").rglob("*"))


def test_an_upload_slot_can_be_used_once(store):
    pid = ims.new_public_id(1)
    store.write(pid, imgs.png())
    with pytest.raises(ImageStoreError) as e:
        store.write(pid, imgs.png(9, 9))
    assert e.value.code == "ALREADY_UPLOADED" and store.inspect(pid).width == 4


def test_inspect_says_none_for_a_missing_image_and_refuses_a_stored_non_image(store):
    pid = ims.new_public_id(1)
    assert store.inspect(pid) is None and store.read_bytes(pid) is None
    store._path(pid).parent.mkdir(parents=True)
    store._path(pid).write_bytes(b"not an image")
    with pytest.raises(ImageStoreError):
        store.inspect(pid)


@pytest.mark.parametrize("bad", ["../../etc/passwd", "briefpay/dev/1/../../x", "/etc/passwd", "", "briefpay/dev/1/" + "a" * 31 + "/"])
def test_a_crafted_id_can_never_reach_a_path_outside_the_store(store, bad):
    for call in (lambda: store.write(bad, imgs.png()), lambda: store.read_bytes(bad), lambda: store.inspect(bad), lambda: store.signed_url(bad),
                 lambda: store.upload_params(bad)):
        with pytest.raises(ImageStoreError) as e:
            call()
        assert e.value.code == "BAD_PUBLIC_ID"


def parse(url):
    from urllib.parse import parse_qs, urlsplit
    q = parse_qs(urlsplit(url).query)
    return q["public_id"][0], int(q["exp"][0]), q["sig"][0]


def test_upload_and_view_tokens_are_bound_to_the_image_and_the_purpose(store):
    pid, other = ims.new_public_id(1), ims.new_public_id(1)
    up = store.upload_params(pid)
    assert up["method"] == "PUT" and up["url"].startswith("http://backend.test/api/images/local-upload?") and up["max_bytes"] == 50_000
    p, exp, sig = parse(up["url"])
    assert p == pid and store.check_upload_token(p, exp, sig)
    assert not store.check_upload_token(other, exp, sig)                      # another image
    assert not store.check_upload_token(p, exp + 1, sig)                      # a later expiry
    assert not store.check_upload_token(p, exp, sig[:-1] + ("0" if sig[-1] != "0" else "1"))
    assert not store.check_upload_token(p, exp, "") and not store.check_view_token(p, exp, sig)    # an upload token cannot be used to view
    url, vexp = store.signed_url(pid)
    vp, vexp2, vsig = parse(url)
    assert store.check_view_token(vp, vexp2, vsig) and not store.check_upload_token(vp, vexp2, vsig) and vexp == vexp2


def test_tokens_expire(store):
    pid = ims.new_public_id(1)
    past = int(time.time()) - 1
    assert not store.check_upload_token(pid, past, ims._sign(store.secret, "upload", pid, past))
    assert not store.check_view_token(pid, past, ims._sign(store.secret, "view", pid, past))
    url, exp = store.signed_url(pid, ttl=60)
    assert 50 <= exp - time.time() <= 61


def test_tokens_made_with_another_secret_are_refused(store, tmp_path):
    other = LocalImageStore(tmp_path / "x", secret="another", base_url="http://backend.test")
    pid = ims.new_public_id(1)
    p, exp, sig = parse(other.upload_params(pid)["url"])
    assert not store.check_upload_token(p, exp, sig)


# =============================== Cloudinary ===============================

CLOUD = "cloudinary://12345:s3cr3t@democloud"
HOSTS = {"api.cloudinary.com": ["13.225.1.1"], "res.cloudinary.com": ["13.225.1.2"]}


def cloudinary(handler, **kw):
    sent = []

    def record(req):
        sent.append(req)
        return handler(req)
    fetcher = SafeFetcher(resolver=lambda h, p: HOSTS[h], transport=httpx.MockTransport(record), allowed_hosts=set(HOSTS))
    return CloudinaryImageStore(CLOUD, fetcher, **kw), sent


def asset(pid, **over):
    d = {"public_id": pid, "format": "jpg", "bytes": 12_345, "width": 800, "height": 600, "type": "authenticated"}
    d.update(over)
    return httpx.Response(200, json=d)


@pytest.mark.parametrize("url", ["", "http://12345:s@c", "cloudinary://c", "cloudinary://k@c", "cloudinary://:s@c", "cloudinary://k:s@", "https://k:s@c"])
def test_the_cloudinary_url_must_be_complete(url):
    with pytest.raises(ImageStoreError) as e:
        CloudinaryImageStore(url)
    assert e.value.code == "CLOUDINARY_NOT_CONFIGURED"


def test_the_upload_form_is_signed_for_exactly_the_fields_sent_and_never_contains_the_secret():
    s, _ = cloudinary(lambda r: asset(""))
    pid = ims.new_public_id(5)
    up = s.upload_params(pid, timestamp=1_700_000_000)
    f = up["fields"]
    assert up["method"] == "POST" and up["url"] == "https://api.cloudinary.com/v1_1/democloud/image/upload"
    assert (f["type"], f["allowed_formats"], f["public_id"], f["timestamp"], f["api_key"]) == ("authenticated", "jpg,png,webp", pid, 1_700_000_000, "12345")
    assert f["transformation"] == ims.INCOMING_TRANSFORMATION
    # the signature is sha1 of the sorted "k=v" pairs of the signed fields (not file, api_key, signature) followed by the secret
    to_sign = f"allowed_formats=jpg,png,webp&public_id={pid}&timestamp=1700000000&transformation={ims.INCOMING_TRANSFORMATION}&type=authenticated"
    assert f["signature"] == hashlib.sha1((to_sign + "s3cr3t").encode()).hexdigest()
    assert "s3cr3t" not in json.dumps(up)
    with pytest.raises(ImageStoreError):
        s.upload_params("briefpay/dev/5/../x")


def test_a_different_field_gives_a_different_signature():
    s, _ = cloudinary(lambda r: asset(""))
    a = s.upload_params(ims.new_public_id(5), timestamp=1)["fields"]["signature"]
    assert a != s.upload_params(ims.new_public_id(5), timestamp=1)["fields"]["signature"]      # public_id is signed
    pid = ims.new_public_id(5)
    assert s.upload_params(pid, timestamp=1)["fields"]["signature"] != s.upload_params(pid, timestamp=2)["fields"]["signature"]


def test_inspect_asks_the_admin_api_with_basic_auth_and_returns_the_metadata():
    pid = ims.new_public_id(5)
    s, sent = cloudinary(lambda r: asset(pid, format="jpeg"))
    info = s.inspect(pid)
    assert (info.format, info.bytes, info.width, info.height, info.sha256) == ("jpg", 12_345, 800, 600, None)
    req = sent[0]
    assert req.headers["host"] == "api.cloudinary.com" and req.url.path == f"/v1_1/democloud/resources/image/authenticated/{pid}"
    assert base64.b64decode(req.headers["authorization"].split()[1]) == b"12345:s3cr3t"


def test_inspect_none_for_a_missing_asset_and_unavailable_when_cloudinary_is_unwell():
    pid = ims.new_public_id(5)
    assert cloudinary(lambda r: httpx.Response(404, json={}))[0].inspect(pid) is None
    for status in (401, 403, 429, 500):
        with pytest.raises(ImageStoreUnavailable):
            cloudinary(lambda r, st=status: httpx.Response(st, json={}))[0].inspect(pid)
    with pytest.raises(ImageStoreUnavailable):
        cloudinary(lambda r: httpx.Response(200, text="<html>"))[0].inspect(pid)
    with pytest.raises(ImageStoreUnavailable):
        cloudinary(lambda r: httpx.Response(200, json={"public_id": pid}))[0].inspect(pid)
    def boom(r):
        raise httpx.ConnectError("down")
    with pytest.raises(ImageStoreUnavailable):
        cloudinary(boom)[0].inspect(pid)


@pytest.mark.parametrize("over", [{"format": "gif"}, {"format": "svg"}, {"type": "upload"}, {"public_id": "briefpay/dev/5/" + "b" * 32}, {"bytes": 6_000_000}])
def test_inspect_refuses_assets_that_are_not_what_we_signed_for(over):
    pid = ims.new_public_id(5)
    with pytest.raises(ImageStoreError):
        cloudinary(lambda r: asset(pid, **over), max_bytes=5_000_000)[0].inspect(pid)


def test_delivery_urls_are_signed_authenticated_and_only_for_valid_ids():
    s, _ = cloudinary(lambda r: asset(""))
    pid = ims.new_public_id(5)
    url, exp = s.signed_url(pid, "png", ttl=120)
    sig = base64.urlsafe_b64encode(hashlib.sha1((pid + ".png" + "s3cr3t").encode()).digest()).decode()[:8]
    assert url == f"https://res.cloudinary.com/democloud/image/authenticated/s--{sig}--/{pid}.png" and 100 <= exp - time.time() <= 121
    for bad in ("../x", "briefpay/dev/5/x"):
        with pytest.raises(ImageStoreError):
            s.signed_url(bad)
    with pytest.raises(ImageStoreError):
        s.signed_url(pid, "gif")


def test_read_bytes_fetches_the_signed_url_from_the_delivery_host_only():
    pid = ims.new_public_id(5)
    s, sent = cloudinary(lambda r: httpx.Response(200, content=imgs.png()))
    assert s.read_bytes(pid, "png") == imgs.png() and sent[0].headers["host"] == "res.cloudinary.com"
    assert cloudinary(lambda r: httpx.Response(404))[0].read_bytes(pid) is None
    with pytest.raises(ImageStoreUnavailable):
        cloudinary(lambda r: httpx.Response(502))[0].read_bytes(pid)


def test_the_cloudinary_fetcher_cannot_be_used_to_reach_anything_else():
    from app.services.safe_fetch import FetchBlocked
    s, sent = cloudinary(lambda r: httpx.Response(200))
    with pytest.raises(FetchBlocked):
        s.fetcher.get("https://evil.example/x")
    assert sent == []


def test_the_factory_picks_the_store_from_settings(monkeypatch, tmp_path):
    ims.configure(None)
    monkeypatch.setattr(get_settings(), "image_provider", "local")
    assert isinstance(ims.get_image_store(), LocalImageStore)
    monkeypatch.setattr(get_settings(), "image_provider", "cloudinary")
    monkeypatch.setattr(get_settings(), "cloudinary_url", CLOUD)
    assert isinstance(ims.get_image_store(), CloudinaryImageStore)
    sentinel = object()
    ims.configure(sentinel)
    assert ims.get_image_store() is sentinel
    ims.configure(None)


# ---- gaps found by the mutation check ----

def test_png_needs_the_whole_signature_and_an_ihdr_chunk():
    good = imgs.png(4, 3)
    assert image_meta.sniff(good) is not None
    assert image_meta.sniff(b"\x89PNG" + b"\x00\x00\x00\x00" + good[8:]) is None            # only the first four signature bytes right
    assert image_meta.sniff(good[:12] + b"IDAT" + good[16:]) is None                         # the first chunk is not IHDR


def test_jpeg_markers_without_a_length_and_non_frame_markers_are_skipped_correctly():
    import struct
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, 30, 40, 1) + b"\x01\x11\x00"
    rst = b"\xff\xd8" + b"\xff\xd0" + b"\xff\xd3" + sof                                      # restart markers carry no length
    assert image_meta.sniff(rst).width == 40
    dht = b"\xff\xc4" + struct.pack(">H", 20) + b"\x00" * 18                                  # a Huffman table is not a frame header
    assert image_meta.sniff(b"\xff\xd8" + dht + sof).width == 40
    dac = b"\xff\xcc" + struct.pack(">H", 4) + b"\x00\x00"
    jpg = b"\xff\xc8" + struct.pack(">H", 4) + b"\x00\x00"
    assert image_meta.sniff(b"\xff\xd8" + dac + sof).width == 40 and image_meta.sniff(b"\xff\xd8" + jpg + sof).width == 40


def test_webp_needs_riff_and_the_vp8_start_code():
    good = imgs.webp_lossy(64, 48)
    assert image_meta.sniff(b"XXXX" + good[4:]) is None
    assert image_meta.sniff(good[:23] + b"\x00\x00\x00" + good[26:]) is None
    assert image_meta.sniff(imgs.webp_lossless()[:20] + b"\x00" + imgs.webp_lossless()[21:]) is None      # VP8L without its signature byte


def test_the_signature_covers_every_field_whatever_order_they_arrive_in():
    s, _ = cloudinary(lambda r: asset(""))
    a = s._signature({"b": 2, "a": 1, "c": 3})
    assert a == s._signature({"c": 3, "a": 1, "b": 2}) == hashlib.sha1(("a=1&b=2&c=3" + "s3cr3t").encode()).hexdigest()


def test_the_default_cloudinary_fetcher_is_locked_to_cloudinary_hosts():
    s = CloudinaryImageStore(CLOUD)
    assert s.fetcher.allowed_hosts == {"api.cloudinary.com", "res.cloudinary.com"}
