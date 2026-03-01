from __future__ import annotations

import inspect
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from refua_studio.storage import JobStore


class JobCancelledError(RuntimeError):
    """Raised when a running job exits early due to cancellation."""


class BackgroundRunner:
    """Executes long-running tasks and writes lifecycle state to JobStore."""

    def __init__(self, store: JobStore, *, max_workers: int = 2) -> None:
        self._store = store
        self._executor = ThreadPoolExecutor(max_workers=max(1, max_workers))
        self._futures: dict[str, Future[None]] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        *,
        kind: str,
        request: dict[str, Any],
        fn: Callable[..., dict[str, Any]],
    ) -> dict[str, Any]:
        job = self._store.create_job(kind=kind, request=request)
        job_id = job["job_id"]
        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[job_id] = cancel_event

        def _wrapped() -> None:
            # If cancel() succeeds before execution, this function is never called.
            if not self._store.set_running(job_id):
                return
            if cancel_event.is_set() or self._store.is_cancel_requested(job_id):
                self._store.set_cancelled(job_id, "Cancelled by user before execution.")
                return
            try:
                result = _invoke_job_fn(fn, cancel_event=cancel_event)
            except JobCancelledError as exc:
                self._store.set_cancelled(job_id, str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                self._store.set_failed(job_id, str(exc))
                return
            if cancel_event.is_set() or self._store.is_cancel_requested(job_id):
                self._store.set_cancelled(job_id, "Cancelled by user during execution.")
                return
            self._store.set_completed(job_id, result)

        future = self._executor.submit(_wrapped)
        with self._lock:
            self._futures[job_id] = future

        def _cleanup(done_future: Future[None]) -> None:
            with self._lock:
                self._futures.pop(job_id, None)
                self._cancel_events.pop(job_id, None)
            if done_future.cancelled():
                self._store.set_cancelled(job_id, "Cancelled before execution.")

        future.add_done_callback(_cleanup)
        refreshed = self._store.get_job(job_id)
        if refreshed is None:
            raise RuntimeError("Submitted job cannot be found.")
        return refreshed

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self._store.get_job(job_id)
        if job is None:
            raise KeyError(job_id)

        with self._lock:
            future = self._futures.get(job_id)
            cancel_event = self._cancel_events.get(job_id)

        if future is None:
            return {
                "job_id": job_id,
                "cancelled": False,
                "status": job["status"],
                "message": "Job is not active.",
            }

        if job["status"] == "queued":
            cancelled = future.cancel()
            if cancelled:
                self._store.set_cancelled(job_id, "Cancelled by user before execution.")
                latest = self._store.get_job(job_id) or job
                return {
                    "job_id": job_id,
                    "cancelled": True,
                    "status": latest["status"],
                    "message": "Job cancelled.",
                }

        if job["status"] == "running":
            if cancel_event is not None:
                cancel_event.set()
            self._store.request_cancel(
                job_id, reason="Cancellation requested by user while running."
            )
            latest = self._store.get_job(job_id) or job
            return {
                "job_id": job_id,
                "cancelled": True,
                "status": latest["status"],
                "message": "Cancellation requested for running job.",
            }

        latest = self._store.get_job(job_id) or job
        return {
            "job_id": job_id,
            "cancelled": False,
            "status": latest["status"],
            "message": "Job is not cancellable in its current state.",
        }

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def _invoke_job_fn(
    fn: Callable[..., dict[str, Any]],
    *,
    cancel_event: threading.Event,
) -> dict[str, Any]:
    signature = inspect.signature(fn)
    if "cancel_event" in signature.parameters:
        return fn(cancel_event=cancel_event)
    return fn()
