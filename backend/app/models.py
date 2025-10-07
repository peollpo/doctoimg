from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class TaskState(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class BackgroundType(str, enum.Enum):
    none = "none"
    color = "color"
    image = "image"


class TaskCreateRequest(BaseModel):
    background_type: BackgroundType = BackgroundType.none
    background_color: Optional[str] = Field(
        default=None,
        pattern=r"^#(?:[0-9a-fA-F]{3}){1,2}$",
        description="Hex color like #RRGGBB",
    )
    dpi: int = Field(default=144, ge=72, le=600)


class TaskResponse(BaseModel):
    task_id: str
    source_name: str
    state: TaskState
    detail: Optional[str] = None
    download_url: Optional[str] = None
    batch_id: Optional[str] = None
    batch_download_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    original_snapshot_url: Optional[str] = None
    owner_id: Optional[int] = None
    owner_email: Optional[str] = None


@dataclass
class Task:
    task_id: str
    source_path: Path
    source_name: str
    created_at: datetime
    dpi: int
    state: TaskState = TaskState.pending
    background_type: BackgroundType = BackgroundType.none
    background_color: Optional[str] = None
    background_image_path: Optional[Path] = None
    error: Optional[str] = None
    result_dir: Optional[Path] = None
    original_snapshot: Optional[Path] = None
    batch_id: Optional[str] = None
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=24)
    )
    owner_id: Optional[int] = None
    owner_email: Optional[str] = None
