from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _json_post(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int = 20) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read(1600).decode("utf-8", errors="replace")


def _error_message(exc: Exception) -> tuple[int | None, str]:
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read(1600).decode("utf-8", errors="replace")
        detail = body.strip() or str(exc)
        return int(exc.code), detail[:600]
    if isinstance(exc, urllib.error.URLError):
        return None, str(exc.reason)[:600]
    return None, str(exc)[:600]


def _chat_completions_url(base_url: str) -> str:
    base = (base_url or "https://api.openai.com/v1").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _gemini_url(base_url: str, model: str, api_key: str) -> str:
    base = (base_url or "https://generativelanguage.googleapis.com/v1beta").strip().rstrip("/")
    model_path = model.strip()
    if not model_path.startswith("models/"):
        model_path = f"models/{model_path}"
    quoted_model = urllib.parse.quote(model_path, safe="/")
    quoted_key = urllib.parse.quote(api_key.strip(), safe="")
    return f"{base}/{quoted_model}:generateContent?key={quoted_key}"


def test_provider_connection(payload: dict[str, Any]) -> dict[str, Any]:
    provider_type = str(payload.get("provider_type") or "openai_compatible")
    model = str(payload.get("model") or "").strip()
    api_key = str(payload.get("api_key") or "").strip()
    base_url = str(payload.get("base_url") or "").strip()
    started = time.monotonic()

    if not model:
        return {"ok": False, "status": None, "message": "请先填写默认模型。", "elapsed_ms": 0}
    if not api_key:
        return {"ok": False, "status": None, "message": "请先填写 API Key。", "elapsed_ms": 0}

    try:
        if provider_type == "gemini":
            endpoint = _gemini_url(base_url, model, api_key)
            status, _ = _json_post(
                endpoint,
                {"Content-Type": "application/json"},
                {
                    "contents": [{"parts": [{"text": "ping"}]}],
                    "generationConfig": {"temperature": 0, "maxOutputTokens": 8},
                },
            )
        else:
            endpoint = _chat_completions_url(base_url)
            status, _ = _json_post(
                endpoint,
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                {
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "temperature": 0,
                    "max_tokens": 8,
                },
            )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {"ok": 200 <= status < 300, "status": status, "message": "连通性测试通过。", "elapsed_ms": elapsed_ms}
    except Exception as exc:
        status, message = _error_message(exc)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {"ok": False, "status": status, "message": message or "连通性测试失败。", "elapsed_ms": elapsed_ms}
