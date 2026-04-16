# Zotero → AI → Obsidian

<div align="center">
将 Zotero 中的论文 PDF 自动转换为结构化精读笔记，并写入 Obsidian。
<p>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/api-FastAPI-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/ui-React%20%2B%20Vite-646cff" alt="React + Vite">
  <img src="https://img.shields.io/badge/pdf-MinerU%20%2B%20pypdf-2ea44f" alt="MinerU + pypdf">
  <img src="https://img.shields.io/badge/platform-macOS-black" alt="macOS">
</p>
</div>

<div align="center">
<a href="./README.md">中文</a> &nbsp;&nbsp;|&nbsp;&nbsp; <a href="./README_EN.md">English</a>
</div>

---

## 简介

这个项目提供一套本地论文精读工作流：从 Zotero 筛选文献，解析 PDF，调用 AI 生成结构化分析，再输出为 Obsidian Markdown 笔记。当前主入口已经改为 `FastAPI` 后端 + `Vite React TypeScript` 前端；旧版 `app.py` Streamlit 入口暂时保留为 legacy 备用。

后端首版仍通过子进程调用现有 `pipeline.py`，这样能保留原有 CLI 行为稳定性，同时为后续直接 service 化预留接口边界。

## 功能特性

- 前后端分离：`backend/` 提供 FastAPI JSON API，`frontend/` 提供 React/Vite 界面。
- Mac 风格工作台：左侧侧边栏只负责页面导航，页面包括 `主面板`、`论文精读`、`实时日志`、`设置`。
- 多供应商模型支持：OpenAI、Gemini、千问、DeepSeek、GLM、AIHubMix、SiliconFlow，以及自定义 OpenAI-compatible 供应商。
- 供应商管理：支持添加新供应商、删除供应商、保存修改、连接测试；API Key 默认隐藏，可点击眼睛切换显示。
- 模型管理：模型列表统一写入 `.config/providers.json` 的 `providers` 字段；论文精读页的模型下拉会随供应商切换自动变化。
- MinerU 集成：支持 `MinerU -> AI` 的结构化解析链路，默认可自动回退到本地 `pypdf`。
- 多模态增强：对 `openai_compatible` 供应商可自动选取论文关键配图，发送给支持视觉输入的模型。
- 安全扫描策略：默认禁止全库扫描，必须显式确认。
- 智能目录归档：优先复用与 Zotero Collection 或已有 Obsidian 目录匹配的路径。
- 本地密钥管理：API Key 与 MinerU Token 保存在项目本地 `.env`，不会写入 `.config/providers.json`。

## 工作流程

1. 从 Zotero 数据库中筛选待处理文献。
2. 定位附件 PDF。
3. 使用 MinerU 或本地 `pypdf` 提取论文内容。
4. 调用 AI 模型生成结构化精读结果。
5. 输出为 Obsidian 可直接使用的 Markdown 笔记。
6. 记录处理状态，避免重复分析。

## 环境要求

- macOS
- Python 3.10+
- Node.js / npm
- 本机可访问 Zotero 数据库及 `storage` 目录
- 已准备可写入的 Obsidian Vault

界面会优先自动探测本机常见的 Obsidian Vault 与 Zotero 数据目录；如有需要，也可以在 `设置` 页面手动调整。

## 安装

```bash
git clone git@github.com:lucasZyh/zotero_ai_obsidian_flow.git
cd zotero_ai_obsidian_flow
pip3 install -r requirements.txt
cd frontend
npm install
cd ..
```

模板目录默认位于：

```text
./templates
```

## 配置

首次使用可以直接在新界面的 `设置` 页面填写 API Key、MinerU Token 和本机路径。也可以在项目根目录手动创建 `.env`：

```dotenv
OPENAI_API_KEY="你的Key"
GEMINI_API_KEY="你的Key"
QWEN_API_KEY="你的Key"
ZHIPU_API_KEY="你的Key"
AIHUBMIX_API_KEY="你的Key"
DEEPSEEK_API_KEY="你的Key"
MINERU_API_TOKEN="你的MinerUToken"
# 可选：用于期刊等级检索（EasyScholar）
SecretKey="你的EasyScholarSecretKey"
```

说明：

- `.config/providers.json` 只保存供应商目录、模型列表、默认模型、Base URL 和环境变量名。
- API Key、MinerU Token、EasyScholar SecretKey 保存在 `.env`。
- 本机路径偏好保存在 `.config/ui_paths.json`。
- `.env`、`.config/ui_paths.json`、`.state/` 默认被 `.gitignore` 忽略。

## 启动

构建前端后以单服务方式启动：

```bash
cd frontend
npm run build
cd ..
python start_app.py
```

启动后访问：

```text
http://127.0.0.1:8000
```

开发模式会同时启动 FastAPI 与 Vite：

```bash
ZOTERO_FLOW_DEV=1 python start_app.py
```

开发模式下前端地址通常为：

```text
http://127.0.0.1:5173
```

旧版 Streamlit 入口仍可作为备用：

```bash
streamlit run app.py
```

## 界面说明

新版 Web UI 使用 Mac 风格左侧导航，侧边栏只负责页面切换，不承载业务表单控件。

| 页面 | 功能 |
|---|---|
| `主面板` | Zotero 统计、最近新增、本周未分析、当前运行状态、关键路径摘要 |
| `论文精读` | 供应商、模型、模板、扫描范围、数量、日期范围、PDF 解析方式、试运行、Force、开始执行 |
| `实时日志` | 当前或最近一次命令、运行状态、进度、日志流、成功/失败结果、停止任务 |
| `设置` | API 供应商、API Key、MinerU Token、MinerU 模型版本、文档语言、模板路径、Obsidian 路径、Zotero 路径 |

### 供应商设置

- 点击 `添加新供应商` 可以新增供应商。
- 点击 `删除供应商` 会出现确认弹窗，确认后删除供应商并移除 `.env` 中对应 API Key。
- 点击 `连接测试` 会用当前表单中的模型、Base URL 和 API Key 发起一次轻量真实请求。
- 点击 `保存修改` 会更新 `.config/providers.json` 中对应供应商配置；API Key 仍写入 `.env`。
- `额外模型（逗号分隔）` 会和默认模型一起形成该供应商的模型列表。

### 论文精读

扫描范围支持：

- `按 Zotero 目录（paper）`
- `按 Zotero 目录（all）`
- `按 Zotero 目录下单篇`
- `按父条目 Key`
- `全库扫描（谨慎）`

当选择 `按 Zotero 目录下单篇` 时，需要先选择一个 Zotero 目录，然后才会出现该目录下论文的可搜索列表。

## MinerU 说明

当前集成方式：

- `PDF 解析方式`：
  - `自动（MinerU 优先）`
  - `MinerU`
  - `本地 pypdf`
- `MinerU API Token`、`MinerU 模型版本`、`文档语言` 在 `设置` 页的 `MinerU 配置` 中维护。
- CLI 参数：
  - `--pdf-parser auto|mineru|pypdf`
  - `--mineru-model-version`，默认 `vlm`
  - `--mineru-language`，默认 `en`
- `auto` 模式优先调用 MinerU 标准 API；若未配置 `MINERU_API_TOKEN`、上传失败、轮询失败或解析失败，则自动回退到本地 `pypdf`。
- `mineru` 模式要求必须配置 `MINERU_API_TOKEN`。
- 主流程仅在运行期间使用临时目录保存 MinerU 的 `full.md` 和图片资源，任务结束后自动清理。
- 对 `openai_compatible` 供应商，最多自动选取 6 张带 `Fig.` / `Figure` 上下文的关键配图作为多模态输入。
- 若模型或服务端不支持图像输入，将自动回退到纯文本模式。

## 试运行模式

勾选 `试运行` 后：

- 会测试 LLM 连通性。
- 当解析方式不是 `pypdf` 时，会额外测试 MinerU API 连通性。
- 不上传真实 PDF。
- 不执行正式论文分析。
- 不写入 Obsidian。

## 输出策略

### Obsidian 输出位置

当前输出目录由两部分组成：

- `Obsidian 库路径`
- `Obsidian 库内文件夹`

例如：

```text
Obsidian 库路径：~/Documents/Obsidian/MyVault
Obsidian 库内文件夹：论文精读
最终输出目录：~/Documents/Obsidian/MyVault/论文精读
```

### 目录决策

输出目录按以下顺序决策：

1. 优先命中与 Zotero Collection 同名的 Obsidian 目录。
2. 使用 AI 输出的建议目录。
3. 在已有目录中进行语义匹配，优先复用最接近目录。
4. 若无可复用目录，则按建议目录新建。
5. 最终兜底到 `论文精读`。

### 去重策略

- 默认按父条目 Key 去重。
- 已处理条目后续会自动跳过。
- 如需重新生成，可启用 `Force`。
- `.state/processed_items.json` 中记录处理状态与北京时间时间戳。

## 项目结构

```text
.
├── backend/                  # FastAPI 后端
├── frontend/                 # Vite + React + TypeScript 前端
├── pipeline.py               # 论文精读核心 CLI 流程
├── app.py                    # legacy Streamlit 备用入口
├── start_app.py              # 新主入口
├── templates/                # 分析模板
├── services/                 # 统计等服务
├── .config/providers.json    # 供应商和模型目录，可提交
├── .config/ui_paths.json     # 本机路径偏好，本地忽略
├── .env                      # API Key / Token，本地忽略
└── .state/                   # 运行状态和日志，本地忽略
```

## 配置文件

| 文件 | 用途 | 是否提交到仓库 |
|---|---|---|
| `.config/providers.json` | 供应商目录、模型、默认设置 | 是 |
| `.env` | API Key / SecretKey / MinerU Token | 否 |
| `.config/ui_paths.json` | 本机 UI 路径偏好 | 否 |
| `.state/processed_items.json` | 已处理条目状态 | 否 |
| `.state/last_run.log` | 最近一次运行日志 | 否 |

重要：`AGENTS.md` 不应被加入 `.gitignore`。当前 `.gitignore` 只忽略本地密钥、运行状态、前端依赖和构建产物等内容。

## 安全与隐私

- 仓库默认忽略 `.env`、`.state/`、`.config/ui_paths.json`。
- API Key 不写入 `.config/providers.json`。
- 前端设置页会显示 API Key 输入框，但默认以密码形式隐藏，可点击眼睛图标切换明文。
- 本地运行前请确认 Zotero 数据库、附件路径与 Obsidian 输出目录均具备访问权限。
- 推送前建议检查本地改动，避免误提交敏感路径与临时文件。

## 常见问题

### 启动时报“未找到可用供应商”

请确认 `.config/providers.json` 存在，且顶层 `providers` 非空。

### 读取不到 Zotero 数据

请在 `设置` 页面确认：

- Zotero 数据库路径，通常为 `~/Zotero/zotero.sqlite`
- Zotero storage 路径，通常为 `~/Zotero/storage`

### 写入 Obsidian 失败

请确认以下两项组合后的最终输出目录存在写权限，并检查 iCloud 同步目录是否可访问：

- Obsidian 库路径
- Obsidian 库内文件夹

### MinerU 可用但仍回退到 pypdf

请检查：

- `.env` 中是否已配置 `MINERU_API_TOKEN`
- `PDF 解析方式` 是否设置为 `自动（MinerU 优先）` 或 `MinerU`
- `设置` 页里的 MinerU 模型版本和文档语言是否符合当前需求
- 运行日志中是否出现 MinerU 上传、轮询或下载失败信息

### 前端页面没有更新

如果使用生产模式，请重新构建前端：

```bash
cd frontend
npm run build
cd ..
python start_app.py
```

如果使用开发模式，确认 Vite 服务正在运行：

```bash
ZOTERO_FLOW_DEV=1 python start_app.py
```
