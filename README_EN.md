# Zotero → AI → Obsidian

<div align="center">
Automatically turn Zotero paper PDFs into structured reading notes and write them into Obsidian.
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

## Overview

This project provides a local paper-reading workflow: select papers from Zotero, parse PDFs, ask an AI model for structured analysis, and export the result as Obsidian Markdown notes. The main app is now a decoupled `FastAPI` backend plus a `Vite React TypeScript` frontend. The older `app.py` Streamlit entry is kept as a legacy fallback.

The first backend version still runs the existing `pipeline.py` through a subprocess. This keeps the current CLI behavior stable while leaving a clear API boundary for later service-level integration.

## Features

- Decoupled architecture: `backend/` provides the FastAPI JSON API, and `frontend/` provides the React/Vite interface.
- Mac-style workspace: the sidebar is page navigation only, with `Dashboard`, `Paper Reading`, `Live Logs`, and `Settings`.
- Multi-provider support: OpenAI, Gemini, Qwen, DeepSeek, GLM, AIHubMix, SiliconFlow, and custom OpenAI-compatible providers.
- Provider management: add providers, delete providers, save edits, and run a connection test. API keys are hidden by default and can be revealed with the eye button.
- Model management: model lists are unified under the top-level `providers` object in `.config/providers.json`; the Paper Reading model selector follows the selected provider.
- MinerU integration: supports a structured `MinerU -> AI` pipeline, with automatic fallback to local `pypdf`.
- Multimodal enhancement: for `openai_compatible` providers, key figures can be selected automatically and sent to vision-capable models.
- Safe scan strategy: full-library scan is disabled unless explicitly confirmed.
- Smart folder routing: prefers Obsidian folders that match Zotero collections or existing vault folders.
- Local secret management: API keys and the MinerU token are stored in the project-local `.env`, not in `.config/providers.json`.

## Workflow

1. Select target papers from the Zotero database.
2. Locate the attached PDF file.
3. Parse the paper with MinerU or local `pypdf`.
4. Send the parsed content to an AI model for structured analysis.
5. Export the result as Obsidian-friendly Markdown.
6. Record processing state to avoid duplicates.

## Requirements

- macOS
- Python 3.10+
- Node.js / npm
- Local access to the Zotero database and `storage` directory
- A writable Obsidian vault

The UI tries to auto-detect common local Obsidian and Zotero paths on first launch. You can still edit them manually in `Settings`.

## Installation

```bash
git clone git@github.com:lucasZyh/zotero_ai_obsidian_flow.git
cd zotero_ai_obsidian_flow
pip3 install -r requirements.txt
cd frontend
npm install
cd ..
```

The default template directory is:

```text
./templates
```

## Configuration

On first launch, you can fill in API keys, the MinerU token, and local paths from the `Settings` page. You can also create a `.env` file in the project root manually:

```dotenv
OPENAI_API_KEY="your-key"
GEMINI_API_KEY="your-key"
QWEN_API_KEY="your-key"
ZHIPU_API_KEY="your-key"
AIHUBMIX_API_KEY="your-key"
DEEPSEEK_API_KEY="your-key"
MINERU_API_TOKEN="your-mineru-token"
# Optional: for journal ranking lookup (EasyScholar)
SecretKey="your-easyscholar-secretkey"
```

Notes:

- `.config/providers.json` stores provider metadata, model lists, default models, Base URLs, and env var names.
- API keys, the MinerU token, and the EasyScholar SecretKey are stored in `.env`.
- Local path preferences are stored in `.config/ui_paths.json`.
- `.env`, `.config/ui_paths.json`, and `.state/` are ignored by default.

## Launch

Build the frontend and run the app as a single service:

```bash
cd frontend
npm run build
cd ..
python start_app.py
```

Then open:

```text
http://127.0.0.1:8000
```

For development, start FastAPI and Vite together:

```bash
ZOTERO_FLOW_DEV=1 python start_app.py
```

The frontend dev URL is usually:

```text
http://127.0.0.1:5173
```

The legacy Streamlit entry is still available as a fallback:

```bash
streamlit run app.py
```

## UI

The new web UI uses a Mac-style sidebar for page switching only. Business controls live inside the pages.

| Page | Purpose |
|---|---|
| `Dashboard` | Zotero statistics, recent additions, weekly unprocessed items, runtime status, and key path summary |
| `Paper Reading` | Provider, model, template, scan scope, count, date range, PDF parser, dry run, Force, and start action |
| `Live Logs` | Current or most recent command, state, progress, log stream, success/failure result, and stop action |
| `Settings` | Providers, API keys, MinerU token, MinerU model version, document language, template path, Obsidian path, and Zotero paths |

### Provider Settings

- Click `添加新供应商` to add a new provider.
- Click `删除供应商` to open a confirmation dialog. Confirming removes the provider and its matching API key from `.env`.
- Click `连接测试` to send a small real request using the current model, Base URL, and API key.
- Click `保存修改` to update the provider in `.config/providers.json`; API keys are still written to `.env`.
- `额外模型（逗号分隔）` is combined with the default model to form the provider's model list.

### Paper Reading

Supported scan scopes:

- `按 Zotero 目录（paper）`
- `按 Zotero 目录（all）`
- `按 Zotero 目录下单篇`
- `按父条目 Key`
- `全库扫描（谨慎）`

When `按 Zotero 目录下单篇` is selected, choose one Zotero collection first; the searchable paper list appears only after a collection has been selected.

## MinerU

Current integration details:

- `PDF Parser`:
  - `自动（MinerU 优先）`
  - `MinerU`
  - `本地 pypdf`
- `MinerU API Token`, `MinerU 模型版本`, and `文档语言` are maintained in the `MinerU 配置` section on the Settings page.
- CLI options:
  - `--pdf-parser auto|mineru|pypdf`
  - `--mineru-model-version`, default `vlm`
  - `--mineru-language`, default `en`
- In `auto` mode, MinerU is used first; if `MINERU_API_TOKEN` is missing or upload/polling/parsing fails, the pipeline falls back to local `pypdf`.
- In `mineru` mode, `MINERU_API_TOKEN` is required.
- MinerU `full.md` and image assets are stored only in a temporary directory during runtime and are cleaned up automatically.
- For `openai_compatible` providers, up to 6 key figures with nearby `Fig.` / `Figure` references are selected as multimodal input.
- If the provider or model does not support image input, the pipeline falls back to text-only mode automatically.

## Dry Run

When `试运行` is enabled:

- LLM connectivity is checked.
- MinerU connectivity is also checked when the parser is not `pypdf`.
- No real PDF is uploaded.
- No actual paper analysis is performed.
- Nothing is written into Obsidian.

## Output Strategy

### Obsidian Output Path

The final output directory is composed from:

- `Obsidian 库路径`
- `Obsidian 库内文件夹`

Example:

```text
Obsidian Vault Path: ~/Documents/Obsidian/MyVault
Folder Inside Vault: 论文精读
Final Output Directory: ~/Documents/Obsidian/MyVault/论文精读
```

### Folder Resolution

The output folder is chosen in this order:

1. Reuse an existing Obsidian folder with the same name as a Zotero collection.
2. Use the folder suggestion generated by AI.
3. Semantically match the closest existing folder.
4. Create a new folder from the suggestion if nothing matches.
5. Fall back to `论文精读`.

### Deduplication

- Papers are deduplicated by parent item key.
- Processed items are skipped by default.
- Use `Force` to regenerate notes.
- `.state/processed_items.json` stores processing state and Beijing-time timestamps.

## Project Structure

```text
.
├── backend/                  # FastAPI backend
├── frontend/                 # Vite + React + TypeScript frontend
├── pipeline.py               # Core paper-reading CLI pipeline
├── app.py                    # Legacy Streamlit fallback
├── start_app.py              # New main entry
├── templates/                # Analysis templates
├── services/                 # Dashboard stats and other services
├── .config/providers.json    # Provider and model catalog, tracked
├── .config/ui_paths.json     # Local path preferences, ignored
├── .env                      # API keys / tokens, ignored
└── .state/                   # Runtime state and logs, ignored
```

## Project Files

| File | Purpose | Tracked in Git |
|---|---|---|
| `.config/providers.json` | Provider metadata, models, and defaults | Yes |
| `.env` | API keys / SecretKey / MinerU token | No |
| `.config/ui_paths.json` | Local UI path preferences | No |
| `.state/processed_items.json` | Processed item state | No |
| `.state/last_run.log` | Last run log | No |

Important: `AGENTS.md` should not be added to `.gitignore`. The current `.gitignore` only ignores local secrets, runtime state, frontend dependencies, and build outputs.

## Security and Privacy

- `.env`, `.state/`, and `.config/ui_paths.json` are ignored by default.
- API keys are not written into `.config/providers.json`.
- The Settings page displays API key inputs, but they are hidden by default and can be toggled with the eye icon.
- Before running locally, make sure the Zotero database, attachments, and Obsidian output path are accessible.
- Review local changes before pushing to avoid committing sensitive paths or temporary files.

## FAQ

### "No available provider found" at startup

Make sure `.config/providers.json` exists and contains a non-empty top-level `providers` object.

### Cannot read Zotero data

Check these values in `Settings`:

- Zotero database path, usually `~/Zotero/zotero.sqlite`
- Zotero storage path, usually `~/Zotero/storage`

### Failed to write to Obsidian

Make sure the final output directory formed by the two settings below is writable, and that your iCloud-synced folder is accessible:

- Obsidian vault path
- Folder inside vault

### MinerU is available but the app still falls back to pypdf

Check:

- Whether `MINERU_API_TOKEN` is configured in `.env`
- Whether `PDF Parser` is set to `自动（MinerU 优先）` or `MinerU`
- Whether the MinerU model version and document language in Settings match your needs
- Whether the runtime log shows MinerU upload, polling, or download failures

### The frontend page did not update

If you use production mode, rebuild the frontend:

```bash
cd frontend
npm run build
cd ..
python start_app.py
```

If you use development mode, make sure Vite is running:

```bash
ZOTERO_FLOW_DEV=1 python start_app.py
```
