const BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

let authToken: string | null = localStorage.getItem('kolibri_token')

export function setAuthToken(token: string | null) {
  authToken = token
  if (token) localStorage.setItem('kolibri_token', token)
  else localStorage.removeItem('kolibri_token')
}

export function getAuthToken() { return authToken }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...init?.headers as Record<string, string> }
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`
  const res = await fetch(`${BASE}${path}`, { headers, ...init })
  if (!res.ok) {
    let detail = `API ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || body.message || detail
    } catch { /* ignore parse error */ }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Position {
  id: string
  code: string
  name: string
  unit: string
  quantity: string
  price: string
  sum: string
  source: string
  comment: string
}

export interface Section {
  id: string
  title: string
  subtotal: string
  positions: Position[]
}

export interface Estimate {
  id: string
  version: number
  status: 'draft' | 'ready' | 'approved' | 'archived'
  title: string
  client: string
  object_name: string
  region: string
  currency: string
  overhead_rate: string
  vat_rate: string
  subtotal: string
  overhead_amount: string
  vat_amount: string
  total: string
  sections: Section[]
  created_at: string
  updated_at: string
}

export interface EstimateListResponse {
  items: Estimate[]
  total: number
  page: number
  page_size: number
}

export interface Document {
  id: string
  title: string
  type: string
  status: string
  client: string
  project: string
  content: string
  variables: Record<string, string>
  template: string
  estimate_id: string | null
  created_at: string
  updated_at: string
}

export interface LibraryItem {
  id: string
  title: string
  item_type: string
  source_id: string
  source_type: string
  status: string
  client: string
  project: string
  file_size: number
  created_at: string
  updated_at: string
}

export interface Agent {
  id: string
  name: string
  role: string
  status: string
  node_id: string | null
  current_task: string | null
  progress: number
  model: string | null
  capabilities: Record<string, unknown>
  cost_accumulated: string
  heartbeat_at: string | null
}

export interface Node {
  id: string
  name: string
  region: string
  ip_address: string
  status: string
  cpu_percent: string
  ram_percent: string
  disk_percent: string
  network_mbps: string
  agent_count: number
  task_count: number
  ping_ms: number
  max_agents: number
  capabilities: Record<string, unknown>
}

export interface Task {
  id: string
  workflow_id: string
  state: string
  priority: number
  owner_agent_id: string | null
  node_id: string | null
  budget_limit: string | null
  attempts: number
  max_retries: number
  result: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface PaginatedList<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface EstimateCreateInput {
  title: string
  status?: Estimate['status']
  client?: string
  object_name?: string
  region?: string
  currency?: string
  overhead_rate?: string
  vat_rate?: string
  sections?: { title: string; positions?: { code: string; name: string; unit: string; quantity: string; price: string; source?: string; comment?: string }[] }[]
}

// ---------------------------------------------------------------------------
// Estimates
// ---------------------------------------------------------------------------

export const estimates = {
  list: (params?: { page?: number; page_size?: number; status?: string; search?: string }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.page_size) qs.set('page_size', String(params.page_size))
    if (params?.status) qs.set('status', params.status)
    if (params?.search) qs.set('search', params.search)
    return request<EstimateListResponse>(`/estimates?${qs}`)
  },
  get: (id: string) => request<Estimate>(`/estimates/${id}`),
  create: (data: EstimateCreateInput) => request<Estimate>('/estimates', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: Partial<EstimateCreateInput & { status: string; sections: EstimateCreateInput['sections'] }>) =>
    request<Estimate>(`/estimates/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: string) => request<void>(`/estimates/${id}`, { method: 'DELETE' }),
  calculate: (id: string) => request<Estimate>(`/estimates/${id}/calculate`, { method: 'POST' }),
  duplicate: (id: string) => request<Estimate>(`/estimates/${id}/duplicate`, { method: 'POST' }),
  pdfUrl: (id: string) => `${BASE}/estimates/${id}/pdf`,
  exportUrl: (id: string, fmt: 'csv' | 'json') => `${BASE}/estimates/${id}/export/${fmt}`,
}

export const health = {
  v1: () => request<{ status: string; service: string; estimates: number }>('/health'),
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export const documents = {
  list: (params?: { page?: number; page_size?: number; type?: string }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.page_size) qs.set('page_size', String(params.page_size))
    if (params?.type) qs.set('type', params.type)
    return request<PaginatedList<Document>>(`/documents?${qs}`)
  },
  get: (id: string) => request<Document>(`/documents/${id}`),
  create: (data: { title: string; type?: string; client?: string; project?: string; content?: string; variables?: Record<string, string>; template?: string }) =>
    request<Document>('/documents', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: Partial<Document>) =>
    request<Document>(`/documents/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: string) => request<void>(`/documents/${id}`, { method: 'DELETE' }),
  pdfUrl: (id: string) => `${BASE}/documents/${id}/pdf`,
  docxUrl: (id: string) => `${BASE}/documents/${id}/docx`,
}

// ---------------------------------------------------------------------------
// Library
// ---------------------------------------------------------------------------

export const library = {
  list: (params?: { page?: number; page_size?: number; item_type?: string; search?: string }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.page_size) qs.set('page_size', String(params.page_size))
    if (params?.item_type) qs.set('item_type', params.item_type)
    if (params?.search) qs.set('search', params.search)
    return request<PaginatedList<LibraryItem>>(`/library?${qs}`)
  },
}

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export const agents = {
  list: (params?: { page?: number; page_size?: number; status?: string }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.page_size) qs.set('page_size', String(params.page_size))
    if (params?.status) qs.set('status', params.status)
    return request<PaginatedList<Agent>>(`/agents?${qs}`)
  },
  get: (id: string) => request<Agent>(`/agents/${id}`),
  create: (data: { name: string; role?: string; model?: string }) =>
    request<Agent>('/agents', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: Partial<Agent>) =>
    request<Agent>(`/agents/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id: string) => request<void>(`/agents/${id}`, { method: 'DELETE' }),
}

// ---------------------------------------------------------------------------
// Nodes
// ---------------------------------------------------------------------------

export const nodes = {
  list: (params?: { page?: number; page_size?: number; status?: string }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.page_size) qs.set('page_size', String(params.page_size))
    if (params?.status) qs.set('status', params.status)
    return request<PaginatedList<Node>>(`/nodes?${qs}`)
  },
  update: (id: string, data: Partial<Node>) =>
    request<Node>(`/nodes/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
}

// ---------------------------------------------------------------------------
// Tasks
// ---------------------------------------------------------------------------

export const tasks = {
  list: (params?: { page?: number; page_size?: number; state?: string }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.page_size) qs.set('page_size', String(params.page_size))
    if (params?.state) qs.set('state', params.state)
    return request<PaginatedList<Task>>(`/tasks?${qs}`)
  },
  update: (id: string, data: Partial<Task>) =>
    request<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
}

// ---------------------------------------------------------------------------
// Cluster
// ---------------------------------------------------------------------------

export interface ClusterStats {
  nodes: { total: number; healthy: number; degraded: number; offline: number }
  agents: { total: number; active: number; idle: number; paused: number }
  tasks: { total: number; running: number; queued: number; completed: number; failed: number }
  resources: { avg_cpu: number; avg_ram: number; avg_disk: number }
}

export const cluster = {
  stats: () => request<ClusterStats>('/cluster/stats'),
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export interface ChatAction {
  type: string
  label: string
  data?: Record<string, unknown>
}

export interface ChatResponse {
  content: string
  reasoning: string
  actions: ChatAction[]
  status: string
}

export const chat = {
  send: (messages: { role: string; content: string }[]) =>
    request<ChatResponse>('/chat', { method: 'POST', body: JSON.stringify({ messages }) }),
}

// ---------------------------------------------------------------------------
// AI Provider
// ---------------------------------------------------------------------------

export interface AIResponse {
  content: string
  reasoning: string
  actions: ChatAction[]
  status: string
}

export interface FixChange {
  type: string
  position: string
  old: string
  new: string
  reason: string
}

export interface FixResponse {
  estimate: Estimate
  changes: FixChange[]
}

export const ai = {
  analyzeEstimate: (estId: string) =>
    request<AIResponse>(`/ai/analyze-estimate?est_id=${estId}`, { method: 'POST' }),
  fixEstimate: (estId: string) =>
    request<FixResponse>(`/ai/fix-estimate?est_id=${estId}`, { method: 'POST' }),
  generateDocument: (type: string, context?: string) =>
    request<AIResponse>('/ai/generate-document', { method: 'POST', body: JSON.stringify({ type, context }) }),
  suggest: (query: string) =>
    request<AIResponse>('/ai/suggest', { method: 'POST', body: JSON.stringify({ query }) }),
}

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

export interface Template {
  id: string
  title: string
  type: string
  variables: string[]
}

export const templates = {
  list: () => request<Template[]>('/templates'),
  get: (id: string) => request<Template>(`/templates/${id}`),
  createDocument: (id: string) => request<Document>(`/templates/${id}/create-document`, { method: 'POST' }),
  render: (id: string, variables: Record<string, string>) =>
    request<{ title: string; content: string; variables: string[] }>(`/templates/${id}/render`, { method: 'POST', body: JSON.stringify({ variables }) }),
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface AuthUser {
  id: string
  email: string
  name: string
  role: string
}

interface AuthResponse {
  access_token: string
  token_type: string
  user: AuthUser
}

export const auth = {
  register: (email: string, name: string, password: string) =>
    request<AuthResponse>('/auth/register', { method: 'POST', body: JSON.stringify({ email, name, password }) }),
  login: (email: string, password: string) =>
    request<AuthResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  me: () => request<AuthUser>('/auth/me'),
  updateMe: (data: { name?: string; email?: string; current_password?: string; new_password?: string }) =>
    request<AuthUser>('/auth/me', { method: 'PUT', body: JSON.stringify(data) }),
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export interface SearchResult {
  type: string
  id: string
  title: string
  score: number
  [key: string]: unknown
}

export interface SearchResponse {
  query: string
  total: number
  results: SearchResult[]
  by_type: Record<string, number>
}

export const search = {
  all: (query: string, types?: string[], limit?: number) =>
    request<SearchResponse>('/search', { method: 'POST', body: JSON.stringify({ query, types, limit }) }),
  web: (query: string) =>
    request<{ query: string; results: string }>('/search/web', { method: 'POST', body: JSON.stringify({ query }) }),
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

export interface ClientContext {
  client_id: string
  client_name: string
  project: string
  region: string
  estimates_count: number
  documents_count: number
  conversations_count: number
  preferences: Record<string, unknown>
  last_updated: string
}

export const context = {
  get: (clientId: string) => request<ClientContext>(`/context/${clientId}`),
  update: (clientId: string, data: Partial<ClientContext>) =>
    request(`/context/${clientId}`, { method: 'POST', body: JSON.stringify(data) }),
  addEstimate: (clientId: string, data: Record<string, unknown>) =>
    request(`/context/${clientId}/estimate`, { method: 'POST', body: JSON.stringify(data) }),
  addDocument: (clientId: string, data: Record<string, unknown>) =>
    request(`/context/${clientId}/document`, { method: 'POST', body: JSON.stringify(data) }),
  addMessage: (clientId: string, data: Record<string, unknown>) =>
    request(`/context/${clientId}/message`, { method: 'POST', body: JSON.stringify(data) }),
  getAIContext: (clientId: string) =>
    request<{ context: string }>(`/context/${clientId}/ai-context`),
}
