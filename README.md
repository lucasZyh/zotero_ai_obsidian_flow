# Zotero -> AI -> Obsidian 自动论文精读流程

将 Zotero 中的论文（含 PDF）自动转为结构化精读笔记，并写入 Obsidian。

## 项目概览

本项目提供一套端到端流程：

1. 读取 Zotero 数据库与附件 PDF。
2. 调用 AI 模型生成结构化论文分析。
3. 基于模板输出 Obsidian Markdown。
4. 自动决策并写入目标目录。
5. 按条目去重，支持强制重跑。

默认输出目录：
`~/Library/Mobile Documents/iCloud~md~obsidian/Documents/研究生/论文精度`

## 核心能力

- 多供应商支持：OpenAI、Gemini、千问、DeepSeek、GLM、AIHubMix、SiliconFlow。
- 可视化运行：Streamlit 界面配置供应商、模型、路径、扫描范围、日志查看。
- 安全扫描策略：默认禁止全库扫描，必须显式指定范围。
- 目录智能归档：优先复用已有目录，避免目录碎片化。
- 本地密钥管理：API Key 存于 `.env`，不写入仓库。

## 快速开始

### 1) 环境要求

- 开发与验证环境：macOS
- Python 3.10+
- 本机可访问 Zotero 数据库及 storage 目录
- 已准备 Obsidian Vault（用于写入输出）

说明：项目默认路径与示例基于 macOS（含 iCloud Drive 目录）。

### 2) 安装

```bash
git clone git@github.com:lucasZyh/zotero_ai_obsidian_flow.git
cd zotero_ai_obsidian_flow
pip3 install -r requirements.txt
```

模板文件默认位于：`./templates`

### 3) 配置 API Key

首次使用仅需创建项目根目录下的 `.env` 文件。

`.config/providers.json` 已随仓库提供；如需新增或调整供应商，可在界面“设置 API Key / 供应商”中修改。

`.env` 示例：

```dotenv
OPENAI_API_KEY="你的Key"
DASHSCOPE_API_KEY="你的Key"
# 可选：用于期刊等级检索（EasyScholar）
SecretKey="你的EasyScholarSecretKey"
```

### 4) 启动界面

```bash
cd zotero_ai_obsidian_flow
streamlit run app.py
```

也可使用：

```bash
python start_app.py
```

## 使用说明（Web UI）

在界面中可完成以下配置与操作：

- 选择 AI 供应商与模型（支持联动下拉和手动输入）。
- 维护 API Key 与供应商配置（弹窗统一管理）。
- 选择模板并设置路径（模板目录、输出目录、Zotero DB、storage）。
- 选择扫描模式：
  - 按 Zotero 目录（论文类型）
  - 按 Zotero 目录（全部类型）
  - 按 Zotero 目录下单篇
  - 按父条目 Key
  - 全库扫描（谨慎）
- 设置最近 N 天、单次处理数量、是否深度思考、是否试运行、是否强制重跑。
- 一键执行并查看实时日志。

## 目录与文件策略

### 自动目录策略

输出目录决策顺序如下：

1. 优先命中与 Zotero Collection 同名的 Obsidian 目录。
2. 读取 AI 输出的“建议目录”。
3. 在已有目录中进行语义匹配，优先复用最接近目录。
4. 若无可复用目录，则按建议目录新建。
5. 最终兜底到 `论文精读`。

### 去重策略

- 默认按父条目 Key 去重。
- 已处理条目后续会自动跳过（即使附件修改时间变化）。
- 如需重跑，可在界面启用 `Force`。

## 配置文件说明

| 文件 | 用途 | 是否提交到仓库 |
|---|---|---|
| `.config/providers.json` | 供应商目录、模型、默认设置 | 是 |
| `.env` | API Key / SecretKey 等敏感信息 | 否 |
| `.config/ui_paths.json` | 本机 UI 路径偏好（本地状态） | 否 |
| `.state/processed_items.json` | 已处理条目状态 | 否 |

## 安全与隐私

- 仓库默认忽略 `.env`、`.state/`、`.config/ui_paths.json`。
- API Key 不写入 `providers.json`，由 `.env` 管理。
- 推送前建议检查本地改动，避免将敏感路径或临时文件误提交。

## 常见问题

### 启动时报“未找到可用供应商”

请确认 `.config/providers.json` 存在且 `provider_specs` 非空。

### 读取不到 Zotero 数据

请在界面“路径设置”中确认：

- Zotero 数据库路径（通常为 `~/Zotero/zotero.sqlite`）
- Zotero storage 路径（通常为 `~/Zotero/storage`）

### 写入 Obsidian 失败

请确认输出目录存在写权限，并检查 iCloud 同步目录是否可访问。
