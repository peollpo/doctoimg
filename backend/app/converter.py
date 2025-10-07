from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from zipfile import ZipFile

from PIL import Image, ImageColor
from pdf2image import convert_from_path

from .config import settings
from .models import BackgroundType, Task
from .storage import create_task_workspace, remove_path


class ConversionError(Exception):
    pass


class Converter:
    def __init__(self) -> None:
        self.libreoffice_cmd = settings.libreoffice_path

    def process(self, task: Task) -> None:
        owner_segment = str(task.owner_id) if task.owner_id is not None else None
        workspace = create_task_workspace(task.task_id, task.source_name, owner_segment)
        task.result_dir = workspace
        source_copy = workspace / "source"
        source_copy.parent.mkdir(exist_ok=True)
        shutil.copy2(task.source_path, source_copy)

        try:
            pdf_path = self._convert_to_pdf(source_copy, workspace)
            images = self._pdf_to_images(pdf_path, dpi=task.dpi)
            processed = self._apply_background(images, task)
            zip_path = self._write_results(processed, images, workspace, task.task_id)
            original_snapshot = workspace / "page-001-original.png"
            if original_snapshot.exists():
                task.original_snapshot = original_snapshot
            task.expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.cleanup_hours)
            expires_file = workspace / "expires_at"
            expires_file.write_text(str(task.expires_at.timestamp()))
            metadata = {
                "source": task.source_name,
                "pages": len(processed),
                "dpi": task.dpi,
                "background": task.background_type.value,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "zip_path": zip_path.name,
                "original_snapshot": task.original_snapshot.name if task.original_snapshot else None,
            }
            (workspace / "metadata.json").write_text(json.dumps(metadata, indent=2))
        finally:
            remove_path(task.source_path)
            if task.background_image_path:
                remove_path(task.background_image_path)
            # We can delete the copied source to save space
            remove_path(source_copy)

    def get_download_url(self, task: Task) -> str:
        return f"/tasks/{task.task_id}/download"

    def get_original_snapshot_url(self, task: Task) -> Optional[str]:
        if not task.original_snapshot:
            return None
        return f"/tasks/{task.task_id}/original"

    def _convert_to_pdf(self, source: Path, workspace: Path) -> Path:
        if source.suffix.lower() == ".pdf":
            return source

        output_dir = workspace / "pdf"
        output_dir.mkdir(exist_ok=True)

        cmd = [
            self.libreoffice_cmd,
            "--headless",
            "--nologo",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(source),
        ]

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError as exc:
            raise ConversionError("LibreOffice not found. Set LIBREOFFICE_PATH.") from exc
        except subprocess.CalledProcessError as exc:
            raise ConversionError(f"LibreOffice failed: {exc.stderr.decode('utf-8', 'ignore')}") from exc

        pdf_files = list(output_dir.glob("*.pdf"))
        if not pdf_files:
            raise ConversionError("PDF conversion produced no output")
        return pdf_files[0]

    def _pdf_to_images(self, pdf_path: Path, dpi: int) -> List[Image.Image]:
        try:
            poppler_path = settings.poppler_path
            images = convert_from_path(
                str(pdf_path),
                dpi=dpi,
                poppler_path=str(poppler_path) if poppler_path else None,
                transparent=True,
            )
        except Exception as exc:  # pylint: disable=broad-except
            raise ConversionError(f"PDF to image conversion failed: {exc}") from exc
        return images

    def _apply_background(self, images: List[Image.Image], task: Task) -> List[Image.Image]:
        if task.background_type == BackgroundType.none:
            return images
        processed: List[Image.Image] = []
        if task.background_type == BackgroundType.color:
            if not task.background_color:
                raise ConversionError("Background color required for color background")
            color = ImageColor.getrgb(task.background_color)
            threshold = settings.background_color_threshold
            for img in images:
                rgba = img.convert("RGBA")
                # Build a mask that keeps darker content (text/images) and replaces
                # near-white pixels with the requested background color.
                gray = rgba.convert("L")
                mask = gray.point(lambda value: 0 if value > threshold else 255)
                base = Image.new("RGB", rgba.size, color)
                composite = Image.composite(rgba.convert("RGB"), base, mask)
                processed.append(composite)
            return processed
        if task.background_type == BackgroundType.image:
            if not task.background_image_path:
                raise ConversionError("Background image missing")
            background_template = Image.open(task.background_image_path).convert("RGB")
            threshold = settings.background_color_threshold
            try:
                for img in images:
                    fg = img.convert("RGB")
                    gray = fg.convert("L")
                    mask = gray.point(lambda value: 0 if value > threshold else 255)
                    bg_resized = background_template.resize(fg.size, Image.LANCZOS)
                    composite = Image.composite(fg, bg_resized, mask)
                    processed.append(composite)
            finally:
                background_template.close()
            return processed
        raise ConversionError("Unsupported background type")

    def _write_results(
        self,
        processed_images: List[Image.Image],
        original_images: List[Image.Image],
        workspace: Path,
        task_id: str,
    ) -> Path:
        images_dir = workspace / "images"
        images_dir.mkdir(exist_ok=True)
        saved_files: List[Path] = []
        for index, img in enumerate(processed_images, start=1):
            target = images_dir / f"page-{index:03d}.png"
            img.save(target, format="PNG")
            saved_files.append(target)

        if original_images:
            first_page = original_images[0].convert("RGB")
            original_path = workspace / "page-001-original.png"
            first_page.save(original_path, format="PNG")
            saved_files.append(original_path)

        zip_path = workspace / f"{task_id}.zip"
        with ZipFile(zip_path, "w") as zipf:
            for file_path in saved_files:
                zipf.write(file_path, arcname=file_path.name)
        return zip_path


converter = Converter()
