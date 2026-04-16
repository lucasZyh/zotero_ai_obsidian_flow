import type {
  BootstrapData,
  DashboardStats,
  JobStartPayload,
  JobStatus,
  MineruSettings,
  PathSettings,
  ProviderConnectionResult,
  ProviderSpec,
  ZoteroPaper
} from './types'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init
  })
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      message = body.detail || message
    } catch {
      // Keep the transport-level message.
    }
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

export const api = {
  bootstrap: () => request<BootstrapData>('/api/app/bootstrap'),
  dashboard: () => request<DashboardStats>('/api/dashboard'),
  collections: () => request<{ collections: string[] }>('/api/collections'),
  papers: (name: string, sinceDays: number) =>
    request<{ papers: ZoteroPaper[] }>(`/api/collections/${encodeURIComponent(name)}/papers?sinceDays=${sinceDays}`),
  currentJob: () => request<JobStatus>('/api/jobs/current'),
  startJob: (payload: JobStartPayload) =>
    request<JobStatus>('/api/jobs', { method: 'POST', body: JSON.stringify(payload) }),
  stopJob: () => request<JobStatus>('/api/jobs/current/stop', { method: 'POST' }),
  jobLog: (tail = 30000) => request<{ content: string; status: JobStatus }>(`/api/jobs/current/log?tail=${tail}`),
  savePaths: (payload: Partial<PathSettings>) =>
    request<PathSettings>('/api/settings/paths', { method: 'PUT', body: JSON.stringify(payload) }),
  providers: () => request<{ providers: ProviderSpec[]; provider_config_path: string }>('/api/settings/providers'),
  saveProvider: (payload: {
    name: string
    model: string
    provider_type: 'openai_compatible' | 'gemini'
    base_url: string
    env_var: string
    custom_models: string[]
    api_key?: string | null
    is_new?: boolean
  }) => request<{ providers: ProviderSpec[]; provider: ProviderSpec }>('/api/settings/providers', {
    method: 'PUT',
    body: JSON.stringify(payload)
  }),
  testProvider: (payload: {
    name: string
    model: string
    provider_type: 'openai_compatible' | 'gemini'
    base_url: string
    api_key?: string | null
  }) => request<ProviderConnectionResult>('/api/settings/providers/test', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  deleteProvider: (name: string) =>
    request<{ providers: ProviderSpec[]; provider_config_path: string }>(`/api/settings/providers/${encodeURIComponent(name)}`, {
      method: 'DELETE'
    }),
  mineru: () => request<MineruSettings>('/api/settings/mineru'),
  saveMineru: (payload: { token: string; model_version: string; language: string }) =>
    request<MineruSettings>('/api/settings/mineru', {
      method: 'PUT',
      body: JSON.stringify(payload)
    })
}
