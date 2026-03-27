#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
APP_PATH = PROJECT_ROOT / "app.py"


def main() -> int:
    if not APP_PATH.exists():
        print(f"未找到 app.py: {APP_PATH}")
        return 1

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP_PATH),
        "--server.address",
        "127.0.0.1",
    ]
    try:
        return subprocess.call(cmd, cwd=str(PROJECT_ROOT), env=env)
    except KeyboardInterrupt:
        print("\n已停止 Streamlit。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
