# Zotero → AI → Obsidian

<div align="center">
将 Zotero 中的论文 PDF 自动转换为结构化精读笔记，并写入 Obsidian。
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

## 简介

这个项目提供一套从文献筛选、PDF 解析、AI 分析到 Markdown 输出的完整流程，适合日常论文阅读、研究笔记沉淀与知识库整理。

## 功能特性

- 多供应商模型支持：OpenAI、Gemini、千问、DeepSeek、GLM、AIHubMix、SiliconFlow。
- MinerU 集成：支持 `MinerU -> AI` 的结构化解析链路，默认可自动回退到本地 `pypdf`。
- 多模态分析增强：对 `openai_compatible` 供应商可自动选取论文关键配图，图文一起发送给支持视觉的模型。
- Streamlit 图形界面：支持在页面中配置模型、路径、扫描范围、日志与运行状态。
- 安全扫描策略：默认禁止全库扫描，必须显式指定范围。
- 智能目录归档：优先复用与 Zotero Collection 或已有 Obsidian 目录匹配的路径。
- 本地密钥管理：API Key 与 MinerU Token 保存在 `.env`，不写入仓库。

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
- 本机可访问 Zotero 数据库及 `storage` 目录
- 已准备可写入的 Obsidian Vault

说明：界面会优先自动探测本机常见的 Obsidian Vault 与 Zotero 数据目录；如有需要，也可以在 `路径设置` 中手动调整。

## 安装

```bash
git clone git@github.com:lucasZyh/zotero_ai_obsidian_flow.git
cd zotero_ai_obsidian_flow
pip3 install -r requirements.txt
```

模板目录默认位于：

```text
./templates
```

## 配置

首次使用需要在项目根目录创建 `.env` 文件。

示例：

```dotenv
OPENAI_API_KEY="你的Key"
DASHSCOPE_API_KEY="你的Key"
MINERU_API_TOKEN="你的MinerUToken"
# 可选：用于期刊等级检索（EasyScholar）
SecretKey="你的EasyScholarSecretKey"
```

说明：

- `.config/providers.json` 提供内置供应商目录、模型和默认设置。
- API Key 与 MinerU Token 推荐通过界面中的 `API设置` 维护。
- `路径设置` 中的 Obsidian 输出现已拆分为“Obsidian 库路径”和“Obsidian 库内文件夹”。
- 敏感信息仅保存在本地 `.env`。

## 启动

```bash
streamlit run app.py
```

或：

```bash
python start_app.py
```

## 界面说明

Web UI 中可完成以下操作：

- 选择 AI 供应商与模型。
- 选择 PDF 解析方式：`自动（MinerU 优先）`、`MinerU`、`本地 pypdf`。
- 配置 MinerU 模型版本与文档语言。
- 通过 `API设置` 弹窗管理：
  - `内置供应商`
  - `新增供应商`
  - `MinerU 配置`
- 通过 `路径设置` 弹窗管理：
  - 供应商配置文件
  - 模板目录
  - Obsidian 库路径
  - Obsidian 库内文件夹
  - Zotero 数据库路径
  - Zotero storage 路径
  - 首次打开时会自动探测本机常见的 Obsidian 与 Zotero 路径作为默认值
- 选择扫描模式：
  - 按 Zotero 目录（论文类型）
  - 按 Zotero 目录（全部类型）
  - 按 Zotero 目录下单篇
  - 按父条目 Key
  - 全库扫描（谨慎）
- 设置最近 N 天、单次分析数量、深度思考、试运行、Force 等参数。
- 查看实时运行日志与执行结果。

## MinerU 说明

当前集成方式：

- CLI 参数：
  - `--pdf-parser auto|mineru|pypdf`
  - `--mineru-model-version`，默认 `vlm`
  - `--mineru-language`，默认 `en`
- `auto` 模式优先调用 MinerU 标准 API；若未配置 `MINERU_API_TOKEN`、上传失败、轮询失败或解析失败，则自动回退到本地 `pypdf`
- `mineru` 模式要求必须配置 `MINERU_API_TOKEN`
- 主流程仅在运行期间使用临时目录保存 MinerU 的 `full.md` 和图片资源，任务结束后自动清理
- 对 `openai_compatible` 供应商，最多自动选取 6 张带 `Fig.` / `Figure` 上下文的关键配图作为多模态输入
- 若模型或服务端不支持图像输入，将自动回退到纯文本模式

### 试运行模式

勾选 `试运行` 后：

- 会测试 LLM 连通性
- 当解析方式不是 `pypdf` 时，会额外测试 MinerU API 连通性
- 不上传真实 PDF
- 不执行正式论文分析
- 不写入 Obsidian

## 输出策略

### Obsidian 输出位置

当前输出目录由两部分组成：

- `Obsidian 库路径`
- `Obsidian 库内文件夹`

例如：

```text
Obsidian库路径：~/Documents/Obsidian/MyVault
Obsidian库内文件夹：论文精读
最终输出目录：~/Documents/Obsidian/MyVault/论文精读
```

### 目录决策

输出目录按以下顺序决策：

1. 优先命中与 Zotero Collection 同名的 Obsidian 目录
2. 使用 AI 输出的建议目录
3. 在已有目录中进行语义匹配，优先复用最接近目录
4. 若无可复用目录，则按建议目录新建
5. 最终兜底到 `论文精读`

### 去重策略

- 默认按父条目 Key 去重
- 已处理条目后续会自动跳过
- 如需重新生成，可启用 `Force`
- `.state/processed_items.json` 中记录处理状态与北京时间时间戳

## 配置文件

| 文件 | 用途 | 是否提交到仓库 |
|---|---|---|
| `.config/providers.json` | 供应商目录、模型、默认设置 | 是 |
| `.env` | API Key / SecretKey / MinerU Token | 否 |
| `.config/ui_paths.json` | 本机 UI 路径偏好 | 否 |
| `.state/processed_items.json` | 已处理条目状态 | 否 |

## 安全与隐私

- 仓库默认忽略 `.env`、`.state/`、`.config/ui_paths.json`
- API Key 不写入 `providers.json`
- 本地运行前请确认 Zotero 数据库、附件路径与 Obsidian 输出目录均具备访问权限
- 推送前建议检查本地改动，避免误提交敏感路径与临时文件

## 常见问题

### 启动时报“未找到可用供应商”

请确认 `.config/providers.json` 存在，且 `provider_specs` 非空。

### 读取不到 Zotero 数据

请在 `路径设置` 弹窗中确认：

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
- 运行日志中是否出现 MinerU 上传、轮询或下载失败信息
