from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

from pipeline import (
    copy_db_to_temp,
    default_provider_config_path,
    list_collections,
    list_papers_in_collection,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PROJECT_ROOT / "templates"
UI_SETTINGS_PATH = PROJECT_ROOT / ".config" / "ui_paths.json"
ENV_PATH = PROJECT_ROOT / ".env"
STATE_FILE_PATH = PROJECT_ROOT / ".state" / "processed_items.json"
LAST_RUN_LOG_PATH = PROJECT_ROOT / ".state" / "last_run.log"
DEFAULT_OBSIDIAN_VAULT = str(Path.home() / "Documents" / "Obsidian")
DEFAULT_OBSIDIAN_FOLDER = "论文精读"
DEFAULT_ZOTERO_DB = str(Path.home() / "Zotero" / "zotero.sqlite")
DEFAULT_ZOTERO_STORAGE = str(Path.home() / "Zotero" / "storage")
DEFAULT_MINERU_MODEL_VERSION = "vlm"
DEFAULT_MINERU_LANGUAGE = "en"


def _path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except Exception:
        return 0.0


def find_obsidian_vault_candidates() -> list[Path]:
    roots = [
        Path.home() / "Documents" / "Obsidian",
        Path.home() / "Obsidian",
        Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents",
    ]
    seen: set[str] = set()
    candidates: list[Path] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        to_check = [root]
        try:
            to_check.extend([p for p in root.iterdir() if p.is_dir()])
        except Exception:
            pass
        for candidate in to_check:
            if not candidate.exists() or not candidate.is_dir():
                continue
            if not (candidate / ".obsidian").exists():
                continue
            key = str(candidate.resolve())
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    candidates.sort(key=lambda p: (-_path_mtime(p / ".obsidian"), -_path_mtime(p), p.name.lower()))
    return candidates


def detect_obsidian_vault_path() -> str:
    candidates = find_obsidian_vault_candidates()
    if candidates:
        return str(candidates[0])
    return DEFAULT_OBSIDIAN_VAULT


def split_obsidian_output_path(raw_path: str) -> tuple[str, str]:
    raw = (raw_path or "").strip()
    if not raw:
        return detect_obsidian_vault_path(), DEFAULT_OBSIDIAN_FOLDER
    path = Path(raw).expanduser()
    current = path
    while True:
        if (current / ".obsidian").exists():
            if current == path:
                return str(current), ""
            rel = path.relative_to(current)
            return str(current), rel.as_posix()
        if current.parent == current:
            break
        current = current.parent
    return str(path), ""


def compose_obsidian_output_path(vault_path: str, folder_path: str) -> str:
    vault = Path(vault_path or detect_obsidian_vault_path()).expanduser()
    folder = (folder_path or "").strip().strip("/").strip()
    if not folder:
        return str(vault)
    return str(vault / Path(folder))


def find_zotero_path_candidates() -> tuple[list[Path], list[Path]]:
    data_roots = [
        Path.home() / "Zotero",
        Path.home() / "Library" / "Application Support" / "Zotero",
    ]
    db_candidates: list[Path] = []
    storage_candidates: list[Path] = []
    seen_db: set[str] = set()
    seen_storage: set[str] = set()
    for root in data_roots:
        db_path = root / "zotero.sqlite"
        if db_path.exists():
            key = str(db_path.resolve())
            if key not in seen_db:
                seen_db.add(key)
                db_candidates.append(db_path)
        storage_path = root / "storage"
        if storage_path.exists() and storage_path.is_dir():
            key = str(storage_path.resolve())
            if key not in seen_storage:
                seen_storage.add(key)
                storage_candidates.append(storage_path)
    db_candidates.sort(key=lambda p: (-_path_mtime(p), str(p).lower()))
    storage_candidates.sort(key=lambda p: (-_path_mtime(p), str(p).lower()))
    return db_candidates, storage_candidates


def detect_zotero_paths() -> tuple[str, str]:
    db_candidates, storage_candidates = find_zotero_path_candidates()
    db_path = db_candidates[0] if db_candidates else Path(DEFAULT_ZOTERO_DB).expanduser()
    sibling_storage = db_path.parent / "storage"
    if sibling_storage.exists() and sibling_storage.is_dir():
        storage_path = sibling_storage
    elif storage_candidates:
        storage_path = storage_candidates[0]
    else:
        storage_path = Path(DEFAULT_ZOTERO_STORAGE).expanduser()
    return str(db_path), str(storage_path)


def load_ui_settings() -> dict[str, Any]:
    if not UI_SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(UI_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_ui_settings(data: dict[str, Any]) -> None:
    UI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    UI_SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_effective_paths() -> dict[str, str]:
    ui_saved = load_ui_settings()
    detected_obsidian_vault = detect_obsidian_vault_path()
    detected_zotero_db, detected_zotero_storage = detect_zotero_paths()
    saved_obsidian_root = str(ui_saved.get("obsidian_root_path") or "")
    saved_obsidian_vault = str(ui_saved.get("obsidian_vault_path") or "")
    saved_obsidian_folder = str(ui_saved.get("obsidian_folder_path") or "")
    if saved_obsidian_root and not (saved_obsidian_vault or saved_obsidian_folder):
        saved_obsidian_vault, saved_obsidian_folder = split_obsidian_output_path(saved_obsidian_root)
    obsidian_vault_path = saved_obsidian_vault or detected_obsidian_vault
    obsidian_folder_path = saved_obsidian_folder or DEFAULT_OBSIDIAN_FOLDER
    obsidian_root_path = compose_obsidian_output_path(obsidian_vault_path, obsidian_folder_path)
    return {
        "provider_config_path": str(ui_saved.get("provider_config_path") or default_provider_config_path()),
        "template_dir_path": str(ui_saved.get("template_dir_path") or TEMPLATES_DIR),
        "obsidian_vault_path": obsidian_vault_path,
        "obsidian_folder_path": obsidian_folder_path,
        "obsidian_root_path": obsidian_root_path,
        "zotero_db_path": str(ui_saved.get("zotero_db_path") or detected_zotero_db),
        "zotero_storage_path": str(ui_saved.get("zotero_storage_path") or detected_zotero_storage),
    }


def persist_paths(data: dict[str, Any]) -> dict[str, str]:
    saved = load_ui_settings()
    current = get_effective_paths()
    merged = {**saved, **current, **{k: str(v) for k, v in data.items() if v is not None}}
    merged["obsidian_root_path"] = compose_obsidian_output_path(
        merged.get("obsidian_vault_path", ""),
        merged.get("obsidian_folder_path", ""),
    )
    save_ui_settings(merged)
    return get_effective_paths()


def get_mineru_ui_settings() -> dict[str, str]:
    saved = load_ui_settings()
    return {
        "model_version": str(saved.get("mineru_model_version") or DEFAULT_MINERU_MODEL_VERSION),
        "language": str(saved.get("mineru_language") or DEFAULT_MINERU_LANGUAGE),
    }


def persist_mineru_ui_settings(data: dict[str, Any]) -> dict[str, str]:
    saved = load_ui_settings()
    if data.get("model_version") is not None:
        saved["mineru_model_version"] = str(data.get("model_version") or "").strip() or DEFAULT_MINERU_MODEL_VERSION
    if data.get("language") is not None:
        saved["mineru_language"] = str(data.get("language") or "").strip() or DEFAULT_MINERU_LANGUAGE
    save_ui_settings(saved)
    return get_mineru_ui_settings()


def _env_quote(v: str) -> str:
    return '"' + (v or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def load_env_map(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        key = k.strip()
        val = v.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        out[key] = val
    return out


def save_env_map(values: dict[str, str], path: Path = ENV_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={_env_quote(v)}" for k, v in sorted(values.items()) if isinstance(k, str) and k.strip()]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def get_env_value(key: str) -> str:
    return load_env_map().get((key or "").strip(), "")


def set_env_value(key: str, value: str) -> None:
    env_key = (key or "").strip()
    if not env_key:
        return
    envs = load_env_map()
    if value.strip():
        envs[env_key] = value.strip()
    else:
        envs.pop(env_key, None)
    save_env_map(envs)


def sanitize_provider_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return ""
    out = []
    for ch in n:
        cat = unicodedata.category(ch)
        if cat.startswith("C"):
            continue
        if cat.startswith("L") or cat.startswith("N") or ch in {"_", "-", "."}:
            out.append(ch)
    n2 = "".join(out).strip()
    has_visible = any(not c.isspace() for c in n2)
    return n2 if has_visible else ""


def provider_env_key(provider_name: str, spec: dict[str, Any] | None = None) -> str:
    spec = spec or {}
    env_var = str(spec.get("env_var") or "").strip()
    if env_var:
        return env_var
    base = re.sub(r"[^A-Za-z0-9]+", "_", provider_name).strip("_").upper()
    return f"{base}_API_KEY" if base else "PROVIDER_API_KEY"


def load_provider_settings(path: str) -> dict[str, Any]:
    p = Path(path).expanduser()
    if not p.exists():
        return {"providers": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {"providers": {}}
    if not isinstance(data, dict):
        data = {"providers": {}}
    data = normalize_provider_settings(data)
    if "providers" not in data or not isinstance(data["providers"], dict):
        data["providers"] = {}
    cleaned = {}
    for k, v in data["providers"].items():
        if not isinstance(k, str):
            continue
        nk = sanitize_provider_name(k)
        if not nk:
            continue
        cleaned[nk] = v if isinstance(v, dict) else {}
    data["providers"] = cleaned
    return data


def normalize_provider_settings(data: dict[str, Any]) -> dict[str, Any]:
    providers_raw = data.get("providers") if isinstance(data.get("providers"), dict) else {}
    specs_raw = data.get("provider_specs") if isinstance(data.get("provider_specs"), dict) else {}
    unified: dict[str, Any] = {}

    for name, item in specs_raw.items():
        if not isinstance(item, dict):
            continue
        models = item.get("models", [])
        if not isinstance(models, list):
            models = []
        unified[str(name)] = {
            "provider_type": item.get("provider_type") or "openai_compatible",
            "env_var": item.get("env_var") or provider_env_key(str(name), {}),
            "default_model": item.get("default_model") or (models[0] if models else ""),
            "models": [str(m).strip() for m in models if str(m).strip()],
            "base_url": item.get("base_url"),
        }

    for name, item in providers_raw.items():
        if not isinstance(item, dict):
            continue
        existing = dict(unified.get(str(name), {}))
        item_models = item.get("models", [])
        if not isinstance(item_models, list):
            item_models = []
        custom_models = item.get("custom_models", [])
        if not isinstance(custom_models, list):
            custom_models = []
        models = list(existing.get("models", []))
        for m in [*item_models, *custom_models, item.get("model") or item.get("default_model")]:
            text = str(m or "").strip()
            if text and text not in models:
                models.append(text)
        unified[str(name)] = {
            "provider_type": item.get("provider_type") or existing.get("provider_type") or "openai_compatible",
            "env_var": item.get("env_var") or existing.get("env_var") or provider_env_key(str(name), {}),
            "default_model": item.get("default_model") or item.get("model") or existing.get("default_model") or (models[0] if models else ""),
            "models": models,
            "base_url": item.get("base_url", existing.get("base_url")),
        }

    return {"providers": unified}


def save_provider_settings(path: str, settings: dict[str, Any]) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    settings = normalize_provider_settings(settings)
    p.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass


def set_provider_api_key(provider_name: str, spec: dict[str, Any] | None, api_key: str) -> None:
    key_name = provider_env_key(provider_name, spec)
    envs = load_env_map()
    if api_key.strip():
        envs[key_name] = api_key.strip()
    else:
        envs.pop(key_name, None)
    save_env_map(envs)


def clean_and_persist_provider_settings(path: str) -> dict[str, Any]:
    settings = load_provider_settings(path)
    providers = settings.setdefault("providers", {})
    migrated = False
    for pname, pitem in list(providers.items()):
        if not isinstance(pitem, dict):
            continue
        old_key = str(pitem.get("api_key", "") or "").strip()
        if old_key:
            set_provider_api_key(pname, pitem, old_key)
            pitem.pop("api_key", None)
            migrated = True
    if migrated or "provider_specs" in settings:
        save_provider_settings(path, settings)
        settings = load_provider_settings(path)
    return settings


def normalize_provider_names(names: list[str]) -> list[str]:
    out = []
    seen = set()
    for n in names:
        nn = sanitize_provider_name(n)
        if not nn or nn in seen:
            continue
        out.append(nn)
        seen.add(nn)
    return out


def get_provider_names(settings: dict[str, Any]) -> list[str]:
    names = [
        sanitize_provider_name(k)
        for k in list((settings.get("providers") or {}).keys())
        if isinstance(k, str)
    ]
    return sorted(set([k for k in names if k]))


def provider_spec_for_ui(provider: str, settings: dict[str, Any]) -> dict[str, Any]:
    saved = dict(((settings.get("providers") or {}).get(provider) or {}))
    models = [str(m).strip() for m in list(saved.get("models", [])) if str(m).strip()]
    default_model = saved.get("default_model") or saved.get("model") or ""
    if default_model and default_model not in models:
        models.append(default_model)
    env_var = provider_env_key(provider, saved)
    api_key = load_env_map().get(env_var, "")
    return {
        "name": provider,
        "provider_type": saved.get("provider_type") or "openai_compatible",
        "base_url": saved.get("base_url") or "",
        "default_model": default_model,
        "models": models,
        "custom_models": models,
        "env_var": env_var,
        "api_key": api_key,
        "has_api_key": bool(api_key),
    }


def get_provider_payload(provider_config_path: str) -> dict[str, Any]:
    settings = clean_and_persist_provider_settings(provider_config_path)
    names = normalize_provider_names(get_provider_names(settings))
    return {
        "providers": [provider_spec_for_ui(name, settings) for name in names],
        "provider_config_path": provider_config_path,
    }


def upsert_provider(provider_config_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    settings = clean_and_persist_provider_settings(provider_config_path)
    name = sanitize_provider_name(str(payload.get("name") or ""))
    if not name:
        raise ValueError("供应商名称不能为空。")
    providers = settings.setdefault("providers", {})
    existing = providers.get(name, {}) if isinstance(providers.get(name, {}), dict) else {}
    is_new = bool(payload.get("is_new")) or name not in providers
    if is_new and not str(payload.get("api_key") or "").strip():
        raise ValueError("新增供应商必须填写 API Key，API Key 会保存到本地 .env。")
    provider_type = str(payload.get("provider_type") or existing.get("provider_type") or "openai_compatible")
    base_url = str(payload.get("base_url") or "")
    model = str(payload.get("model") or payload.get("default_model") or "").strip()
    env_var = str(payload.get("env_var") or existing.get("env_var") or provider_env_key(name, {})).strip()
    raw_custom_models = payload.get("custom_models", [])
    if isinstance(raw_custom_models, str):
        custom_models = [m.strip() for m in raw_custom_models.split(",") if m.strip()]
    elif isinstance(raw_custom_models, list):
        custom_models = [str(m).strip() for m in raw_custom_models if str(m).strip()]
    else:
        custom_models = []
    models = []
    for item in [*custom_models, model]:
        text = str(item or "").strip()
        if text and text not in models:
            models.append(text)
    providers[name] = {
        "provider_type": provider_type,
        "env_var": env_var,
        "default_model": model,
        "models": models,
        "base_url": base_url or None,
    }
    if "api_key" in payload and payload["api_key"] is not None:
        set_provider_api_key(name, providers[name], str(payload["api_key"]))
    save_provider_settings(provider_config_path, settings)
    return provider_spec_for_ui(name, settings)


def delete_provider(provider_config_path: str, provider_name: str) -> None:
    settings = clean_and_persist_provider_settings(provider_config_path)
    name = sanitize_provider_name(provider_name)
    providers = settings.setdefault("providers", {})
    if not name or name not in providers:
        raise ValueError(f"供应商不存在：{provider_name}")
    existing = providers.pop(name)
    if isinstance(existing, dict):
        set_provider_api_key(name, existing, "")
    save_provider_settings(provider_config_path, settings)


def list_template_files(template_dir: str) -> list[dict[str, str]]:
    d = Path(template_dir).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    files = sorted(d.glob("*.md"), key=lambda p: p.name.lower())
    return [{"name": p.name, "path": str(p)} for p in files]


def load_collection_names(zotero_db: str) -> list[str]:
    if not Path(zotero_db).expanduser().exists():
        return []
    temp_db = copy_db_to_temp(zotero_db)
    conn = None
    try:
        conn = sqlite3.connect(temp_db)
        return list_collections(conn)
    finally:
        if conn:
            conn.close()
        Path(temp_db).unlink(missing_ok=True)


def load_papers_for_collection(zotero_db: str, collection_name: str, since_days: int) -> list[dict[str, Any]]:
    if not Path(zotero_db).expanduser().exists() or not collection_name:
        return []
    temp_db = copy_db_to_temp(zotero_db)
    conn = None
    try:
        conn = sqlite3.connect(temp_db)
        rows = list_papers_in_collection(conn, collection_name, since_days=since_days)
        return [{"key": k, "title": t, "date_modified": d} for k, t, d in rows]
    finally:
        if conn:
            conn.close()
        Path(temp_db).unlink(missing_ok=True)
