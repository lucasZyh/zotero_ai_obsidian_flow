#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"


def main() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    api_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    dev_mode = os.environ.get("ZOTERO_FLOW_DEV", "").strip().lower() in {"1", "true", "yes"}
    frontend_proc = None
    try:
        if dev_mode:
            if not FRONTEND_DIR.exists():
                print(f"未找到前端目录: {FRONTEND_DIR}")
                return 1
            frontend_proc = subprocess.Popen(["npm", "run", "dev"], cwd=str(FRONTEND_DIR), env=env)
            print("前端开发服务器：http://127.0.0.1:5173")
        elif FRONTEND_DIST.exists():
            print("应用地址：http://127.0.0.1:8000")
        else:
            print("未找到 frontend/dist。请先运行：cd frontend && npm install && npm run build")
            print("或使用开发模式：ZOTERO_FLOW_DEV=1 python start_app.py")
        return subprocess.call(api_cmd, cwd=str(PROJECT_ROOT), env=env)
    except KeyboardInterrupt:
        print("\n已停止应用。")
        return 130
    finally:
        if frontend_proc and frontend_proc.poll() is None:
            frontend_proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())