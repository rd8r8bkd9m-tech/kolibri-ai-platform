import type { ConversationArtifact } from '@/features/conversation/ArtifactCard'
import { normalizeImageArtifact } from '@/features/conversation/imageArtifact'
import { normalizeFileArtifact } from '@/features/conversation/fileArtifact'
import { calculateEstimateTotals, calculatePositionSum } from '@/features/estimates/estimateMath'
import type {
  ChatAction,
  ChatWorkSummary,
  Document,
  Estimate,
  EstimateCreateInput,
  EstimateEvidenceIssue,
  EstimateTruthStatus,
  FileArtifact,
  ImageArtifact,
  PriceSourceEvidence,
} from '@/lib/api'

type UnknownRecord = Record<string, unknown>

export type PersistedArtifactReference =
  | { type: 'estimate'; id: string; version: number; title: string }
  | { type: 'document'; id: string; title: string }
  | { type: 'image'; value: ImageArtifact }
  | { type: 'file'; value: FileArtifact }

export interface RestoredConversationMetadata {
  responseId?: string
  workEvents: ChatWorkSummary[]
  actions: ChatAction[]
  artifact?: PersistedArtifactReference
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const DECIMAL = /^-?\d+(?:\.\d+)?$/
const ACTION_TYPES = new Set(['create_estimate', 'create_document', 'present_image', 'present_artifact'])
const WORK_STATUSES = new Set(['active', 'completed', 'failed'])
const WORK_STAGES = new Set<ChatWorkSummary['stage']>([
  'accepted', 'planning', 'reasoning_summary', 'provider_route', 'provider_attempt',
  'response_received', 'tool_execution', 'source_retrieval', 'calculation',
  'artifact_materialization', 'artifact_verification', 'background', 'resuming',
  'verification', 'cancelled',
])

function record(value: unknown): UnknownRecord | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as UnknownRecord
    : null
}

function requiredString(value: unknown, maxLength: number): string | null {
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  return normalized && normalized.length <= maxLength ? normalized : null
}

function optionalString(value: unknown, maxLength: number, fallback = ''): string | null {
  if (value === undefined || value === null || value === '') return fallback
  return typeof value === 'string' && value.length <= maxLength ? value : null
}

function decimalString(value: unknown): string | null {
  const normalized = typeof value === 'number' && Number.isFinite(value) ? String(value) : value
  return typeof normalized === 'string' && normalized.length <= 64 && DECIMAL.test(normalized)
    ? normalized
    : null
}

function stringList(value: unknown, maxItems = 100, maxLength = 2_000): string[] | null {
  if (value === undefined) return []
  if (!Array.isArray(value) || value.length > maxItems) return null
  const items: string[] = []
  for (const entry of value) {
    const item = requiredString(entry, maxLength)
    if (!item) return null
    items.push(item)
  }
  return items
}

function normalizePriceEvidence(value: unknown): PriceSourceEvidence | null {
  const evidence = record(value)
  if (!evidence) return null
  const positionCode = requiredString(evidence.position_code, 80)
  const sourceId = requiredString(evidence.source_id, 160)
  const url = requiredString(evidence.url, 2_000)
  const title = requiredString(evidence.source_title, 500)
  const sourceType = requiredString(evidence.source_type, 80)
  const region = requiredString(evidence.region, 240)
  const observedAt = requiredString(evidence.observed_at, 64)
  const priceDate = requiredString(evidence.price_date, 10)
  const unit = requiredString(evidence.unit, 40)
  const unitPrice = decimalString(evidence.unit_price)
  const vatStatus = requiredString(evidence.vat_status, 120)
  const quote = requiredString(evidence.quote, 500)
  const currency = requiredString(evidence.currency, 8)
  const sha256 = requiredString(evidence.content_sha256, 64)
  const verification = requiredString(evidence.verification, 40)
  const attestation = requiredString(evidence.attestation, 64)
  if (!positionCode || !sourceId || !url || !title || !sourceType || !region || !observedAt || !priceDate || !unit || unitPrice === null || !vatStatus || !quote || !currency || !sha256 || !verification || !attestation) return null
  if (!['official_index', 'official_catalog', 'government_procurement', 'supplier_quote', 'supplier_catalog', 'marketplace', 'user_document'].includes(sourceType)) return null
  if (!['included', 'excluded', 'not_applicable', 'unknown'].includes(vatStatus)) return null
  if (!['source_backed', 'verified'].includes(verification)) return null
  if (verification === 'verified' && vatStatus === 'unknown') return null
  if (!/^[a-f0-9]{64}$/.test(sha256)) return null
  if (!/^[a-f0-9]{64}$/.test(attestation)) return null
  try {
    const parsed = new URL(url)
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.hash) return null
  } catch {
    return null
  }
  return {
    position_code: positionCode,
    source_id: sourceId,
    url,
    source_title: title,
    source_type: sourceType,
    region,
    observed_at: observedAt,
    price_date: priceDate,
    unit,
    unit_price: unitPrice,
    vat_status: vatStatus,
    quote,
    currency,
    content_sha256: sha256,
    verification,
    attestation,
  }
}

function normalizeEvidenceIssues(value: unknown): EstimateEvidenceIssue[] | null {
  if (value === undefined) return []
  if (!Array.isArray(value) || value.length > 200) return null
  const result: EstimateEvidenceIssue[] = []
  for (const raw of value) {
    const issue = record(raw)
    if (!issue) return null
    const code = requiredString(issue.code, 80)
    const positionCode = optionalString(issue.position_code, 80)
    const message = requiredString(issue.message, 500)
    if (!code || positionCode === null || !message) return null
    result.push({ code, position_code: positionCode || undefined, message })
  }
  return result
}

function normalizeEstimateDraft(value: unknown): EstimateCreateInput | null {
  const data = record(value)
  if (!data) return null
  const title = requiredString(data.title, 160)
  const client = optionalString(data.client, 240)
  const objectName = optionalString(data.object_name, 240)
  const region = optionalString(data.region, 240)
  const currency = optionalString(data.currency, 8, 'RUB')
  const overheadRate = data.overhead_rate === undefined ? '0' : decimalString(data.overhead_rate)
  const vatRate = data.vat_rate === undefined ? '0' : decimalString(data.vat_rate)
  const assumptions = stringList(data.assumptions)
  const questions = stringList(data.questions)
  const sourceNote = optionalString(data.source_note, 2_000)
  const evidenceIssues = normalizeEvidenceIssues(data.evidence_issues)
  if (!title || client === null || objectName === null || region === null || currency === null || overheadRate === null || vatRate === null) return null
  if (assumptions === null || questions === null || sourceNote === null || evidenceIssues === null) return null
  if (!Array.isArray(data.sections) || data.sections.length > 100) return null

  let positionsTotal = 0
  const sections: NonNullable<EstimateCreateInput['sections']> = []
  for (const sectionValue of data.sections) {
    const section = record(sectionValue)
    if (!section) return null
    const sectionTitle = requiredString(section.title, 240)
    if (!sectionTitle || !Array.isArray(section.positions) || section.positions.length > 500) return null
    positionsTotal += section.positions.length
    if (positionsTotal > 2_000) return null
    const positions: NonNullable<NonNullable<EstimateCreateInput['sections']>[number]['positions']> = []
    for (const positionValue of section.positions) {
      const position = record(positionValue)
      if (!position) return null
      const code = optionalString(position.code, 80)
      const name = requiredString(position.name, 320)
      const unit = requiredString(position.unit, 40)
      const quantity = decimalString(position.quantity)
      const price = decimalString(position.price)
      const comment = optionalString(position.comment, 1_000)
      if (code === null || !name || !unit || quantity === null || price === null || comment === null) return null
      if (Number(quantity) < 0 || Number(price) < 0) return null
      const rawEvidence = Array.isArray(position.price_evidence)
        ? position.price_evidence
        : position.source_evidence === undefined ? [] : [position.source_evidence]
      if (rawEvidence.length > 50) return null
      const priceEvidence = rawEvidence
        .map(normalizePriceEvidence)
        .filter((item): item is PriceSourceEvidence => item !== null)
        .filter(item => item.position_code === code)
      const source = priceEvidence.find(item => item.url)?.url || ''
      positions.push({
        code,
        name,
        unit,
        quantity,
        price,
        sum: calculatePositionSum({ quantity, price }),
        source,
        price_evidence: priceEvidence,
        comment,
      })
    }
    sections.push({ title: sectionTitle, positions })
  }

  const allPositions = sections.flatMap(section => section.positions ?? [])
  const positive = allPositions.filter(position => Number(position.quantity) > 0 && Number(position.price) > 0)
  const complete = positive.length > 0 && positive.length === allPositions.length
  // A create_estimate action is browser-visible message metadata, not an
  // authoritative persisted estimate. Preserve syntactically valid evidence
  // (including its opaque attestation) so the server can verify it during
  // materialization, but never promote truth from a value the browser cannot
  // authenticate. Only a hydrated persisted artifact may display a promoted
  // source-backed/verified status.
  const pricingStatus: EstimateTruthStatus = complete ? 'preliminary' : 'needs_input'
  const estimateStatus: EstimateTruthStatus = pricingStatus
  const priceSources = allPositions.flatMap(position => position.price_evidence ?? [])
  const totals = calculateEstimateTotals(sections, overheadRate, vatRate)

  return {
    title,
    client,
    object_name: objectName,
    region,
    currency,
    overhead_rate: overheadRate,
    vat_rate: vatRate,
    estimate_status: estimateStatus,
    pricing_status: pricingStatus,
    scope_status: 'unverified',
    price_sources: priceSources,
    evidence_issues: evidenceIssues,
    totals,
    assumptions,
    questions,
    source_note: sourceNote,
    sections,
  }
}

function normalizeDocumentDraft(value: unknown): Record<string, unknown> | null {
  const data = record(value)
  if (!data) return null
  const title = requiredString(data.title, 160)
  const type = optionalString(data.type, 40, 'custom')
  const client = optionalString(data.client, 240)
  const project = optionalString(data.project, 240)
  const content = optionalString(data.content, 500_000)
  const template = optionalString(data.template, 120)
  if (!title || type === null || client === null || project === null || content === null || template === null) return null
  const variablesRecord = record(data.variables ?? {})
  if (!variablesRecord || Object.keys(variablesRecord).length > 100) return null
  const variables: Record<string, string> = {}
  for (const [key, item] of Object.entries(variablesRecord)) {
    if (!key || key.length > 120 || typeof item !== 'string' || item.length > 10_000) return null
    variables[key] = item
  }
  return { title, type, client, project, content, variables, template }
}

export function normalizePersistedAction(value: unknown): ChatAction | null {
  const action = record(value)
  if (!action) return null
  const type = requiredString(action.type, 40)
  const label = requiredString(action.label, 120)
  if (!type || !label || !ACTION_TYPES.has(type)) return null
  if (type === 'create_estimate') {
    const data = normalizeEstimateDraft(action.data)
    if (!data) return null
    const safeLabel = data.estimate_status === 'needs_input'
      ? 'Уточнить данные для сметы'
      : 'Открыть предварительную смету'
    return { type, label: safeLabel, data: data as unknown as UnknownRecord }
  }
  if (type === 'create_document') {
    const data = normalizeDocumentDraft(action.data)
    return data ? { type, label, data } : null
  }
  try {
    const data = record(action.data)
    if (!data) return null
    return type === 'present_image'
      ? { type, label, data: normalizeImageArtifact(data) as unknown as UnknownRecord }
      : { type, label, data: normalizeFileArtifact(data) as unknown as UnknownRecord }
  } catch {
    return null
  }
}

function optionalMetadataString(value: unknown, maxLength: number): string | undefined | null {
  if (value === undefined || value === null || value === '') return undefined
  return typeof value === 'string' && value.length <= maxLength ? value : null
}

function normalizeWorkEvent(value: unknown): ChatWorkSummary | null {
  const event = record(value)
  if (!event) return null
  const stage = requiredString(event.stage, 80)
  const status = requiredString(event.status, 20)
  const summary = requiredString(event.summary, 600)
  if (!stage || !WORK_STAGES.has(stage as ChatWorkSummary['stage']) || !status || !summary || !WORK_STATUSES.has(status)) return null
  const kind = event.kind === 'reasoning_excerpt' ? 'reasoning_excerpt' : 'stage'
  const stepId = optionalMetadataString(event.step_id, 160)
  const summaryId = optionalMetadataString(event.summary_id, 160)
  const occurredAt = optionalMetadataString(event.occurred_at, 48)
  const responseId = optionalMetadataString(event.response_id, 160)
  const sequence = event.sequence === undefined
    ? undefined
    : Number.isSafeInteger(event.sequence) && Number(event.sequence) >= 0 ? Number(event.sequence) : null
  const provider = optionalMetadataString(event.provider, 80)
  const model = optionalMetadataString(event.model, 120)
  const artifactType = optionalMetadataString(event.artifact_type, 40)
  const artifactId = optionalMetadataString(event.artifact_id, 160)
  if (
    stepId === null || summaryId === null || occurredAt === null || responseId === null || sequence === null
    || provider === null || model === null || artifactType === null || artifactId === null
  ) return null
  return {
    kind,
    ...(stepId ? { step_id: stepId } : {}),
    ...(summaryId ? { summary_id: summaryId } : {}),
    stage: stage as ChatWorkSummary['stage'],
    status: status as ChatWorkSummary['status'],
    summary,
    ...(occurredAt ? { occurred_at: occurredAt } : {}),
    ...(responseId ? { response_id: responseId } : {}),
    ...(sequence !== undefined ? { sequence } : {}),
    ...(provider ? { provider } : {}),
    ...(model ? { model } : {}),
    ...(artifactType ? { artifact_type: artifactType } : {}),
    ...(artifactId ? { artifact_id: artifactId } : {}),
  }
}

function persistedArtifactReference(value: unknown): PersistedArtifactReference | undefined {
  const artifact = record(value)
  const type = artifact && requiredString(artifact.type, 20)
  if (!artifact || !type) return undefined
  if (type === 'estimate') {
    const id = requiredString(artifact.id, 64)
    const title = requiredString(artifact.title, 160)
    const version = Number(artifact.version)
    return id && UUID.test(id) && title && Number.isSafeInteger(version) && version > 0
      ? { type, id, title, version }
      : undefined
  }
  if (type === 'document') {
    const id = requiredString(artifact.id, 64)
    const title = requiredString(artifact.title, 160)
    return id && UUID.test(id) && title ? { type, id, title } : undefined
  }
  if (type === 'image') {
    try {
      return { type, value: normalizeImageArtifact(artifact) }
    } catch {
      return undefined
    }
  }
  if (type === 'file') {
    try {
      const value = record(artifact.value)
      return value ? { type, value: normalizeFileArtifact(value) } : undefined
    } catch {
      return undefined
    }
  }
  return undefined
}

export function conversationArtifactReference(artifact: ConversationArtifact): PersistedArtifactReference {
  if (artifact.type === 'estimate') {
    return {
      type: 'estimate',
      id: artifact.value.id,
      version: artifact.value.version,
      title: artifact.value.title,
    }
  }
  if (artifact.type === 'document') {
    return { type: 'document', id: artifact.value.id, title: artifact.value.title }
  }
  if (artifact.type === 'image') {
    return { type: 'image', value: normalizeImageArtifact(artifact.value as unknown as UnknownRecord) }
  }
  return { type: 'file', value: normalizeFileArtifact(artifact.value as unknown as UnknownRecord) }
}

function artifactReferenceJson(reference: PersistedArtifactReference): Record<string, unknown> {
  if (reference.type === 'image') return { ...reference.value }
  if (reference.type === 'file') return { type: 'file', value: { ...reference.value } }
  return { ...reference }
}

export function buildPersistedConversationMetadata(input: {
  responseId?: string | null
  workEvents?: readonly ChatWorkSummary[]
  actions?: readonly ChatAction[]
  artifact?: ConversationArtifact | null
}): Record<string, unknown> {
  const responseId = requiredString(input.responseId, 160)
  const workEvents = (input.workEvents ?? [])
    .slice(-128)
    .map(normalizeWorkEvent)
    .filter((value): value is ChatWorkSummary => value !== null)
  const artifact = input.artifact ? conversationArtifactReference(input.artifact) : undefined
  const actions = artifact
    ? []
    : (input.actions ?? [])
      .slice(0, 8)
      .map(normalizePersistedAction)
      .filter((value): value is ChatAction => value !== null)
  const metadata: Record<string, unknown> = {
    ...(responseId ? { response_id: responseId } : {}),
    ...(workEvents.length ? { work_events: workEvents } : {}),
    ...(actions.length ? { actions } : {}),
    ...(artifact ? { artifact: artifactReferenceJson(artifact) } : {}),
  }
  if (new TextEncoder().encode(JSON.stringify(metadata)).byteLength > 280_000) {
    delete metadata.actions
  }
  return metadata
}

export function restoreConversationMetadata(value: unknown): RestoredConversationMetadata {
  const metadata = record(value) ?? {}
  const responseId = requiredString(metadata.response_id, 160) ?? undefined
  const workEvents = Array.isArray(metadata.work_events)
    ? metadata.work_events
      .slice(-128)
      .map(normalizeWorkEvent)
      .filter((item): item is ChatWorkSummary => item !== null)
    : []
  const hasArtifactField = metadata.artifact !== undefined
  const artifact = persistedArtifactReference(metadata.artifact)
  const actions = hasArtifactField || !Array.isArray(metadata.actions)
    ? []
    : metadata.actions
      .slice(0, 8)
      .map(normalizePersistedAction)
      .filter((item): item is ChatAction => item !== null)
  return { responseId, workEvents, actions, artifact }
}

export async function hydratePersistedArtifact(
  reference: PersistedArtifactReference,
  loaders: {
    estimate: (id: string) => Promise<Estimate>
    document: (id: string) => Promise<Document>
  },
): Promise<ConversationArtifact> {
  if (reference.type === 'image') return { type: 'image', value: reference.value }
  if (reference.type === 'file') return { type: 'file', value: reference.value }
  if (reference.type === 'estimate') {
    const value = await loaders.estimate(reference.id)
    if (value.id !== reference.id || value.version < reference.version) {
      throw new Error('Persisted estimate reference is stale or inconsistent')
    }
    return { type: 'estimate', value }
  }
  const value = await loaders.document(reference.id)
  if (value.id !== reference.id) throw new Error('Persisted document reference is inconsistent')
  return { type: 'document', value }
}

export function imageArtifactFromReference(reference?: PersistedArtifactReference): ConversationArtifact | undefined {
  return reference?.type === 'image' ? { type: 'image', value: reference.value } : undefined
}
