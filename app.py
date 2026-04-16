#!/usr/bin/env python3
import os
import json
import shlex
import re
import html
import sqlite3
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import streamlit as st

from pipeline import (
    copy_db_to_temp,
    default_provider_config_path,
    list_collections,
    list_papers_in_collection,
)
from ui.dashboard import render_zotero_dashboard
from ui.styles import APP_CSS


PROJECT_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
UI_SETTINGS_PATH = PROJECT_ROOT / ".config" / "ui_paths.json"
ENV_PATH = PROJECT_ROOT / ".env"
STATE_FILE_PATH = PROJECT_ROOT / ".state" / "processed_items.json"
DEFAULT_OBSIDIAN_VAULT = str(Path.home() / "Documents" / "Obsidian")
DEFAULT_OBSIDIAN_FOLDER = "论文精读"
DEFAULT_ZOTERO_DB = str(Path.home() / "Zotero" / "zotero.sqlite")
DEFAULT_ZOTERO_STORAGE = str(Path.home() / "Zotero" / "storage")


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
    storage_path = Path("")
    sibling_storage = db_path.parent / "storage"
    if sibling_storage.exists() and sibling_storage.is_dir():
        storage_path = sibling_storage
    elif storage_candidates:
        storage_path = storage_candidates[0]
    else:
        storage_path = Path(DEFAULT_ZOTERO_STORAGE).expanduser()
    return str(db_path), str(storage_path)


def load_provider_settings(path: str) -> dict:
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


def normalize_provider_settings(data: dict) -> dict:
    providers_raw = data.get("providers") if isinstance(data.get("providers"), dict) else {}
    specs_raw = data.get("provider_specs") if isinstance(data.get("provider_specs"), dict) else {}
    unified: dict[str, dict] = {}

    for name, item in specs_raw.items():
        if not isinstance(item, dict):
            continue
        models = item.get("models", [])
        if not isinstance(models, list):
            models = []
        clean_models = [str(m).strip() for m in models if str(m).strip()]
        unified[str(name)] = {
            "provider_type": item.get("provider_type") or "openai_compatible",
            "env_var": item.get("env_var") or provider_env_key(str(name), {}),
            "default_model": item.get("default_model") or (clean_models[0] if clean_models else ""),
            "models": clean_models,
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
        for value in [*item_models, *custom_models, item.get("model") or item.get("default_model")]:
            text = str(value or "").strip()
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


def save_provider_settings(path: str, settings: dict) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    settings = normalize_provider_settings(settings)
    p.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass


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


def provider_env_key(provider_name: str, spec: dict | None = None) -> str:
    spec = spec or {}
    env_var = str(spec.get("env_var") or "").strip()
    if env_var:
        return env_var
    base = re.sub(r"[^A-Za-z0-9]+", "_", provider_name).strip("_").upper()
    return f"{base}_API_KEY" if base else "PROVIDER_API_KEY"


def get_provider_api_key(provider_name: str, spec: dict | None = None) -> str:
    key_name = provider_env_key(provider_name, spec)
    return load_env_map().get(key_name, "")


def set_provider_api_key(provider_name: str, spec: dict | None, api_key: str) -> None:
    key_name = provider_env_key(provider_name, spec)
    envs = load_env_map()
    if api_key.strip():
        envs[key_name] = api_key.strip()
    else:
        envs.pop(key_name, None)
    save_env_map(envs)


def load_ui_settings() -> dict:
    if not UI_SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(UI_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_ui_settings(data: dict) -> None:
    UI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    UI_SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_and_persist_provider_settings(path: str) -> dict:
    settings = load_provider_settings(path)
    # 迁移旧版 providers.json 中明文 api_key 到 .env，再从配置中移除
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
        st.info(f"检测到旧版 API Key，已自动迁移到 {ENV_PATH}")
    return settings

def get_provider_names(settings: dict) -> list[str]:
    saved = [sanitize_provider_name(k) for k in list((settings.get("providers") or {}).keys()) if isinstance(k, str)]
    saved = [k for k in saved if k]
    return sorted(set(saved))


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


def sanitize_provider_name(name: str) -> str:
    # 去掉首尾空白和不可见字符（零宽字符、控制字符等），并约束为可见标识字符
    n = (name or "").strip()
    if not n:
        return ""
    out = []
    for ch in n:
        cat = unicodedata.category(ch)
        if cat.startswith("C"):
            continue
        # 允许字母/数字（含中文等 Unicode 字母），以及常见分隔符
        if cat.startswith("L") or cat.startswith("N") or ch in {"_", "-", "."}:
            out.append(ch)
    n2 = "".join(out).strip()
    has_visible = any(not c.isspace() for c in n2)
    return n2 if has_visible else ""


def provider_spec_for_ui(provider: str, settings: dict) -> dict:
    saved = ((settings.get("providers") or {}).get(provider) or {})
    models = [str(m).strip() for m in list(saved.get("models", [])) if str(m).strip()]
    default_model = saved.get("default_model") or saved.get("model") or ""
    if default_model and default_model not in models:
        models.append(default_model)
    env_var = provider_env_key(provider, saved)
    return {
        "provider_type": saved.get("provider_type") or "openai_compatible",
        "base_url": saved.get("base_url") or "",
        "default_model": default_model,
        "models": models,
        "env_var": env_var,
        "api_key": load_env_map().get(env_var, ""),
    }


@st.dialog("API设置")
def provider_settings_dialog(provider_config: str):
    settings = load_provider_settings(provider_config)
    providers = settings.setdefault("providers", {})
    page = st.radio("页面", ["内置供应商", "新增供应商", "MinerU 配置"], horizontal=True, index=0, label_visibility="collapsed")

    if page == "内置供应商":
        names = normalize_provider_names(get_provider_names(settings))
        if not names:
            st.warning("未找到供应商，请先新增供应商。")
            st.stop()
        chosen = st.selectbox("选择供应商", names, index=0)
        spec = provider_spec_for_ui(chosen, settings)

        env_var = str(spec.get("env_var", "") or "")
        api_key = st.text_input("API Key", value=spec.get("api_key", ""), type="password")
        if env_var:
            st.caption(f"将保存到本地 `.env`：`{env_var}`（不写入 providers.json）")
        model = st.text_input("默认模型", value=spec["default_model"])
        provider_type = st.selectbox("供应商类型", ["openai_compatible", "gemini"], index=0 if spec["provider_type"] == "openai_compatible" else 1)
        base_url = st.text_input("Base URL（openai_compatible 时使用）", value=str(spec["base_url"]))
        custom_models = st.text_input("额外模型（逗号分隔）", value=", ".join([m for m in spec["models"] if isinstance(m, str) and m.strip()]))

        if st.button("保存当前供应商配置", key="save_existing_provider"):
            items = [x.strip() for x in custom_models.split(",") if x.strip()]
            if model.strip() and model.strip() not in items:
                items.append(model.strip())
            set_provider_api_key(chosen, {"env_var": env_var}, api_key)
            providers[chosen] = {
                "provider_type": provider_type,
                "env_var": env_var or provider_env_key(chosen, {}),
                "default_model": model.strip(),
                "models": items,
                "base_url": base_url.strip(),
            }
            save_provider_settings(provider_config, settings)
            st.success("已保存")
            st.rerun()
    elif page == "新增供应商":
        new_name = st.text_input("供应商名称（英文标识）", value="")
        new_env_var = st.text_input("`.env` 中 API Key 变量名（新供应商）", value="")
        new_api_key = st.text_input("API Key（可选，本地保存）", value="", type="password")
        new_model = st.text_input("默认模型（新供应商）", value="")
        new_type = st.selectbox("类型（新供应商）", ["openai_compatible", "gemini"], index=0)
        new_base_url = st.text_input("Base URL（新供应商）", value="")
        if st.button("添加供应商", key="add_new_provider"):
            name = sanitize_provider_name(new_name)
            if not name:
                st.error("请先填写供应商名称")
            else:
                providers[name] = {
                    "provider_type": new_type,
                    "env_var": new_env_var.strip() or provider_env_key(name, {}),
                    "default_model": new_model.strip(),
                    "models": [new_model.strip()] if new_model.strip() else [],
                    "base_url": new_base_url.strip(),
                }
                set_provider_api_key(name, providers[name], new_api_key)
                save_provider_settings(provider_config, settings)
                st.success(f"已添加供应商：{name}")
                st.rerun()
    else:
        mineru_token = st.text_input(
            "MinerU API Token",
            value=get_env_value("MINERU_API_TOKEN"),
            type="password",
            key="mineru_api_token_input",
        )
        st.caption("将保存到本地 `.env`：`MINERU_API_TOKEN`")
        if st.button("保存 MinerU Token", key="save_mineru_token"):
            set_env_value("MINERU_API_TOKEN", mineru_token)
            st.success("MinerU Token 已保存")
            st.rerun()


@st.dialog("路径设置")
def path_settings_dialog(ui_locked: bool):
    ui_saved = load_ui_settings()
    detected_obsidian_vault = detect_obsidian_vault_path()
    detected_zotero_db, detected_zotero_storage = detect_zotero_paths()
    saved_obsidian_root = ui_saved.get("obsidian_root_path", "")
    saved_obsidian_vault = ui_saved.get("obsidian_vault_path", "")
    saved_obsidian_folder = ui_saved.get("obsidian_folder_path", "")
    if saved_obsidian_root and not (saved_obsidian_vault or saved_obsidian_folder):
        saved_obsidian_vault, saved_obsidian_folder = split_obsidian_output_path(saved_obsidian_root)
    if "provider_config_path" not in st.session_state:
        st.session_state["provider_config_path"] = ui_saved.get("provider_config_path", default_provider_config_path())
    if "template_dir_path" not in st.session_state:
        st.session_state["template_dir_path"] = ui_saved.get("template_dir_path", str(TEMPLATES_DIR))
    if "obsidian_vault_path" not in st.session_state:
        st.session_state["obsidian_vault_path"] = saved_obsidian_vault or detected_obsidian_vault
    if "obsidian_folder_path" not in st.session_state:
        st.session_state["obsidian_folder_path"] = saved_obsidian_folder or DEFAULT_OBSIDIAN_FOLDER
    if "zotero_db_path" not in st.session_state:
        st.session_state["zotero_db_path"] = ui_saved.get("zotero_db_path", detected_zotero_db)
    if "zotero_storage_path" not in st.session_state:
        st.session_state["zotero_storage_path"] = ui_saved.get("zotero_storage_path", detected_zotero_storage)

    provider_config = st.text_input(
        "供应商配置文件",
        value=st.session_state.get("provider_config_path", default_provider_config_path()),
        key="provider_config_path",
        disabled=ui_locked,
    )

    st.text_input(
        "模板目录",
        value=st.session_state.get("template_dir_path", str(TEMPLATES_DIR)),
        key="template_dir_path",
        disabled=ui_locked,
    )

    st.text_input(
        "Obsidian库路径",
        value=st.session_state.get("obsidian_vault_path", detected_obsidian_vault),
        key="obsidian_vault_path",
        disabled=ui_locked,
    )

    obsidian_folder = st.text_input(
        "Obsidian库内文件夹",
        value=st.session_state.get("obsidian_folder_path", DEFAULT_OBSIDIAN_FOLDER),
        key="obsidian_folder_path",
        disabled=ui_locked,
        help="相对于 Obsidian 库根目录的输出位置，例如：论文精读 或 Research/Papers",
    )

    st.text_input(
        "Zotero数据库",
        value=st.session_state.get("zotero_db_path", detected_zotero_db),
        key="zotero_db_path",
        disabled=ui_locked,
    )

    st.text_input(
        "Zotero storage目录",
        value=st.session_state.get("zotero_storage_path", detected_zotero_storage),
        key="zotero_storage_path",
        disabled=ui_locked,
    )

    if st.button("保存路径设置", key="save_path_settings_btn", disabled=ui_locked):
        obsidian_output_path = compose_obsidian_output_path(
            st.session_state.get("obsidian_vault_path", detected_obsidian_vault),
            st.session_state.get("obsidian_folder_path", DEFAULT_OBSIDIAN_FOLDER),
        )
        save_ui_settings(
            {
                "provider_config_path": st.session_state.get("provider_config_path", default_provider_config_path()),
                "template_dir_path": st.session_state.get("template_dir_path", str(TEMPLATES_DIR)),
                "obsidian_vault_path": st.session_state.get("obsidian_vault_path", detected_obsidian_vault),
                "obsidian_folder_path": st.session_state.get("obsidian_folder_path", DEFAULT_OBSIDIAN_FOLDER),
                "obsidian_root_path": obsidian_output_path,
                "zotero_db_path": st.session_state.get("zotero_db_path", detected_zotero_db),
                "zotero_storage_path": st.session_state.get("zotero_storage_path", detected_zotero_storage),
            }
        )
        st.success("路径设置已保存")
        st.rerun()


@st.cache_data(ttl=60)
def load_collection_names(zotero_db: str):
    if not Path(zotero_db).exists():
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


@st.cache_data(ttl=60)
def load_papers_for_collection(zotero_db: str, collection_name: str, since_days: int):
    if not Path(zotero_db).exists() or not collection_name:
        return []
    temp_db = copy_db_to_temp(zotero_db)
    conn = None
    try:
        conn = sqlite3.connect(temp_db)
        return list_papers_in_collection(conn, collection_name, since_days=since_days)
    finally:
        if conn:
            conn.close()
        Path(temp_db).unlink(missing_ok=True)


def list_template_files(template_dir: str) -> list[Path]:
    d = Path(template_dir).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    files = sorted(d.glob("*.md"), key=lambda p: p.name.lower())
    return files


def render_overview_cards(
    ui_locked: bool,
    mode: str,
    provider: str,
    model: str,
    limit: int,
    since_days: int,
    dry_run: bool,
    force: bool,
    selected_collections: list[str],
    selected_collection_item: str | None,
    selected_parent_item_keys: list[str],
    allow_global: bool,
    progress_text: str = "",
    host=None,
) -> None:
    if mode == "按 Zotero 目录（paper）":
        scope = f"{len(selected_collections)} 个目录"
    elif mode == "按 Zotero 目录（all）":
        scope = f"{len(selected_collections)} 个目录（all）"
    elif mode == "按 Zotero目录下单篇":
        scope = f"1 篇（{selected_collection_item or '未选择'}）"
    elif mode == "按父条目Key":
        scope = f"{len(selected_parent_item_keys)} 个 key"
    else:
        scope = "全库扫描" if allow_global else "全库扫描（未确认）"

    flags = []
    if dry_run:
        flags.append("试运行")
    if force:
        flags.append("Force")
    flags_text = " / ".join(flags) if flags else "标准执行"

    run_state = "运行中（已锁定）" if ui_locked else "空闲"
    run_sub = f"执行进度：{progress_text}" if progress_text else "等待执行"

    target = host if host is not None else st
    with (target.container() if host is not None else st.container()):
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(
            f"""
<div class="metric-card">
  <div class="metric-label">运行状态</div>
  <div class="metric-value">{html.escape(run_state)}</div>
  <div class="metric-sub">{html.escape(run_sub)}</div>
</div>
""",
            unsafe_allow_html=True,
        )
        c2.markdown(
            f"""
<div class="metric-card">
  <div class="metric-label">扫描模式</div>
  <div class="metric-value">{html.escape(mode)}</div>
</div>
""",
            unsafe_allow_html=True,
        )
        c3.markdown(
            f"""
<div class="metric-card">
  <div class="metric-label">扫描范围</div>
  <div class="metric-value">{html.escape(scope)}</div>
</div>
""",
            unsafe_allow_html=True,
        )
        c4.markdown(
            f"""
<div class="metric-card">
  <div class="metric-label">模型参数</div>
  <div class="metric-value">{html.escape(provider)} · {html.escape(str(model))}</div>
  <div class="metric-sub">limit={int(limit)} · since={int(since_days)} · {html.escape(flags_text)}</div>
</div>
""",
            unsafe_allow_html=True,
        )


def count_progress_from_log(content: str, dry_run: bool) -> int:
    if not content:
        return 0
    if dry_run:
        return len(re.findall(r"^\[DRY-RUN\]\s*将处理论文\s*:", content, flags=re.M))
    return len(re.findall(r"^\[OK\]\s*已写入\s*:", content, flags=re.M))


@st.fragment(run_every="800ms")
def render_live_log_panel() -> None:
    current_proc = st.session_state.get("run_proc")
    log_path = st.session_state.get("run_log_path", "")
    cmd_display = st.session_state.get("run_cmd_display", "")
    if not current_proc and not log_path:
        return

    running_now = bool(current_proc and current_proc.poll() is None)
    toggle_label = "▼ 输出日志（实时）" if st.session_state.get("log_panel_open", False) else "▶ 输出日志（实时）"
    if st.button(toggle_label, key="toggle_log_panel_btn"):
        st.session_state["log_panel_open"] = not st.session_state.get("log_panel_open", False)
        st.rerun()

    if st.session_state.get("log_panel_open", False):
        st.markdown(
            f"""
<div class="log-status-row">
  <span class="log-pill {'running' if running_now else 'idle'}">{'运行中' if running_now else '空闲'}</span>
  <span class="log-hint">{'日志将持续刷新，执行结束自动解锁配置。' if running_now else '最近一次执行日志保留在下方。'}</span>
</div>
            """,
            unsafe_allow_html=True,
        )
        if cmd_display:
            st.code(cmd_display, language="bash")
        if log_path and Path(log_path).exists():
            content = Path(log_path).read_text(encoding="utf-8", errors="ignore")
            st.text(content[-30000:] if content else "")
        else:
            st.text("")

    if current_proc:
        rc = current_proc.poll()
        if rc is not None:
            st.session_state["run_proc"] = None
            st.session_state["run_last_returncode"] = rc
            st.rerun()
    elif st.session_state.get("log_panel_open", False) and st.session_state.get("run_last_returncode") is not None:
        rc = int(st.session_state["run_last_returncode"])
        if rc == 0:
            st.success("执行成功")
        else:
            st.error(f"执行失败，退出码 {rc}")


def main():
    st.set_page_config(page_title="Zotero 论文精读自动化", layout="wide")
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.markdown(
        """
<div class="hero-panel">
  <div class="hero-title">Zotero → AI → Obsidian 自动化</div>
  <div class="hero-sub">按目录或单篇执行精读，自动写入 Obsidian。</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # 初始化可持久化 UI 路径设置
    ui_saved = load_ui_settings()
    detected_obsidian_vault = detect_obsidian_vault_path()
    detected_zotero_db, detected_zotero_storage = detect_zotero_paths()
    saved_obsidian_root = ui_saved.get("obsidian_root_path", "")
    saved_obsidian_vault = ui_saved.get("obsidian_vault_path", "")
    saved_obsidian_folder = ui_saved.get("obsidian_folder_path", "")
    if saved_obsidian_root and not (saved_obsidian_vault or saved_obsidian_folder):
        saved_obsidian_vault, saved_obsidian_folder = split_obsidian_output_path(saved_obsidian_root)
    if "provider_config_path" not in st.session_state:
        st.session_state["provider_config_path"] = ui_saved.get("provider_config_path", default_provider_config_path())
    if "template_dir_path" not in st.session_state:
        st.session_state["template_dir_path"] = ui_saved.get("template_dir_path", str(TEMPLATES_DIR))
    if "obsidian_vault_path" not in st.session_state:
        st.session_state["obsidian_vault_path"] = saved_obsidian_vault or detected_obsidian_vault
    if "obsidian_folder_path" not in st.session_state:
        st.session_state["obsidian_folder_path"] = saved_obsidian_folder or DEFAULT_OBSIDIAN_FOLDER
    if "zotero_db_path" not in st.session_state:
        st.session_state["zotero_db_path"] = ui_saved.get("zotero_db_path", detected_zotero_db)
    if "zotero_storage_path" not in st.session_state:
        st.session_state["zotero_storage_path"] = ui_saved.get("zotero_storage_path", detected_zotero_storage)
    if "run_proc" not in st.session_state:
        st.session_state["run_proc"] = None
    if "run_log_path" not in st.session_state:
        st.session_state["run_log_path"] = ""
    if "run_cmd_display" not in st.session_state:
        st.session_state["run_cmd_display"] = ""
    if "run_last_returncode" not in st.session_state:
        st.session_state["run_last_returncode"] = None
    if "run_target_limit" not in st.session_state:
        st.session_state["run_target_limit"] = 0
    if "run_is_dry_run" not in st.session_state:
        st.session_state["run_is_dry_run"] = False
    if "log_panel_open" not in st.session_state:
        st.session_state["log_panel_open"] = False

    run_proc = st.session_state.get("run_proc")
    ui_locked = bool(run_proc and run_proc.poll() is None)

    with st.sidebar:
        st.header("基础配置")
        provider_config = st.session_state["provider_config_path"]
        template_dir = st.session_state["template_dir_path"]
        obsidian_root = compose_obsidian_output_path(
            st.session_state.get("obsidian_vault_path", detected_obsidian_vault),
            st.session_state.get("obsidian_folder_path", DEFAULT_OBSIDIAN_FOLDER),
        )
        zotero_db = st.session_state["zotero_db_path"]
        zotero_storage = st.session_state["zotero_storage_path"]

        settings = clean_and_persist_provider_settings(provider_config)
        provider_names = normalize_provider_names(get_provider_names(settings))
        provider_names = [x for x in provider_names if isinstance(x, str) and x.strip()]
        if not provider_names:
            st.error("未找到可用供应商，请先在“API设置”中添加。")
            st.stop()
        provider_state_key = "provider_selected_value_v5"
        if st.session_state.get(provider_state_key) not in provider_names:
            st.session_state[provider_state_key] = "qwen" if "qwen" in provider_names else provider_names[0]
        provider = st.selectbox("AI 提供商", provider_names, key=provider_state_key, disabled=ui_locked)

        spec = provider_spec_for_ui(provider, settings)
        model_options = list(spec["models"])
        if not model_options and spec["default_model"]:
            model_options = [spec["default_model"]]
        default_model = spec["default_model"] or (model_options[0] if model_options else "")
        manual_option = "手动输入模型..."
        if default_model and default_model not in model_options:
            model_options.append(default_model)
        model_menu = model_options + [manual_option]
        model_state_key = "model_selected_value_v5"
        if st.session_state.get(model_state_key) not in model_menu:
            st.session_state[model_state_key] = default_model if default_model in model_menu else model_menu[0]
        selected_model = st.selectbox("模型", model_menu, key=model_state_key, disabled=ui_locked)
        if selected_model == manual_option:
            model = st.text_input("输入模型名", value=default_model, key="model_custom_value_v5", disabled=ui_locked)
        else:
            model = selected_model
        b1, b2 = st.columns(2)
        with b1:
            if st.button("API设置", disabled=ui_locked, use_container_width=True):
                provider_settings_dialog(provider_config)
        with b2:
            if st.button("路径设置", disabled=ui_locked, use_container_width=True):
                path_settings_dialog(ui_locked)

        templates = list_template_files(template_dir)
        if not templates:
            st.error(f"模板目录为空：{Path(template_dir).expanduser()}")
            st.stop()
        template_names = [p.name for p in templates]
        selected_template_name = st.selectbox("模板文件（下拉）", template_names, index=0, disabled=ui_locked)
        template = str(Path(template_dir).expanduser() / selected_template_name)

        limit = st.number_input("单次分析文献数量", min_value=1, value=1, step=1, disabled=ui_locked)
        since_days = st.number_input("最近N天内的文献(0为全部文献)", min_value=0, value=0, step=1, disabled=ui_locked)
        enable_thinking = st.checkbox("深度思考（不建议开启）", value=False, disabled=ui_locked)
        dry_run = st.checkbox("试运行（测试连通，不分析）", value=False, disabled=ui_locked)
        force = st.checkbox("Force（忽略已处理记录）", value=False, disabled=ui_locked)
        pdf_parser_label = st.selectbox(
            "PDF 解析方式",
            ["自动（MinerU 优先）", "MinerU", "本地 pypdf"],
            index=0,
            key="pdf_parser_mode_v1",
            disabled=ui_locked,
        )
        parser_mode_map = {
            "自动（MinerU 优先）": "auto",
            "MinerU": "mineru",
            "本地 pypdf": "pypdf",
        }
        pdf_parser = parser_mode_map[pdf_parser_label]
        mineru_model_version = st.text_input(
            "MinerU 模型版本",
            value="vlm",
            key="mineru_model_version_v1",
            disabled=ui_locked,
        )
        mineru_language = st.text_input(
            "文档语言",
            value="en",
            key="mineru_language_v1",
            disabled=ui_locked,
        )

        # 将路径设置持久化，保证下次打开沿用
        save_ui_settings(
            {
                "provider_config_path": st.session_state.get("provider_config_path", default_provider_config_path()),
                "template_dir_path": st.session_state.get("template_dir_path", str(TEMPLATES_DIR)),
                "obsidian_vault_path": st.session_state.get("obsidian_vault_path", detected_obsidian_vault),
                "obsidian_folder_path": st.session_state.get("obsidian_folder_path", DEFAULT_OBSIDIAN_FOLDER),
                "obsidian_root_path": obsidian_root,
                "zotero_db_path": st.session_state.get("zotero_db_path", detected_zotero_db),
                "zotero_storage_path": st.session_state.get("zotero_storage_path", detected_zotero_storage),
            }
        )

    render_zotero_dashboard(zotero_db, ui_locked, STATE_FILE_PATH)
    st.subheader("扫描范围")
    mode = st.radio(
        "选择模式",
        ["按 Zotero 目录（paper）", "按 Zotero 目录（all）", "按 Zotero目录下单篇", "按父条目Key", "全库扫描（谨慎）"],
        horizontal=True,
        key="scan_mode_radio",
        disabled=ui_locked,
    )

    selected_collections = []
    selected_collection_item = None
    selected_parent_item_keys: list[str] = []
    allow_global = False
    collection_all_types = False

    if mode == "按 Zotero 目录（paper）":
        st.caption("仅分析目录中的论文（排除学位论文），选择父目录会自动包含其所有子目录。")
        names = load_collection_names(zotero_db)
        if not names:
            st.warning("未读取到 collection，请检查 Zotero 数据库路径")
        selected_collections = st.multiselect("选择一个或多个目录", names, disabled=ui_locked)
    elif mode == "按 Zotero 目录（all）":
        st.caption("分析目录中的所有内容（不限类型），选择父目录会自动包含其所有子目录。")
        names = load_collection_names(zotero_db)
        if not names:
            st.warning("未读取到 collection，请检查 Zotero 数据库路径")
        selected_collections = st.multiselect("选择一个或多个目录", names, disabled=ui_locked)
        collection_all_types = True
    elif mode == "按 Zotero目录下单篇":
        names = load_collection_names(zotero_db)
        if not names:
            st.warning("未读取到 collection，请检查 Zotero 数据库路径")
        selected_collection = st.selectbox("选择目录", options=names, index=None, placeholder="请选择一个目录", disabled=ui_locked)
        if selected_collection:
            papers = load_papers_for_collection(zotero_db, selected_collection, int(since_days))
            if since_days > 0:
                st.caption(f"当前仅显示最近 {int(since_days)} 天更新的论文")
            options = [f"{k} | {t}" for k, t, _ in papers]
            chosen = st.selectbox("选择该目录中的论文", options=options, index=None, placeholder="请选择一篇论文", disabled=ui_locked)
            if chosen:
                selected_collections = [selected_collection]
                selected_collection_item = chosen.split(" | ", 1)[0]
                collection_all_types = True
    elif mode == "按父条目Key":
        st.caption("输入一个或多个父条目 key（逗号/空格/换行分隔），将按 key 直接查找并处理")
        raw_keys = st.text_area(
            "父条目 key",
            placeholder="例如：A6G4QK3V\n或 A6G4QK3V, DWE9YC63",
            key="parent_item_keys_input",
            disabled=ui_locked,
        )
        items = re.split(r"[\s,，;；]+", raw_keys.strip())
        selected_parent_item_keys = [x.strip() for x in items if x.strip()]
    else:
        allow_global = st.checkbox("我确认要全库扫描", value=False, disabled=ui_locked)

    current_log_path = st.session_state.get("run_log_path", "")
    progress_text = ""
    if current_log_path and Path(current_log_path).exists():
        snapshot = Path(current_log_path).read_text(encoding="utf-8", errors="ignore")
        done = count_progress_from_log(snapshot, bool(st.session_state.get("run_is_dry_run", False)))
        target_limit = int(st.session_state.get("run_target_limit") or 0)
        progress_text = f"{done}/{target_limit}" if target_limit > 0 else str(done)

    overview_box = st.empty()
    render_overview_cards(
        ui_locked=ui_locked,
        mode=mode,
        provider=provider,
        model=str(model),
        limit=int(limit),
        since_days=int(since_days),
        dry_run=bool(dry_run),
        force=bool(force),
        selected_collections=selected_collections,
        selected_collection_item=selected_collection_item,
        selected_parent_item_keys=selected_parent_item_keys,
        allow_global=allow_global,
        progress_text=progress_text,
        host=overview_box,
    )

    if st.button("开始执行", type="primary", key="run_action_btn", disabled=ui_locked):
        model = str(model).strip()
        if not model:
            st.error("请填写模型名。")
            st.stop()
        if mode == "按 Zotero目录下单篇" and not selected_collection_item:
            st.error("请先选择目录和论文。")
            st.stop()
        if mode == "按父条目Key" and not selected_parent_item_keys:
            st.error("请至少输入一个父条目 key。")
            st.stop()
        providers = settings.setdefault("providers", {})
        old = providers.get(provider, {})
        if not isinstance(old, dict):
            old = {}
        models = list(spec["models"])
        if model and model not in models:
            models.append(model)
        providers[provider] = {
            "default_model": model,
            "provider_type": old.get("provider_type", spec.get("provider_type", "openai_compatible")),
            "env_var": old.get("env_var") or spec.get("env_var") or provider_env_key(provider, {}),
            "models": models,
            "base_url": old.get("base_url", spec.get("base_url", "")),
        }
        save_provider_settings(provider_config, settings)

        cmd = [
            sys.executable,
            "-u",
            "pipeline.py",
            "--provider",
            provider,
            "--template",
            template,
            "--obsidian-root",
            obsidian_root,
            "--zotero-db",
            zotero_db,
            "--zotero-storage",
            zotero_storage,
            "--provider-config",
            provider_config,
            "--limit",
            str(int(limit)),
            "--since-days",
            str(int(since_days)),
            "--pdf-parser",
            pdf_parser,
            "--mineru-model-version",
            mineru_model_version.strip() or "vlm",
            "--mineru-language",
            mineru_language.strip() or "en",
        ]

        if model.strip():
            cmd += ["--model", model.strip()]
        if enable_thinking:
            cmd.append("--enable-thinking")
        if dry_run:
            cmd.append("--dry-run")
        if force:
            cmd.append("--force")

        for c in selected_collections:
            cmd += ["--collection", c]
        if selected_collection_item:
            cmd += ["--collection-item-key", selected_collection_item, "--limit", "1"]
        for k in selected_parent_item_keys:
            cmd += ["--parent-item-key", k]
        if collection_all_types:
            cmd.append("--collection-all-types")
        if allow_global:
            cmd.append("--allow-global-scan")

        cmd_display = " ".join(shlex.quote(x) for x in cmd)
        st.session_state["run_cmd_display"] = cmd_display

        run_env = os.environ.copy()
        run_env["PYTHONUNBUFFERED"] = "1"
        run_log = PROJECT_ROOT / ".state" / "last_run.log"
        run_log.parent.mkdir(parents=True, exist_ok=True)
        run_log.write_text("", encoding="utf-8")
        log_handle = open(run_log, "a", encoding="utf-8")
        p = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            text=True,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            bufsize=1,
            env=run_env,
        )
        log_handle.close()
        st.session_state["run_proc"] = p
        st.session_state["run_log_path"] = str(run_log)
        st.session_state["run_last_returncode"] = None
        st.session_state["run_target_limit"] = int(limit)
        st.session_state["run_is_dry_run"] = bool(dry_run)
        st.rerun()

    render_live_log_panel()


if __name__ == "__main__":
    main()
