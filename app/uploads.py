"""File-upload helpers."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import UPLOADS_DIR

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"}
# Generous allow-list for the internal mini file-sharing service.
ALLOWED_SHARED_EXT = {
    *ALLOWED_IMAGE_EXT,
    *ALLOWED_DOC_EXT,
    ".ppt", ".pptx", ".odt", ".ods", ".odp", ".rtf", ".csv", ".md",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".mp3", ".wav", ".ogg", ".m4a", ".flac",
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".epub", ".djvu",
}
MAX_BYTES = 12 * 1024 * 1024  # 12 MB
MAX_SHARED_BYTES = 100 * 1024 * 1024  # 100 MB for the shared file service


def _safe_save(
    file: UploadFile, allowed_ext: set[str], max_bytes: int = MAX_BYTES
) -> tuple[str, str, int, str]:
    if not file or not file.filename:
        raise HTTPException(400, "Файл не выбран")
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_ext:
        raise HTTPException(400, f"Недопустимый тип файла: {ext}")
    data = file.file.read()
    if len(data) > max_bytes:
        mb = max_bytes // (1024 * 1024)
        raise HTTPException(400, f"Файл слишком большой (макс. {mb} МБ)")
    if not data:
        raise HTTPException(400, "Пустой файл")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_urlsafe(16)}{ext}"
    target = UPLOADS_DIR / name
    target.write_bytes(data)
    url = f"/static/uploads/{name}"
    mime = file.content_type or ""
    return url, file.filename, len(data), mime


def save_image(file: UploadFile) -> str:
    url, _, _, _ = _safe_save(file, ALLOWED_IMAGE_EXT)
    return url


def save_document(file: UploadFile) -> str:
    url, _, _, _ = _safe_save(file, ALLOWED_DOC_EXT)
    return url


def save_shared_file(file: UploadFile) -> tuple[str, str, int, str]:
    """Save an upload for the mini file-sharing service.

    Returns (url, original_filename, size_bytes, mime_type).
    """
    return _safe_save(file, ALLOWED_SHARED_EXT, max_bytes=MAX_SHARED_BYTES)
