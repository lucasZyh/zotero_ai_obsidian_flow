# Zotero → AI → Obsidian

<div align="center">
Automatically turn papers stored in Zotero into structured reading notes and write them into Obsidian.
<p>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/ui-Streamlit-ff4b4b" alt="Streamlit">
  <img src="https://img.shields.io/badge/pdf-MinerU%20%2B%20pypdf-2ea44f" alt="MinerU + pypdf">
  <img src="https://img.shields.io/badge/platform-macOS-black" alt="macOS">
</p>
</div>

<div align="center">
<a href="./README.md">中文</a> &nbsp;&nbsp;|&nbsp;&nbsp; <a href="./README_EN.md">English</a>
</div>
---

## Overview

This project provides a complete local workflow for paper processing: literature selection, PDF parsing, AI analysis, and Markdown export. It is designed for academic reading, research note taking, and long-term knowledge management.

## Features

- Multi-provider model support: OpenAI, Gemini, Qwen, DeepSeek, GLM, AIHubMix, and SiliconFlow.
- MinerU integration: supports a structured `MinerU -> AI` pipeline, with automatic fallback to local `pypdf`.
- Multimodal enhancement: for `openai_compatible` providers, key figures can be selected automatically and sent together with the paper text to vision-capable models.
- Streamlit UI: configure models, paths, scan scopes, logs, and runtime status from the web interface.
- Safe scan strategy: full-library scan is disabled by default unless explicitly enabled.
- Smart folder routing: prefers existing Obsidian folders that match Zotero collections.
- Local secret management: API keys and MinerU token are stored in `.env`, not in the repository.

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
- Local access to the Zotero database and `storage` directory
- A writable Obsidian vault

Note: the UI will automatically detect common local Obsidian and Zotero paths on first launch. You can still adjust them manually in `Path Settings`.

## Installation

```bash
git clone git@github.com:lucasZyh/zotero_ai_obsidian_flow.git
cd zotero_ai_obsidian_flow
pip3 install -r requirements.txt
```

The default template directory is:

```text
./templates
```

## Configuration

Create a `.env` file in the project root before first use.

Example:

```dotenv
OPENAI_API_KEY="your-key"
DASHSCOPE_API_KEY="your-key"
MINERU_API_TOKEN="your-mineru-token"
# Optional: for journal ranking lookup (EasyScholar)
SecretKey="your-easyscholar-secretkey"
```

Notes:

- `.config/providers.json` stores built-in provider metadata, models, and defaults.
- API keys and the MinerU token are best managed from `API Settings` in the UI.
- Obsidian output settings are now split into `Obsidian Vault Path` and `Folder Inside Vault`.
- Sensitive values stay in the local `.env` file only.

## Launch

```bash
streamlit run app.py
```

or:

```bash
python start_app.py
```

## UI

The web UI supports:

- Selecting the AI provider and model
- Choosing the PDF parser: `Auto (Prefer MinerU)`, `MinerU`, or `Local pypdf`
- Configuring MinerU model version and document language
- Managing `API Settings`:
  - `Built-in Providers`
  - `Add Provider`
  - `MinerU Settings`
- Managing `Path Settings`:
  - Provider config file
  - Template directory
  - Obsidian vault path
  - Folder inside vault
  - Zotero database path
  - Zotero storage path
  - On first launch, common local Obsidian and Zotero paths are auto-detected as defaults
- Selecting scan scope:
  - By Zotero collection (paper only)
  - By Zotero collection (all item types)
  - Single paper inside a Zotero collection
  - By parent item key
  - Full library scan (careful)
- Configuring recent days, batch size, deep thinking, dry run, and force mode
- Viewing live logs and runtime status

## MinerU

Current integration details:

- CLI options:
  - `--pdf-parser auto|mineru|pypdf`
  - `--mineru-model-version`, default `vlm`
  - `--mineru-language`, default `en`
- In `auto` mode, MinerU is used first; if `MINERU_API_TOKEN` is missing or upload/polling/parsing fails, the pipeline falls back to local `pypdf`
- In `mineru` mode, `MINERU_API_TOKEN` is required
- MinerU `full.md` and image assets are stored only in a temporary directory during runtime and are cleaned up automatically
- For `openai_compatible` providers, up to 6 key figures with nearby `Fig.` / `Figure` references are selected as multimodal input
- If the provider or model does not support image input, the pipeline falls back to text-only mode automatically

### Dry Run

When `Dry Run` is enabled:

- LLM connectivity is checked
- MinerU connectivity is also checked when the parser is not `pypdf`
- No real PDF is uploaded
- No actual paper analysis is performed
- Nothing is written into Obsidian

## Output Strategy

### Obsidian Output Path

The final output directory is composed from:

- `Obsidian Vault Path`
- `Folder Inside Vault`

Example:

```text
Obsidian Vault Path: ~/Documents/Obsidian/MyVault
Folder Inside Vault: Papers
Final Output Directory: ~/Documents/Obsidian/MyVault/Papers
```

### Folder Resolution

The output folder is chosen in the following order:

1. Reuse an existing Obsidian folder with the same name as a Zotero collection
2. Use the folder suggestion generated by AI
3. Semantically match the closest existing folder
4. Create a new folder from the suggestion if nothing matches
5. Fallback to `论文精读`

### Deduplication

- Papers are deduplicated by parent item key
- Processed items are skipped by default
- Use `Force` to regenerate notes
- `.state/processed_items.json` stores processing state and Beijing-time timestamps

## Project Files

| File | Purpose | Tracked in Git |
|---|---|---|
| `.config/providers.json` | Provider metadata, models, and defaults | Yes |
| `.env` | API keys / SecretKey / MinerU token | No |
| `.config/ui_paths.json` | Local UI path preferences | No |
| `.state/processed_items.json` | Processed item state | No |

## Security and Privacy

- `.env`, `.state/`, and `.config/ui_paths.json` are ignored by default
- API keys are not written into `providers.json`
- Before running locally, make sure the Zotero database, attachments, and Obsidian output path are accessible
- Review local changes before pushing to avoid committing sensitive paths or temporary files

## FAQ

### “No available provider found” at startup

Make sure `.config/providers.json` exists and contains a non-empty `provider_specs`.

### Cannot read Zotero data

Check these values in `Path Settings`:

- Zotero database path, usually `~/Zotero/zotero.sqlite`
- Zotero storage path, usually `~/Zotero/storage`

### Failed to write to Obsidian

Make sure the final output directory formed by the two settings below is writable, and that your iCloud-synced folder is accessible:

- Obsidian vault path
- Folder inside vault

### MinerU is available but the app still falls back to pypdf

Check:

- Whether `MINERU_API_TOKEN` is configured in `.env`
- Whether `PDF Parser` is set to `Auto (Prefer MinerU)` or `MinerU`
- Whether the runtime log shows MinerU upload, polling, or download failures
