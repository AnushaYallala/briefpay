"""Image endpoints (SPEC 10): signed upload, register an uploaded asset, short-lived signed view URL.

  POST /images/upload-signature   member   -> where and how to upload (a signed Cloudinary form, or a signed local PUT url)
  PUT  /images/local-upload       signed   -> LOCAL provider only: receives the bytes
  POST /images                    member   -> verify the asset really is an acceptable image in this project's folder, save metadata
  GET  /images/{id}/url           member   -> signed delivery URL that expires
  GET  /images/local/file         signed   -> LOCAL provider only: serves the bytes for a signed URL
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import api_error, current_user, require_member
from app.db import get_db
from app.models import Image, Project, User
from app.services import image_meta, image_store as store_mod
from app.services.image_store import ImageStoreError, ImageStoreUnavailable

router = APIRouter()


class SignatureIn(BaseModel):
    project_id: int
    purpose: Literal["EVIDENCE"] = "EVIDENCE"


class RegisterIn(BaseModel):
    project_id: int
    public_id: str = Field(max_length=200)


def _store():
    return store_mod.get_image_store()


def _local():
    s = _store()
    if not isinstance(s, store_mod.LocalImageStore):
        raise api_error(404, "NOT_FOUND", "Not available with this image provider")
    return s


def _fail(e: ImageStoreError):
    raise api_error(422, e.code, e.message) from e


def _unavailable(e: ImageStoreUnavailable):
    raise api_error(503, "IMAGES_UNAVAILABLE", "The image service could not be reached; try again shortly") from e


@router.post("/images/upload-signature")
def upload_signature(body: SignatureIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if db.get(Project, body.project_id) is None:
        raise api_error(404, "PROJECT_NOT_FOUND", "No such project")
    require_member(db, body.project_id, user)
    public_id = store_mod.new_public_id(body.project_id)
    try:
        upload = _store().upload_params(public_id)
    except ImageStoreError as e:
        raise api_error(503, e.code, e.message) from e
    return {"public_id": public_id, "provider": _store().provider, "upload": upload}


@router.put("/images/local-upload", status_code=201)
async def local_upload(request: Request, public_id: str = Query(max_length=200), exp: int = Query(), sig: str = Query(max_length=128)) -> dict:
    s = _local()
    if not s.check_upload_token(public_id, exp, sig):
        raise api_error(403, "BAD_UPLOAD_TOKEN", "This upload link is invalid or has expired")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > s.max_bytes:
        raise api_error(413, "IMAGE_TOO_LARGE", f"Images can be at most {s.max_bytes // 1_000_000} MB")
    data = await request.body()
    try:
        info = s.write(public_id, data)
    except ImageStoreError as e:
        raise api_error(413 if e.code == "IMAGE_TOO_LARGE" else 409 if e.code == "ALREADY_UPLOADED" else 422, e.code, e.message) from e
    return {"format": info.format, "bytes": info.bytes, "width": info.width, "height": info.height}


@router.post("/images", status_code=201)
def register_image(body: RegisterIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if db.get(Project, body.project_id) is None:
        raise api_error(404, "PROJECT_NOT_FOUND", "No such project")
    require_member(db, body.project_id, user)
    if store_mod.project_of(body.public_id) != body.project_id:       # the folder is the proof it was signed for this project
        raise api_error(422, "WRONG_FOLDER", "That image does not belong to this project")
    existing = db.scalars(select(Image).where(Image.public_id == body.public_id)).first()
    if existing is not None:
        if existing.uploaded_by != user.id:
            raise api_error(409, "IMAGE_TAKEN", "That image was registered by someone else")
        return _image_view(existing)
    try:
        info = _store().inspect(body.public_id)
    except ImageStoreError as e:
        _fail(e)
    except ImageStoreUnavailable as e:
        _unavailable(e)
    if info is None:
        raise api_error(422, "IMAGE_NOT_FOUND", "Nothing has been uploaded for that image yet")
    img = Image(project_id=body.project_id, uploaded_by=user.id, provider=_store().provider, public_id=body.public_id,
                delivery_type="authenticated", format=info.format, bytes=info.bytes, width=info.width, height=info.height, sha256=info.sha256)
    db.add(img)
    db.commit()
    return _image_view(img)


def _image_view(i: Image) -> dict:
    return {"image_id": i.id, "project_id": i.project_id, "format": i.format, "bytes": i.bytes, "width": i.width, "height": i.height}


@router.get("/images/{image_id}/url")
def image_url(image_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    img = db.get(Image, image_id)
    if img is None:
        raise api_error(404, "IMAGE_NOT_FOUND", "No such image")
    require_member(db, img.project_id, user)
    s = _store()
    try:
        url, exp = s.signed_url(img.public_id, img.format) if s.provider == "CLOUDINARY" else s.signed_url(img.public_id)
    except ImageStoreError as e:
        _fail(e)
    return {"url": url, "expires_at": exp}


@router.get("/images/local/file")
def local_file(public_id: str = Query(max_length=200), exp: int = Query(), sig: str = Query(max_length=128)) -> Response:
    s = _local()
    if not s.check_view_token(public_id, exp, sig):
        raise api_error(403, "BAD_URL", "This link is invalid or has expired")
    data = s.read_bytes(public_id)
    info = image_meta.sniff(data) if data else None
    if info is None:
        raise api_error(404, "IMAGE_NOT_FOUND", "No such image")
    return Response(data, media_type=info.mime, headers={"Cache-Control": "private, max-age=60", "X-Content-Type-Options": "nosniff",
                                                         "Content-Disposition": "inline", "Content-Security-Policy": "default-src 'none'; sandbox"})
