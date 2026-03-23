from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import threading
import time
from typing import Any, Iterator

from clawcures_ui.bridge import CampaignBridge
from clawcures_ui.storage import JobStore

_SUCCESS_DELAY_SECONDS = 1.0
_FAILURE_DELAY_SECONDS = 5.0
_HEARTBEAT_INTERVAL_SECONDS = 2.0


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ContinuousDiscoveryService:
    """Runs the default ClawCures mission continuously in the background."""

    def __init__(
        self,
        store: JobStore,
        bridge: CampaignBridge,
        *,
        objective: str,
        success_delay_seconds: float = _SUCCESS_DELAY_SECONDS,
        failure_delay_seconds: float = _FAILURE_DELAY_SECONDS,
    ) -> None:
        self._store = store
        self._bridge = bridge
        self._objective = objective.strip()
        self._success_delay_seconds = max(float(success_delay_seconds), 0.0)
        self._failure_delay_seconds = max(float(failure_delay_seconds), 0.0)
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._controller_job_id: str | None = None
        self._cycle_index = 0

    def start(self) -> dict[str, Any] | None:
        if not self._objective:
            return None
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._store.get_job(self._controller_job_id or "")

            self._stop_event.clear()
            self._cycle_index = 0
            job = self._store.create_job(
                kind="continuous_discovery_agent",
                request={
                    "objective": self._objective,
                    "mode": "continuous",
                    "autostart": True,
                },
            )
            self._controller_job_id = str(job["job_id"])
            self._store.set_running(self._controller_job_id)
            self._publish_controller_progress(
                phase="starting",
                summary="Continuous discovery agent booting.",
                cycle_index=0,
            )
            self._thread = threading.Thread(
                target=self._run_loop,
                name="clawcures-continuous-agent",
                daemon=True,
            )
            self._thread.start()
            return self._store.get_job(self._controller_job_id)

    def shutdown(self) -> None:
        self._request_stop(mark_job_cancel_requested=False)
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)

    def manages_job(self, job_id: str) -> bool:
        controller_job_id = self._controller_job_id
        return bool(controller_job_id) and controller_job_id == job_id

    def cancel(self, job_id: str) -> dict[str, Any]:
        if not self.manages_job(job_id):
            raise KeyError(job_id)
        self._request_stop(mark_job_cancel_requested=True)
        self._publish_controller_progress(
            phase="stop_requested",
            summary="Stop requested; finishing the current phase before shutdown.",
            cycle_index=self._cycle_index,
        )
        latest = self._store.get_job(job_id)
        return {
            "job_id": job_id,
            "cancelled": True,
            "status": latest["status"] if latest is not None else "running",
            "message": "Continuous discovery agent stop requested.",
        }

    def status(self) -> dict[str, Any]:
        controller_job_id = self._controller_job_id
        thread = self._thread
        controller_job = (
            self._store.get_job(controller_job_id) if controller_job_id else None
        )
        progress = controller_job.get("progress") if isinstance(controller_job, dict) else None
        return {
            "enabled": True,
            "controller_job_id": controller_job_id,
            "running": bool(thread is not None and thread.is_alive()),
            "objective": self._objective,
            "progress": progress,
        }

    def _request_stop(self, *, mark_job_cancel_requested: bool) -> None:
        self._stop_event.set()
        controller_job_id = self._controller_job_id
        if mark_job_cancel_requested and controller_job_id:
            self._store.request_cancel(
                controller_job_id,
                reason="Continuous discovery agent stop requested.",
            )

    def _run_loop(self) -> None:
        controller_job_id = self._controller_job_id
        if not controller_job_id:
            return

        try:
            while not self._stop_event.is_set():
                self._cycle_index += 1
                cycle_index = self._cycle_index
                cycle_job = self._store.create_job(
                    kind="continuous_discovery_cycle",
                    request={
                        "objective": self._objective,
                        "mode": "continuous",
                        "source_job_id": controller_job_id,
                        "cycle_index": cycle_index,
                    },
                )
                cycle_job_id = str(cycle_job["job_id"])
                self._store.set_running(cycle_job_id)

                try:
                    with self._heartbeat_phase(
                        cycle_job_id=cycle_job_id,
                        phase="planning",
                        summary=f"Cycle {cycle_index}: planning the next discovery run.",
                        cycle_index=cycle_index,
                    ):
                        plan_payload = self._bridge.plan(
                            objective=self._objective,
                            system_prompt=None,
                        )

                    plan = plan_payload.get("plan")
                    if not isinstance(plan, dict):
                        raise RuntimeError("Continuous discovery cycle returned an invalid plan.")
                    plan_calls = _plan_call_count(plan)
                    self._publish_cycle_progress(
                        cycle_job_id=cycle_job_id,
                        phase="plan_ready",
                        summary=f"Cycle {cycle_index}: plan ready with {plan_calls} calls.",
                        cycle_index=cycle_index,
                        plan_calls=plan_calls,
                    )
                    if self._stop_event.is_set():
                        self._store.set_cancelled(
                            cycle_job_id,
                            "Continuous discovery agent stopped after planning.",
                        )
                        break

                    with self._heartbeat_phase(
                        cycle_job_id=cycle_job_id,
                        phase="executing",
                        summary=f"Cycle {cycle_index}: executing {plan_calls} planned calls.",
                        cycle_index=cycle_index,
                        plan_calls=plan_calls,
                    ):
                        execution_payload = self._bridge.execute_plan(
                            plan=plan,
                            event_callback=self._store.job_event_callback(cycle_job_id),
                        )

                    result = _merge_cycle_payload(
                        cycle_index=cycle_index,
                        plan_payload=plan_payload,
                        execution_payload=execution_payload,
                    )
                    result_count = len(result.get("results", [])) if isinstance(
                        result.get("results"), list
                    ) else 0
                    promising_count = _promising_count(result)
                    self._publish_cycle_progress(
                        cycle_job_id=cycle_job_id,
                        phase="completed",
                        summary=(
                            f"Cycle {cycle_index}: completed with {result_count} results "
                            f"and {promising_count} promising candidates."
                        ),
                        cycle_index=cycle_index,
                        plan_calls=plan_calls,
                        result_count=result_count,
                        promising_count=promising_count,
                    )

                    if self._stop_event.is_set():
                        self._store.set_cancelled(
                            cycle_job_id,
                            "Continuous discovery agent stopped during execution.",
                        )
                        break

                    self._store.set_completed(cycle_job_id, result)
                    self._publish_controller_progress(
                        phase="cooldown",
                        summary=(
                            f"Cycle {cycle_index} complete. Waiting "
                            f"{self._success_delay_seconds:.1f}s before the next cycle."
                        ),
                        cycle_index=cycle_index,
                        result_count=result_count,
                        promising_count=promising_count,
                        plan_calls=plan_calls,
                    )
                    if self._stop_event.wait(self._success_delay_seconds):
                        break
                except Exception as exc:  # noqa: BLE001
                    self._publish_cycle_progress(
                        cycle_job_id=cycle_job_id,
                        phase="failed",
                        summary=f"Cycle {cycle_index}: {exc}",
                        cycle_index=cycle_index,
                    )
                    self._store.set_failed(cycle_job_id, str(exc))
                    self._publish_controller_progress(
                        phase="retry_wait",
                        summary=(
                            f"Cycle {cycle_index} failed. Retrying in "
                            f"{self._failure_delay_seconds:.1f}s."
                        ),
                        cycle_index=cycle_index,
                        error=str(exc),
                    )
                    if self._stop_event.wait(self._failure_delay_seconds):
                        break
                    continue
        except Exception as exc:  # noqa: BLE001
            self._store.set_failed(controller_job_id, str(exc))
            return

        if self._store.is_cancel_requested(controller_job_id) or self._stop_event.is_set():
            self._store.set_cancelled(
                controller_job_id,
                "Continuous discovery agent stopped.",
            )
        else:
            self._store.set_completed(
                controller_job_id,
                {"objective": self._objective, "stopped": True},
            )

    @contextmanager
    def _heartbeat_phase(
        self,
        *,
        cycle_job_id: str,
        phase: str,
        summary: str,
        cycle_index: int,
        **extra: Any,
    ) -> Iterator[None]:
        stop_heartbeat = threading.Event()
        phase_started_at = _utc_now_iso()
        phase_started_monotonic = time.monotonic()
        heartbeat_counter = 0
        heartbeat_lock = threading.Lock()
        controller_job_id = self._controller_job_id

        def emit() -> None:
            nonlocal heartbeat_counter
            with heartbeat_lock:
                heartbeat_counter += 1
                payload = _build_progress_payload(
                    phase=phase,
                    summary=summary,
                    cycle_index=cycle_index,
                    phase_started_at=phase_started_at,
                    phase_elapsed_seconds=time.monotonic() - phase_started_monotonic,
                    heartbeat_count=heartbeat_counter,
                    **extra,
                )
            self._store.update_progress(cycle_job_id, payload)
            if controller_job_id:
                self._store.update_progress(controller_job_id, payload)

        emit()

        thread = threading.Thread(
            target=self._run_heartbeat_loop,
            args=(stop_heartbeat, emit),
            name=f"clawcures-heartbeat-{phase}",
            daemon=True,
        )
        thread.start()
        try:
            yield
        finally:
            stop_heartbeat.set()
            thread.join(timeout=0.2)

    def _run_heartbeat_loop(
        self,
        stop_heartbeat: threading.Event,
        emit: Any,
    ) -> None:
        while not stop_heartbeat.wait(_HEARTBEAT_INTERVAL_SECONDS):
            if self._stop_event.is_set():
                return
            emit()

    def _publish_cycle_progress(
        self,
        *,
        cycle_job_id: str,
        phase: str,
        summary: str,
        cycle_index: int,
        **extra: Any,
    ) -> None:
        payload = _build_progress_payload(
            phase=phase,
            summary=summary,
            cycle_index=cycle_index,
            phase_started_at=_utc_now_iso(),
            phase_elapsed_seconds=0.0,
            heartbeat_count=1,
            **extra,
        )
        self._store.update_progress(cycle_job_id, payload)
        self._publish_controller_progress(
            phase=phase,
            summary=summary,
            cycle_index=cycle_index,
            **extra,
        )

    def _publish_controller_progress(
        self,
        *,
        phase: str,
        summary: str,
        cycle_index: int,
        **extra: Any,
    ) -> None:
        controller_job_id = self._controller_job_id
        if not controller_job_id:
            return
        payload = _build_progress_payload(
            phase=phase,
            summary=summary,
            cycle_index=cycle_index,
            phase_started_at=_utc_now_iso(),
            phase_elapsed_seconds=0.0,
            heartbeat_count=1,
            **extra,
        )
        self._store.update_progress(controller_job_id, payload)


def _build_progress_payload(
    *,
    phase: str,
    summary: str,
    cycle_index: int,
    phase_started_at: str,
    phase_elapsed_seconds: float,
    heartbeat_count: int,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "phase": phase,
        "summary": summary,
        "cycle_index": int(cycle_index),
        "phase_started_at": phase_started_at,
        "phase_elapsed_seconds": round(float(phase_elapsed_seconds), 1),
        "heartbeat_count": int(heartbeat_count),
        "last_heartbeat_at": _utc_now_iso(),
    }
    for key, value in extra.items():
        if value is None:
            continue
        payload[key] = value
    return payload


def _plan_call_count(plan: dict[str, Any]) -> int:
    calls = plan.get("calls")
    if not isinstance(calls, list):
        return 0
    return len(calls)


def _promising_count(payload: dict[str, Any]) -> int:
    summary = payload.get("promising_cures_summary")
    if isinstance(summary, dict):
        try:
            return int(summary.get("promising_count", 0))
        except (TypeError, ValueError):
            pass
    cures = payload.get("promising_cures")
    if isinstance(cures, list):
        return len(cures)
    return 0


def _merge_cycle_payload(
    *,
    cycle_index: int,
    plan_payload: dict[str, Any],
    execution_payload: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(plan_payload)
    payload.update(execution_payload)
    payload["cycle_index"] = int(cycle_index)

    warnings: list[str] = []
    for item in (plan_payload.get("warnings"), execution_payload.get("warnings")):
        if isinstance(item, list):
            warnings.extend(str(entry) for entry in item if str(entry).strip())
    if warnings:
        payload["warnings"] = list(dict.fromkeys(warnings))
    return payload
