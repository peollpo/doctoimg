# Doc to Image Service

A small FastAPI-based service that converts uploaded Word/PDF documents into page images with optional backgrounds. It relies on LibreOffice for DOC/DOCX to PDF conversion and Poppler for PDF rasterization.

## Features

- Upload `.doc`, `.docx`, or `.pdf` files.
- Choose between no background, a solid color background, or a custom background image.
- Tasks are processed asynchronously; poll for status and download the resulting images as a ZIP archive.
- Lightweight frontend served from the same backend for quick testing.

## Requirements

- **LibreOffice** (`soffice`) available on the PATH.
- **Poppler** utilities for PDF rasterization (`pdf2image` expects `pdftoppm`).
- Python 3.10+
- (Optional) ImageMagick if you plan to extend post-processing.

### macOS setup

```bash
brew install --cask libreoffice
brew install poppler
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### Linux setup (Ubuntu example)

```bash
sudo apt-get update
sudo apt-get install -y libreoffice libreoffice-writer poppler-utils python3-venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

If LibreOffice is not on the PATH, set `LIBREOFFICE_PATH` in a `.env` file inside `backend/` or export it before running the server.

## Running locally

```bash
source .venv/bin/activate  # if not already active
cd backend
uvicorn app.main:app --reload
```

Open `http://localhost:8000/` to use the web interface. The backend also exposes:

- `POST /tasks` – create a conversion task (multipart form data).
- `GET /tasks/{task_id}` – poll task status.
- `GET /tasks/{task_id}/download` – download the ZIP archive once complete.

Uploads and results are stored under `data/uploads` and `data/results` respectively. Files are kept for 24 hours by default (configurable via `cleanup_hours`).

## Deployment Notes

- Wrap the FastAPI app with a production ASGI server (Uvicorn with Gunicorn, or Hypercorn).
- Mount `/static` and `/` through the app or serve the `frontend/` directory via a CDN/reverse proxy.
- Configure a background supervisor to ensure LibreOffice/Poppler binaries exist on the Linux VPS.
- Schedule a cron or background job to purge old entries in `data/results` if you expect heavy traffic.

## TODO / Extensions

- Persist task metadata in a database instead of in-memory.
- Replace the in-memory worker with Celery/RQ for horizontal scaling.
- Add authentication/rate limiting for public deployments.
- Support additional background options (e.g., gradients, tiling backgrounds).
- Stream per-page previews or return individual URLs instead of a ZIP archive.
