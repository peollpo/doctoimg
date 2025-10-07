from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import StrapiUser, get_current_user
from .config import settings
from .converter import converter
from .models import BackgroundType, Task, TaskResponse, TaskState
from .storage import cleanup_expired, generate_task_id, save_upload
from .task_queue import init_task_queue

ALLOWED_SUFFIXES = {".doc", ".docx", ".pdf"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def get_task_queue():
    return init_task_queue(converter)


frontend_dir = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="Doc to Image Service", version="0.1.0")

app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    init_task_queue(converter)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    queue = init_task_queue(converter)
    queue.shutdown()


@app.get("/healthz")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def serve_index() -> FileResponse:
    index_file = frontend_dir / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend not built")
    return FileResponse(index_file)


@app.post("/tasks", response_model=list[TaskResponse])
async def create_task(
    files: List[UploadFile] = File(...),
    background_type: BackgroundType = Form(BackgroundType.none),
    background_color: Optional[str] = Form(None),
    dpi: int = Form(144),
    background_image: Optional[UploadFile] = File(None),
    queue=Depends(get_task_queue),
    user: StrapiUser = Depends(get_current_user),
) -> list[TaskResponse]:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    processed_tasks: list[TaskResponse] = []

    # 为这批任务生成统一的 batch_id
    batch_id = generate_task_id() if len(files) > 1 else None

    if background_type == BackgroundType.color and not background_color:
        raise HTTPException(status_code=400, detail="Background color required")

    background_image_bytes: Optional[bytes] = None
    background_image_suffix: Optional[str] = None
    if background_type == BackgroundType.image:
        if not background_image:
            raise HTTPException(status_code=400, detail="Background image file required")
        background_image_bytes = await background_image.read()
        background_image_suffix = Path(background_image.filename or "background.png").suffix or ".png"
        await background_image.close()

    for upload in files:
        filename = upload.filename or "document"
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            continue

        if upload.content_type and upload.content_type not in ALLOWED_MIME_TYPES:
            # Allow fallback if MIME missing but suffix valid
            pass

        source_path = await save_upload(upload, settings.upload_dir)

        background_path: Optional[Path] = None
        if background_image_bytes is not None and background_image_suffix is not None:
            background_path = settings.upload_dir / f"bg-{generate_task_id()}{background_image_suffix}"
            background_path.write_bytes(background_image_bytes)

        task_id = generate_task_id()
        task = Task(
            task_id=task_id,
            source_path=source_path,
            source_name=filename,
            created_at=datetime.now(timezone.utc),
            dpi=dpi,
            background_type=background_type,
            background_color=background_color,
            background_image_path=background_path,
            batch_id=batch_id,
            owner_id=user.id,
            owner_email=user.email,
        )
        queue.add_task(task)
        processed_tasks.append(queue.to_response(task))

    if not processed_tasks:
        raise HTTPException(status_code=400, detail="No supported documents found in folder")

    return processed_tasks


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    queue=Depends(get_task_queue),
    user: StrapiUser = Depends(get_current_user),
) -> TaskResponse:
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not permitted")
    cleanup_expired(datetime.now(timezone.utc))
    return queue.to_response(task)


@app.get("/tasks/{task_id}/download")
async def download_task(
    task_id: str,
    queue=Depends(get_task_queue),
    user: StrapiUser = Depends(get_current_user),
) -> FileResponse:
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not permitted")
    if task.state != TaskState.completed or not task.result_dir:
        raise HTTPException(status_code=400, detail="Task not completed")

    zip_path = task.result_dir / f"{task.task_id}.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Result not found")

    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/tasks/{task_id}/original")
async def download_original(
    task_id: str,
    queue=Depends(get_task_queue),
    user: StrapiUser = Depends(get_current_user),
) -> FileResponse:
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not permitted")
    if task.state != TaskState.completed or not task.original_snapshot:
        raise HTTPException(status_code=400, detail="Original snapshot not available")
    if not task.original_snapshot.exists():
        raise HTTPException(status_code=404, detail="Original snapshot missing")
    return FileResponse(task.original_snapshot, media_type="image/png", filename=task.original_snapshot.name)


@app.get("/batches/{batch_id}/download")
async def download_batch(
    batch_id: str,
    queue=Depends(get_task_queue),
    user: StrapiUser = Depends(get_current_user),
) -> FileResponse:
    """下载批次中所有已完成任务的图片，打包成一个 ZIP"""
    from zipfile import ZipFile
    import tempfile

    # 查找该批次的所有任务
    batch_tasks: list[Task] = []
    with queue._lock:
        for task in queue.tasks.values():
            if task.batch_id == batch_id and task.owner_id == user.id:
                batch_tasks.append(task)

    if not batch_tasks:
        raise HTTPException(status_code=404, detail="Batch not found")

    # 检查是否所有任务都已完成
    incomplete_tasks = [t for t in batch_tasks if t.state != TaskState.completed]
    if incomplete_tasks:
        raise HTTPException(
            status_code=400,
            detail=f"{len(incomplete_tasks)} task(s) still processing. Please wait."
        )

    # 创建临时 ZIP 文件
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    temp_zip.close()

    try:
        with ZipFile(temp_zip.name, 'w') as zipf:
            for task in batch_tasks:
                if not task.result_dir or not task.result_dir.exists():
                    continue

                # 使用文档标题作为文件夹名
                folder_name = task.result_dir.name
                images_dir = task.result_dir / "images"

                if images_dir.exists():
                    for image_file in sorted(images_dir.glob("*.png")):
                        arcname = f"{folder_name}/{image_file.name}"
                        zipf.write(image_file, arcname=arcname)

        return FileResponse(
            temp_zip.name,
            media_type="application/zip",
            filename=f"batch-{batch_id}.zip",
            background=None  # 不在后台删除，让 OS 清理临时文件
        )
    except Exception as e:
        # 清理临时文件
        Path(temp_zip.name).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to create batch zip: {str(e)}")
