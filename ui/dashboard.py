from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from pipeline import copy_db_to_temp
from services.dashboard_stats import ITEM_TYPE_CN, compute_zotero_dashboard_stats


@st.cache_data(ttl=45)
def _load_zotero_dashboard_stats_cached(zotero_db: str, state_version: str, state_file_path: str) -> dict:
    del state_version
    return compute_zotero_dashboard_stats(zotero_db, Path(state_file_path), copy_db_to_temp)


def render_zotero_dashboard(zotero_db: str, ui_locked: bool, state_file_path: Path) -> None:
    state_version = "0"
    if state_file_path.exists():
        try:
            state_version = str(state_file_path.stat().st_mtime_ns)
        except Exception:
            state_version = "0"

    stats = _load_zotero_dashboard_stats_cached(zotero_db, state_version, str(state_file_path))
    if stats["total_items"] <= 0 and not Path(zotero_db).exists():
        st.warning("仪表盘未加载：请先检查 Zotero 数据库路径。")
        return

    if "dashboard_view" not in st.session_state:
        st.session_state["dashboard_view"] = "total"
    if "dashboard_total_mode" not in st.session_state:
        st.session_state["dashboard_total_mode"] = "type"
    if "dashboard_page_weekly" not in st.session_state:
        st.session_state["dashboard_page_weekly"] = 1
    if "dashboard_page_weekly_unprocessed" not in st.session_state:
        st.session_state["dashboard_page_weekly_unprocessed"] = 1

    def _pick_view(view: str) -> None:
        if st.session_state.get("dashboard_view") != view:
            st.session_state["dashboard_view"] = view
            if view == "weekly_new":
                st.session_state["dashboard_page_weekly"] = 1
            elif view == "weekly_unprocessed":
                st.session_state["dashboard_page_weekly_unprocessed"] = 1

    st.markdown("#### Zotero 仪表盘")
    c1, c3, c4, c5 = st.columns(4)
    with c1:
        if st.button(f"库中文献总数\n{int(stats['total_items'])}", key="dash_view_total", use_container_width=True):
            _pick_view("total")
            st.rerun()
    with c3:
        if st.button(f"本月新增文献\n{int(stats['monthly_new_items'])}", key="dash_view_monthly", use_container_width=True):
            _pick_view("monthly_new")
            st.rerun()
    with c4:
        if st.button(f"本周新添加文献\n{int(stats['weekly_new_items'])}", key="dash_view_weekly", use_container_width=True):
            _pick_view("weekly_new")
            st.rerun()
    with c5:
        if st.button(f"本周未分析\n{int(stats['weekly_unprocessed_items'])}", key="dash_view_weekly_unprocessed", use_container_width=True):
            _pick_view("weekly_unprocessed")
            st.rerun()

    view = st.session_state.get("dashboard_view", "total")

    def _render_type_distribution(type_counts: list[tuple[str, int]], title: str) -> None:
        if not type_counts:
            st.info("暂无条目类型统计。")
            return
        max_count = max([c for _, c in type_counts] + [1])
        rows_html = []
        for tname, cnt in type_counts:
            pct = int((cnt / max_count) * 100)
            rows_html.append(
                f"""
<div class="type-row">
  <div class="type-name">{html.escape(str(tname))}</div>
  <div class="type-bar-wrap"><div class="type-bar" style="width:{pct}%"></div></div>
  <div class="type-cnt">{int(cnt)}</div>
</div>
"""
            )
        st.markdown(
            f"""
<div class="metric-card dashboard-card {'dashboard-locked' if ui_locked else ''}">
  <div class="metric-label">{html.escape(title)}</div>
  {''.join(rows_html)}
</div>
            """,
            unsafe_allow_html=True,
        )

    def _render_type_split_distribution(rows: list[dict], title: str) -> None:
        if not rows:
            st.info("暂无条目类型统计。")
            return
        max_total = max([int(r.get("total", 0)) for r in rows] + [1])
        rows_html = []
        for r in rows:
            tname_raw = str(r.get("type_name", "") or "unknown")
            tname = ITEM_TYPE_CN.get(tname_raw, tname_raw)
            total = int(r.get("total", 0))
            un = int(r.get("unprocessed", 0))
            done = int(r.get("processed", 0))
            total_pct = int((total / max_total) * 100) if max_total > 0 else 0
            done_inner = int((done / total) * 100) if total > 0 else 0
            un_inner = max(0, 100 - done_inner) if total > 0 else 0
            rows_html.append(
                f"""
<div class="type-row-split">
  <div class="type-name">{html.escape(tname)}</div>
  <div class="type-bar-split-wrap">
    <div class="type-bar-total" style="width:{total_pct}%">
      <div class="type-bar-processed" style="width:{done_inner}%"></div>
      <div class="type-bar-unprocessed" style="width:{un_inner}%"></div>
    </div>
  </div>
  <div class="type-cnt-split">{done}/{total}（未{un}）</div>
</div>
"""
            )
        st.markdown(
            f"""
<div class="metric-card dashboard-card {'dashboard-locked' if ui_locked else ''}">
  <div class="metric-label">{html.escape(title)}</div>
  {''.join(rows_html)}
  <div class="split-legend">
    <span class="split-chip"><span class="split-dot" style="background:#5b9bd5;"></span>已分析</span>
    <span class="split-chip"><span class="split-dot" style="background:#e8b96d;"></span>未分析</span>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

    def _render_title_list(rows: list[dict], title: str, page_key: str) -> None:
        if not rows:
            st.markdown(
                f"""
<div class="metric-card dashboard-card {'dashboard-locked' if ui_locked else ''}">
  <div class="metric-label">{html.escape(title)}</div>
</div>
                """,
                unsafe_allow_html=True,
            )
            st.info("暂无数据。")
            return

        per_page = 10
        total = len(rows)
        total_pages = max(1, (total + per_page - 1) // per_page)
        cur_page = int(st.session_state.get(page_key, 1))
        cur_page = max(1, min(cur_page, total_pages))
        st.session_state[page_key] = cur_page

        start = (cur_page - 1) * per_page
        end = min(start + per_page, total)
        show_rows = rows[start:end]
        rows_html = []
        for idx, row in enumerate(show_rows, start=start + 1):
            title_txt = str(row.get("title", "") or row.get("parent_key", "")).strip()
            key_txt = str(row.get("parent_key", "")).strip()
            date_txt = str(row.get("date_added", "")).strip()
            analyzed = bool(row.get("analyzed", False))
            status_cls = "analyzed" if analyzed else "unanalyzed"
            status_txt = "已分析" if analyzed else "未分析"
            rows_html.append(
                f"""
<div class="list-row">
  <div class="list-idx">{idx}.</div>
  <div class="list-title">{html.escape(title_txt)}</div>
  <div class="list-key">{html.escape(key_txt)}</div>
  <div class="list-date">{html.escape(date_txt)}</div>
  <div class="list-status {status_cls}">{status_txt}</div>
</div>
"""
            )
        st.markdown(
            f"""
<div class="metric-card dashboard-card {'dashboard-locked' if ui_locked else ''}">
  <div class="metric-label">{html.escape(title)}</div>
  <div class="list-block">
    {''.join(rows_html)}
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        if total_pages > 1:
            p1, p2, p3 = st.columns([1, 1, 6])
            with p1:
                if st.button("上一页", key=f"{page_key}_prev", disabled=cur_page <= 1):
                    st.session_state[page_key] = cur_page - 1
                    st.rerun()
            with p2:
                if st.button("下一页", key=f"{page_key}_next", disabled=cur_page >= total_pages):
                    st.session_state[page_key] = cur_page + 1
                    st.rerun()
            with p3:
                st.caption(f"第 {cur_page}/{total_pages} 页，共 {total} 条")

    if view == "total":
        t1, t2, t3, _ = st.columns([1, 1, 1.3, 5.7])
        with t1:
            if st.button("按条目", key="total_mode_type", use_container_width=True):
                st.session_state["dashboard_total_mode"] = "type"
                st.rerun()
        with t2:
            if st.button("按文件夹", key="total_mode_folder", use_container_width=True):
                st.session_state["dashboard_total_mode"] = "folder"
                st.rerun()
        with t3:
            if st.button("按文件夹（仅论文）", key="total_mode_folder_paper", use_container_width=True):
                st.session_state["dashboard_total_mode"] = "folder_paper"
                st.rerun()

        total_mode = st.session_state.get("dashboard_total_mode", "type")
        if total_mode == "folder":
            _render_type_split_distribution(stats.get("folder_split_all", []), "顶层文件夹分布")
            st.caption("说明：按顶层文件夹统计时，同一条目位于多个文件夹会被分别计入。")
        elif total_mode == "folder_paper":
            _render_type_split_distribution(stats.get("folder_split_papers", []), "论文分布")
            st.caption("说明：仅统计论文类型（期刊/会议/预印本/报告/手稿/学位论文），同一条目位于多个文件夹会被分别计入")
        else:
            _render_type_split_distribution(stats.get("type_split_all", []), "文件类型分布（总量 Top 10）")
    elif view == "monthly_new":
        _render_type_distribution(stats.get("top_folder_counts_monthly_new", []), "顶层文件夹分布（本月新增）")
    elif view == "weekly_new":
        _render_title_list(stats.get("weekly_titles", []), "本周新添加文献标题", "dashboard_page_weekly")
    else:
        _render_title_list(stats.get("weekly_unprocessed_titles", []), "本周未分析文献标题", "dashboard_page_weekly_unprocessed")
