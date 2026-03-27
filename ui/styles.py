APP_CSS = r'''
<style>
/* ====== Apple-like 极简专业主题 ====== */
:root {
  --bg-0: #f3f4f6;
  --bg-1: #f8fafc;
  --card: rgba(255, 255, 255, 0.78);
  --line: #d6dce5;
  --text-0: #111827;
  --text-1: #4b5563;
  --accent: #0a84ff;
}

html, body, [class*="css"] {
  font-family: "SF Pro Text", "SF Pro Display", -apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", "Noto Sans CJK SC", sans-serif !important;
}

[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1300px 500px at 85% -10%, rgba(10, 132, 255, 0.12), transparent 70%),
    linear-gradient(180deg, var(--bg-1) 0%, var(--bg-0) 100%);
}

.main [data-testid="block-container"] {
  padding-top: 1.2rem;
  padding-bottom: 2.2rem;
}

[data-testid="stHeader"] {
  background: transparent !important;
}

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(244,247,252,0.96) 100%);
  border-right: 1px solid rgba(206,214,224,0.8);
}

[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
  padding-top: 0.8rem;
}

h1, h2, h3 {
  color: var(--text-0) !important;
  letter-spacing: -0.02em;
}

p, label, .stCaption, .stMarkdown {
  color: var(--text-1);
}

.hero-panel {
  border: 1px solid var(--line);
  background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(250,252,255,0.86));
  border-radius: 18px;
  padding: 1rem 1.15rem;
  box-shadow: 0 14px 30px rgba(17, 24, 39, 0.08);
  margin-bottom: 0.85rem;
}

.hero-title {
  font-size: 2.15rem;
  font-weight: 760;
  color: var(--text-0);
  line-height: 1.18;
  margin-bottom: 0.35rem;
}

.hero-sub {
  font-size: 0.98rem;
  color: #5a6677;
}

.metric-card {
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0.72rem 0.85rem;
  background: var(--card);
  backdrop-filter: blur(6px);
  box-shadow: 0 8px 20px rgba(17, 24, 39, 0.06);
  min-height: 88px;
}

.metric-label {
  font-size: 0.74rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 0.2rem;
}

.metric-value {
  font-size: 0.95rem;
  font-weight: 620;
  color: #0f172a;
  line-height: 1.25;
}

.metric-sub {
  margin-top: 0.25rem;
  font-size: 0.74rem;
  color: #64748b;
}

.dashboard-card {
  margin-bottom: 0.75rem;
}

.dashboard-locked {
  opacity: 0.95;
}

.type-row {
  display: grid;
  grid-template-columns: minmax(120px, 180px) 1fr 48px;
  gap: 0.55rem;
  align-items: center;
  margin-top: 0.42rem;
}

.type-name {
  font-size: 0.82rem;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.type-bar-wrap {
  height: 8px;
  background: #e7edf6;
  border-radius: 999px;
  overflow: hidden;
}

.type-bar {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #8dc4ff 0%, #0a84ff 100%);
}

.type-cnt {
  text-align: right;
  font-size: 0.8rem;
  color: #475569;
  font-variant-numeric: tabular-nums;
}

.type-row-split {
  display: grid;
  grid-template-columns: minmax(120px, 180px) 1fr 92px;
  gap: 0.55rem;
  align-items: center;
  margin-top: 0.36rem;
}

.type-bar-split-wrap {
  height: 8px;
  background: #e7edf6;
  border-radius: 999px;
  overflow: hidden;
}

.type-bar-total {
  display: flex;
  height: 100%;
  border-radius: 999px;
  overflow: hidden;
}

.type-bar-processed {
  height: 100%;
  background: linear-gradient(90deg, #9dc8f2 0%, #5b9bd5 100%);
}

.type-bar-unprocessed {
  height: 100%;
  background: linear-gradient(90deg, #f6d8aa 0%, #e8b96d 100%);
}

.type-cnt-split {
  text-align: right;
  font-size: 0.78rem;
  color: #475569;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.split-legend {
  margin-top: 0.3rem;
  font-size: 0.78rem;
  color: #64748b;
  display: flex;
  gap: 0.8rem;
}

.split-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}

.split-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}

.list-block {
  margin-top: 0.22rem;
}

.list-row {
  display: grid;
  grid-template-columns: 28px 1fr auto auto auto;
  gap: 0.55rem;
  align-items: baseline;
  padding: 0.42rem 0;
  border-bottom: 1px solid rgba(214, 220, 229, 0.7);
}

.list-row:last-child {
  border-bottom: none;
}

.list-idx {
  color: #64748b;
  font-variant-numeric: tabular-nums;
}

.list-title {
  color: #1f2937;
  font-size: 0.93rem;
  line-height: 1.34;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.list-key {
  color: #0b9444;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.74rem;
  line-height: 1.15;
  font-weight: 500;
  background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.24);
  border-radius: 8px;
  padding: 0.08rem 0.40rem;
  display: inline-flex;
  align-items: center;
  white-space: nowrap;
}

.list-date {
  color: #64748b;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.76rem;
  white-space: nowrap;
  line-height: 1.2;
}

.list-status {
  font-size: 0.74rem;
  line-height: 1.15;
  font-weight: 500;
  border-radius: 8px;
  padding: 0.08rem 0.40rem;
  border: 1px solid transparent;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
}

.list-status.analyzed {
  color: #0b63c7;
  background: rgba(10, 132, 255, 0.1);
  border-color: rgba(10, 132, 255, 0.26);
}

.list-status.unanalyzed {
  color: #9a5b00;
  background: rgba(232, 185, 109, 0.18);
  border-color: rgba(232, 185, 109, 0.35);
  cursor: default;
  transition: background-color 120ms ease, border-color 120ms ease;
}

.list-status.unanalyzed:hover {
  background: rgba(232, 185, 109, 0.24);
  border-color: rgba(232, 185, 109, 0.45);
}

.donut-legend {
  margin-top: 0.2rem;
}

.donut-legend-row {
  display: grid;
  grid-template-columns: 12px 1fr auto;
  gap: 0.4rem;
  align-items: center;
  padding: 0.18rem 0;
}

.donut-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.donut-name {
  font-size: 0.82rem;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.donut-val {
  font-size: 0.8rem;
  color: #64748b;
  font-variant-numeric: tabular-nums;
}

.log-status-row {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  margin-bottom: 0.45rem;
}

.log-pill {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 0.2rem 0.6rem;
  font-size: 0.78rem;
  font-weight: 600;
}

.log-pill.running {
  background: #e6f2ff;
  border-color: #9ecaff;
  color: #0b63c7;
}

.log-pill.idle {
  background: #eef2f7;
  color: #465468;
}

.log-hint {
  font-size: 0.78rem;
  color: #6b7280;
}

.stCodeBlock, [data-testid="stCodeBlock"] {
  border: 1px solid #d9e2ec !important;
  border-radius: 12px !important;
}

[data-testid="stText"] {
  border: 1px solid #d7dfe9;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.88);
  padding: 0.6rem 0.65rem;
}

.stButton > button, .stDownloadButton > button {
  border-radius: 12px !important;
}

.st-key-dash_view_total button,
.st-key-dash_view_unprocessed button,
.st-key-dash_view_monthly button,
.st-key-dash_view_weekly button,
.st-key-dash_view_weekly_unprocessed button {
  min-height: 82px !important;
  border: 1px solid #d8e0eb !important;
  background: rgba(255,255,255,0.9) !important;
  color: #0f172a !important;
  font-weight: 640 !important;
  line-height: 1.35 !important;
}

.st-key-dash_view_total button:hover,
.st-key-dash_view_unprocessed button:hover,
.st-key-dash_view_monthly button:hover,
.st-key-dash_view_weekly button:hover,
.st-key-dash_view_weekly_unprocessed button:hover {
  border-color: #9bc7ff !important;
  box-shadow: 0 8px 16px rgba(10, 132, 255, 0.16) !important;
}

.st-key-total_mode_type button,
.st-key-total_mode_folder button,
.st-key-total_mode_folder_paper button {
  min-height: 34px !important;
  padding: 0.18rem 0.7rem !important;
  font-size: 0.92rem !important;
  border-radius: 10px !important;
  border: 1px solid #d3dbe6 !important;
  background: rgba(255, 255, 255, 0.88) !important;
  box-shadow: none !important;
}

.st-key-total_mode_type button:hover,
.st-key-total_mode_folder button:hover,
.st-key-total_mode_folder_paper button:hover {
  border-color: #9bc7ff !important;
  background: rgba(244, 249, 255, 0.95) !important;
}

.st-key-run_action_btn {
  margin-top: 12px;
}

[data-testid="baseButton-primary"] {
  background: linear-gradient(180deg, #2a8fff 0%, #0a84ff 100%) !important;
  border: none !important;
  box-shadow: 0 10px 18px rgba(10, 132, 255, 0.28) !important;
}

/* Streamlit 不同版本的主按钮选择器兼容 */
.stButton > button[kind="primary"],
button[kind="primary"],
button[data-testid="baseButton-primary"] {
  background: linear-gradient(180deg, #2a8fff 0%, #0a84ff 100%) !important;
  color: #ffffff !important;
  border: 1px solid rgba(10, 132, 255, 0.75) !important;
  box-shadow: 0 10px 18px rgba(10, 132, 255, 0.25) !important;
}

.stButton > button[kind="primary"]:hover,
button[kind="primary"]:hover,
button[data-testid="baseButton-primary"]:hover {
  background: linear-gradient(180deg, #3a98ff 0%, #1f8dff 100%) !important;
  transform: translateY(-1px);
}

.stTextInput > div > div > input,
.stTextArea textarea,
.stNumberInput input,
[data-baseweb="select"] > div {
  border-radius: 12px !important;
}

/* 路径右侧“无按钮化”点击热区 */
.st-key-pick_template_dir_btn,
.st-key-pick_obsidian_root_btn,
.st-key-pick_zotero_db_btn,
.st-key-pick_zotero_storage_btn {
  margin-left: -30px;
  margin-top: 0;
  display: flex;
  align-items: center;
  height: 42px;
}
.st-key-pick_template_dir_btn button,
.st-key-pick_obsidian_root_btn button,
.st-key-pick_zotero_db_btn button,
.st-key-pick_zotero_storage_btn button {
  min-width: 32px !important;
  width: 32px !important;
  height: 40px !important;
  padding: 0 !important;
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  border-radius: 0 8px 8px 0 !important;
  color: transparent !important;
  position: relative;
}
.st-key-pick_template_dir_btn button::after,
.st-key-pick_obsidian_root_btn button::after,
.st-key-pick_zotero_db_btn button::after,
.st-key-pick_zotero_storage_btn button::after {
  content: "📁";
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: #6b7280;
}
/* 给输入框预留右侧图标空间 */
.st-key-template_dir_path input,
.st-key-obsidian_root_path input,
.st-key-zotero_db_path input,
.st-key-zotero_storage_path input {
  padding-right: 44px !important;
  border-radius: 12px 0 0 12px !important;
  min-height: 40px !important;
  line-height: 40px !important;
}

</style>
'''
