"""
Amazon Seller ID 提取工具 — 启动器
双击运行即可启动 Web 服务并自动打开浏览器
"""

import importlib.util
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
REQUIREMENTS = BASE_DIR / "requirements.txt"
URL = "http://127.0.0.1:5000"
MAX_WAIT = 15  # 最大等待秒数


def check_dependencies():
    """检查核心依赖是否已安装"""
    # 格式: (requirements.txt 中的包名, Python 导入模块名)
    required = [
        ("flask", "flask"),
        ("curl_cffi", "curl_cffi"),
        ("beautifulsoup4", "bs4"),
        ("lxml", "lxml"),
        ("pandas", "pandas"),
        ("python_dotenv", "dotenv"),
    ]
    missing = []
    for pkg_name, module_name in required:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            missing.append(pkg_name)
    return missing


def wait_for_server(url: str, timeout: int = MAX_WAIT) -> bool:
    """轮询等待服务就绪"""
    import urllib.request

    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    os.chdir(BASE_DIR)

    print("=" * 50)
    print("Amazon Seller ID 提取工具")
    print("=" * 50)

    # 检查依赖
    missing = check_dependencies()
    if missing:
        print(f"\n⚠️ 检测到缺少依赖: {', '.join(missing)}")
        print("请先执行安装命令:\n")
        print("    pip install -r requirements.txt\n")
        print("安装完成后重新运行本程序。")
        try:
            input("\n按回车键退出...")
        except EOFError:
            pass
        sys.exit(1)

    print("\n✅ 依赖检查通过")
    print(f"🚀 正在启动服务...")

    # 导入 web_app（会触发 init_app，恢复队列并启动 worker）
    sys.path.insert(0, str(BASE_DIR))
    import web_app

    # 在后台线程中启动 Flask 服务
    import threading

    def run_flask():
        web_app.app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # 等待服务就绪
    print(f"⏳ 等待服务启动 ({URL})...")
    if wait_for_server(URL):
        print(f"✅ 服务已启动")
        print(f"🌐 正在打开浏览器...")
        webbrowser.open(URL)
    else:
        print(f"⚠️ 服务启动较慢，请手动打开浏览器访问: {URL}")

    print("\n" + "=" * 50)
    print("服务运行中，请勿关闭本窗口")
    print("按 Ctrl+C 停止服务")
    print("=" * 50 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 正在停止服务...")
        web_app.task_queue.stop_worker()
        print("👋 已退出")
        sys.exit(0)


if __name__ == "__main__":
    main()
