from __future__ import annotations

import threading
import time
from datetime import datetime
from queue import Queue
from typing import Dict, Optional

from rich.console import Console

from .config import settings
from .models import Task, TaskResponse, TaskState


class TaskQueue:
    def __init__(self, converter) -> None:
        self.converter = converter
        self.console = Console()
        self.tasks: Dict[str, Task] = {}
        self._queue: Queue[Task] = Queue()
        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._workers = [
            threading.Thread(target=self._worker_loop, name=f"worker-{i}", daemon=True)
            for i in range(settings.max_worker_threads)
        ]
        for worker in self._workers:
            worker.start()

    def add_task(self, task: Task) -> None:
        with self._lock:
            self.tasks[task.task_id] = task
        self._queue.put(task)

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self.tasks.get(task_id)

    def to_response(self, task: Task) -> TaskResponse:
        return TaskResponse(
            task_id=task.task_id,
            source_name=task.source_name,
            state=task.state,
            detail=task.error,
            download_url=self.converter.get_download_url(task) if task.state == TaskState.completed else None,
            batch_id=task.batch_id,
            batch_download_url=f"/batches/{task.batch_id}/download" if task.batch_id and task.state == TaskState.completed else None,
            expires_at=task.expires_at if task.state == TaskState.completed else None,
            original_snapshot_url=self.converter.get_original_snapshot_url(task) if task.state == TaskState.completed else None,
            owner_id=task.owner_id,
            owner_email=task.owner_email,
        )

    def shutdown(self) -> None:
        self._shutdown.set()
        for _ in self._workers:
            self._queue.put(None)  # type: ignore[arg-type]
        for worker in self._workers:
            worker.join(timeout=2)

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            task: Optional[Task] = self._queue.get()
            if task is None:
                break

            with self._lock:
                current = self.tasks.get(task.task_id)
                if current:
                    current.state = TaskState.processing

            self.console.log(f"Processing task {task.task_id}")
            try:
                self.converter.process(task)
                with self._lock:
                    current = self.tasks.get(task.task_id)
                    if current:
                        current.state = TaskState.completed
                        current.result_dir = task.result_dir
                        current.expires_at = task.expires_at
                        current.original_snapshot = task.original_snapshot
            except Exception as exc:  # pylint: disable=broad-except
                self.console.log(f"Task {task.task_id} failed: {exc}")
                with self._lock:
                    current = self.tasks.get(task.task_id)
                    if current:
                        current.state = TaskState.failed
                        current.error = str(exc)
            finally:
                self._queue.task_done()
                time.sleep(settings.worker_poll_interval)


task_queue: Optional[TaskQueue] = None


def init_task_queue(converter) -> TaskQueue:
    global task_queue
    if task_queue is None:
        task_queue = TaskQueue(converter=converter)
    return task_queue
