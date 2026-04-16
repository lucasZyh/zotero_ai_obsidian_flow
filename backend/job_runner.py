from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.config import (
    LAST_RUN_LOG_PATH,
    PROJECT_ROOT,
    get_effective_paths,
    load_provider_settings,
    provider_spec_for_ui,
    save_provider_settings,
)
from backend.schemas import JobStartRequest


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def count_progress_from_log(content: str, dry_run: bool) -> int:
    if not content:
        return 0
    if dry_run:
        return len(re.findall(r"^\[DRY-RUN\]\s*将处理论文\s*:", content, flags=re.M))
    return len(re.findall(r"^\[OK\]\s*已写入\s*:", content, flags=re.M))


class JobRunner:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._proc: subprocess.Popen[str] | None = None
        self._meta: dict[str, Any] = {
            "state": "idle",
            "running": False,
            "returncode": None,
            "command": "",
            "log_path": "",
            "target_limit": 0,
            "dry_run": False,
            "started_at": None,
            "finished_at": None,
            "stopped": False,
        }

    def _refresh_locked(self) -> None:
        if not self._proc:
            return
        rc = self._proc.poll()
        if rc is None:
            self._meta["state"] = "running"
            self._meta["running"] = True
            return
        self._meta["running"] = False
        self._meta["returncode"] = rc
        self._meta["finished_at"] = self._meta.get("finished_at") or _now_iso()
        if self._meta.get("stopped"):
            self._meta["state"] = "stopped"
        elif rc == 0:
            self._meta["state"] = "succeeded"
        else:
            self._meta["state"] = "failed"
        self._proc = None

    def _read_log_unlocked(self, tail: int = 30000) -> str:
        if not self._meta.get("started_at"):
            return ""
        log_path = Path(str(self._meta.get("log_path") or LAST_RUN_LOG_PATH))
        if not log_path.exists():
            return ""
        content = log_path.read_text(encoding="utf-8", errors="ignore")
        if tail > 0:
            return content[-tail:]
        return content

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            log_content = self._read_log_unlocked()
            progress_count = count_progress_from_log(log_content, bool(self._meta.get("dry_run")))
            target_limit = int(self._meta.get("target_limit") or 0)
            progress_text = f"{progress_count}/{target_limit}" if target_limit > 0 else str(progress_count)
            return {
                **self._meta,
                "progress_count": progress_count,
                "progress_text": progress_text,
            }

    def log(self, tail: int = 30000) -> dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            return {"content": self._read_log_unlocked(tail), "status": self.status()}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            if not self._proc:
                return self.status()
            self._meta["stopped"] = True
            self._proc.terminate()
        return self.status()

    def start(self, payload: JobStartRequest) -> dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            if self._proc and self._proc.poll() is None:
                raise RuntimeError("已有论文精读任务正在运行，请等待完成或先停止当前任务。")

            paths = get_effective_paths()
            provider_config = paths["provider_config_path"]
            template_path = self._resolve_template(paths["template_dir_path"], payload.template_name)
            if not template_path.exists():
                raise ValueError(f"模板不存在：{template_path}")
            if not payload.model.strip():
                raise ValueError("请填写模型名。")
            self._validate_scope(payload)
            self._persist_model(provider_config, payload.provider, payload.model)

            cmd = self._build_command(payload, paths, template_path, provider_config)
            cmd_display = " ".join(shlex.quote(x) for x in cmd)
            run_env = os.environ.copy()
            run_env["PYTHONUNBUFFERED"] = "1"
            LAST_RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            LAST_RUN_LOG_PATH.write_text("", encoding="utf-8")
            log_handle = open(LAST_RUN_LOG_PATH, "a", encoding="utf-8")
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(PROJECT_ROOT),
                    text=True,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    env=run_env,
                )
            finally:
                log_handle.close()

            self._proc = proc
            self._meta = {
                "state": "running",
                "running": True,
                "returncode": None,
                "command": cmd_display,
                "log_path": str(LAST_RUN_LOG_PATH),
                "target_limit": int(payload.limit),
                "dry_run": bool(payload.dry_run),
                "started_at": _now_iso(),
                "finished_at": None,
                "stopped": False,
                "provider": payload.provider,
                "model": payload.model,
                "scan_mode": payload.scan_mode,
            }
            return self.status()

    def _resolve_template(self, template_dir: str, template_name: str) -> Path:
        raw = Path(template_name).expanduser()
        if raw.is_absolute():
            return raw
        return Path(template_dir).expanduser() / template_name

    def _validate_scope(self, payload: JobStartRequest) -> None:
        if payload.scan_mode in {"collection_paper", "collection_all"} and not payload.collections:
            raise ValueError("请至少选择一个 Zotero 目录。")
        if payload.scan_mode == "single_item":
            if not payload.collections:
                raise ValueError("请先选择目录。")
            if not (payload.collection_item_key or "").strip():
                raise ValueError("请先选择目录中的论文。")
        if payload.scan_mode == "parent_keys" and not [k for k in payload.parent_item_keys if k.strip()]:
            raise ValueError("请至少输入一个父条目 key。")
        if payload.scan_mode == "global" and not payload.allow_global_scan:
            raise ValueError("全库扫描需要显式确认。")

    def _persist_model(self, provider_config: str, provider: str, model: str) -> None:
        settings = load_provider_settings(provider_config)
        spec = provider_spec_for_ui(provider, settings)
        providers = settings.setdefault("providers", {})
        old = providers.get(provider, {})
        if not isinstance(old, dict):
            old = {}
        custom_models = old.get("custom_models", [])
        if not isinstance(custom_models, list):
            custom_models = []
        if model not in spec["models"] and model not in custom_models:
            custom_models.append(model)
        providers[provider] = {
            "model": model,
            "provider_type": old.get("provider_type", spec.get("provider_type", "openai_compatible")),
            "base_url": old.get("base_url", spec.get("base_url", "")),
            "custom_models": custom_models,
        }
        save_provider_settings(provider_config, settings)

    def _build_command(
        self,
        payload: JobStartRequest,
        paths: dict[str, str],
        template_path: Path,
        provider_config: str,
    ) -> list[str]:
        cmd = [
            sys.executable,
            "-u",
            "pipeline.py",
            "--provider",
            payload.provider,
            "--template",
            str(template_path),
            "--obsidian-root",
            paths["obsidian_root_path"],
            "--zotero-db",
            paths["zotero_db_path"],
            "--zotero-storage",
            paths["zotero_storage_path"],
            "--provider-config",
            provider_config,
            "--limit",
            str(int(payload.limit)),
            "--since-days",
            str(int(payload.since_days)),
            "--pdf-parser",
            payload.pdf_parser,
            "--mineru-model-version",
            payload.mineru_model_version.strip() or "vlm",
            "--mineru-language",
            payload.mineru_language.strip() or "en",
            "--model",
            payload.model.strip(),
        ]
        if payload.enable_thinking:
            cmd.append("--enable-thinking")
        if payload.dry_run:
            cmd.append("--dry-run")
        if payload.force:
            cmd.append("--force")
        if payload.scan_mode in {"collection_paper", "collection_all", "single_item"}:
            for collection in payload.collections:
                cmd += ["--collection", collection]
        if payload.scan_mode in {"collection_all", "single_item"}:
            cmd.append("--collection-all-types")
        if payload.scan_mode == "single_item" and payload.collection_item_key:
            cmd += ["--collection-item-key", payload.collection_item_key, "--limit", "1"]
        if payload.scan_mode == "parent_keys":
            for key in payload.parent_item_keys:
                if key.strip():
                    cmd += ["--parent-item-key", key.strip()]
        if payload.scan_mode == "global":
            cmd.append("--allow-global-scan")
        return cmd


job_runner = JobRunner()
