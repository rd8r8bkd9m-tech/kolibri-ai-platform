const DEFAULT_API_BASE = '/api/v1'
const CANARY_PATH_PREFIX = '/__canary/'
const CANARY_RELEASE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/

function hasUnsafeCanaryPathSegment(pathname: string): boolean {
  if (pathname.includes('//')) return true

  for (const segment of pathname.split('/')) {
    if (!segment) continue

    try {
      const decodedSegment = decodeURIComponent(segment)
      if (decodedSegment === '.' || decodedSegment === '..') return true
      if (decodedSegment.includes('/') || decodedSegment.includes('\\')) return true
    } catch {
      return true
    }
  }

  return false
}

export function resolveApiBase(pathname?: string | null): string {
  if (typeof pathname !== 'string') return DEFAULT_API_BASE
  if (!pathname.startsWith(CANARY_PATH_PREFIX)) return DEFAULT_API_BASE
  if (hasUnsafeCanaryPathSegment(pathname)) return DEFAULT_API_BASE

  const rest = pathname.slice(CANARY_PATH_PREFIX.length)
  const releaseIdEnd = rest.indexOf('/')
  if (releaseIdEnd <= 0) return DEFAULT_API_BASE

  const releaseId = rest.slice(0, releaseIdEnd)
  if (!CANARY_RELEASE_ID_PATTERN.test(releaseId)) return DEFAULT_API_BASE

  return `/__canary/${releaseId}${DEFAULT_API_BASE}`
}

const BASE = resolveApiBase(typeof window === 'undefined' ? undefined : window.location.pathname)

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

function errorDetail(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object') return fallback
  const payload = body as Record<string, unknown>
  if (typeof payload.message === 'string') return payload.message
  if (typeof payload.detail === 'string') return payload.detail
  if (payload.detail && typeof payload.detail === 'object') {
    const detail = payload.detail as Record<string, unknown>
    if (typeof detail.message === 'string') return detail.message
    if (typeof detail.code === 'string') return detail.code
  }
  return fallback
}

let authToken: string | null = null

try {
  if (typeof localStorage !== 'undefined') localStorage.removeItem('kolibri_token')
} catch {
  // Legacy bearer cleanup is best effort; browser auth now uses HttpOnly cookie.
}

export function setAuthToken(token: string | null) {
  authToken = token
}

export function getAuthToken() { return authToken }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...init?.headers as Record<string, string> }
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`
  const res = await fetch(`${BASE}${path}`, { ...init, headers, credentials: 'include' })
  if (!res.ok) {
    let detail = `API ${res.status}`
    try {
      detail = errorDetail(await res.json(), detail)
    } catch { /* ignore parse error */ }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type EstimateTruthStatus = 'needs_input' | 'preliminary' | 'source_backed' | 'verified'

export interface PriceSourceEvidence {
  position_code?: string
  source_id?: string
  url?: string
  source_title?: string
  source_type?: string
  region?: string
  observed_at?: string
  price_date?: string
  unit?: string
  unit_price?: string
  vat_status?: string
  quote?: string
  currency?: string
  content_sha256?: string
  verification?: string
  attestation?: string
}

export interface Position {
  id: string
  code: string
  name: string
  unit: string
  quantity: string
  price: string
  sum: string
  source: string
  source_evidence?: PriceSourceEvidence | null
  price_evidence?: PriceSourceEvidence[]
  comment: string
}

export interface EstimateEvidenceIssue {
  code: string
  position_code?: string
  message: string
}

export interface EstimateTotals {
  subtotal: string
  overhead_amount: string
  vat_amount: string
  total: string
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
  estimate_status?: EstimateTruthStatus
  pricing_status?: EstimateTruthStatus
  scope_status?: 'unverified' | 'verified'
  price_sources?: PriceSourceEvidence[]
  evidence_issues?: EstimateEvidenceIssue[]
  price_as_of?: string | null
  assumptions?: string[]
  questions?: string[]
  source_note?: string
  created_at: string
  updated_at: string
}

export interface EstimateListResponse {
  items: Estimate[]
  total: number
  page: number
  page_size: number
}

export interface EstimateRevisionSummary {
  id: string
  estimate_id: string
  version: number
  title: string
  status: Estimate['status']
  total: string
  created_at: string
}

export interface EstimateRevisionListResponse {
  items: EstimateRevisionSummary[]
  total: number
}

export interface EstimateRevisionResponse {
  id: string
  estimate_id: string
  version: number
  snapshot: Estimate
  created_at: string
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

export interface ImageArtifact {
  id: string
  type: 'image'
  revision: number
  title: string
  prompt: string
  mime_type: 'image/png' | 'image/jpeg' | 'image/webp'
  size_bytes: number
  sha256: string
  model: string
  created_at: string
  updated_at: string
  url: string
  download_url: string
  revision_url: string
  revision_download_url: string
  reopen_url: string
  history_url: string
  source_artifact_id?: string
}

export interface FileArtifact {
  id: string
  type: 'document.pdf' | 'document.docx' | 'document.xlsx' | 'document.pptx' | 'site.bundle' | 'app.bundle'
  revision: number
  title: string
  filename: string
  mime_type: string
  size_bytes: number
  sha256: string
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
  url: string
  download_url: string
  revision_url: string
  revision_download_url: string
  reopen_url: string
  history_url: string
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

export interface ShellBootstrap {
  session_id: string
  session_type: 'anonymous' | 'authenticated'
  restored: boolean
  expires_at: string | null
}

export interface Project {
  id: string
  title: string
  title_source: 'default' | 'message' | 'manual'
  status: 'active' | 'deleted'
  version: number
  message_count: number
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
  last_message_at: string | null
  deleted_at: string | null
}

export interface ProjectListResponse {
  items: Project[]
  total: number
  page: number
  page_size: number
}

export type ProjectMessageRole = 'user' | 'assistant' | 'system' | 'tool'
export type ProjectMessageStatus = 'pending' | 'streaming' | 'completed' | 'failed' | 'cancelled'

export interface ProjectMessage {
  id: string
  project_id: string
  sequence: number
  version: number
  role: ProjectMessageRole
  content: string
  status: ProjectMessageStatus
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ProjectMessageListResponse {
  items: ProjectMessage[]
  total: number
  after: number
  limit: number
}

export type FactoryAvailability = 'live' | 'partial' | 'stale' | 'unavailable'

export interface FactoryConnectionTruth {
  status: 'online' | 'offline' | 'unknown'
  connected: boolean
  reported_health: unknown
  source: 'node_health_report'
}

export interface FactoryFreshnessTruth {
  status: 'fresh' | 'degraded' | 'stale' | 'unknown'
  fresh: boolean
  heartbeat_at: string | null
  heartbeat_age_seconds: number | null
}

export interface FactoryCapabilityExecution {
  name: string
  runner: string | null
  runner_status: string | null
  executable: boolean
  reasons: string[]
}

export interface FactoryExecutionTruth {
  status: 'active' | 'ready' | 'blocked' | 'quarantined' | 'unavailable'
  active: boolean
  reported_active: boolean
  active_task_id: string | null
  executable: boolean
  executable_capabilities: string[]
  blocked: boolean
  blocked_reasons: string[]
  quarantined: boolean
  quarantine_reason: string | null
  schedulable: boolean
}

export interface FactoryTaskEvidence {
  task_id: string
  capability: string | null
  attempt_id: string | null
  completed_at: string | null
  result_sha256: string
  binding_sha256: string
  verifier: string
  verifier_schema: string | null
  evidence_source: string
}

export interface FactoryVerificationTruth {
  status: 'verified' | 'unverified' | 'unavailable'
  verified: boolean
  last_successful_task: FactoryTaskEvidence | null
  source: string
  as_of: string | null
  reason: string | null
}

export interface FactoryCapabilities {
  items?: string[]
  runners?: Record<string, unknown>
  execution?: FactoryCapabilityExecution[]
  executable_items?: string[]
  [key: string]: unknown
}

export interface FactoryListTruth {
  availability: FactoryAvailability
  source: string
  as_of: string
  membership?: Record<string, unknown>
  freshness?: Record<string, unknown>
  verification?: Record<string, unknown>
  derivation?: string
}

export interface Agent {
  id: string
  name: string
  role: string
  status: string
  node_id: string | null
  current_task: string | null
  progress: number | null
  model: string | null
  connection: FactoryConnectionTruth
  freshness: FactoryFreshnessTruth
  execution: FactoryExecutionTruth
  verification: FactoryVerificationTruth
  capabilities: FactoryCapabilities
  cost_accumulated: string
  heartbeat_at: string | null
}

export interface Node {
  id: string
  name: string
  region: string
  ip_address: string
  status: string
  connection: FactoryConnectionTruth
  freshness: FactoryFreshnessTruth
  execution: FactoryExecutionTruth
  verification: FactoryVerificationTruth
  cpu_percent: string
  ram_percent: string
  disk_percent: string
  network_mbps: string
  agent_count: number
  task_count: number
  ping_ms: number
  max_agents: number
  capabilities: FactoryCapabilities
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
  result?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface TaskDetail extends Task {
  kind: string
  objective: string
  runner: string | null
  required_capability: string | null
  attempt_id: string | null
  fencing_token: number | null
  result_reference: string | null
  verification: {
    verdict: string | null
    failed_checks: string[]
    result_sha256: string | null
    binding_sha256: string | null
  }
}

export interface PaginatedList<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  truth?: FactoryListTruth
}

export interface EstimateCreateInput {
  title: string
  client?: string
  object_name?: string
  region?: string
  currency?: string
  overhead_rate?: string
  vat_rate?: string
  estimate_status?: EstimateTruthStatus
  pricing_status?: EstimateTruthStatus
  scope_status?: 'unverified' | 'verified'
  price_sources?: PriceSourceEvidence[]
  evidence_issues?: EstimateEvidenceIssue[]
  totals?: EstimateTotals
  price_as_of?: string | null
  assumptions?: string[]
  questions?: string[]
  source_note?: string
  sections?: { title: string; positions?: { code: string; name: string; unit: string; quantity: string; price: string; sum?: string; source?: string; source_evidence?: PriceSourceEvidence | null; price_evidence?: PriceSourceEvidence[]; comment?: string }[] }[]
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
  update: (id: string, data: Partial<EstimateCreateInput & { status: string; sections: EstimateCreateInput['sections'] }> & { version: number }) =>
    request<Estimate>(`/estimates/${id}`, {
      method: 'PUT',
      headers: { 'If-Match': `"${data.version}"` },
      body: JSON.stringify(data),
    }),
  delete: (id: string) => request<void>(`/estimates/${id}`, { method: 'DELETE' }),
  calculate: (id: string, version: number) => request<Estimate>(`/estimates/${id}/calculate`, {
    method: 'POST',
    headers: { 'If-Match': `"${version}"` },
  }),
  duplicate: (id: string) => request<Estimate>(`/estimates/${id}/duplicate`, { method: 'POST' }),
  revisions: (id: string) => request<EstimateRevisionListResponse>(`/estimates/${id}/revisions`),
  revision: (id: string, version: number) => request<EstimateRevisionResponse>(`/estimates/${id}/revisions/${version}`),
  pdfUrl: (id: string, version?: number) => `${BASE}/estimates/${id}/pdf${version ? `?version=${version}` : ''}`,
  exportUrl: (id: string, fmt: 'csv' | 'json' | 'xlsx', version?: number) =>
    `${BASE}/estimates/${id}/export/${fmt}${version ? `?version=${version}` : ''}`,
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
// Shell bootstrap and durable project history
// ---------------------------------------------------------------------------

let shellBootstrapPromise: Promise<ShellBootstrap> | null = null

export function resetShellBootstrapForTests() {
  shellBootstrapPromise = null
}

export function ensureShellBootstrap(force = false): Promise<ShellBootstrap> {
  if (force) shellBootstrapPromise = null
  if (!shellBootstrapPromise) {
    shellBootstrapPromise = request<ShellBootstrap>('/shell/bootstrap', { method: 'POST' })
      .catch(error => {
        shellBootstrapPromise = null
        throw error
      })
  }
  return shellBootstrapPromise
}

async function projectRequest<T>(path: string, init?: RequestInit): Promise<T> {
  await ensureShellBootstrap()
  try {
    return await request<T>(path, init)
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 428) throw error
    await ensureShellBootstrap(true)
    return request<T>(path, init)
  }
}

export const shell = {
  bootstrap: ensureShellBootstrap,
}

export const projects = {
  list: (params?: { page?: number; page_size?: number; include_deleted?: boolean }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.page_size) qs.set('page_size', String(params.page_size))
    if (params?.include_deleted) qs.set('include_deleted', 'true')
    return projectRequest<ProjectListResponse>(`/projects?${qs}`)
  },
  get: (id: string) => projectRequest<Project>(`/projects/${encodeURIComponent(id)}`),
  claim: (id: string, token: string) => projectRequest<Project>(
    `/projects/${encodeURIComponent(id)}/claim`,
    { method: 'POST', body: JSON.stringify({ token }) },
  ),
  create: (data: { title?: string; metadata?: Record<string, unknown>; client_request_id?: string } = {}, idempotencyKey?: string) =>
    projectRequest<Project>('/projects', {
      method: 'POST',
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
      body: JSON.stringify(data),
    }),
  update: (id: string, data: { title?: string; metadata?: Record<string, unknown> }) =>
    projectRequest<Project>(`/projects/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id: string) =>
    projectRequest<Project>(`/projects/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  restore: (id: string) =>
    projectRequest<Project>(`/projects/${encodeURIComponent(id)}/restore`, { method: 'POST' }),
  listMessages: (id: string, params?: { after?: number; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.after !== undefined) qs.set('after', String(params.after))
    if (params?.limit) qs.set('limit', String(params.limit))
    return projectRequest<ProjectMessageListResponse>(`/projects/${encodeURIComponent(id)}/messages?${qs}`)
  },
  appendMessage: (
    projectId: string,
    data: { role: ProjectMessageRole; content: string; status?: ProjectMessageStatus; metadata?: Record<string, unknown>; client_message_id?: string },
    idempotencyKey?: string,
  ) => projectRequest<ProjectMessage>(`/projects/${encodeURIComponent(projectId)}/messages`, {
    method: 'POST',
    headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
    body: JSON.stringify(data),
  }),
  updateMessage: (
    projectId: string,
    messageId: string,
    data: { content?: string; status?: ProjectMessageStatus; metadata?: Record<string, unknown> },
    idempotencyKey?: string,
  ) => projectRequest<ProjectMessage>(
    `/projects/${encodeURIComponent(projectId)}/messages/${encodeURIComponent(messageId)}`,
    {
      method: 'PATCH',
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
      body: JSON.stringify(data),
    },
  ),
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
  create: (objective: string, idempotencyKey: string) =>
    request<Task>('/tasks', {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify({ objective }),
    }),
  get: (id: string) => request<TaskDetail>(`/tasks/${encodeURIComponent(id)}`),
  events: (id: string, params?: { after_sequence?: number; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.after_sequence) qs.set('after_sequence', String(params.after_sequence))
    if (params?.limit) qs.set('limit', String(params.limit))
    return request<FactoryTaskEventPage & { next_sequence: number }>(`/tasks/${encodeURIComponent(id)}/events?${qs}`)
  },
  cancel: (id: string, reason = 'cancelled_by_portal_owner') =>
    request<Task>(`/tasks/${encodeURIComponent(id)}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  update: (id: string, data: Partial<Task>) =>
    request<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
}

// ---------------------------------------------------------------------------
// Cluster
// ---------------------------------------------------------------------------

export interface ClusterStats {
  nodes: {
    membership_total: number
    connected: number
    fresh: number
    capability_executable: number
    active: number
    verified: number
    blocked: number
    quarantined: number
    stale: number
  }
  agents: { membership_total: number; active: number; idle: number; paused: number; executable: number; verified: number }
  tasks: { total: number; running: number; queued: number; completed: number; failed: number; cancelled: number }
  resources: { avg_cpu: number | null; avg_ram: number | null; avg_disk: number | null }
  truth: { availability: FactoryAvailability; source: string; as_of: string; task_pages: number; verification?: Record<string, unknown> }
}

export const cluster = {
  stats: () => request<ClusterStats>('/cluster/stats'),
}

// ---------------------------------------------------------------------------
// Unified Factory Control Center
// ---------------------------------------------------------------------------

export interface FactoryModelRoute {
  id: string
  public_name: string
  provider?: string | null
  status: string
  capabilities: string[]
  route?: string | null
  reason?: string | null
  evidence?: Record<string, unknown>
}

export interface FactoryModelsResponse {
  public_model: string
  routes: FactoryModelRoute[]
  routing_status: string
  as_of: string
  source: string
}

export interface FormulaGate {
  id: string
  label: string
  status: 'passed' | 'failed' | 'pending' | 'unavailable'
  evidence_sha256?: string | null
  reason?: string | null
}

export interface LocalModelCandidate {
  id: string
  node_id: string
  status: string
  runtime: string
  gates: FormulaGate[]
}

export interface LocalModelsResponse {
  items: LocalModelCandidate[]
  admitted_total: number
  candidate_total: number
  as_of: string
  generation_id?: string
  index_sha256?: string
  source: string
}

export interface FormulaCandidate {
  id: string
  status: 'candidate_only' | 'quarantined'
  eligible_for_signed_release: boolean
  legacy_distill_quarantined: boolean
  gates: FormulaGate[]
  rejection_reasons: string[]
}

export interface FormulaLearningStatus {
  status: string
  mode: string
  candidate_only: boolean
  active_model: string | null
  candidate_model: string | null
  gates: FormulaGate[]
  candidates: FormulaCandidate[]
  as_of: string
  generation_id?: string
  index_sha256?: string
  source: string
}

export interface FactoryTaskSummary {
  total: number
  queued: number
  running: number
  waiting_review: number
  completed: number
  failed: number
  cancelled: number
  dead_letter: number
  as_of: string
}

export interface FactoryTaskEvent {
  event_id: string
  task_id: string
  event_type: string
  state: string | null
  actor: string | null
  node_id: string | null
  attempt_id: string | null
  occurred_at: string
  sequence: number
  payload_sha256: string
  data?: Record<string, unknown>
}

export interface FactoryTaskEventPage {
  items: FactoryTaskEvent[]
  total: number
  next_cursor: string | null
  as_of: string
  source: string
}

export const factoryControl = {
  models: () => request<FactoryModelsResponse>('/control/models'),
  localModels: () => request<LocalModelsResponse>('/control/local-models'),
  learning: () => request<FormulaLearningStatus>('/control/learning'),
  summary: () => request<FactoryTaskSummary>('/control/tasks/summary'),
  events: (params?: { task_id?: string; cursor?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.task_id) qs.set('task_id', params.task_id)
    if (params?.cursor) qs.set('after_cursor', params.cursor)
    if (params?.limit) qs.set('limit', String(params.limit))
    return request<FactoryTaskEventPage>(`/control/events?${qs}`)
  },
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
  reasoning?: string
  actions: ChatAction[]
  status: string
  error_code?: string
  recoverable?: boolean
  capability?: string
}

export type ChatWorkStage =
  | 'accepted'
  | 'planning'
  | 'reasoning_summary'
  | 'provider_route'
  | 'provider_attempt'
  | 'response_received'
  | 'tool_execution'
  | 'source_retrieval'
  | 'calculation'
  | 'artifact_materialization'
  | 'artifact_verification'
  | 'background'
  | 'resuming'
  | 'verification'
  | 'cancelled'

export interface ChatWorkSummary {
  kind?: 'stage' | 'reasoning_excerpt'
  step_id?: string
  summary_id?: string
  stage: ChatWorkStage
  summary: string
  status: 'active' | 'completed' | 'failed'
  occurred_at?: string
  response_id?: string
  sequence?: number
  provider?: string
  model?: string
  artifact_type?: string
  artifact_id?: string
}

export type SafeResponseEventType =
  | 'response.created'
  | 'response.status.updated'
  | 'response.output_text.delta'
  | 'response.tool.started'
  | 'response.tool.completed'
  | 'response.work_summary.updated'
  | 'response.source.added'
  | 'response.artifact.ready'
  | 'response.completed'
  | 'response.failed'
  | 'response.cancelled'
  | 'provider.attempt.failed'

const SAFE_RESPONSE_EVENT_TYPES = new Set<SafeResponseEventType>([
  'response.created',
  'response.status.updated',
  'response.output_text.delta',
  'response.tool.started',
  'response.tool.completed',
  'response.work_summary.updated',
  'response.source.added',
  'response.artifact.ready',
  'response.completed',
  'response.failed',
  'response.cancelled',
  'provider.attempt.failed',
])

const NONTERMINAL_RESPONSE_STATUSES = new Set([
  'queued',
  'planning',
  'in_progress',
  'running',
  'waiting_for_input',
  'approval_required',
  'verifying',
])

export interface ProviderAttemptFailedEvent {
  type: 'provider.attempt.failed'
  provider: string
  model?: string
  failure_kind: string
  will_retry: boolean
}

export interface ChatStreamEvent {
  type?: SafeResponseEventType
  response_id?: string
  sequence?: number
  content?: string
  done?: boolean
  status?: string
  error_code?: string
  recoverable?: boolean
  capability?: string
  actions?: ChatAction[]
  provider?: string
  model?: string
  fallback_used?: boolean
  work_summary?: ChatWorkSummary
  provider_event?: ProviderAttemptFailedEvent
}

export type ChatExecutionMode = 'fast' | 'deep'

export interface ChatExecutionPolicy {
  mode: ChatExecutionMode
  reasoning_effort: 'low' | 'high'
  tool_choice: 'auto'
  background: boolean
  allowed_capabilities: string[]
}

export interface ChatAttachmentRef {
  id: string
  name: string
  mime_type: string
  size_bytes: number
}

export interface ChatRequestOptions {
  policy?: ChatExecutionPolicy
  project_id?: string
  previous_response_id?: string
  attachments?: ChatAttachmentRef[]
  idempotencyKey?: string
}

export interface ServerSentEvent {
  event?: string
  id?: string
  data: string
}

function parseSseFrame(frame: string): ServerSentEvent | null {
  const normalized = frame.replace(/\r\n/g, '\n')
  const data: string[] = []
  let event: string | undefined
  let id: string | undefined
  for (const line of normalized.split('\n')) {
    if (!line || line.startsWith(':')) continue
    const separator = line.indexOf(':')
    const field = separator === -1 ? line : line.slice(0, separator)
    const value = separator === -1 ? '' : line.slice(separator + 1).replace(/^ /, '')
    if (field === 'data') data.push(value)
    else if (field === 'event') event = value
    else if (field === 'id') id = value
  }
  if (!data.length) return null
  return { event, id, data: data.join('\n') }
}

export async function readEventStream(
  response: Response,
  onEvent: (event: ServerSentEvent) => void,
): Promise<void> {
  if (!response.ok || !response.body) throw new ApiError(response.status, `Event stream ${response.status}`)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const parsed = parseSseFrame(frame)
      if (parsed) onEvent(parsed)
    }
    if (done) break
  }
  const trailing = parseSseFrame(buffer)
  if (trailing) onEvent(trailing)
}

const SAFE_WORK_STAGES = new Set<ChatWorkStage>([
  'accepted',
  'planning',
  'reasoning_summary',
  'provider_route',
  'provider_attempt',
  'response_received',
  'tool_execution',
  'source_retrieval',
  'calculation',
  'artifact_materialization',
  'artifact_verification',
  'background',
  'resuming',
  'verification',
  'cancelled',
])

const WORK_STAGE_ALIASES: Record<string, ChatWorkStage> = {
  answer: 'response_received',
  calculating: 'tool_execution',
  sourcing: 'source_retrieval',
  verifying: 'verification',
  retrying: 'resuming',
  factory_dispatch: 'provider_route',
  factory_verified: 'verification',
  codex_turn: 'tool_execution',
  plan_updated: 'planning',
}

const WORK_STATUS_ALIASES: Record<string, ChatWorkSummary['status']> = {
  queued: 'active',
  in_progress: 'active',
  running: 'active',
  success: 'completed',
  ready: 'completed',
  idle: 'completed',
  error: 'failed',
  unavailable: 'failed',
  retrying: 'active',
  waiting: 'active',
  recovering: 'active',
}

function safeWorkStage(value: unknown): ChatWorkStage | undefined {
  const normalized = safeString(value, 80)?.toLowerCase()
  if (!normalized) return undefined
  const stage = WORK_STAGE_ALIASES[normalized] ?? normalized
  return SAFE_WORK_STAGES.has(stage as ChatWorkStage) ? stage as ChatWorkStage : undefined
}

function safeWorkStatus(value: unknown, stage?: ChatWorkStage): ChatWorkSummary['status'] {
  if (value === 'completed' || value === 'failed') return value
  if (value === 'cancelled') return stage === 'cancelled' ? 'completed' : 'failed'
  if (typeof value !== 'string') return 'active'
  return WORK_STATUS_ALIASES[value.trim().toLowerCase()] ?? 'active'
}

function safeString(value: unknown, maxLength = 240): string | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.trim()
  return normalized ? normalized.slice(0, maxLength) : undefined
}

function normalizeWorkSummaryPayload(value: unknown): ChatWorkSummary | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined
  const payload = value as Record<string, unknown>
  const stage = safeWorkStage(payload.stage)
  const summary = safeString(payload.summary)
  if (!stage || !summary) return undefined
  const kind = payload.kind === 'reasoning_excerpt' ? 'reasoning_excerpt' : 'stage'
  return {
    kind,
    step_id: safeString(payload.step_id, 160),
    summary_id: safeString(payload.summary_id, 160),
    stage,
    summary,
    status: safeWorkStatus(payload.status, stage),
    occurred_at: safeString(payload.occurred_at, 48),
    response_id: safeString(payload.response_id, 160),
    sequence: typeof payload.sequence === 'number' && Number.isSafeInteger(payload.sequence) && payload.sequence >= 0
      ? payload.sequence
      : undefined,
    artifact_type: safeString(payload.artifact_type, 80),
    artifact_id: safeString(payload.artifact_id, 160),
  }
}

function normalizeProviderFailurePayload(value: unknown): ProviderAttemptFailedEvent | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined
  const payload = value as Record<string, unknown>
  if (payload.type !== 'provider.attempt.failed') return undefined
  return {
    type: 'provider.attempt.failed',
    provider: safeString(payload.provider, 80) ?? 'unknown',
    model: safeString(payload.model, 120),
    failure_kind: safeString(payload.failure_kind, 80) ?? 'provider_error',
    will_retry: payload.will_retry === true,
  }
}

function workSummaryFromResponseEvent(type: SafeResponseEventType, payload: Record<string, unknown>): ChatWorkSummary | undefined {
  if (type === 'response.work_summary.updated' && payload.work_summary && typeof payload.work_summary === 'object') {
    const summary = normalizeWorkSummaryPayload(payload.work_summary)
    if (!summary) return undefined
    return {
      ...summary,
      response_id: safeString(payload.response_id, 160) ?? summary.response_id,
      sequence: typeof payload.sequence === 'number' && Number.isSafeInteger(payload.sequence) && payload.sequence >= 0
        ? payload.sequence
        : summary.sequence,
    }
  }
  const name = typeof payload.name === 'string' ? payload.name : undefined
  const title = typeof payload.title === 'string' ? payload.title : undefined
  if (type === 'response.tool.started' || type === 'response.tool.completed') {
    return {
      stage: 'tool_execution',
      status: type.endsWith('completed') ? 'completed' : 'active',
      summary: `${type.endsWith('completed') ? 'Инструмент завершён' : 'Запущен инструмент'}${name ? `: ${name}` : ''}`,
    }
  }
  if (type === 'response.source.added') {
    return { stage: 'source_retrieval', status: 'completed', summary: `Добавлен источник${title ? `: ${title}` : ''}` }
  }
  if (type === 'response.artifact.ready') {
    return {
      stage: 'artifact_verification',
      status: 'completed',
      summary: `Артефакт готов${title ? `: ${title}` : ''}`,
      artifact_type: typeof payload.artifact_type === 'string' ? payload.artifact_type : undefined,
      artifact_id: typeof payload.artifact_id === 'string' ? payload.artifact_id : undefined,
    }
  }
  if (type === 'response.status.updated') {
    const status = typeof payload.status === 'string' ? payload.status : 'running'
    return {
      stage: status === 'queued' ? 'background' : status === 'verifying' ? 'verification' : 'planning',
      status: safeWorkStatus(status),
      summary: typeof payload.summary === 'string' ? payload.summary : `Статус задачи: ${status}`,
    }
  }
  if (type === 'response.cancelled') return { stage: 'cancelled', status: 'completed', summary: 'Задача отменена' }
  return undefined
}

function actionsFromResponseEvent(
  type: SafeResponseEventType,
  payload: Record<string, unknown>,
  response?: Record<string, unknown>,
): ChatAction[] | undefined {
  const actions = Array.isArray(payload.actions)
    ? payload.actions
    : Array.isArray(response?.actions) ? response.actions : undefined
  if (actions) return actions.filter((value): value is ChatAction => Boolean(value && typeof value === 'object'))

  if (type !== 'response.artifact.ready') return undefined
  const artifact = payload.artifact && typeof payload.artifact === 'object' && !Array.isArray(payload.artifact)
    ? payload.artifact as Record<string, unknown>
    : payload.data && typeof payload.data === 'object' && !Array.isArray(payload.data)
      ? payload.data as Record<string, unknown>
      : undefined
  if (!artifact) return undefined
  return payload.artifact_type === 'image'
    ? [{ type: 'present_image', label: 'Открыть изображение', data: artifact }]
    : [{ type: 'present_artifact', label: 'Открыть артефакт', data: artifact }]
}

export function normalizeStreamEvent(envelope: ServerSentEvent): ChatStreamEvent | null {
  if (!envelope.data || envelope.data === '[DONE]') return null
  let payload: Record<string, unknown>
  try {
    const parsed = JSON.parse(envelope.data) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    payload = parsed as Record<string, unknown>
  } catch {
    return null
  }

  const rawType = typeof payload.type === 'string' ? payload.type : envelope.event
  if (rawType && !SAFE_RESPONSE_EVENT_TYPES.has(rawType as SafeResponseEventType)) return null
  const type = rawType as SafeResponseEventType | undefined
  if (!type) {
    const status = safeString(payload.status, 40)
    return {
      content: typeof payload.content === 'string' ? payload.content : undefined,
      done: payload.done === true && !NONTERMINAL_RESPONSE_STATUSES.has(status ?? ''),
      status,
      error_code: safeString(payload.error_code, 120),
      recoverable: payload.recoverable === true,
      capability: safeString(payload.capability, 120),
      actions: Array.isArray(payload.actions) ? payload.actions as ChatAction[] : undefined,
      provider: safeString(payload.provider, 80),
      model: safeString(payload.model, 120),
      fallback_used: payload.fallback_used === true,
      work_summary: normalizeWorkSummaryPayload(payload.work_summary),
      provider_event: normalizeProviderFailurePayload(payload.provider_event),
      response_id: safeString(payload.response_id, 160),
      sequence: typeof payload.sequence === 'number' ? payload.sequence : undefined,
    }
  }
  const response = payload.response && typeof payload.response === 'object'
    ? payload.response as Record<string, unknown>
    : undefined
  const responseError = response?.error && typeof response.error === 'object'
    ? response.error as Record<string, unknown>
    : undefined
  const responseId = typeof payload.response_id === 'string'
    ? payload.response_id
    : typeof response?.id === 'string' ? response.id : undefined
  const sequence = typeof payload.sequence === 'number' ? payload.sequence : undefined

  if (type === 'provider.attempt.failed') {
    return {
      type,
      response_id: responseId,
      sequence,
      provider_event: normalizeProviderFailurePayload(payload),
    }
  }

  const workSummary = workSummaryFromResponseEvent(type, payload)
  const actions = actionsFromResponseEvent(type, payload, response)
  const delta = type === 'response.output_text.delta' && typeof payload.delta === 'string' ? payload.delta : undefined
  const terminal = type === 'response.completed' || type === 'response.failed' || type === 'response.cancelled'
  const responseStatus = safeString(payload.status, 40) ?? safeString(response?.status, 40)
  return {
    type,
    response_id: responseId,
    sequence,
    content: delta,
    done: terminal,
    status: type === 'response.failed'
      ? 'failed'
      : type === 'response.cancelled'
        ? 'cancelled'
        : terminal
          ? 'completed'
          : type === 'response.status.updated' ? responseStatus : undefined,
    error_code: safeString(payload.error_code, 120) ?? safeString(responseError?.code, 120),
    recoverable: payload.recoverable === true || responseError?.recoverable === true,
    capability: safeString(payload.capability, 120) ?? safeString(responseError?.capability, 120),
    actions,
    work_summary: workSummary,
  }
}

interface LegacyChatResponse {
  response?: string
  content?: string
  reasoning?: string
  actions?: ChatAction[]
  status?: string
  error_code?: string
  recoverable?: boolean
  capability?: string
}

function normalizeChatResponse(payload: LegacyChatResponse): ChatResponse {
  const content = payload.content ?? payload.response ?? ''
  const failed = ['error', 'failed', 'incomplete', 'unavailable', 'capability_unavailable'].includes(payload.status ?? '')
  const actions = Array.isArray(payload.actions) ? payload.actions : []
  if (!content.trim() && !actions.length && !failed && !payload.error_code) {
    throw new ApiError(502, 'Kolibri API returned an empty response')
  }

  return {
    content,
    reasoning: payload.reasoning,
    actions,
    status: payload.status ?? 'completed',
    error_code: payload.error_code,
    recoverable: payload.recoverable === true,
    capability: payload.capability,
  }
}

export const chat = {
  send: async (messages: { role: string; content: string }[], options: ChatRequestOptions = {}) => {
    const payload = await request<LegacyChatResponse>('/chat', {
      method: 'POST',
      headers: options.idempotencyKey ? { 'Idempotency-Key': options.idempotencyKey } : undefined,
      body: JSON.stringify({ messages, ...options, idempotencyKey: undefined }),
    })
    return normalizeChatResponse(payload)
  },
  stream: async (
    messages: { role: string; content: string }[],
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
    options: ChatRequestOptions = {},
  ) => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (authToken) headers.Authorization = `Bearer ${authToken}`
    if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey
    const response = await fetch(`${BASE}/chat/stream`, {
      method: 'POST',
      headers,
      credentials: 'include',
      body: JSON.stringify({ messages, ...options, idempotencyKey: undefined }),
      signal,
    })
    let finalEvent: ChatStreamEvent = { done: false }
    let durableResponseId: string | undefined
    let lastSequence = 0
    let receivedDurableHandoff = false
    let legacyContentAwaitingCanonical: string | undefined
    let canonicalContentAwaitingLegacy: string | undefined
    await readEventStream(response, envelope => {
      const normalized = normalizeStreamEvent(envelope)
      if (normalized) {
        let event = normalized
        if (
          !event.type
          && event.content
          && event.content === canonicalContentAwaitingLegacy
        ) {
          event = { ...event, content: undefined }
          canonicalContentAwaitingLegacy = undefined
        } else if (!event.type && event.content) {
          legacyContentAwaitingCanonical = event.content
        } else if (
          event.type === 'response.output_text.delta'
          && event.content
          && event.content === legacyContentAwaitingCanonical
        ) {
          // The browser chat endpoint emits both its legacy text chunk and the
          // canonical sequenced delta during migration. Keep the canonical
          // cursor/evidence while delivering the user-visible text only once.
          event = { ...event, content: undefined }
          legacyContentAwaitingCanonical = undefined
        } else if (event.type === 'response.output_text.delta' && event.content) {
          canonicalContentAwaitingLegacy = event.content
        }
        finalEvent = event
        durableResponseId = event.response_id ?? durableResponseId
        if (Number.isSafeInteger(event.sequence) && (event.sequence as number) > lastSequence) {
          lastSequence = event.sequence as number
        }
        if (
          event.type === 'response.status.updated'
          && NONTERMINAL_RESPONSE_STATUSES.has(event.status ?? '')
        ) {
          receivedDurableHandoff = true
        }
        onEvent(event)
      }
    })

    if (finalEvent.done !== true && durableResponseId) {
      if (!receivedDurableHandoff) {
        throw new ApiError(502, 'Chat stream ended before a durable background handoff')
      }
      return resumeResponseAfterDisconnect(durableResponseId, onEvent, {
        signal,
        startingAfter: lastSequence,
      })
    }
    return finalEvent
  },
}

// ---------------------------------------------------------------------------
// Durable OpenAI-compatible responses
// ---------------------------------------------------------------------------

export type DurableResponseStatus =
  | 'queued'
  | 'planning'
  | 'running'
  | 'waiting_for_input'
  | 'approval_required'
  | 'verifying'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface DurableResponse {
  id: string
  object: 'response'
  status: DurableResponseStatus
  created_at?: string | number
  updated_at?: string | number
  output_text?: string
  last_sequence?: number
  error?: { code?: string; message?: string } | null
}

export interface CreateResponseInput {
  input: string | { role: string; content: string }[]
  policy: ChatExecutionPolicy
  project_id?: string
  attachments?: ChatAttachmentRef[]
  idempotencyKey?: string
}

export const responses = {
  create: ({ idempotencyKey, ...data }: CreateResponseInput, signal?: AbortSignal) =>
    request<DurableResponse>('/responses', {
      method: 'POST',
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
      body: JSON.stringify({ model: 'kolibri', background: data.policy.background, ...data }),
      signal,
    }),
  get: (id: string, signal?: AbortSignal) =>
    request<DurableResponse>(`/responses/${encodeURIComponent(id)}`, { signal }),
  stream: async (
    id: string,
    onEvent: (event: ChatStreamEvent) => void,
    options: { startingAfter?: number; signal?: AbortSignal } = {},
  ) => {
    const qs = new URLSearchParams()
    if (options.startingAfter !== undefined) qs.set('starting_after', String(options.startingAfter))
    const headers: Record<string, string> = { Accept: 'text/event-stream' }
    if (authToken) headers.Authorization = `Bearer ${authToken}`
    const response = await fetch(`${BASE}/responses/${encodeURIComponent(id)}/events?${qs}`, {
      headers,
      credentials: 'include',
      signal: options.signal,
    })
    let finalEvent: ChatStreamEvent = { response_id: id, done: false }
    await readEventStream(response, envelope => {
      const event = normalizeStreamEvent(envelope)
      if (!event) return
      finalEvent = { ...event, response_id: event.response_id ?? id }
      onEvent(finalEvent)
    })
    return finalEvent
  },
  resume: (
    id: string,
    startingAfter: number,
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
  ) => responses.stream(id, onEvent, { startingAfter, signal }),
  cancel: (id: string) =>
    request<DurableResponse>(`/responses/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
}

export async function resumeResponseAfterDisconnect(
  id: string,
  onEvent: (event: ChatStreamEvent) => void,
  options: {
    signal?: AbortSignal
    maxAttempts?: number
    retryDelayMs?: number
    startingAfter?: number
  } = {},
): Promise<ChatStreamEvent> {
  const maxAttempts = Math.min(5, Math.max(1, Math.trunc(options.maxAttempts ?? 3)))
  const retryDelayMs = Math.max(0, Math.trunc(options.retryDelayMs ?? 180))
  let startingAfter = Number.isSafeInteger(options.startingAfter)
    ? Math.max(0, options.startingAfter as number)
    : 0
  let lastError: unknown = new Error('Response stream did not reach a terminal event')

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (options.signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError')
    try {
      const finalEvent = await responses.resume(id, startingAfter, event => {
        const sequence = event.sequence
        if (!Number.isSafeInteger(sequence) || (sequence as number) <= startingAfter) return
        startingAfter = sequence as number
        onEvent(event)
      }, options.signal)
      if (finalEvent.done === true) return finalEvent
      lastError = new Error('Response replay ended before a terminal event')
    } catch (error) {
      if (options.signal?.aborted) throw error
      lastError = error
    }

    if (attempt + 1 < maxAttempts && retryDelayMs > 0) {
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(resolve, retryDelayMs * (attempt + 1))
        options.signal?.addEventListener('abort', () => {
          window.clearTimeout(timeout)
          reject(new DOMException('The operation was aborted.', 'AbortError'))
        }, { once: true })
      })
    }
  }

  throw lastError
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

export const ai = {
  analyzeEstimate: (estId: string) =>
    request<AIResponse>(`/ai/analyze-estimate?est_id=${estId}`, { method: 'POST' }),
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
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  me: () => request<AuthUser>('/auth/me'),
  updateMe: (data: { name?: string; email?: string; current_password?: string; new_password?: string }) =>
    request<AuthUser>('/auth/me', { method: 'PUT', body: JSON.stringify(data) }),
}

// ---------------------------------------------------------------------------
// Organizations
// ---------------------------------------------------------------------------

export type OrganizationRole = 'owner' | 'admin' | 'member'
export type OrganizationMembershipStatus = 'active' | 'suspended'

export interface OrganizationSummary {
  id: string
  name: string
  slug: string
  status: 'active'
  role: OrganizationRole
  membership_status: 'active'
  selected: boolean
}

export interface OrganizationListResponse {
  items: OrganizationSummary[]
}

export interface OrganizationMembership {
  id: string
  organization_id: string
  user: {
    id: string
    email: string
    name: string
  }
  role: OrganizationRole
  status: OrganizationMembershipStatus
  created_at: string
  updated_at: string
}

export interface OrganizationMembershipListResponse {
  items: OrganizationMembership[]
}

export const organizations = {
  list: () => request<OrganizationListResponse>('/organizations', { cache: 'no-store' }),
  create: (data: { name: string; slug?: string }) =>
    request<OrganizationSummary>('/organizations', {
      method: 'POST',
      body: JSON.stringify(data),
      cache: 'no-store',
    }),
  select: (organizationId: string) =>
    request<OrganizationSummary>(`/organizations/${encodeURIComponent(organizationId)}/select`, {
      method: 'POST',
      cache: 'no-store',
    }),
  memberships: (organizationId: string) =>
    request<OrganizationMembershipListResponse>(
      `/organizations/${encodeURIComponent(organizationId)}/memberships`,
      { cache: 'no-store' },
    ),
  invite: (organizationId: string, data: { email: string; role: Exclude<OrganizationRole, 'owner'> }) =>
    request<OrganizationMembership>(
      `/organizations/${encodeURIComponent(organizationId)}/memberships`,
      { method: 'POST', body: JSON.stringify(data), cache: 'no-store' },
    ),
  changeRole: (organizationId: string, membershipId: string, role: OrganizationRole) =>
    request<OrganizationMembership>(
      `/organizations/${encodeURIComponent(organizationId)}/memberships/${encodeURIComponent(membershipId)}`,
      { method: 'PATCH', body: JSON.stringify({ role }), cache: 'no-store' },
    ),
  suspend: (organizationId: string, membershipId: string) =>
    request<OrganizationMembership>(
      `/organizations/${encodeURIComponent(organizationId)}/memberships/${encodeURIComponent(membershipId)}/suspend`,
      { method: 'POST', cache: 'no-store' },
    ),
}

// ---------------------------------------------------------------------------
// Developer API keys
// ---------------------------------------------------------------------------

export interface DeveloperApiKey {
  id: string
  object: 'api_key'
  name: string
  prefix: string
  created_at: number
  last_used_at: number | null
  revoked: boolean
  revoked_at: number | null
}

export interface DeveloperApiKeyListResponse {
  object: 'list'
  data: DeveloperApiKey[]
}

export interface DeveloperApiKeyCreated extends DeveloperApiKey {
  /** The plaintext secret is returned once and must never be persisted by the client. */
  secret: string
  secret_shown_once: true
}

export const developerApiKeys = {
  list: () => request<DeveloperApiKeyListResponse>('/developer/api-keys', {
    cache: 'no-store',
  }),
  create: (name: string) => request<DeveloperApiKeyCreated>('/developer/api-keys', {
    method: 'POST',
    body: JSON.stringify({ name }),
    cache: 'no-store',
  }),
  revoke: (id: string) => request<DeveloperApiKey>(`/developer/api-keys/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    cache: 'no-store',
  }),
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
