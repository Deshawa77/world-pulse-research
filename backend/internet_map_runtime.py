from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from processing.internet_map_storage import load_internet_map_stream_snapshot, persist_internet_map_runtime_status


CycleBuilder = Callable[..., dict[str, Any]]
TaskRunner = Callable[..., dict[str, Any] | None]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


class InternetMapRuntime:
    def __init__(
        self,
        *,
        cycle_interval_sec: int = 45,
        backtest_interval_sec: int = 15 * 60,
        maintenance_interval_sec: int = 6 * 60 * 60,
    ) -> None:
        self._cycle_interval_sec = max(10, cycle_interval_sec)
        self._backtest_interval_sec = max(300, backtest_interval_sec)
        self._maintenance_interval_sec = max(900, maintenance_interval_sec)
        self._lock = threading.Condition()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._cycle_builder: CycleBuilder | None = None
        self._backtest_runner: TaskRunner | None = None
        self._maintenance_runner: TaskRunner | None = None
        self._pending_request_id = 0
        self._last_completed_request_id = 0
        self._active_request_id = 0
        self._last_snapshot = load_internet_map_stream_snapshot()
        self._last_cycle_started_at: str | None = None
        self._last_cycle_finished_at: str | None = None
        self._last_cycle_status = "idle"
        self._last_cycle_reason = "bootstrap"
        self._last_mode = "online"
        self._refresh_sources = True
        self._in_progress = False
        self._error_count = 0
        self._cycle_count = 0
        self._last_error: str | None = None
        self._last_backtest_at: str | None = None
        self._last_backtest_status: str | None = None
        self._last_maintenance_at: str | None = None
        self._last_maintenance_status: str | None = None

    def configure(self, *, cycle_builder: CycleBuilder, backtest_runner: TaskRunner | None = None, maintenance_runner: TaskRunner | None = None) -> None:
        self._cycle_builder = cycle_builder
        self._backtest_runner = backtest_runner
        self._maintenance_runner = maintenance_runner

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._loop, name="internet-map-runtime", daemon=True)
            self._thread.start()

    def request_cycle(
        self,
        *,
        mode: str = "online",
        refresh_sources: bool = True,
        reason: str = "manual",
        block: bool = False,
        timeout_sec: float = 20.0,
    ) -> dict[str, Any]:
        with self._lock:
            self._pending_request_id += 1
            request_id = self._pending_request_id
            self._last_mode = str(mode or "online")
            self._refresh_sources = bool(refresh_sources)
            self._last_cycle_reason = str(reason or "manual")
            self._wake_event.set()
            self._lock.notify_all()
            if not block:
                return self.status()
            end_at = time.time() + max(1.0, timeout_sec)
            while self._last_completed_request_id < request_id and time.time() < end_at:
                remaining = max(0.25, end_at - time.time())
                self._lock.wait(timeout=remaining)
            return self.status()

    def latest_snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            return self._last_snapshot or load_internet_map_stream_snapshot()

    def status(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._last_snapshot or load_internet_map_stream_snapshot()
            stream_status = snapshot.get("stream_status") if isinstance(snapshot, dict) and isinstance(snapshot.get("stream_status"), dict) else {}
            collector_summary = snapshot.get("collector_summary") if isinstance(snapshot, dict) and isinstance(snapshot.get("collector_summary"), dict) else {}
            payload = snapshot.get("payload") if isinstance(snapshot, dict) and isinstance(snapshot.get("payload"), dict) else {}
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            queued_cycles = max(0, self._pending_request_id - max(self._last_completed_request_id, self._active_request_id))
            status = {
                "status": "running" if self._in_progress else ("ok" if snapshot else "idle"),
                "scheduler_enabled": self._running,
                "in_progress": self._in_progress,
                "queue_depth": queued_cycles,
                "last_cycle_reason": self._last_cycle_reason,
                "last_cycle_started_at": self._last_cycle_started_at,
                "last_cycle_finished_at": self._last_cycle_finished_at,
                "last_cycle_status": self._last_cycle_status,
                "last_mode": self._last_mode,
                "refresh_sources": self._refresh_sources,
                "cycle_interval_sec": self._cycle_interval_sec,
                "backtest_interval_sec": self._backtest_interval_sec,
                "maintenance_interval_sec": self._maintenance_interval_sec,
                "cycle_count": self._cycle_count,
                "error_count": self._error_count,
                "last_error": self._last_error,
                "last_backtest_at": self._last_backtest_at,
                "last_backtest_status": self._last_backtest_status,
                "last_maintenance_at": self._last_maintenance_at,
                "last_maintenance_status": self._last_maintenance_status,
                "run_id": snapshot.get("run_id") if isinstance(snapshot, dict) else None,
                "captured_at": snapshot.get("captured_at") if isinstance(snapshot, dict) else None,
                "cycle_latency_ms": float(stream_status.get("cycle_latency_ms") or 0.0),
                "collector_total_records": int(collector_summary.get("total_records") or 0),
                "source_stage": summary.get("source_stage"),
            }
            persist_internet_map_runtime_status(status)
            return status

    def _loop(self) -> None:
        next_cycle = time.monotonic() + self._cycle_interval_sec
        next_backtest = time.monotonic() + self._backtest_interval_sec
        next_maintenance = time.monotonic() + self._maintenance_interval_sec
        while True:
            now = time.monotonic()
            timeout = max(0.5, min(next_cycle - now, next_backtest - now, next_maintenance - now))
            self._wake_event.wait(timeout=timeout)
            self._wake_event.clear()

            request_id = 0
            reason = "scheduled_cycle"
            mode = self._last_mode
            refresh_sources = True
            should_cycle = False
            with self._lock:
                now = time.monotonic()
                if self._pending_request_id > self._last_completed_request_id:
                    request_id = self._pending_request_id
                    self._active_request_id = request_id
                    reason = self._last_cycle_reason or "queued_refresh"
                    mode = self._last_mode
                    refresh_sources = self._refresh_sources
                    should_cycle = True
                elif now >= next_cycle:
                    reason = "scheduled_cycle"
                    mode = self._last_mode
                    refresh_sources = True
                    should_cycle = True
                if should_cycle:
                    self._in_progress = True
                    self._last_cycle_started_at = _iso_now()
                    self._last_cycle_status = "running"
                    persist_internet_map_runtime_status(self.status())

            if should_cycle:
                try:
                    snapshot = self._run_cycle(mode=mode, refresh_sources=refresh_sources, reason=reason)
                    with self._lock:
                        self._last_snapshot = snapshot
                        self._cycle_count += 1
                        self._last_cycle_status = "ok"
                        self._last_error = None
                except Exception as exc:
                    with self._lock:
                        self._error_count += 1
                        self._last_cycle_status = "error"
                        self._last_error = str(exc)
                finally:
                    with self._lock:
                        self._last_cycle_finished_at = _iso_now()
                        self._in_progress = False
                        self._last_completed_request_id = max(self._last_completed_request_id, self._active_request_id)
                        self._active_request_id = 0
                        next_cycle = time.monotonic() + self._cycle_interval_sec
                        self._lock.notify_all()
                        persist_internet_map_runtime_status(self.status())

            now = time.monotonic()
            if now >= next_backtest:
                self._run_periodic_task("backtest")
                next_backtest = time.monotonic() + self._backtest_interval_sec
            if now >= next_maintenance:
                self._run_periodic_task("maintenance")
                next_maintenance = time.monotonic() + self._maintenance_interval_sec

    def _run_cycle(self, *, mode: str, refresh_sources: bool, reason: str) -> dict[str, Any]:
        if self._cycle_builder is None:
            raise RuntimeError("internet-map runtime cycle builder is not configured")
        snapshot = self._cycle_builder(mode=mode, refresh_sources=refresh_sources, reason=reason)
        if not isinstance(snapshot, dict):
            raise RuntimeError("internet-map cycle builder returned an invalid snapshot")
        return snapshot

    def _run_periodic_task(self, task_name: str) -> None:
        runner = self._backtest_runner if task_name == "backtest" else self._maintenance_runner
        if runner is None:
            return
        try:
            result = runner(reason=f"scheduled_{task_name}") or {}
            status = str(result.get("status") or "ok") if isinstance(result, dict) else "ok"
        except Exception as exc:
            status = f"error:{exc}"
        now = _iso_now()
        with self._lock:
            if task_name == "backtest":
                self._last_backtest_at = now
                self._last_backtest_status = status
            else:
                self._last_maintenance_at = now
                self._last_maintenance_status = status
            persist_internet_map_runtime_status(self.status())


DEFAULT_RUNTIME = InternetMapRuntime()
