"""
Flask Web 应用
- 单页应用入口、API、SSE 实时推送
- 启动时自动恢复队列状态并启动后台 worker
"""

import json
import queue as py_queue
import time
from pathlib import Path

from flask import Flask, render_template, request, jsonify, Response, send_file

import config
from task_queue import TaskQueue
from utils import load_urls

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB 上传限制

# ========== 全局队列实例 ==========
task_queue = TaskQueue(max_workers=config.DEFAULT_WORKERS)

# SSE 客户端队列列表
_sse_clients: list[py_queue.Queue] = []


def _broadcast_event(event: str, data: dict):
    """广播事件到所有 SSE 客户端"""
    dead = []
    for i, q in enumerate(_sse_clients):
        try:
            q.put_nowait((event, data))
        except py_queue.Full:
            pass
        except Exception:
            dead.append(i)
    # 清理死客户端（倒序删除）
    for i in reversed(dead):
        try:
            _sse_clients.pop(i)
        except IndexError:
            pass


# 绑定队列事件回调
task_queue.set_event_callback(_broadcast_event)


# ========== 页面路由 ==========

@app.route("/")
def index():
    return render_template("index.html")


# ========== API 路由 ==========

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """接收多行 URL 文本，创建新任务并入队"""
    data = request.get_json(silent=True) or {}
    raw = (data.get("urls") or "").strip()

    if not raw:
        return jsonify({"error": "请输入 URL"}), 400

    urls = []
    seen = set()
    for line in raw.splitlines():
        u = line.strip()
        if u and u not in seen:
            seen.add(u)
            urls.append(u)

    if not urls:
        return jsonify({"error": "未找到有效 URL"}), 400

    job_id = task_queue.add_job(urls, name=f"batch_{len(urls)}")

    return jsonify({
        "success": True,
        "job_id": job_id,
        "total": len(urls),
    })


@app.route("/api/jobs", methods=["GET"])
def api_jobs():
    """获取所有任务列表"""
    status = task_queue.get_status()
    return jsonify(status)


@app.route("/api/jobs/<job_id>", methods=["GET"])
def api_job_detail(job_id: str):
    """获取单个任务详情 + 结果预览"""
    job = task_queue.get_job(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404

    preview = task_queue.get_job_results_preview(job_id, limit=20)
    data = job.to_dict()
    data["preview"] = preview
    return jsonify(data)


@app.route("/api/jobs/<job_id>/download", methods=["GET"])
def api_job_download(job_id: str):
    """下载任务结果 CSV"""
    job = task_queue.get_job(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404

    path = Path(job.output_file)
    if not path.exists():
        return jsonify({"error": "结果文件尚未生成"}), 404

    return send_file(
        str(path),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{job.name}_seller_id.csv",
    )


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def api_job_cancel(job_id: str):
    """取消任务"""
    ok = task_queue.cancel_job(job_id)
    if not ok:
        return jsonify({"error": "任务不存在或已完成"}), 400
    return jsonify({"success": True})


@app.route("/api/queue/status", methods=["GET"])
def api_queue_status():
    """获取队列实时快照"""
    return jsonify(task_queue.get_status())


# ========== SSE 路由 ==========

@app.route("/api/stream")
def api_stream():
    """Server-Sent Events 端点"""
    client_q = py_queue.Queue(maxsize=100)
    _sse_clients.append(client_q)

    def event_stream():
        # 先推送一次当前状态
        try:
            status = task_queue.get_status()
            yield f"event: status\ndata: {json.dumps(status, ensure_ascii=False)}\n\n"
        except Exception:
            pass

        while True:
            try:
                event, data = client_q.get(timeout=30)
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            except py_queue.Empty:
                # 发送注释保持连接
                yield ":heartbeat\n\n"
            except Exception:
                break

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ========== 启动恢复 ==========

def init_app():
    """应用初始化：恢复状态并启动 worker"""
    restored = task_queue.load_state()
    task_queue.start_worker()
    if restored:
        print("[WebApp] 已恢复之前未完成的任务队列")
    else:
        print("[WebApp] 无历史任务，等待新任务")


init_app()


if __name__ == "__main__":
    # 本地开发模式
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
