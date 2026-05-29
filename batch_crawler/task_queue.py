"""
任务队列引擎
- 全局串行执行：所有 URL 进入同一个队列，单后台线程逐个消费
- 状态持久化：data/queue_state.json，崩溃后可恢复
- SSE 事件推送：通过回调函数通知前端
"""

import json
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import config
from crawler_http import process_single_url_http, _refresh_session
from utils import ensure_dirs, save_results

DATA_DIR = Path(config.BASE_DIR) / "data"
STATE_FILE = DATA_DIR / "queue_state.json"


@dataclass
class Job:
    id: str
    name: str
    total: int = 0
    processed: int = 0
    success: int = 0
    failed: int = 0
    status: str = "pending"  # pending | running | completed | cancelled
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    output_file: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        return cls(**d)


class TaskQueue:
    """全局任务队列，单线程串行消费"""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._jobs: Dict[str, Job] = {}
        self._current: Optional[Dict[str, Any]] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._session_counter = 0
        self._event_callback: Optional[Callable[[str, dict], None]] = None

        ensure_dirs()
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def set_event_callback(self, callback: Callable[[str, dict], None]):
        """设置 SSE 事件推送回调: callback(event_name, data_dict)"""
        self._event_callback = callback

    def _emit(self, event: str, data: dict):
        """内部触发事件"""
        if self._event_callback:
            try:
                self._event_callback(event, data)
            except Exception:
                pass

    def _persist_state(self):
        """原子写持久化状态"""
        try:
            pending = []
            # 遍历队列中的所有项（不消费）
            # queue.Queue 不支持直接遍历，需要临时取出再放回
            temp = []
            while True:
                try:
                    item = self._queue.get_nowait()
                    temp.append(item)
                    pending.append({"job_id": item[0], "url": item[1]})
                except queue.Empty:
                    break
            for item in temp:
                self._queue.put(item)

            state = {
                "version": 1,
                "pending": pending,
                "current": self._current,
                "jobs": {jid: job.to_dict() for jid, job in self._jobs.items()},
            }
            tmp_path = STATE_FILE.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            tmp_path.replace(STATE_FILE)
        except Exception as e:
            print(f"[TaskQueue] 持久化失败: {e}")

    def load_state(self) -> bool:
        """从磁盘恢复队列状态，返回是否成功恢复"""
        if not STATE_FILE.exists():
            return False
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            # 恢复 jobs
            self._jobs = {
                jid: Job.from_dict(jdata)
                for jid, jdata in state.get("jobs", {}).items()
            }

            # 恢复 pending 队列
            for item in state.get("pending", []):
                job_id = item.get("job_id")
                url = item.get("url")
                if job_id and url and job_id in self._jobs:
                    self._queue.put((job_id, url))
                    # 恢复 pending 状态
                    if self._jobs[job_id].status == "completed":
                        self._jobs[job_id].status = "pending"

            # 恢复 current（如果之前有正在处理的，重新入队）
            current = state.get("current")
            if current:
                job_id = current.get("job_id")
                url = current.get("url")
                if job_id and url and job_id in self._jobs:
                    self._queue.put((job_id, url))
                    if self._jobs[job_id].status == "completed":
                        self._jobs[job_id].status = "pending"

            print(f"[TaskQueue] 状态恢复: {len(self._jobs)} 个任务, {self._queue.qsize()} 个 URL 待处理")
            return True
        except Exception as e:
            print(f"[TaskQueue] 状态恢复失败: {e}，将重置状态")
            self._jobs = {}
            self._queue = queue.Queue()
            return False

    def add_job(self, urls: List[str], name: str) -> str:
        """创建新任务并入队，返回 job_id"""
        job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        output_file = str(Path(config.OUTPUT_DIR) / f"{job_id}_seller_id.csv")

        # 去重
        seen = set()
        unique_urls = []
        for u in urls:
            u = u.strip()
            if u and u not in seen:
                seen.add(u)
                unique_urls.append(u)

        job = Job(
            id=job_id,
            name=name,
            total=len(unique_urls),
            output_file=output_file,
        )

        with self._lock:
            self._jobs[job_id] = job
            for url in unique_urls:
                self._queue.put((job_id, url))

        self._persist_state()
        self._emit("job_added", job.to_dict())
        print(f"[TaskQueue] 新增任务 {job_id}: {job.name}, {job.total} 个 URL")
        return job_id

    def cancel_job(self, job_id: str) -> bool:
        """取消任务：清空该任务在队列中的 URL，标记状态"""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            if job.status == "completed":
                return False

            job.status = "cancelled"

            # 从队列中移除该 job 的 URL（临时取出筛选后放回）
            temp = []
            removed = 0
            while True:
                try:
                    item = self._queue.get_nowait()
                    if item[0] == job_id:
                        removed += 1
                    else:
                        temp.append(item)
                except queue.Empty:
                    break
            for item in temp:
                self._queue.put(item)

        self._persist_state()
        self._emit("job_cancelled", {"job_id": job_id, "removed": removed})
        print(f"[TaskQueue] 任务取消 {job_id}, 移除 {removed} 个待处理 URL")
        return True

    def get_status(self) -> dict:
        """获取队列实时快照"""
        with self._lock:
            return {
                "queue_size": self._queue.qsize(),
                "current": self._current,
                "jobs": [job.to_dict() for job in self._jobs.values()],
            }

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def start_worker(self):
        """启动后台工作线程"""
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        print("[TaskQueue] 工作线程已启动")

    def stop_worker(self):
        """停止后台工作线程"""
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def _worker_loop(self):
        """后台消费者主循环：严格串行逐个处理 URL"""
        while not self._stop_event.is_set():
            try:
                job_id, url = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            with self._lock:
                job = self._jobs.get(job_id)
                if not job or job.status == "cancelled":
                    self._queue.task_done()
                    continue

                # 标记当前处理
                self._current = {
                    "job_id": job_id,
                    "url": url,
                    "started_at": datetime.now().isoformat(),
                }
                if job.status == "pending":
                    job.status = "running"

            self._persist_state()
            self._emit("progress", {
                "job_id": job_id,
                "url": url,
                "type": "start",
                "queue_left": self._queue.qsize(),
            })

            try:
                result = process_single_url_http(url)
                # 写入结果 CSV（IO 操作在锁外进行）
                save_results([result], job.output_file, mode="a")

                with self._lock:
                    # 更新计数
                    job.processed += 1
                    if result.get("status") == "success" and result.get("seller_id"):
                        job.success += 1
                    else:
                        job.failed += 1
                    job_processed = job.processed
                    job_total = job.total

                self._emit("progress", {
                    "job_id": job_id,
                    "url": url,
                    "type": "done",
                    "status": result.get("status"),
                    "seller_id": result.get("seller_id"),
                    "seller_name": result.get("seller_name"),
                    "title": result.get("title"),
                    "error": result.get("error"),
                    "queue_left": self._queue.qsize(),
                    "job_processed": job_processed,
                    "job_total": job_total,
                })

            except Exception as e:
                with self._lock:
                    job.processed += 1
                    job.failed += 1
                    job_processed = job.processed
                    job_total = job.total

                self._emit("progress", {
                    "job_id": job_id,
                    "url": url,
                    "type": "error",
                    "error": str(e),
                    "queue_left": self._queue.qsize(),
                    "job_processed": job_processed,
                    "job_total": job_total,
                })

            # Session 定期刷新（串行模式下每 15 个 URL 刷新一次）
            self._session_counter += 1
            if self._session_counter % 15 == 0:
                try:
                    _refresh_session()
                except Exception:
                    pass

            with self._lock:
                # 检查任务是否完成
                if job.processed >= job.total:
                    job.status = "completed"
                    self._emit("job_complete", {"job_id": job_id, "job": job.to_dict()})
                    print(f"[TaskQueue] 任务完成 {job_id}: {job.success}/{job.total}")

                self._current = None
            self._queue.task_done()
            self._persist_state()

    def get_job_results_preview(self, job_id: str, limit: int = 20) -> List[dict]:
        """读取任务结果 CSV 的前 N 条作为预览"""
        job = self._jobs.get(job_id)
        if not job or not Path(job.output_file).exists():
            return []
        try:
            import csv
            rows = []
            with open(job.output_file, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    if i >= limit:
                        break
                    rows.append(dict(row))
            return rows
        except Exception:
            return []
