"""Where evidence screenshots live (SPEC 2, 12): an `ImageStore` with a local-disk and a Cloudinary implementation.

The database holds only metadata. Pixels live on disk (dev, tests) or in Cloudinary (prod, delivery type `authenticated`).
Every public id is generated here, in one shape, and parsed back with one strict pattern, so a caller can never reach a
path or an asset outside `briefpay/{env}/{project_id}/`.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit

from app.config import get_settings
from app.services import image_meta
from app.services.safe_fetch import FetchBlocked, FetchFailed, SafeFetcher

ALLOWED_FORMATS = ("jpg", "png", "webp")
UPLOAD_SECONDS = 600
PUBLIC_ID = re.compile(r"^briefpay/([a-z0-9]{1,12})/(\d{1,12})/([0-9a-f]{32})\Z")
INCOMING_TRANSFORMATION = "c_limit,w_1600,h_1600/fl_strip_profile"


class ImageStoreError(Exception):
    """The store refused something (bad file, too big, wrong folder)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class ImageStoreUnavailable(Exception):
    """The store could not be asked right now (network, provider down)."""


@dataclass(frozen=True)
class AssetInfo:
    format: str
    bytes: int
    width: int
    height: int
    sha256: str | None = None


def env_label() -> str:
    return re.sub(r"[^a-z0-9]", "", get_settings().app_env.lower())[:12] or "dev"


def new_public_id(project_id: int) -> str:
    return f"briefpay/{env_label()}/{int(project_id)}/{secrets.token_hex(16)}"


def project_of(public_id: str) -> int | None:
    """The project a public id belongs to, only if it has exactly the shape this deployment generates."""
    m = PUBLIC_ID.match(public_id or "")
    return int(m.group(2)) if m and m.group(1) == env_label() else None


def _sign(secret: str, *parts) -> str:
    return hmac.new(secret.encode(), "|".join(str(p) for p in parts).encode(), hashlib.sha256).hexdigest()


def _check(info: AssetInfo | None, max_bytes: int) -> AssetInfo:
    if info is None:
        raise ImageStoreError("NOT_AN_IMAGE", "That file is not a JPEG, PNG or WebP image")
    if info.bytes > max_bytes:
        raise ImageStoreError("IMAGE_TOO_LARGE", f"Images can be at most {max_bytes // 1_000_000} MB")
    return info


# =============================== local disk ===============================

class LocalImageStore:
    provider = "LOCAL"

    def __init__(self, root: str | Path | None = None, secret: str | None = None, base_url: str | None = None, max_bytes: int | None = None):
        s = get_settings()
        self.root = Path(root or s.local_images_dir)
        self.secret, self.base_url = secret or s.jwt_secret, (base_url or s.app_base_url).rstrip("/")
        self.max_bytes = max_bytes or s.image_max_bytes

    def _path(self, public_id: str) -> Path:
        m = PUBLIC_ID.match(public_id or "")
        if not m:
            raise ImageStoreError("BAD_PUBLIC_ID", "Not a valid image id")
        return self.root / m.group(1) / m.group(2) / f"{m.group(3)}.img"

    # ---- upload ----
    def upload_params(self, public_id: str) -> dict:
        self._path(public_id)
        exp = int(time.time()) + UPLOAD_SECONDS
        sig = _sign(self.secret, "upload", public_id, exp)
        return {"method": "PUT", "url": f"{self.base_url}/api/images/local-upload?public_id={quote(public_id, safe='')}&exp={exp}&sig={sig}",
                "headers": {"Content-Type": "application/octet-stream"}, "max_bytes": self.max_bytes, "expires_in": UPLOAD_SECONDS}

    def check_upload_token(self, public_id: str, exp: int, sig: str) -> bool:
        return exp >= time.time() and hmac.compare_digest(sig or "", _sign(self.secret, "upload", public_id, exp))

    def write(self, public_id: str, data: bytes) -> AssetInfo:
        path = self._path(public_id)
        if len(data) > self.max_bytes:
            raise ImageStoreError("IMAGE_TOO_LARGE", f"Images can be at most {self.max_bytes // 1_000_000} MB")
        info = image_meta.sniff(data)
        _check(AssetInfo(info.format, len(data), info.width, info.height) if info else None, self.max_bytes)
        if path.exists():
            raise ImageStoreError("ALREADY_UPLOADED", "This upload slot was already used")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{secrets.token_hex(4)}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return AssetInfo(info.format, len(data), info.width, info.height, hashlib.sha256(data).hexdigest())

    # ---- read ----
    def read_bytes(self, public_id: str) -> bytes | None:
        path = self._path(public_id)
        return path.read_bytes() if path.is_file() else None

    def inspect(self, public_id: str) -> AssetInfo | None:
        data = self.read_bytes(public_id)
        if data is None:
            return None
        info = image_meta.sniff(data)
        return _check(AssetInfo(info.format, len(data), info.width, info.height, hashlib.sha256(data).hexdigest()) if info else None, self.max_bytes)

    def signed_url(self, public_id: str, ttl: int | None = None) -> tuple[str, int]:
        self._path(public_id)
        exp = int(time.time()) + (ttl or get_settings().image_url_ttl_seconds)
        return f"{self.base_url}/api/images/local/file?public_id={quote(public_id, safe='')}&exp={exp}&sig={_sign(self.secret, 'view', public_id, exp)}", exp

    def check_view_token(self, public_id: str, exp: int, sig: str) -> bool:
        return exp >= time.time() and hmac.compare_digest(sig or "", _sign(self.secret, "view", public_id, exp))


# =============================== Cloudinary ===============================

class CloudinaryImageStore:
    """Signed direct browser upload; the API secret never leaves the backend (SPEC 13).

    NOT YET RUN AGAINST A REAL ACCOUNT (GAP-60): the signing recipes follow Cloudinary's documentation and are tested against
    fixed vectors and a scripted API, but must be proven with `scripts/sandbox_check.py` once an account exists.
    """
    provider = "CLOUDINARY"
    API = "https://api.cloudinary.com"
    DELIVERY = "https://res.cloudinary.com"

    def __init__(self, cloudinary_url: str | None = None, fetcher: SafeFetcher | None = None, max_bytes: int | None = None):
        url = cloudinary_url if cloudinary_url is not None else get_settings().cloudinary_url
        parts = urlsplit(url)
        if parts.scheme != "cloudinary" or not (parts.username and parts.password and parts.hostname):
            raise ImageStoreError("CLOUDINARY_NOT_CONFIGURED", "CLOUDINARY_URL must look like cloudinary://key:secret@cloud_name")
        self.key, self.secret, self.cloud = parts.username, parts.password, parts.hostname
        self.fetcher = fetcher or SafeFetcher(allowed_hosts={"api.cloudinary.com", "res.cloudinary.com"})
        self.max_bytes = max_bytes or get_settings().image_max_bytes

    def _signature(self, params: dict) -> str:
        to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params))
        return hashlib.sha1((to_sign + self.secret).encode()).hexdigest()

    def upload_params(self, public_id: str, *, timestamp: int | None = None) -> dict:
        if not PUBLIC_ID.match(public_id or ""):
            raise ImageStoreError("BAD_PUBLIC_ID", "Not a valid image id")
        signed = {"allowed_formats": ",".join(ALLOWED_FORMATS), "public_id": public_id, "timestamp": int(timestamp or time.time()),
                  "transformation": INCOMING_TRANSFORMATION, "type": "authenticated"}
        return {"method": "POST", "url": f"{self.API}/v1_1/{self.cloud}/image/upload",
                "fields": {**signed, "api_key": self.key, "signature": self._signature(signed)},
                "max_bytes": self.max_bytes, "expires_in": UPLOAD_SECONDS}

    def _basic(self) -> dict:
        return {"Authorization": "Basic " + base64.b64encode(f"{self.key}:{self.secret}".encode()).decode()}

    def inspect(self, public_id: str) -> AssetInfo | None:
        if not PUBLIC_ID.match(public_id or ""):
            raise ImageStoreError("BAD_PUBLIC_ID", "Not a valid image id")
        try:
            r = self.fetcher.get(f"{self.API}/v1_1/{self.cloud}/resources/image/authenticated/{quote(public_id, safe='/')}", self._basic())
        except (FetchBlocked, FetchFailed) as e:
            raise ImageStoreUnavailable(str(e)) from e
        if r.status == 404:
            return None
        if r.status != 200:
            raise ImageStoreUnavailable(f"Cloudinary answered {r.status}")
        try:
            d = json.loads(r.text)
            info = AssetInfo(str(d["format"]).lower().replace("jpeg", "jpg"), int(d["bytes"]), int(d["width"]), int(d["height"]))
            ok = d.get("public_id") == public_id and d.get("type") == "authenticated"
        except (ValueError, KeyError, TypeError):
            raise ImageStoreUnavailable("Cloudinary sent something unreadable") from None
        if not ok or info.format not in ALLOWED_FORMATS:
            raise ImageStoreError("NOT_AN_IMAGE", "That asset is not an acceptable image")
        return _check(info, self.max_bytes)

    def signed_url(self, public_id: str, fmt: str = "jpg", ttl: int | None = None) -> tuple[str, int]:
        """Signed delivery URL for an authenticated asset. Cloudinary signs `public_id.format` with the secret (first 8 chars of base64url(sha1))."""
        if not PUBLIC_ID.match(public_id or "") or fmt not in ALLOWED_FORMATS:
            raise ImageStoreError("BAD_PUBLIC_ID", "Not a valid image id")
        path = f"{public_id}.{fmt}"
        sig = base64.urlsafe_b64encode(hashlib.sha1((path + self.secret).encode()).digest()).decode()[:8]
        return f"{self.DELIVERY}/{self.cloud}/image/authenticated/s--{sig}--/{path}", int(time.time()) + (ttl or get_settings().image_url_ttl_seconds)

    def read_bytes(self, public_id: str, fmt: str = "jpg") -> bytes | None:
        url, _ = self.signed_url(public_id, fmt)
        try:
            r = self.fetcher.get(url)
        except (FetchBlocked, FetchFailed) as e:
            raise ImageStoreUnavailable(str(e)) from e
        if r.status == 404:
            return None
        if r.status != 200:
            raise ImageStoreUnavailable(f"Cloudinary answered {r.status}")
        return r.body


_store = None


def get_image_store():
    """The store for this deployment. Tests install their own with `configure`."""
    global _store
    if _store is not None:
        return _store
    if get_settings().image_provider.lower() == "cloudinary":
        return CloudinaryImageStore()
    return LocalImageStore()


def configure(store) -> None:
    global _store
    _store = store
