from __future__ import annotations

import fcntl
import hashlib
import json
import threading
import time
import uuid
from contextlib import contextmanager

from .models import AnalysisError, Stock

ACTIVE_STATUSES = ("running", "preparing", "pausing", "stopping", "resetting")
LEGACY_STATUSES = {"resetting": "stopping", "reset": "stopped"}


class JobManager:
    def __init__(self, engine):
        self.engine = engine
        self.lock = threading.RLock()
        self.lease = None
        self.thread = None
        self.active: str | None = None
        self.jobs = {item["id"]: item for item in engine.store.jobs(limit=-1)}
        if self._acquire():
            try:
                for job in self.jobs.values():
                    if job["status"] in ACTIVE_STATUSES:
                        job["status"] = "stopped" if self._stop_requested(job["id"]) else "paused"
                        self._save(job)
            finally:
                self._release()

    def _acquire(self):
        handle = (self.engine.directory / "scan.lock").open("a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        self.lease = handle
        return True

    def _release(self):
        if self.lease:
            fcntl.flock(self.lease, fcntl.LOCK_UN)
            self.lease.close()
            self.lease = None

    def is_running(self):
        with self.lock:
            if self.active or not self._acquire():
                return True
            self._release()
            return False

    @contextmanager
    def _history_guard(self):
        # 网页与 CLI 恢复任务时共用短锁，避免刚删除的暂停任务被并发恢复。
        with (self.engine.directory / "history.lock").open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _configuration(self):
        # 凭据可更换；同一任务的指标、模型、过滤与聚合口径不能中途改变。
        raw = self.engine.settings.model_dump(mode="json", exclude={"jev_api_key", "tushare_token", "language", "request_timeout", "request_interval"})
        return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()

    def _read(self, identifier):
        job = self.engine.store.job(identifier)
        if not job:
            raise AnalysisError("job_missing", "找不到扫描任务。", "Scan job not found.")
        return {**job, "status": LEGACY_STATUSES.get(job["status"], job["status"])}

    def _stop_requested(self, identifier):
        # 兼容旧版本的重置标记，历史任务不需要重写或重新执行。
        return self.engine.store.get(f"stop:{identifier}") or self.engine.store.get(f"reset:{identifier}")

    def _save(self, job):
        job["updated"] = time.time()
        self.engine.store.save_job(job)

    def list(self):
        with self.lock:
            # 较早的任务也能从历史中恢复，不能被最近 50 条的默认窗口隐藏。
            jobs = [self.summary(job) for job in self.engine.store.jobs(limit=-1)]
            return jobs[:50] + [job for job in jobs[50:] if job["status"] in ACTIVE_STATUSES]

    def search(self, scope="all", status="all", page=0, limit=20):
        status = LEGACY_STATUSES.get(status, status)
        with self.lock:
            jobs = [self.summary(job) for job in self.engine.store.jobs(limit=-1) if scope == "all" or job["scope"] == scope]
            matches = [job for job in jobs if status == "all" or job["status"] == status]
        total = len(matches)
        page = min(page, max(0, (total - 1) // limit))
        return {"items": matches[page * limit:(page + 1) * limit], "total": total, "page": page, "limit": limit}

    def summary(self, job):
        rows = job.get("items", [])
        job = {**job, "status": LEGACY_STATUSES.get(job["status"], job["status"])}
        if self._stop_requested(job["id"]):
            job = {**job, "status": "stopping" if job["status"] in ACTIVE_STATUSES else "stopped"}
        elif job["status"] in ("running", "preparing") and self.engine.store.get(f"pause:{job['id']}"):
            job = {**job, "status": "pausing"}
        return {**{key: value for key, value in job.items() if key not in ("items", "sessions")}, "total": len(rows), "downloaded": sum(item["data_status"] != "pending" for item in rows), "completed": sum(item["status"] == "ready" for item in rows), "failed": sum(item["status"] == "failed" for item in rows), "skipped": sum(item["status"] == "skipped" for item in rows), "remaining": sum(item["status"] == "pending" for item in rows)}

    def get(self, identifier):
        with self.lock:
            job = self._read(identifier)
            deleted = self.engine.store.deleted_ids("analysis")
            items = [{**item, "analysis_id": None, "analysis_deleted": True} if item.get("analysis_id") in deleted else item for item in job.get("items", [])]
            return {**self.summary(job), "items": items}

    def delete(self, identifiers):
        with self.lock, self._history_guard():
            for identifier in identifiers:
                job = self._read(identifier)
                if identifier == self.active or self.summary(job)["status"] in ACTIVE_STATUSES:
                    raise AnalysisError("job_active", "请先暂停或中止选中的运行任务，再删除扫描记录。", "Pause or stop the selected running tasks before deleting their records.")
            return self.engine.store.delete_records("job", identifiers)

    def restore(self, token):
        with self.lock, self._history_guard():
            return self.engine.store.restore_records("job", token)

    def start(self, symbols: list[str] | None = None) -> dict:
        if not self.engine.settings.jev_api_key.get_secret_value():
            raise AnalysisError("needs_key", "批量扫描前请先配置 Jev API key。", "Configure a Jev API key before starting a batch scan.")
        with self.lock:
            if self.active or not self._acquire():
                raise AnalysisError("job_active", "已有扫描正在运行，请先暂停。", "A scan is already running; pause it first.")
            identifier = uuid.uuid4().hex[:16]
            job = {"id": identifier, "created": time.time(), "status": "preparing", "phase": "preparing", "scope": "market" if symbols is None else "watchlist", "symbols": symbols, "items": [], "as_of": None, "error": None, "configuration": self._configuration()}
            self.jobs[identifier] = job
            self.active = identifier
            self._save(job)
            self.thread = threading.Thread(target=self._run, args=(identifier,), daemon=True)
            self.thread.start()
            return self.summary(job)

    def pause(self, identifier):
        with self.lock:
            job = self._read(identifier)
            if job["status"] in ("running", "preparing"):
                # 独立暂停标记避免另一个进程将整个任务快照写回并覆盖进度。
                self.engine.store.put(f"pause:{identifier}", True)
                job["status"] = "pausing"
            return self.summary(job)

    def resume(self, identifier, retry_failed=False):
        with self.lock, self._history_guard():
            job = self._read(identifier)
            if job["status"] in ("stopping", "stopped") or self._stop_requested(identifier):
                raise AnalysisError("job_stopped", "该任务已中止或正在中止，不能继续或重试。请开始新的扫描。", "This job is stopped or stopping and cannot be resumed or retried. Start a new scan.")
            if job.get("configuration") != self._configuration():
                raise AnalysisError("job_config_changed", "分析配置已变化，请新建扫描任务。", "Analysis configuration changed; start a new scan.")
            if not self.engine.settings.jev_api_key.get_secret_value():
                raise AnalysisError("needs_key", "请先配置 Jev API key。", "Configure a Jev API key first.")
            if self.active or not self._acquire():
                raise AnalysisError("job_active", "已有扫描正在运行。", "A scan is already running.")
            self.jobs[identifier] = job
            self.engine.store.put(f"pause:{identifier}", False)
            if retry_failed:
                for item in job["items"]:
                    if item["status"] == "failed":
                        item.update(status="pending", data_status="pending", error=None, analysis_id=None)
            job["status"], job["error"] = "running", None
            self.active = identifier
            self._save(job)
            self.thread = threading.Thread(target=self._run, args=(identifier,), daemon=True)
            self.thread.start()
            return self.summary(job)

    def stop(self, identifier):
        with self.lock, self._history_guard():
            job = self._read(identifier)
            if job["status"] in ("completed", "partial", "failed", "stopped"):
                return self.summary(job)
            # 只写控制标记，不覆盖其他进程正在保存的进度；保留历史分析与行情缓存。
            self.engine.store.put(f"stop:{identifier}", True)
            if not self.active and self._acquire():
                try:
                    job = self._read(identifier)
                    job["status"] = "stopped"
                    self._save(job)
                finally:
                    self._release()
            return self.summary(job)

    def reset(self, identifier):
        # 旧调用方仍可使用 reset；所有新界面和状态统一为中止。
        return self.stop(identifier)

    def _paused(self, job):
        with self.lock:
            if self._stop_requested(job["id"]):
                job["status"] = "stopped"
                self._save(job)
                return True
            if job["status"] == "pausing" or self.engine.store.get(f"pause:{job['id']}"):
                job["status"] = "paused"
                self._save(job)
                return True
            return False

    def _run(self, identifier):
        job = self.jobs[identifier]
        try:
            if self._paused(job):
                return
            sessions, cutoff = self.engine.context()
            if self._paused(job):
                return
            if job["as_of"] and job["as_of"] != cutoff.isoformat():
                raise AnalysisError("job_expired", "扫描的截止交易日已变化，请创建新任务，避免混用不同时点。", "The completed trading date has changed. Start a new scan to avoid mixing cutoffs.")
            job["as_of"] = cutoff.isoformat()
            if not job["items"]:
                stocks = self.engine.provider.universe()
                if self._paused(job):
                    return
                if job["symbols"] is not None:
                    wanted = set(job["symbols"])
                    stocks = [stock for stock in stocks if stock.symbol in wanted]
                    if len(stocks) != len(wanted):
                        raise AnalysisError("unknown_stock", "部分自选股票不在当前 A 股名单中。", "Some watchlist stocks are absent from the current universe.")
                job["items"] = [{"stock": stock.model_dump(), "data_status": "pending", "status": "pending", "analysis_id": None, "error": None} for stock in stocks]
            if self._paused(job):
                return
            job["status"], job["phase"] = "running", "data"
            self._save(job)
            for item in job["items"]:
                if self._paused(job):
                    return
                if item["data_status"] != "pending":
                    continue
                stock = Stock.model_validate(item["stock"])
                try:
                    self.engine.filter_stock(stock)
                    frame, _ = self.engine.provider.bars(stock.symbol, cutoff)
                    self.engine.check_frame(frame, cutoff)
                    item["above_ma20"] = bool(frame.close.iloc[-1] > frame.close.tail(20).mean())
                    item["data_status"] = "ready"
                except AnalysisError as exc:
                    filtered = exc.code in ("special_filtered", "market_filtered", "suspended", "insufficient_history", "liquidity_filtered")
                    item["data_status"], item["status"] = "skipped" if filtered else "failed", "skipped" if filtered else "failed"
                    item["error"] = {"code": exc.code, "zh": exc.zh, "en": exc.en}
                self._save(job)
            if self._paused(job):
                return
            if job["scope"] == "market":
                eligible = [item for item in job["items"] if item["status"] != "skipped"]
                valid = [item for item in eligible if item["data_status"] == "ready"]
                if valid:
                    self.engine.store.put(self.engine.breadth_key(cutoff), {"as_of": cutoff.isoformat(), "coverage": len(valid) / max(1, len(eligible)), "above_ma20_pct": 100 * sum(item["above_ma20"] for item in valid) / len(valid), "sample": len(valid)})
            job["phase"] = "analysis"
            self._save(job)
            for item in job["items"]:
                if self._paused(job):
                    return
                if item["status"] != "pending":
                    continue
                stock = Stock.model_validate(item["stock"])
                try:
                    analysis = self.engine.analyze(stock.symbol, stock=stock, pinned_context=(sessions, cutoff))
                    item["analysis_id"] = analysis.id
                    item["status"] = "ready" if analysis.status == "ready" else "failed"
                    item["action"], item["horizon"] = analysis.action, analysis.horizon
                    if analysis.status != "ready":
                        item["error"] = analysis.notices[-1]
                        # 认证或模型故障不会对整张股票表重复付费重试。
                        job["status"], job["error"] = "paused", item["error"]
                        self._save(job)
                        return
                except AnalysisError as exc:
                    item["status"], item["error"] = "failed", {"code": exc.code, "zh": exc.zh, "en": exc.en}
                self._save(job)
            if self._paused(job):
                return
            job["status"] = "partial" if any(item["status"] == "failed" for item in job["items"]) else "completed"
            self._save(job)
        except AnalysisError as exc:
            job["status"], job["error"] = "failed", {"code": exc.code, "zh": exc.zh, "en": exc.en}
            self._save(job)
        except Exception:
            job["status"], job["error"] = "failed", {"code": "internal_error", "zh": "扫描发生内部错误，请检查本地日志。", "en": "Internal scan error; check local logs."}
            self._save(job)
            import logging
            logging.getLogger(__name__).exception("Scan failed")
        finally:
            with self.lock:
                # 请求可能恰好在最后一次保存或异常处理时到达，退出前仍需确认。
                try:
                    self._paused(job)
                finally:
                    self.active = None
                    self._release()

    def shutdown(self):
        if self.active:
            self.pause(self.active)
        if self.thread:
            self.thread.join()
