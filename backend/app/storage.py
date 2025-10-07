from __future__ import annotations

import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from .config import settings


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name).strip().lower()
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug or "document"


def generate_task_id() -> str:
    return uuid.uuid4().hex


async def save_upload(upload: UploadFile, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    file_suffix = Path(upload.filename or "document").suffix
    safe_name = f"{uuid.uuid4().hex}{file_suffix}"
    destination = destination_dir / safe_name

    with destination.open("wb") as f:
        while chunk := await upload.read(1024 * 1024):
            f.write(chunk)
    await upload.close()
    return destination


def create_task_workspace(task_id: str, source_name: str, owner_segment: Optional[str] = None) -> Path:
    base_name = Path(source_name).stem
    slug = _slugify(base_name)
    parts: list[Path] = [settings.result_dir]
    if owner_segment:
        parts.append(Path(_slugify(owner_segment)))
    workspace = Path(*parts) / slug
    if workspace.exists():
        workspace = Path(*parts) / f"{slug}-{task_id[:8]}"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def remove_path(path: Optional[Path]) -> None:
    if path and path.exists():
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def _maybe_cleanup(task_dir: Path, now: datetime) -> bool:
    expires_at_file = task_dir / "expires_at"
    if not expires_at_file.exists():
        return False
    try:
        expires_timestamp = float(expires_at_file.read_text().strip())
    except ValueError:
        return False
    if expires_timestamp < now.timestamp():
        shutil.rmtree(task_dir, ignore_errors=True)
        return True
    return False


def cleanup_expired(now: datetime) -> None:
    for entry in settings.result_dir.iterdir():
        if not entry.is_dir():
            continue
        removed = _maybe_cleanup(entry, now)
        if removed:
            continue
        for child in entry.iterdir():
            if not child.is_dir():
                continue
            _maybe_cleanup(child, now)
        try:
            if not any(entry.iterdir()):
                entry.rmdir()
        except OSError:
            pass
