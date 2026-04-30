"""File-upload helpers."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import UPLOADS_DIR

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"}
MAX_BYTES = 12 * 1024 * 1024  # 12 MB


def _safe_save(file: UploadFile, allowed_ext: set[str]) -> str:
    if not file or not file.filename:
        raise HTTPException(400, "Файл не выбран")
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_ext:
        raise HTTPException(400, f"Недопустимый тип файла: {ext}")
    data = file.file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "Файл слишком большой (макс. 12 МБ)")
    if not data:
        raise HTTPException(400, "Пустой файл")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_urlsafe(16)}{ext}"
    target = UPLOADS_DIR / name
    target.write_bytes(data)
    return f"/static/uploads/{name}"


def save_image(file: UploadFile) -> str:
    return _safe_save(file, ALLOWED_IMAGE_EXT)


def save_document(file: UploadFile) -> str:
    return _safe_save(file, ALLOWED_DOC_EXT)
