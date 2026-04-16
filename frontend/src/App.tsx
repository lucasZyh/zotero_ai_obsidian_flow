import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from './api'
import type {
  BootstrapData,
  DashboardStats,
  JobStartPayload,
  JobStatus,
  PageKey,
  PathSettings,
  ProviderConnectionResult,
  PdfParser,
  ProviderSpec,
  ScanMode,
  TemplateFile,
  ZoteroPaper
} from './types'

const pageItems: Array<{ key: PageKey; label: string; symbol: string }> = [
  { key: 'dashboard', label: '主面板', symbol: '⌘' },
  { key: 'reader', label: '论文精读', symbol: 'A' },
  { key: 'logs', label: '实时日志', symbol: '>' },
  { key: 'settings', label: '设置', symbol: 'S' }
]

const scanModes: Array<{ value: ScanMode; label: string; help: string }> = [
  { value: 'collection_paper', label: '按 Zotero 目录（paper）', help: '仅分析目录中的论文条目' },
  { value: 'collection_all', label: '按 Zotero 目录（all）', help: '分析目录内所有含 PDF 的条目' },
  { value: 'single_item', label: '按 Zotero 目录下单篇', help: '从目录中挑选一篇论文' },
  { value: 'parent_keys', label: '按父条目 Key', help: '直接输入 Zotero 父条目 key' },
  { value: 'global', label: '全库扫描（谨慎）', help: '需要显式确认后运行' }
]

const parserOptions: Array<{ value: PdfParser; label: string }> = [
  { value: 'auto', label: '自动（MinerU 优先）' },
  { value: 'mineru', label: 'MinerU' },
  { value: 'pypdf', label: '本地 pypdf' }
]

const emptyJob: JobStatus = {
  state: 'idle',
  running: false,
  returncode: null,
  command: '',
  log_path: '',
  target_limit: 0,
  dry_run: false,
  started_at: null,
  finished_at: null,
  stopped: false,
  progress_count: 0,
  progress_text: '0'
}

function splitKeys(raw: string): string[] {
  return raw
    .split(/[\s,，;；]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

const readerPrefsKey = 'zotero-flow-reader-prefs-v1'
const currentPageKey = 'zotero-flow-current-page-v1'
const validPages = new Set<PageKey>(pageItems.map((item) => item.key))

interface ReaderPrefs {
  providerName?: string
  modelByProvider?: Record<string, string>
  model?: string
  templateName?: string
  scanMode?: ScanMode
  selectedCollections?: string[]
  limit?: number
  sinceDays?: number
  enableThinking?: boolean
  dryRun?: boolean
  force?: boolean
  pdfParser?: PdfParser
}

function loadReaderPrefs(): ReaderPrefs {
  try {
    const raw = window.localStorage.getItem(readerPrefsKey)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function saveReaderPrefs(prefs: ReaderPrefs) {
  window.localStorage.setItem(readerPrefsKey, JSON.stringify(prefs))
}

function getInitialPage(): PageKey {
  const hashPage = window.location.hash.replace(/^#\/?/, '') as PageKey
  if (validPages.has(hashPage)) return hashPage
  const savedPage = window.localStorage.getItem(currentPageKey) as PageKey | null
  if (savedPage && validPages.has(savedPage)) return savedPage
  return 'dashboard'
}

function App() {
  const [page, setPageState] = useState<PageKey>(getInitialPage)
  const [bootstrap, setBootstrap] = useState<BootstrapData | null>(null)
  const [dashboard, setDashboard] = useState<DashboardStats | null>(null)
  const [collections, setCollections] = useState<string[]>([])
  const [job, setJob] = useState<JobStatus>(emptyJob)
  const [logText, setLogText] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const refreshBootstrap = async () => {
    const data = await api.bootstrap()
    setBootstrap(data)
    setJob(data.job)
  }

  const refreshDashboard = async () => {
    const data = await api.dashboard()
    setDashboard(data)
  }

  useEffect(() => {
    Promise.all([refreshBootstrap(), refreshDashboard(), api.collections().then((r) => setCollections(r.collections))])
      .catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => {
      api.currentJob()
        .then(setJob)
        .catch(() => undefined)
      if (job.started_at && (page === 'logs' || job.running)) {
        api.jobLog()
          .then((r) => {
            setLogText(r.content)
            setJob(r.status)
          })
          .catch(() => undefined)
      }
      if (page === 'dashboard') {
        refreshDashboard().catch(() => undefined)
      }
    }, job.running ? 1200 : 3000)
    return () => window.clearInterval(timer)
  }, [page, job.running])

  const paths = bootstrap?.paths
  const providers = bootstrap?.providers || []
  const templates = bootstrap?.templates || []

  const showNotice = (message: string) => {
    setNotice(message)
    window.setTimeout(() => setNotice(''), 2600)
  }

  const setPage = (nextPage: PageKey) => {
    setPageState(nextPage)
    window.localStorage.setItem(currentPageKey, nextPage)
    window.history.replaceState(null, '', `#${nextPage}`)
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">Z</div>
          <div>
            <div className="brand-title">Zotero Flow</div>
            <div className="brand-subtitle">AI 精读工作台</div>
          </div>
        </div>
        <nav className="nav-list" aria-label="页面导航">
          {pageItems.map((item) => (
            <button
              key={item.key}
              className={`nav-item ${page === item.key ? 'active' : ''}`}
              onClick={() => setPage(item.key)}
              type="button"
            >
              <span className="nav-symbol">{item.symbol}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <StatusBadge job={job} />
          <div className="sidebar-path">{paths?.obsidian_folder_path || '论文精读'}</div>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Zotero → AI → Obsidian</p>
            <h1>{pageItems.find((item) => item.key === page)?.label}</h1>
          </div>
          <div className="topbar-status">
            <span className="progress-text">进度 {job.progress_text}</span>
            <StatusBadge job={job} />
          </div>
        </header>

        {notice && <div className="notice success">{notice}</div>}
        {error && (
          <button className="notice error" onClick={() => setError('')} type="button">
            {error}
          </button>
        )}

        {!bootstrap ? (
          <section className="empty-state">正在读取本地配置...</section>
        ) : (
          <>
            {page === 'dashboard' && (
              <DashboardPage dashboard={dashboard} job={job} paths={paths!} providers={providers} />
            )}
            {page === 'reader' && (
              <ReaderPage
                job={job}
                providers={providers}
                templates={templates}
                collections={collections}
                defaults={bootstrap.defaults}
                onStarted={(nextJob) => {
                  setJob(nextJob)
                  setLogText('')
                  setPage('logs')
                  showNotice('任务已启动，日志会自动刷新。')
                }}
                onError={setError}
              />
            )}
            {page === 'logs' && (
              <LogsPage
                job={job}
                logText={logText}
                onRefresh={() =>
                  api.jobLog().then((r) => {
                    setLogText(r.content)
                    setJob(r.status)
                  })
                }
                onStop={() =>
                  api.stopJob().then((nextJob) => {
                    setJob(nextJob)
                    showNotice('已发送停止指令。')
                  })
                }
              />
            )}
            {page === 'settings' && (
              <SettingsPage
                paths={paths!}
                providers={providers}
                onSaved={async (message) => {
                  await refreshBootstrap()
                  await api.collections().then((r) => setCollections(r.collections))
                  showNotice(message)
                }}
                onError={setError}
              />
            )}
          </>
        )}
      </main>
    </div>
  )
}

function StatusBadge({ job }: { job: JobStatus }) {
  const text = job.running ? '运行中' : job.state === 'succeeded' ? '完成' : job.state === 'failed' ? '失败' : job.state === 'stopped' ? '已停止' : '空闲'
  return <span className={`status-badge ${job.state}`}>{text}</span>
}

function DashboardPage({
  dashboard,
  job,
  paths,
  providers
}: {
  dashboard: DashboardStats | null
  job: JobStatus
  paths: PathSettings
  providers: ProviderSpec[]
}) {
  if (!dashboard) {
    return <section className="empty-state">正在加载 Zotero 统计...</section>
  }

  return (
    <div className="page-grid">
      <section className="metric-grid">
        <Metric title="库中文献" value={dashboard.total_items} detail="Zotero 条目总量" />
        <Metric title="本月新增" value={dashboard.monthly_new_items} detail="新增条目" />
        <Metric title="本周新增" value={dashboard.weekly_new_items} detail="最近 7 天" />
        <Metric title="本周未分析" value={dashboard.weekly_unprocessed_items} detail="待处理优先级" tone="warm" />
      </section>

      <section className="content-grid two">
        <Panel title="运行概览">
          <div className="run-summary">
            <div>
              <span className="muted">当前状态</span>
              <strong>{job.running ? '正在处理论文' : '没有正在运行的任务'}</strong>
            </div>
            <div>
              <span className="muted">进度</span>
              <strong>{job.progress_text}</strong>
            </div>
            <div>
              <span className="muted">模型</span>
              <strong>{job.provider && job.model ? `${job.provider} · ${job.model}` : '尚未启动'}</strong>
            </div>
          </div>
        </Panel>
        <Panel title="关键路径">
          <dl className="path-list">
            <div><dt>Obsidian</dt><dd>{paths.obsidian_root_path}</dd></div>
            <div><dt>Zotero DB</dt><dd>{paths.zotero_db_path}</dd></div>
            <div><dt>模板目录</dt><dd>{paths.template_dir_path}</dd></div>
            <div><dt>供应商</dt><dd>{providers.length} 个</dd></div>
          </dl>
        </Panel>
      </section>

      <section className="content-grid two">
        <Panel title="文件类型分布">
          <SplitBars rows={dashboard.type_split_all || []} />
        </Panel>
        <Panel title="论文文件夹分布">
          <SplitBars rows={dashboard.folder_split_papers || dashboard.folder_split_all || []} />
        </Panel>
      </section>

      <section className="content-grid two">
        <Panel title="本周新添加">
          <PaperList rows={dashboard.weekly_titles || []} />
        </Panel>
        <Panel title="本周未分析">
          <PaperList rows={dashboard.weekly_unprocessed_titles || []} />
        </Panel>
      </section>
    </div>
  )
}

function Metric({ title, value, detail, tone = 'blue' }: { title: string; value: number; detail: string; tone?: 'blue' | 'warm' }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{title}</span>
      <strong>{value}</strong>
      <em>{detail}</em>
    </div>
  )
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-title">{title}</div>
      {children}
    </section>
  )
}

function SplitBars({ rows }: { rows: Array<{ type_name: string; total: number; processed: number; unprocessed: number }> }) {
  if (!rows.length) {
    return <div className="empty-line">暂无统计数据</div>
  }
  const max = Math.max(...rows.map((row) => row.total), 1)
  return (
    <div className="bar-list">
      {rows.slice(0, 10).map((row) => {
        const width = Math.max(4, Math.round((row.total / max) * 100))
        const done = row.total ? Math.round((row.processed / row.total) * 100) : 0
        return (
          <div className="bar-row" key={row.type_name}>
            <span title={row.type_name}>{row.type_name}</span>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${width}%` }}>
                <i style={{ width: `${done}%` }} />
              </div>
            </div>
            <b>{row.processed}/{row.total}</b>
          </div>
        )
      })}
    </div>
  )
}

function PaperList({ rows }: { rows: Array<{ title: string; parent_key: string; date_added: string; analyzed?: boolean }> }) {
  if (!rows.length) {
    return <div className="empty-line">暂无数据</div>
  }
  return (
    <div className="paper-list">
      {rows.slice(0, 8).map((row) => (
        <div className="paper-row" key={`${row.parent_key}-${row.title}`}>
          <div>
            <strong title={row.title}>{row.title || row.parent_key}</strong>
            <span>{row.date_added || '无日期'}</span>
          </div>
          <code>{row.parent_key}</code>
        </div>
      ))}
    </div>
  )
}

function ReaderPage({
  job,
  providers,
  templates,
  collections,
  defaults,
  onStarted,
  onError
}: {
  job: JobStatus
  providers: ProviderSpec[]
  templates: TemplateFile[]
  collections: string[]
  defaults: BootstrapData['defaults']
  onStarted: (job: JobStatus) => void
  onError: (message: string) => void
}) {
  const [providerName, setProviderName] = useState(providers[0]?.name || '')
  const selectedProvider = providers.find((item) => item.name === providerName) || providers[0]
  const [model, setModel] = useState(selectedProvider?.default_model || '')
  const [modelByProvider, setModelByProvider] = useState<Record<string, string>>({})
  const [templateName, setTemplateName] = useState(templates[0]?.name || '')
  const [scanMode, setScanMode] = useState<ScanMode>(defaults.scan_mode)
  const [selectedCollections, setSelectedCollections] = useState<string[]>([])
  const [collectionFilter, setCollectionFilter] = useState('')
  const [papers, setPapers] = useState<ZoteroPaper[]>([])
  const [paperFilter, setPaperFilter] = useState('')
  const [collectionItemKey, setCollectionItemKey] = useState('')
  const [parentKeysRaw, setParentKeysRaw] = useState('')
  const [allowGlobal, setAllowGlobal] = useState(false)
  const [limit, setLimit] = useState(defaults.limit)
  const [sinceDays, setSinceDays] = useState(defaults.since_days)
  const [enableThinking, setEnableThinking] = useState(false)
  const [dryRun, setDryRun] = useState(false)
  const [force, setForce] = useState(false)
  const [pdfParser, setPdfParser] = useState<PdfParser>(defaults.pdf_parser)
  const [prefsLoaded, setPrefsLoaded] = useState(false)

  useEffect(() => {
    if (prefsLoaded) return
    const prefs = loadReaderPrefs()
    if (prefs.providerName && providers.some((provider) => provider.name === prefs.providerName)) {
      setProviderName(prefs.providerName)
    } else if (!providerName && providers[0]) {
      setProviderName(providers[0].name)
    }
    if (prefs.modelByProvider && typeof prefs.modelByProvider === 'object') {
      setModelByProvider(prefs.modelByProvider)
    }
    const initialProvider = prefs.providerName || providers[0]?.name || ''
    const provider = providers.find((item) => item.name === initialProvider) || providers[0]
    const savedModel = prefs.modelByProvider?.[initialProvider] || prefs.model
    if (savedModel && provider?.models.includes(savedModel)) {
      setModel(savedModel)
    } else if (provider) {
      setModel(provider.default_model || provider.models[0] || '')
    }
    if (prefs.templateName && templates.some((template) => template.name === prefs.templateName)) {
      setTemplateName(prefs.templateName)
    } else if (!templateName && templates[0]) {
      setTemplateName(templates[0].name)
    }
    if (prefs.scanMode) setScanMode(prefs.scanMode)
    if (Array.isArray(prefs.selectedCollections)) setSelectedCollections(prefs.selectedCollections)
    if (typeof prefs.limit === 'number') setLimit(Math.max(1, prefs.limit))
    if (typeof prefs.sinceDays === 'number') setSinceDays(Math.max(0, prefs.sinceDays))
    if (typeof prefs.enableThinking === 'boolean') setEnableThinking(prefs.enableThinking)
    if (typeof prefs.dryRun === 'boolean') setDryRun(prefs.dryRun)
    if (typeof prefs.force === 'boolean') setForce(prefs.force)
    if (prefs.pdfParser) setPdfParser(prefs.pdfParser)
    if (providers.length && templates.length) setPrefsLoaded(true)
  }, [prefsLoaded, providers, templates, providerName, templateName])

  useEffect(() => {
    if (!providerName && providers[0]) {
      setProviderName(providers[0].name)
    }
  }, [providers, providerName])

  useEffect(() => {
    if (!prefsLoaded || !selectedProvider) return
    const savedForProvider = modelByProvider[selectedProvider.name]
    if (savedForProvider && selectedProvider.models.includes(savedForProvider)) {
      setModel(savedForProvider)
      return
    }
    const fallback = selectedProvider.default_model || selectedProvider.models[0] || ''
    if (model !== fallback) {
      setModel(fallback)
    }
  }, [prefsLoaded, selectedProvider?.name])

  useEffect(() => {
    if (!templateName && templates[0]) {
      setTemplateName(templates[0].name)
    }
  }, [templates, templateName])

  useEffect(() => {
    const collection = selectedCollections[0]
    if (scanMode !== 'single_item' || !collection) {
      setPapers([])
      return
    }
    api.papers(collection, sinceDays)
      .then((result) => {
        setPapers(result.papers)
        if (collectionItemKey && !result.papers.some((paper) => paper.key === collectionItemKey)) {
          setCollectionItemKey('')
        }
      })
      .catch((err) => onError(err.message))
  }, [scanMode, selectedCollections[0], sinceDays])

  useEffect(() => {
    if (!prefsLoaded) return
    saveReaderPrefs({
      providerName,
      modelByProvider,
      model,
      templateName,
      scanMode,
      selectedCollections,
      limit,
      sinceDays,
      enableThinking,
      dryRun,
      force,
      pdfParser
    })
  }, [
    prefsLoaded,
    providerName,
    model,
    modelByProvider,
    templateName,
    scanMode,
    selectedCollections,
    limit,
    sinceDays,
    enableThinking,
    dryRun,
    force,
    pdfParser
  ])

  const modelOptions = useMemo(() => {
    return selectedProvider ? [...selectedProvider.models] : []
  }, [selectedProvider])

  const selectProvider = (name: string) => {
    if (providerName && model) {
      setModelByProvider((prev) => ({ ...prev, [providerName]: model }))
    }
    setProviderName(name)
  }

  const selectModel = (value: string) => {
    setModel(value)
    if (providerName) {
      setModelByProvider((prev) => ({ ...prev, [providerName]: value }))
    }
  }

  const filteredCollections = collections.filter((name) => name.toLowerCase().includes(collectionFilter.toLowerCase()))
  const filteredPapers = papers.filter((paper) => {
    const needle = paperFilter.trim().toLowerCase()
    if (!needle) return true
    return paper.key.toLowerCase().includes(needle) || paper.title.toLowerCase().includes(needle)
  })
  const disabled = job.running

  const toggleCollection = (name: string) => {
    if (scanMode === 'single_item') {
      setCollectionItemKey('')
      setPaperFilter('')
    }
    setSelectedCollections((prev) => {
      if (scanMode === 'single_item') {
        return prev[0] === name ? [] : [name]
      }
      return prev.includes(name) ? prev.filter((item) => item !== name) : [...prev, name]
    })
  }

  const start = async () => {
    const payload: JobStartPayload = {
      provider: providerName,
      model,
      template_name: templateName,
      scan_mode: scanMode,
      collections: selectedCollections,
      collection_item_key: collectionItemKey || null,
      parent_item_keys: splitKeys(parentKeysRaw),
      allow_global_scan: allowGlobal,
      limit,
      since_days: sinceDays,
      enable_thinking: enableThinking,
      dry_run: dryRun,
      force,
      pdf_parser: pdfParser,
      mineru_model_version: defaults.mineru_model_version,
      mineru_language: defaults.mineru_language
    }
    try {
      const nextJob = await api.startJob(payload)
      onStarted(nextJob)
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="page-grid">
      <section className="content-grid two form-layout">
        <Panel title="模型与模板">
          <div className="field-grid">
            <label>
              <span>AI 提供商</span>
              <select value={providerName} onChange={(e) => selectProvider(e.target.value)} disabled={disabled}>
                {providers.map((provider) => <option key={provider.name}>{provider.name}</option>)}
              </select>
            </label>
            <label>
              <span>模型</span>
              <select value={model} onChange={(e) => selectModel(e.target.value)} disabled={disabled}>
                {modelOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className="wide">
              <span>模板文件</span>
              <select value={templateName} onChange={(e) => setTemplateName(e.target.value)} disabled={disabled}>
                {templates.map((template) => <option key={template.name}>{template.name}</option>)}
              </select>
            </label>
          </div>
        </Panel>

        <Panel title="执行参数">
          <div className="field-grid">
            <label>
              <span>单次分析数量</span>
              <input type="number" min={1} value={limit} onChange={(e) => setLimit(Number(e.target.value))} disabled={disabled} />
            </label>
            <label>
              <span>最近 N 天</span>
              <input type="number" min={0} value={sinceDays} onChange={(e) => setSinceDays(Number(e.target.value))} disabled={disabled} />
            </label>
            <label>
              <span>PDF 解析方式</span>
              <select value={pdfParser} onChange={(e) => setPdfParser(e.target.value as PdfParser)} disabled={disabled}>
                {parserOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </label>
          </div>
          <div className="toggle-row">
            <label><input type="checkbox" checked={enableThinking} onChange={(e) => setEnableThinking(e.target.checked)} disabled={disabled} /> 深度思考</label>
            <label><input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} disabled={disabled} /> 试运行</label>
            <label><input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} disabled={disabled} /> Force</label>
          </div>
        </Panel>
      </section>

      <Panel title="扫描范围">
        <div className="mode-list">
          {scanModes.map((mode) => (
            <button
              key={mode.value}
              type="button"
              className={`mode-button ${scanMode === mode.value ? 'active' : ''}`}
              onClick={() => {
                setScanMode(mode.value)
                setCollectionItemKey('')
              }}
              disabled={disabled}
            >
              <strong>{mode.label}</strong>
              <span>{mode.help}</span>
            </button>
          ))}
        </div>

        {(scanMode === 'collection_paper' || scanMode === 'collection_all' || scanMode === 'single_item') && (
          <div className="selector-area">
            <label className="search-box">
              <span>筛选目录</span>
              <input value={collectionFilter} onChange={(e) => setCollectionFilter(e.target.value)} placeholder="输入目录名" disabled={disabled} />
            </label>
            <div className="collection-list">
              {filteredCollections.map((name) => (
                <label key={name} className="collection-item">
                  <input
                    type="checkbox"
                    checked={selectedCollections.includes(name)}
                    onChange={() => toggleCollection(name)}
                    disabled={disabled}
                  />
                  <span>{name}</span>
                </label>
              ))}
              {!filteredCollections.length && <div className="empty-line">未读取到 collection，请检查 Zotero 数据库路径</div>}
            </div>
          </div>
        )}

        {scanMode === 'single_item' && selectedCollections[0] && (
          <div className="full-field paper-picker">
            <label className="search-box">
              <span>选择该目录中的论文</span>
              <input
                value={paperFilter}
                onChange={(e) => setPaperFilter(e.target.value)}
                placeholder="搜索标题或 Zotero Key"
                disabled={disabled || !papers.length}
              />
            </label>
            <div className="paper-picker-list" role="listbox" aria-label="选择该目录中的论文">
              {!papers.length && <div className="empty-line">该目录下暂无可选论文</div>}
              {papers.length > 0 && !filteredPapers.length && <div className="empty-line">没有匹配的论文</div>}
              {filteredPapers.map((paper) => (
                <button
                  key={paper.key}
                  className={`paper-picker-item ${collectionItemKey === paper.key ? 'active' : ''}`}
                  onClick={() => setCollectionItemKey(paper.key)}
                  type="button"
                  role="option"
                  aria-selected={collectionItemKey === paper.key}
                  disabled={disabled}
                >
                  <strong title={paper.title}>{paper.title || paper.key}</strong>
                  <span className="paper-picker-meta">{paper.key} · {paper.date_modified || '无日期'}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {scanMode === 'parent_keys' && (
          <label className="full-field">
            <span>父条目 key</span>
            <textarea
              value={parentKeysRaw}
              onChange={(e) => setParentKeysRaw(e.target.value)}
              placeholder="例如：A6G4QK3V 或 A6G4QK3V, DWE9YC63"
              disabled={disabled}
            />
          </label>
        )}

        {scanMode === 'global' && (
          <label className="confirm-line">
            <input type="checkbox" checked={allowGlobal} onChange={(e) => setAllowGlobal(e.target.checked)} disabled={disabled} />
            我确认要全库扫描
          </label>
        )}
      </Panel>

      <div className="action-row">
        <button className="primary-action" onClick={start} disabled={disabled || !providers.length || !templates.length} type="button">
          开始执行
        </button>
      </div>
    </div>
  )
}

function LogsPage({
  job,
  logText,
  onRefresh,
  onStop
}: {
  job: JobStatus
  logText: string
  onRefresh: () => Promise<void>
  onStop: () => Promise<void>
}) {
  const hasCurrentRun = Boolean(job.started_at)
  return (
    <div className="page-grid">
      <section className="content-grid two">
        <Panel title="执行状态">
          <div className="run-summary">
            <div><span className="muted">状态</span><strong>{job.state}</strong></div>
            <div><span className="muted">进度</span><strong>{job.progress_text}</strong></div>
            <div><span className="muted">退出码</span><strong>{job.returncode ?? '未结束'}</strong></div>
          </div>
        </Panel>
        <Panel title="日志控制">
          <div className="button-row">
            <button onClick={() => void onRefresh()} disabled={!hasCurrentRun} type="button">刷新日志</button>
            <button onClick={() => void onStop()} disabled={!job.running} type="button">停止任务</button>
          </div>
          <p className="muted small-text">{hasCurrentRun ? job.log_path : '本次还没有执行任务'}</p>
        </Panel>
      </section>
      <Panel title="执行命令">
        <pre className="command-block">{hasCurrentRun && job.command ? job.command : '本次还没有启动任务'}</pre>
      </Panel>
      <Panel title="输出日志">
        <pre className="log-block">{hasCurrentRun ? logText || '暂无日志。任务启动后会自动刷新。' : '本次执行日志会在点击“开始执行”后显示。'}</pre>
      </Panel>
    </div>
  )
}

function SettingsPage({
  paths,
  providers,
  onSaved,
  onError
}: {
  paths: PathSettings
  providers: ProviderSpec[]
  onSaved: (message: string) => Promise<void>
  onError: (message: string) => void
}) {
  const [pathForm, setPathForm] = useState(paths)
  const emptyProviderForm = {
    name: '',
    model: '',
    provider_type: 'openai_compatible' as 'openai_compatible' | 'gemini',
    base_url: '',
    env_var: '',
    custom_models: '',
    api_key: ''
  }
  const [providerName, setProviderName] = useState(providers[0]?.name || '')
  const [isAddingProvider, setIsAddingProvider] = useState(false)
  const [providerForm, setProviderForm] = useState({
    name: providers[0]?.name || '',
    model: providers[0]?.default_model || '',
    provider_type: providers[0]?.provider_type || 'openai_compatible',
    base_url: providers[0]?.base_url || '',
    env_var: providers[0]?.env_var || '',
    custom_models: providers[0]?.models?.join(', ') || '',
    api_key: providers[0]?.api_key || ''
  })
  const [mineruToken, setMineruToken] = useState('')
  const [mineruModelVersion, setMineruModelVersion] = useState('vlm')
  const [mineruLanguage, setMineruLanguage] = useState('en')
  const [showApiKey, setShowApiKey] = useState(false)
  const [showMineruToken, setShowMineruToken] = useState(false)
  const [providerToDelete, setProviderToDelete] = useState<ProviderSpec | null>(null)
  const [isDeletingProvider, setIsDeletingProvider] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [connectionResult, setConnectionResult] = useState<ProviderConnectionResult | null>(null)
  const [isTestingProvider, setIsTestingProvider] = useState(false)

  useEffect(() => {
    setPathForm(paths)
  }, [paths])

  useEffect(() => {
    api.mineru()
      .then((result) => {
        setMineruToken(result.token || '')
        setMineruModelVersion(result.model_version || 'vlm')
        setMineruLanguage(result.language || 'en')
      })
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    if (isAddingProvider) return
    const provider = providers.find((item) => item.name === providerName) || providers[0]
    if (!provider) return
    setProviderName(provider.name)
    setProviderForm({
      name: provider.name,
      model: provider.default_model,
      provider_type: provider.provider_type,
      base_url: provider.base_url,
      env_var: provider.env_var,
      custom_models: provider.models.join(', '),
      api_key: provider.api_key || ''
    })
  }, [providerName, providers, isAddingProvider])

  useEffect(() => {
    setConnectionResult(null)
  }, [
    providerForm.name,
    providerForm.model,
    providerForm.provider_type,
    providerForm.base_url,
    providerForm.api_key,
    isAddingProvider
  ])

  const updatePath = (key: keyof PathSettings, value: string) => {
    setPathForm((prev) => ({ ...prev, [key]: value }))
  }

  const savePaths = async () => {
    try {
      await api.savePaths(pathForm)
      await onSaved('路径设置已保存。')
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err))
    }
  }

  const saveProvider = async () => {
    try {
      if (isAddingProvider && !providerForm.api_key.trim()) {
        onError('新增供应商必须填写 API Key，API Key 会保存到本地 .env。')
        return
      }
      const result = await api.saveProvider({
        name: providerForm.name,
        model: providerForm.model,
        provider_type: providerForm.provider_type as 'openai_compatible' | 'gemini',
        base_url: providerForm.base_url,
        env_var: '',
        custom_models: providerForm.custom_models.split(',').map((item) => item.trim()).filter(Boolean),
        api_key: providerForm.api_key ? providerForm.api_key : undefined,
        is_new: isAddingProvider
      })
      const savedProvider = result.provider
      setIsAddingProvider(false)
      setProviderName(savedProvider.name)
      setProviderForm({
        name: savedProvider.name,
        model: savedProvider.default_model,
        provider_type: savedProvider.provider_type,
        base_url: savedProvider.base_url,
        env_var: savedProvider.env_var,
        custom_models: savedProvider.models.join(', '),
        api_key: savedProvider.api_key || ''
      })
      await onSaved('供应商设置已保存。')
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err))
    }
  }

  const testProvider = async () => {
    setIsTestingProvider(true)
    setConnectionResult(null)
    try {
      const result = await api.testProvider({
        name: providerForm.name,
        model: providerForm.model,
        provider_type: providerForm.provider_type as 'openai_compatible' | 'gemini',
        base_url: providerForm.base_url,
        api_key: providerForm.api_key || null
      })
      setConnectionResult(result)
    } catch (err) {
      setConnectionResult({
        ok: false,
        status: null,
        message: err instanceof Error ? err.message : String(err),
        elapsed_ms: 0
      })
    } finally {
      setIsTestingProvider(false)
    }
  }

  const deleteProvider = async () => {
    if (!providerToDelete) return
    const deletingName = providerToDelete.name
    setIsDeletingProvider(true)
    setDeleteError('')
    try {
      const result = await api.deleteProvider(deletingName)
      const nextProvider = result.providers[0]
      setProviderToDelete(null)
      setIsDeletingProvider(false)
      if (nextProvider) {
        setProviderName(nextProvider.name)
        setProviderForm({
          name: nextProvider.name,
          model: nextProvider.default_model,
          provider_type: nextProvider.provider_type,
          base_url: nextProvider.base_url,
          env_var: nextProvider.env_var,
          custom_models: nextProvider.models.join(', '),
          api_key: nextProvider.api_key || ''
        })
      } else {
        setProviderName('')
        setProviderForm(emptyProviderForm)
      }
      await onSaved(`已删除供应商：${deletingName}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setDeleteError(message)
      setIsDeletingProvider(false)
      onError(message)
    }
  }

  const saveMineru = async () => {
    try {
      const result = await api.saveMineru({
        token: mineruToken,
        model_version: mineruModelVersion,
        language: mineruLanguage
      })
      setMineruToken(result.token || '')
      setMineruModelVersion(result.model_version || 'vlm')
      setMineruLanguage(result.language || 'en')
      await onSaved('MinerU 配置已保存。')
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="page-grid">
      <section className="content-grid two">
        <Panel title="路径设置">
          <div className="field-grid single">
            <label><span>供应商配置文件</span><input value={pathForm.provider_config_path} onChange={(e) => updatePath('provider_config_path', e.target.value)} /></label>
            <label><span>模板目录</span><input value={pathForm.template_dir_path} onChange={(e) => updatePath('template_dir_path', e.target.value)} /></label>
            <label><span>Obsidian 库路径</span><input value={pathForm.obsidian_vault_path} onChange={(e) => updatePath('obsidian_vault_path', e.target.value)} /></label>
            <label><span>Obsidian 库内文件夹</span><input value={pathForm.obsidian_folder_path} onChange={(e) => updatePath('obsidian_folder_path', e.target.value)} /></label>
            <label><span>Zotero 数据库</span><input value={pathForm.zotero_db_path} onChange={(e) => updatePath('zotero_db_path', e.target.value)} /></label>
            <label><span>Zotero storage 目录</span><input value={pathForm.zotero_storage_path} onChange={(e) => updatePath('zotero_storage_path', e.target.value)} /></label>
          </div>
          <div className="button-row"><button onClick={() => void savePaths()} type="button">保存路径设置</button></div>
        </Panel>

        <Panel title="API 供应商">
          <div className="field-grid">
            <label className="wide">
              <span>选择供应商</span>
              <select value={providerName} onChange={(e) => setProviderName(e.target.value)} disabled={isAddingProvider}>
                {providers.map((provider) => <option key={provider.name}>{provider.name}</option>)}
              </select>
            </label>
            <label><span>供应商名称</span><input value={providerForm.name} onChange={(e) => setProviderForm((prev) => ({ ...prev, name: e.target.value }))} /></label>
            <label>
              <span>供应商类型</span>
              <select
                value={providerForm.provider_type}
                onChange={(e) =>
                  setProviderForm((prev) => ({
                    ...prev,
                    provider_type: e.target.value as 'openai_compatible' | 'gemini'
                  }))
                }
              >
                <option value="openai_compatible">openai_compatible</option>
                <option value="gemini">gemini</option>
              </select>
            </label>
            <label><span>默认模型</span><input value={providerForm.model} onChange={(e) => setProviderForm((prev) => ({ ...prev, model: e.target.value }))} /></label>
            <label><span>API Key</span>
              <div className="secret-field">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  value={providerForm.api_key}
                  placeholder="未配置"
                  onChange={(e) => setProviderForm((prev) => ({ ...prev, api_key: e.target.value }))}
                />
                <button
                  className="secret-toggle"
                  onClick={() => setShowApiKey((value) => !value)}
                  type="button"
                  title={showApiKey ? '隐藏 API Key' : '显示 API Key'}
                  aria-label={showApiKey ? '隐藏 API Key' : '显示 API Key'}
                >
                  {showApiKey ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              </div>
            </label>
            <label className="wide"><span>Base URL</span><input value={providerForm.base_url} onChange={(e) => setProviderForm((prev) => ({ ...prev, base_url: e.target.value }))} /></label>
            <label className="wide"><span>额外模型（逗号分隔）</span><input value={providerForm.custom_models} onChange={(e) => setProviderForm((prev) => ({ ...prev, custom_models: e.target.value }))} /></label>
          </div>
          <div className="button-row">
            {!isAddingProvider && (
              <button
                onClick={() => {
                  setIsAddingProvider(true)
                  setProviderForm(emptyProviderForm)
                  setShowApiKey(false)
                }}
                type="button"
              >
                添加新供应商
              </button>
            )}
            {isAddingProvider && (
              <button
                onClick={() => {
                  setIsAddingProvider(false)
                  setProviderName(providers[0]?.name || '')
                }}
                type="button"
              >
                取消新增
              </button>
            )}
            <button onClick={() => void testProvider()} disabled={isTestingProvider} type="button">
              {isTestingProvider ? '测试中...' : '连接测试'}
            </button>
            <button onClick={() => void saveProvider()} type="button">{isAddingProvider ? '保存新供应商' : '保存修改'}</button>
            {!isAddingProvider && providerName && (
              <button
                className="danger-button"
                onClick={() => {
                  const provider = providers.find((item) => item.name === providerName)
                  if (provider) {
                    setDeleteError('')
                    setProviderToDelete(provider)
                  }
                }}
                type="button"
              >
                删除供应商
              </button>
            )}
          </div>
          {connectionResult && (
            <div className={`connection-result ${connectionResult.ok ? 'success' : 'error'}`}>
              <strong>{connectionResult.ok ? '连通正常' : '连通失败'}</strong>
              <span>
                {connectionResult.status ? `HTTP ${connectionResult.status} · ` : ''}
                {connectionResult.message}
                {connectionResult.elapsed_ms ? ` · ${connectionResult.elapsed_ms}ms` : ''}
              </span>
            </div>
          )}
        </Panel>
      </section>

      <Panel title="MinerU 配置">
        <div className="mineru-grid">
          <label><span>MinerU API Token</span>
            <div className="secret-field">
              <input
                type={showMineruToken ? 'text' : 'password'}
                value={mineruToken}
                onChange={(e) => setMineruToken(e.target.value)}
                placeholder="输入新 Token"
              />
              <button
                className="secret-toggle"
                onClick={() => setShowMineruToken((value) => !value)}
                type="button"
                title={showMineruToken ? '隐藏 MinerU Token' : '显示 MinerU Token'}
                aria-label={showMineruToken ? '隐藏 MinerU Token' : '显示 MinerU Token'}
              >
                {showMineruToken ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
          </label>
          <label>
            <span>MinerU 模型版本</span>
            <input value={mineruModelVersion} onChange={(e) => setMineruModelVersion(e.target.value)} placeholder="vlm" />
          </label>
          <label>
            <span>文档语言</span>
            <input value={mineruLanguage} onChange={(e) => setMineruLanguage(e.target.value)} placeholder="en" />
          </label>
        </div>
        <div className="button-row"><button onClick={() => void saveMineru()} type="button">保存 MinerU 配置</button></div>
      </Panel>
      {providerToDelete && (
        <div className="modal-backdrop" role="presentation">
          <div className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-provider-title">
            <div className="panel-title" id="delete-provider-title">确认删除供应商</div>
            <p>
              将删除供应商 <strong>{providerToDelete.name}</strong>，并移除本地 `.env` 中对应的 API Key。
            </p>
            {deleteError && <div className="inline-error">{deleteError}</div>}
            <div className="button-row">
              <button onClick={() => setProviderToDelete(null)} disabled={isDeletingProvider} type="button">取消</button>
              <button className="danger-button" onClick={() => void deleteProvider()} disabled={isDeletingProvider} type="button">
                {isDeletingProvider ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function EyeIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M2.6 12c2.1-3.2 5.2-5 9.4-5s7.3 1.8 9.4 5c-2.1 3.2-5.2 5-9.4 5s-7.3-1.8-9.4-5Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function EyeOffIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3.4 4.7 19.3 20.6" />
      <path d="M9.9 9.9A3 3 0 0 0 14.1 14.1" />
      <path d="M7.4 7.7C5.4 8.7 3.8 10.2 2.6 12c2.1 3.2 5.2 5 9.4 5 1.4 0 2.7-.2 3.8-.6" />
      <path d="M11 7.1c.3 0 .7-.1 1-.1 4.2 0 7.3 1.8 9.4 5-.6.9-1.3 1.7-2.1 2.4" />
    </svg>
  )
}

export default App
