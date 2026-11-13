from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from time import perf_counter, sleep
from uuid import uuid4

from ..core.models import ResearchEvent, ResearchJob, ResearchRequest, utc_now
from ..security.preview_security import PreviewLimitError
from .research import PROMPT_VERSION, ResearchExecutionError, ResearchService

_REPLACE_ATTEMPTS = 6
_REPLACE_RETRY_SECONDS = 0.05


class ResearchCancelled(RuntimeError):
    pass


class ResearchCapacityError(RuntimeError):
    pass


class _Control:
    def __init__(self):
        self.pause_gate = asyncio.Event()
        self.pause_gate.set()
        self.cancel_requested = False


class JsonJobStore:
    """Original storage: one JSON file per research job."""

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir

    async def save(self, job: ResearchJob, owner_id: str) -> None:
        def write() -> None:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            target = self.storage_dir / f"{job.id}.json"
            temporary = target.with_suffix(f".{uuid4().hex}.tmp")
            payload = {
                "schema_version": 2,
                "owner_id": owner_id,
                "job": job.model_dump(mode="json"),
            }
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                # Windows refuses to replace a file that another handle (e.g.
                # an antivirus scan) briefly holds open; retry for under 1 second.
                for attempt in range(_REPLACE_ATTEMPTS):
                    try:
                        temporary.replace(target)
                        return
                    except PermissionError:
                        if attempt == _REPLACE_ATTEMPTS - 1:
                            raise
                        sleep(_REPLACE_RETRY_SECONDS * (attempt + 1))
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        await asyncio.to_thread(write)

    async def load(self, job_id: str) -> tuple[str, ResearchJob] | None:
        path = self.storage_dir / f"{job_id}.json"
        if not path.is_file():
            return None
        try:
            raw = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
            if isinstance(raw, dict) and "job" in raw:
                return str(raw.get("owner_id") or "local"), ResearchJob.model_validate(raw["job"])
            return "local", ResearchJob.model_validate(raw)
        except (OSError, ValueError):
            return None

    async def delete(self, job_id: str) -> None:
        await asyncio.to_thread((self.storage_dir / f"{job_id}.json").unlink, missing_ok=True)


class ResearchJobManager:
    def __init__(self, service: ResearchService, storage_dir: Path, max_active: int = 4, capacity=None, store=None):
        self.service = service
        self.storage_dir = storage_dir
        self.store = store or JsonJobStore(storage_dir)
        self.jobs: dict[str, ResearchJob] = {}
        self.owners: dict[str, str] = {}
        self.controls: dict[str, _Control] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.max_active = max(1, max_active)
        self.capacity = capacity
        self._lock = asyncio.Lock()
        self._persist_locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def _fingerprint(request: ResearchRequest) -> str:
        raw = json.dumps(request.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def create(self, request: ResearchRequest, owner_id: str = "local") -> ResearchJob:
        fingerprint = self._fingerprint(request)
        async with self._lock:
            for job in self.jobs.values():
                if job.fingerprint == fingerprint and job.status in {
                    "queued", "running", "pause_requested", "paused", "cancel_requested"
                } and self.owners.get(job.id, "local") == owner_id:
                    copy = job.model_copy(deep=True)
                    copy.deduplicated = True
                    return copy
            active = sum(
                job.status in {"queued", "running", "pause_requested", "paused", "cancel_requested"}
                for job in self.jobs.values()
            )
            if active >= self.max_active:
                raise ResearchCapacityError(f"研究同時執行上限已達（{self.max_active}）")
            job = ResearchJob(
                id=f"research_job_{utc_now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}",
                fingerprint=fingerprint, request=request,
                model=self.service.gemini.settings.gemini_model,
                prompt_version=PROMPT_VERSION,
            )
            self.jobs[job.id] = job
            self.owners[job.id] = owner_id
            self.controls[job.id] = _Control()
            await self._persist(job)
            self.tasks[job.id] = asyncio.create_task(self._run(job.id), name=job.id)
            return job.model_copy(deep=True)

    async def get(self, job_id: str, owner_id: str = "local") -> ResearchJob | None:
        job = self.jobs.get(job_id)
        if job:
            if self.owners.get(job_id, "local") != owner_id:
                return None
            # A terminal status is assigned immediately before the final atomic
            # persistence.  Wait for that short finalization window so callers
            # cannot observe "completed" and then reopen a stale "running"
            # file from disk.
            task = self.tasks.get(job_id)
            if (
                task
                and task is not asyncio.current_task()
                and job.status in {"completed", "failed", "cancelled"}
            ):
                await asyncio.shield(task)
                job = self.jobs.get(job_id, job)
            return job.model_copy(deep=True)
        record = await self.store.load(job_id)
        if record is None:
            return None
        stored_owner, loaded = record
        if stored_owner != owner_id:
            return None
        self.owners[job_id] = stored_owner
        if loaded.status in {"queued", "running", "pause_requested", "paused", "cancel_requested"}:
            loaded.status = "failed"
            loaded.error = {"code": "server_restarted", "message": "後端重啟中斷了尚未完成的研究；請重新送出", "retryable": True}
            loaded.updated_at = utc_now()
            loaded.completed_at = loaded.updated_at
            await self._persist(loaded)
        self.jobs[job_id] = loaded
        return loaded.model_copy(deep=True)

    async def pause(self, job_id: str, owner_id: str = "local") -> ResearchJob | None:
        job = self.jobs.get(job_id)
        control = self.controls.get(job_id)
        if job and self.owners.get(job_id, "local") != owner_id:
            return None
        if not job or not control:
            return await self.get(job_id, owner_id)
        if job.status in {"queued", "running"}:
            control.pause_gate.clear()
            job.status = "pause_requested"
            job.updated_at = utc_now()
            await self._persist(job)
        return job.model_copy(deep=True)

    async def resume(self, job_id: str, owner_id: str = "local") -> ResearchJob | None:
        job = self.jobs.get(job_id)
        control = self.controls.get(job_id)
        if job and self.owners.get(job_id, "local") != owner_id:
            return None
        if not job or not control:
            return await self.get(job_id, owner_id)
        if job.status in {"paused", "pause_requested"}:
            job.status = "running"
            job.updated_at = utc_now()
            control.pause_gate.set()
            await self._append_control_event(job, "研究繼續", "已在工具呼叫邊界繼續執行", "completed")
        return job.model_copy(deep=True)

    async def cancel(self, job_id: str, owner_id: str = "local") -> ResearchJob | None:
        job = self.jobs.get(job_id)
        control = self.controls.get(job_id)
        if job and self.owners.get(job_id, "local") != owner_id:
            return None
        if not job or not control:
            return await self.get(job_id, owner_id)
        if job.status not in {"completed", "failed", "cancelled"}:
            control.cancel_requested = True
            job.status = "cancel_requested"
            job.updated_at = utc_now()
            control.pause_gate.set()
            await self._persist(job)
        return job.model_copy(deep=True)

    async def purge(self, job_id: str, owner_id: str = "local") -> bool:
        """Permanently remove a job; a job still running is stopped first."""
        if not await self.get(job_id, owner_id):
            return False
        task = self.tasks.get(job_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        for table in (self.jobs, self.owners, self.controls, self.tasks, self._persist_locks):
            table.pop(job_id, None)
        await self.store.delete(job_id)
        return True

    async def _checkpoint(self, job: ResearchJob, control: _Control) -> None:
        if control.cancel_requested:
            raise ResearchCancelled("使用者取消研究")
        if not control.pause_gate.is_set():
            job.status = "paused"
            job.current_operation = "已到達安全邊界，等待繼續"
            job.updated_at = utc_now()
            await self._append_control_event(job, "研究暫停", "已完成進行中的 API 呼叫，現在停在安全工作邊界", "paused")
            await control.pause_gate.wait()
            if control.cancel_requested:
                raise ResearchCancelled("使用者取消研究")
            job.status = "running"
            job.updated_at = utc_now()

    async def _emit(self, job: ResearchJob, **payload) -> None:
        payload.pop("demo", None)
        payload["sequence"] = len(job.events) + 1
        payload["id"] = f"event_{payload['sequence']}_{uuid4().hex[:6]}"
        event = ResearchEvent.model_validate(payload)
        job.events.append(event)
        job.progress = max(job.progress, event.progress)
        job.current_phase = event.phase
        job.current_operation = event.action if event.status == "started" else None
        job.updated_at = utc_now()
        await self._persist(job)

    async def _append_control_event(self, job: ResearchJob, action: str, detail: str, status: str) -> None:
        sequence = len(job.events) + 1
        job.events.append(ResearchEvent(
            id=f"event_{sequence}_{uuid4().hex[:6]}", sequence=sequence,
            phase="control", agent="Control Agent", action=action, detail=detail,
            source="研究任務控制", status=status, progress=job.progress,
            metadata={"control_boundary": True},
        ))
        job.updated_at = utc_now()
        await self._persist(job)

    async def _run(self, job_id: str) -> None:
        job = self.jobs[job_id]
        control = self.controls[job_id]
        started = perf_counter()
        if control.cancel_requested:
            job.status = "cancel_requested"
        elif not control.pause_gate.is_set():
            job.status = "pause_requested"
        else:
            job.status = "running"
        job.updated_at = utc_now()
        await self._persist(job)
        capacity_acquired = False
        try:
            if self.capacity:
                await self.capacity.acquire(self.owners.get(job_id, "local"))
                capacity_acquired = True
            await self._checkpoint(job, control)
            result = await self.service.run(
                job.request,
                emit=lambda **payload: self._emit(job, **payload),
                checkpoint=lambda: self._checkpoint(job, control),
            )
            job.result = result
            job.evidence = result.evidence
            job.metrics = result.metrics
            job.usage = result.usage
            job.progress = 100
            job.status = "completed"
        except ResearchCancelled as exc:
            job.status = "cancelled"
            job.error = {"code": "cancelled", "message": str(exc), "retryable": False}
            await self._append_control_event(job, "取消研究", "任務已在安全工作邊界停止", "cancelled")
        except ResearchExecutionError as exc:
            job.status = "failed"
            job.error = {"code": exc.code, "message": str(exc), "retryable": exc.retryable}
        except PreviewLimitError as exc:
            job.status = "failed"
            job.error = {"code": "preview_limit", "message": str(exc), "retryable": False}
        except Exception as exc:
            job.status = "failed"
            job.error = {"code": "internal_error", "message": str(exc), "retryable": True}
        finally:
            job.duration_ms = round((perf_counter() - started) * 1000)
            job.completed_at = utc_now() if job.status in {"completed", "failed", "cancelled"} else None
            job.updated_at = utc_now()
            job.current_operation = None
            await self._persist(job)
            self.tasks.pop(job_id, None)
            if capacity_acquired:
                await self.capacity.release(self.owners.get(job_id, "local"))

    async def _persist(self, job: ResearchJob) -> None:
        # Serialize writes per job so two snapshots never race on the same record.
        lock = self._persist_locks.setdefault(job.id, asyncio.Lock())
        async with lock:
            await self.store.save(job, self.owners.get(job.id, "local"))
