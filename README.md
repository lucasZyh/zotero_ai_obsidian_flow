# Zotero -> AI -> Obsidian 自动论文精读流程

这个工具会自动：

1. 从本地 `Zotero` 读取论文元数据和 PDF。
2. 把 PDF 文本交给你选择的 AI（ChatGPT / Gemini / 千问）。
3. 按你提供的模板生成深度分析 Markdown。
4. 自动选择（或创建）Obsidian 文件夹并写入笔记。
5. 支持多供应商：OpenAI、Gemini、千问、DeepSeek、GLM、AIHubMix、硅基流动（SiliconFlow）。

## 已按你的需求调整

1. 默认输出目录：
`/Users/yuanhao/Library/Mobile Documents/iCloud~md~obsidian/Documents/研究生/论文精度`

2. 默认不允许全库扫描，必须明确范围：
- 扫描某一个 Zotero 目录（collection，仅论文类型）：`--collection`
- 扫描某一个 Zotero 目录（all，目录下所有含 PDF 类型）：`--collection --collection-all-types`
- 扫描某个 Zotero 目录下的单篇：`--collection + --collection-item-key`
- 按父条目 key 直接扫描：`--parent-item-key`（可重复）
- 若确实要全库扫描，需显式加 `--allow-global-scan`

3. 提供可视化操作界面（Streamlit）：`app.py`
4. 模板默认放在项目目录 `templates/`，网页为下拉选择；模板目录路径可在“设置（路径）”里修改。

## 1) 安装

```bash
cd /Users/yuanhao/Documents/code/home
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

模板文件请放在：
`/Users/yuanhao/Documents/code/home/templates`

## 2) 配置 API Key

API Key 统一保存在项目根目录 `.env`（可在 Web 界面“设置 API Key / 供应商”中维护）。
脚本会读取 `.env`，不再依赖系统环境变量。

## 3) 命令行运行示例

### 按某个 Zotero 目录（推荐）

```bash
python pipeline.py \
  --provider deepseek \
  --template "./templates/论文深度分析模板.md" \
  --collection "新文献阅读" \
  --limit 2 \
  --since-days 0
```

### 按 Zotero 目录下单篇（不手动查 key 的话可用界面选）

```bash
python pipeline.py \
  --provider openai \
  --template "./templates/论文深度分析模板.md" \
  --collection "新文献阅读" \
  --collection-item-key ABCD1234 \
  --limit 1
```

### 按父条目 key 直接处理

```bash
python pipeline.py \
  --provider qwen \
  --template "./templates/论文深度分析模板.md" \
  --parent-item-key A6G4QK3V \
  --limit 1
```

### 全库扫描（需显式确认）

```bash
python pipeline.py \
  --provider openai \
  --template "./templates/论文深度分析模板.md" \
  --allow-global-scan \
  --limit 5
```

### 试运行（仅测连通，不执行分析）

```bash
python pipeline.py ... --dry-run
```
该模式会测试模型 API 是否联通，并打印将处理/将写入路径；不会提取 PDF 文本做分析，也不会写入 Obsidian。

## 4) 可视化界面

```bash
cd /Users/yuanhao/Documents/code/home
source .venv/bin/activate
streamlit run app.py
```

界面里可以：
- 选择 AI 提供商/模型
- 可选开启“深度思考”开关（当前对 qwen / deepseek / openai 生效）
- 模型按供应商联动下拉；也可手动输入，保存后会自动加入该供应商下拉列表
- 主界面隐藏 API Key；通过“设置 API Key / 供应商”按钮弹窗统一配置
- 弹窗分为两个页面：默认“现有供应商配置”，切换后可“新增自定义供应商”
- 模板始终下拉选择；模板目录路径可在“设置（路径）”里修改
- 路径相关项收纳在侧边栏最下方的“设置（路径）”里（模板目录、输出目录、Zotero数据库、storage目录）
- 选择扫描模式（按目录 / 按目录下单篇 / 按父条目Key / 全库）
- `最近N天更新` 默认是 `0`（显示全部），并会影响“按目录下单篇”的可选论文列表
- 一键执行并查看日志

## 5) 自动目录策略

脚本会按以下顺序决定保存目录：

1. 优先复用 Obsidian 中与 Zotero Collection 同名的目录。
2. 读取 AI 输出的 `建议目录：xxx`。
3. 再次调用 AI，将“建议目录”与“已有目录列表”做匹配，优先复用语义最接近的已有目录。
4. 若仍无法匹配，使用 `建议目录` 新建目录。
5. 最终落到 `论文精读` 目录（不存在会自动创建）。

## 6) 去重策略

- 默认按父条目 key 去重，已处理过的条目会跳过（即使附件 PDF 批注导致时间变化）。
- 用 `--force` 可强制重跑。
