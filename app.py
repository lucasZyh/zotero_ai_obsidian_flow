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
DEFAULT_OBSIDIAN = "/Users/yuanhao/Library/Mobile Documents/iCloud~md~obsidian/Documents/研究生/论文精度"
DEFAULT_ZOTERO_DB = str(Path.home() / "Zotero" / "zotero.sqlite")
DEFAULT_ZOTERO_STORAGE = str(Path.home() / "Zotero" / "storage")


def load_provider_settings(path: str) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        return {"providers": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {"providers": {}}
    if "provider_specs" not in data or not isinstance(data["provider_specs"], dict):
        data["provider_specs"] = {}
    if "providers" not in data or not isinstance(data["providers"], dict):
        data["providers"] = {}
    # 清洗异常 key（空字符串/空白）
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


def save_provider_settings(path: str, settings: dict) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
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
    specs = settings.setdefault("provider_specs", {})
    migrated = False
    for pname, pitem in list(providers.items()):
        if not isinstance(pitem, dict):
            continue
        old_key = str(pitem.get("api_key", "") or "").strip()
        if old_key:
            set_provider_api_key(pname, specs.get(pname, {}), old_key)
            pitem.pop("api_key", None)
            migrated = True
    if migrated:
        st.info(f"检测到旧版 API Key，已自动迁移到 {ENV_PATH}")
    save_provider_settings(path, settings)
    return settings


def get_provider_names(settings: dict) -> list[str]:
    saved = [sanitize_provider_name(k) for k in list((settings.get("providers") or {}).keys()) if isinstance(k, str)]
    saved = [k for k in saved if k]
    builtins = [sanitize_provider_name(k) for k in list((settings.get("provider_specs") or {}).keys()) if isinstance(k, str)]
    builtins = [k for k in builtins if k]
    return sorted(set(builtins + saved))


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
    builtin = dict(((settings.get("provider_specs") or {}).get(provider) or {}))
    saved = ((settings.get("providers") or {}).get(provider) or {})
    models = list(builtin.get("models", []))
    custom_models = saved.get("custom_models", [])
    if isinstance(custom_models, list):
        for m in custom_models:
            if isinstance(m, str) and m.strip() and m not in models:
                models.append(m)
    default_model = saved.get("model") or builtin.get("default_model") or ""
    if default_model and default_model not in models:
        models.append(default_model)
    return {
        "provider_type": saved.get("provider_type") or builtin.get("provider_type") or "openai_compatible",
        "base_url": saved.get("base_url", builtin.get("base_url", "")) or "",
        "default_model": default_model,
        "models": models,
        "env_var": provider_env_key(provider, builtin),
        "api_key": get_provider_api_key(provider, builtin),
    }


@st.dialog("设置 API Key / 供应商")
def provider_settings_dialog(provider_config: str):
    settings = load_provider_settings(provider_config)
    providers = settings.setdefault("providers", {})
    catalog = settings.setdefault("provider_specs", {})
    page = st.radio("页面", ["现有供应商配置", "新增自定义供应商"], horizontal=True, index=0)

    if page == "现有供应商配置":
        names = normalize_provider_names(get_provider_names(settings))
        if not names:
            names = list((settings.get("provider_specs") or {}).keys())
        chosen = st.selectbox("选择供应商", names, index=0)
        spec = provider_spec_for_ui(chosen, settings)
        saved_raw = providers.get(chosen, {})
        saved_extra_models = saved_raw.get("custom_models", []) if isinstance(saved_raw, dict) else []
        if not isinstance(saved_extra_models, list):
            saved_extra_models = []

        env_var = str(spec.get("env_var", "") or "")
        api_key = st.text_input("API Key", value=spec.get("api_key", ""), type="password")
        if env_var:
            st.caption(f"将保存到本地 `.env`：`{env_var}`（不写入 providers.json）")
        model = st.text_input("默认模型", value=spec["default_model"])
        provider_type = st.selectbox("供应商类型", ["openai_compatible", "gemini"], index=0 if spec["provider_type"] == "openai_compatible" else 1)
        base_url = st.text_input("Base URL（openai_compatible 时使用）", value=str(spec["base_url"]))
        custom_models = st.text_input("额外模型（逗号分隔）", value=",".join([m for m in saved_extra_models if isinstance(m, str) and m.strip()]))

        if st.button("保存当前供应商配置", key="save_existing_provider"):
            items = [x.strip() for x in custom_models.split(",") if x.strip()]
            set_provider_api_key(chosen, ((settings.get("provider_specs") or {}).get(chosen) or {}), api_key)
            providers[chosen] = {
                "model": model.strip(),
                "provider_type": provider_type,
                "base_url": base_url.strip(),
                "custom_models": items,
            }
            save_provider_settings(provider_config, settings)
            st.success("已保存")
            st.rerun()
    else:
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
                catalog[name] = {
                    "provider_type": new_type,
                    "env_var": new_env_var.strip() or provider_env_key(name, {}),
                    "default_model": new_model.strip(),
                    "models": [new_model.strip()] if new_model.strip() else [],
                    "base_url": new_base_url.strip(),
                }
                providers[name] = {
                    "model": new_model.strip(),
                    "provider_type": new_type,
                    "base_url": new_base_url.strip(),
                    "custom_models": [new_model.strip()] if new_model.strip() else [],
                }
                set_provider_api_key(name, catalog[name], new_api_key)
                save_provider_settings(provider_config, settings)
                st.success(f"已添加供应商：{name}")
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


def _apple_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace("\"", "\\\"")


def pick_directory_dialog(initial_dir: str) -> str:
    # 使用 osascript 弹出系统对话框，避免 tkinter 在非主线程崩溃
    initial = _apple_escape(initial_dir or str(Path.home()))
    script = (
        f'set p to POSIX file "{initial}"\n'
        "set chosenFolder to choose folder default location p\n"
        "POSIX path of chosenFolder"
    )
    try:
        p = subprocess.run(["osascript", "-e", script], text=True, capture_output=True)
        if p.returncode != 0:
            return ""
        return (p.stdout or "").strip()
    except Exception:
        return ""


def pick_file_dialog(initial_dir: str, filetypes: list[tuple[str, str]]) -> str:
    initial = _apple_escape(initial_dir or str(Path.home()))
    script = (
        f'set p to POSIX file "{initial}"\n'
        "set chosenFile to choose file default location p\n"
        "POSIX path of chosenFile"
    )
    try:
        p = subprocess.run(["osascript", "-e", script], text=True, capture_output=True)
        if p.returncode != 0:
            return ""
        return (p.stdout or "").strip()
    except Exception:
        return ""


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

    # 处理上一轮“选择路径”按钮写入的待更新值，避免修改已实例化 widget 的同 key
    pending_map = {
        "pending_provider_config_path": "provider_config_path",
        "pending_template_dir_path": "template_dir_path",
        "pending_obsidian_root_path": "obsidian_root_path",
        "pending_zotero_db_path": "zotero_db_path",
        "pending_zotero_storage_path": "zotero_storage_path",
    }
    for pending_key, target_key in pending_map.items():
        if pending_key in st.session_state and st.session_state[pending_key]:
            st.session_state[target_key] = st.session_state[pending_key]
            del st.session_state[pending_key]

    # 初始化可持久化 UI 路径设置
    ui_saved = load_ui_settings()
    if "provider_config_path" not in st.session_state:
        st.session_state["provider_config_path"] = ui_saved.get("provider_config_path", default_provider_config_path())
    if "template_dir_path" not in st.session_state:
        st.session_state["template_dir_path"] = ui_saved.get("template_dir_path", str(TEMPLATES_DIR))
    if "obsidian_root_path" not in st.session_state:
        st.session_state["obsidian_root_path"] = ui_saved.get("obsidian_root_path", DEFAULT_OBSIDIAN)
    if "zotero_db_path" not in st.session_state:
        st.session_state["zotero_db_path"] = ui_saved.get("zotero_db_path", DEFAULT_ZOTERO_DB)
    if "zotero_storage_path" not in st.session_state:
        st.session_state["zotero_storage_path"] = ui_saved.get("zotero_storage_path", DEFAULT_ZOTERO_STORAGE)
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
        obsidian_root = st.session_state["obsidian_root_path"]
        zotero_db = st.session_state["zotero_db_path"]
        zotero_storage = st.session_state["zotero_storage_path"]

        settings = clean_and_persist_provider_settings(provider_config)
        provider_names = normalize_provider_names(get_provider_names(settings))
        provider_names = [x for x in provider_names if isinstance(x, str) and x.strip()]
        if not provider_names:
            st.error("未找到可用供应商，请先在“设置 API Key / 供应商”中添加。")
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
        if st.button("设置 API Key / 供应商", disabled=ui_locked):
            provider_settings_dialog(provider_config)

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

        with st.expander("路径设置", expanded=False):
            provider_config = st.text_input("供应商配置文件", key="provider_config_path", disabled=ui_locked)

            c1, c2 = st.columns([20, 1], gap="small")
            with c1:
                template_dir = st.text_input("模板目录", key="template_dir_path", disabled=ui_locked)
            with c2:
                st.write("")
                if st.button(" ", key="pick_template_dir_btn", help="选择模板目录", disabled=ui_locked):
                    chosen = pick_directory_dialog(template_dir)
                    if chosen:
                        st.session_state["pending_template_dir_path"] = chosen
                        st.rerun()

            c1, c2 = st.columns([20, 1], gap="small")
            with c1:
                obsidian_root = st.text_input("Obsidian输出目录", key="obsidian_root_path", disabled=ui_locked)
            with c2:
                st.write("")
                if st.button(" ", key="pick_obsidian_root_btn", help="选择 Obsidian 输出目录", disabled=ui_locked):
                    chosen = pick_directory_dialog(obsidian_root)
                    if chosen:
                        st.session_state["pending_obsidian_root_path"] = chosen
                        st.rerun()

            c1, c2 = st.columns([20, 1], gap="small")
            with c1:
                zotero_db = st.text_input("Zotero数据库", key="zotero_db_path", disabled=ui_locked)
            with c2:
                st.write("")
                if st.button(" ", key="pick_zotero_db_btn", help="选择 Zotero 数据库文件", disabled=ui_locked):
                    initial_dir = str(Path(zotero_db).expanduser().parent) if zotero_db else str(Path.home())
                    chosen = pick_file_dialog(initial_dir, [("SQLite DB", "*.sqlite"), ("All files", "*.*")])
                    if chosen:
                        st.session_state["pending_zotero_db_path"] = chosen
                        st.rerun()

            c1, c2 = st.columns([20, 1], gap="small")
            with c1:
                zotero_storage = st.text_input("Zotero storage目录", key="zotero_storage_path", disabled=ui_locked)
            with c2:
                st.write("")
                if st.button(" ", key="pick_zotero_storage_btn", help="选择 Zotero storage 目录", disabled=ui_locked):
                    chosen = pick_directory_dialog(zotero_storage)
                    if chosen:
                        st.session_state["pending_zotero_storage_path"] = chosen
                        st.rerun()

        # 将路径设置持久化，保证下次打开沿用
        save_ui_settings(
            {
                "provider_config_path": st.session_state.get("provider_config_path", default_provider_config_path()),
                "template_dir_path": st.session_state.get("template_dir_path", str(TEMPLATES_DIR)),
                "obsidian_root_path": st.session_state.get("obsidian_root_path", DEFAULT_OBSIDIAN),
                "zotero_db_path": st.session_state.get("zotero_db_path", DEFAULT_ZOTERO_DB),
                "zotero_storage_path": st.session_state.get("zotero_storage_path", DEFAULT_ZOTERO_STORAGE),
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
