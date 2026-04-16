export type PageKey = 'dashboard' | 'reader' | 'logs' | 'settings'

export type ScanMode = 'collection_paper' | 'collection_all' | 'single_item' | 'parent_keys' | 'global'

export type PdfParser = 'auto' | 'mineru' | 'pypdf'

export interface PathSettings {
  provider_config_path: string
  template_dir_path: string
  obsidian_vault_path: string
  obsidian_folder_path: string
  obsidian_root_path: string
  zotero_db_path: string
  zotero_storage_path: string
}

export interface TemplateFile {
  name: string
  path: string
}

export interface ProviderSpec {
  name: string
  provider_type: 'openai_compatible' | 'gemini'
  base_url: string
  default_model: string
  models: string[]
  custom_models: string[]
  env_var: string
  api_key: string
  has_api_key: boolean
}

export interface ProviderConnectionResult {
  ok: boolean
  status: number | null
  message: string
  elapsed_ms: number
}

export interface MineruSettings {
  env_var: string
  token: string
  has_token: boolean
  model_version: string
  language: string
}

export interface JobStatus {
  state: 'idle' | 'running' | 'succeeded' | 'failed' | 'stopped'
  running: boolean
  returncode: number | null
  command: string
  log_path: string
  target_limit: number
  dry_run: boolean
  started_at: string | null
  finished_at: string | null
  stopped: boolean
  progress_count: number
  progress_text: string
  provider?: string
  model?: string
  scan_mode?: ScanMode
}

export interface BootstrapData {
  paths: PathSettings
  templates: TemplateFile[]
  providers: ProviderSpec[]
  job: JobStatus
  defaults: {
    pdf_parser: PdfParser
    mineru_model_version: string
    mineru_language: string
    scan_mode: ScanMode
    limit: number
    since_days: number
  }
}

export interface DashboardStats {
  total_items: number
  weekly_new_items: number
  monthly_new_items: number
  unprocessed_items: number
  weekly_unprocessed_items: number
  type_split_all: SplitRow[]
  folder_split_all: SplitRow[]
  folder_split_papers: SplitRow[]
  top_folder_counts_monthly_new: [string, number][]
  weekly_titles: PaperRow[]
  weekly_unprocessed_titles: PaperRow[]
}

export interface SplitRow {
  type_name: string
  total: number
  processed: number
  unprocessed: number
}

export interface PaperRow {
  title: string
  parent_key: string
  date_added: string
  analyzed?: boolean
}

export interface ZoteroPaper {
  key: string
  title: string
  date_modified: string
}

export interface JobStartPayload {
  provider: string
  model: string
  template_name: string
  scan_mode: ScanMode
  collections: string[]
  collection_item_key?: string | null
  parent_item_keys: string[]
  allow_global_scan: boolean
  limit: number
  since_days: number
  enable_thinking: boolean
  dry_run: boolean
  force: boolean
  pdf_parser: PdfParser
  mineru_model_version: string
  mineru_language: string
}
