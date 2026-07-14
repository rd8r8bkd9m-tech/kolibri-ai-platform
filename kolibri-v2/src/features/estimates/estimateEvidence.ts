import type { Estimate, EstimateTruthStatus, Position, PriceSourceEvidence } from '@/lib/api'

type UnknownRecord = Record<string, unknown>

export interface PositionEvidenceView {
  position: Position
  evidence: PriceSourceEvidence | null
  verified: boolean
  reason: string
}

export interface EstimateEvidenceSummary {
  estimateStatus: EstimateTruthStatus
  pricingStatus: EstimateTruthStatus
  totalPricedRows: number
  verifiedRows: number
  dateLabel: string | null
  rows: PositionEvidenceView[]
}

export const estimateTruthLabels: Record<EstimateTruthStatus, string> = {
  needs_input: 'Нужны исходные данные',
  preliminary: 'Предварительная',
  source_backed: 'Цены подтверждены источниками',
  verified: 'Проверена',
}

function record(value: unknown): UnknownRecord | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as UnknownRecord
    : null
}

function optionalText(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function truthStatus(value: unknown): EstimateTruthStatus | null {
  return value === 'needs_input' || value === 'preliminary' || value === 'source_backed' || value === 'verified'
    ? value
    : null
}

function evidenceFromUnknown(value: unknown): PriceSourceEvidence | null {
  const source = record(value)
  if (!source) return null
  return {
    position_code: optionalText(source.position_code ?? source.positionCode),
    source_id: optionalText(source.source_id ?? source.sourceId),
    url: optionalText(source.url ?? source.source_url),
    source_title: optionalText(source.source_title ?? source.title),
    source_type: optionalText(source.source_type ?? source.type),
    region: optionalText(source.region),
    observed_at: optionalText(source.observed_at ?? source.observedAt ?? source.retrieved_at),
    price_date: optionalText(source.price_date ?? source.priceDate ?? source.as_of),
    unit: optionalText(source.unit),
    unit_price: optionalText(source.unit_price ?? source.price),
    vat_status: optionalText(source.vat_status ?? source.vatStatus),
    quote: optionalText(source.quote),
    currency: optionalText(source.currency),
    content_sha256: optionalText(source.content_sha256 ?? source.sha256),
    verification: optionalText(source.verification ?? source.status),
    attestation: optionalText(source.attestation),
  }
}

function sourceCatalog(estimate: Estimate): PriceSourceEvidence[] {
  const raw = estimate as unknown as UnknownRecord
  const entries = estimate.price_sources ?? (Array.isArray(raw.priceSources) ? raw.priceSources : [])
  return entries.map(evidenceFromUnknown).filter((value): value is PriceSourceEvidence => value !== null)
}

function mergeEvidence(primary: PriceSourceEvidence, catalogEntry: PriceSourceEvidence | undefined): PriceSourceEvidence {
  if (!catalogEntry) return primary
  return { ...catalogEntry, ...Object.fromEntries(Object.entries(primary).filter(([, value]) => value !== undefined)) }
}

function positionEvidenceCandidates(estimate: Estimate, position: Position): PriceSourceEvidence[] {
  const rawPosition = position as unknown as UnknownRecord
  const catalog = sourceCatalog(estimate)
  const rawCandidates = [
    ...(Array.isArray(position.price_evidence) ? position.price_evidence : []),
    ...(Array.isArray(rawPosition.priceEvidence) ? rawPosition.priceEvidence : []),
    position.source_evidence,
    rawPosition.sourceEvidence,
    rawPosition.evidence,
    ...catalog.filter(item => item.position_code === position.code),
  ]
  const result: PriceSourceEvidence[] = []
  const seen = new Set<string>()
  for (const rawCandidate of rawCandidates) {
    const embedded = evidenceFromUnknown(rawCandidate)
    if (!embedded) continue
    const catalogEntry = catalog.find(item => item.source_id && item.source_id === embedded.source_id)
    const merged = mergeEvidence(embedded, catalogEntry)
    const key = `${merged.position_code || ''}:${merged.source_id || ''}:${merged.url || ''}`
    if (seen.has(key)) continue
    seen.add(key)
    result.push(merged)
  }
  return result
}

function normalizedUnit(value: string): string {
  return value.toLocaleLowerCase('ru-RU').replace(/\s+/g, '').replace(/м[\^2]/g, 'м²').replace('кв.м', 'м²')
}

function regionTokens(value: string): Set<string> {
  const stop = new Set(['республика', 'область', 'край', 'город', 'район', 'россия', 'рф'])
  return new Set(value.toLocaleLowerCase('ru-RU')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .split(' ')
    .filter(token => token.length > 2 && !stop.has(token)))
}

function regionsOverlap(estimateRegion: string, evidenceRegion: string): boolean {
  const expected = regionTokens(estimateRegion)
  const actual = regionTokens(evidenceRegion)
  if (!expected.size || !actual.size) return false
  return [...expected].some(token => actual.has(token))
}

function sameMoney(left: string, right: string): boolean {
  const leftValue = Number(left.replace(',', '.'))
  const rightValue = Number(right.replace(',', '.'))
  return Number.isFinite(leftValue)
    && Number.isFinite(rightValue)
    && Math.round(leftValue * 100) === Math.round(rightValue * 100)
}

function validSourceUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:'
  } catch {
    return false
  }
}

function validEvidenceDate(value: string): boolean {
  return Number.isFinite(Date.parse(value))
}

function evidenceDate(evidence: PriceSourceEvidence): string | null {
  const value = evidence.price_date || evidence.observed_at
  return value && validEvidenceDate(value) ? value : null
}

function evidenceBindingReason(estimate: Estimate, position: Position, evidence: PriceSourceEvidence | null): string {
  if (!evidence) return position.source
    ? 'Указан текст источника, но нет проверяемой привязки цены к строке'
    : 'Для цены не приложен проверяемый источник'
  const verification = evidence.verification?.toLocaleLowerCase('ru-RU')
  if (verification !== 'source_backed' && verification !== 'verified') return 'Источник не прошёл проверку привязки'
  if (!evidence.position_code || evidence.position_code !== position.code) return 'Источник не привязан к коду строки'
  if (!evidence.source_id) return 'У источника отсутствует идентификатор'
  if (!evidence.url || !validSourceUrl(evidence.url)) return 'Нет проверяемой ссылки на источник'
  if (!evidence.region || !regionsOverlap(estimate.region, evidence.region)) return 'Регион источника не совпадает с регионом сметы'
  if (!evidenceDate(evidence)) return 'Не указана дата наблюдения цены'
  if (!evidence.unit || normalizedUnit(evidence.unit) !== normalizedUnit(position.unit)) return 'Единица цены не совпадает со строкой'
  if (!evidence.unit_price || !sameMoney(evidence.unit_price, position.price)) return 'Цена источника не совпадает с ценой строки'
  if (!evidence.currency || evidence.currency.toUpperCase() !== estimate.currency.toUpperCase()) return 'Валюта источника не совпадает со сметой'
  if (evidence.content_sha256 && !/^[a-f0-9]{64}$/i.test(evidence.content_sha256)) return 'Контрольная сумма источника некорректна'
  return ''
}

function dateRangeLabel(values: string[]): string | null {
  const timestamps = values.map(value => Date.parse(value)).filter(Number.isFinite).sort((left, right) => left - right)
  if (!timestamps.length) return null
  const format = (timestamp: number) => new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Moscow',
  }).format(new Date(timestamp))
  const first = format(timestamps[0])
  const last = format(timestamps[timestamps.length - 1])
  return first === last ? first : `${first}–${last}`
}

export function estimateEvidenceSummary(estimate: Estimate): EstimateEvidenceSummary {
  const raw = estimate as unknown as UnknownRecord
  const declaredEstimate = truthStatus(estimate.estimate_status ?? raw.estimateStatus ?? raw.verification_status) ?? 'preliminary'
  const declaredPricing = truthStatus(estimate.pricing_status ?? raw.pricingStatus ?? raw.evidence_status) ?? 'preliminary'
  const positions = estimate.sections.flatMap(section => section.positions)
  const priced = positions.filter(position => Number(position.price.replace(',', '.')) > 0)
  const rows = priced.map(position => {
    const candidates = positionEvidenceCandidates(estimate, position)
    const evaluated = candidates.map(evidence => ({ evidence, reason: evidenceBindingReason(estimate, position, evidence) }))
    const accepted = evaluated.find(item => item.reason === '')
    const fallback = accepted ?? evaluated[0]
    const evidence = fallback?.evidence ?? null
    const reason = fallback?.reason ?? evidenceBindingReason(estimate, position, null)
    return { position, evidence, verified: Boolean(accepted), reason }
  })
  const verifiedRows = rows.filter(row => row.verified).length
  const allPricesBound = rows.length > 0 && verifiedRows === rows.length
  const allPricesIndependentlyVerified = allPricesBound && rows.every(
    row => row.evidence?.verification?.toLocaleLowerCase('ru-RU') === 'verified',
  )
  const pricingStatus: EstimateTruthStatus = declaredPricing === 'needs_input'
    ? 'needs_input'
    : !allPricesBound
      ? 'preliminary'
      : declaredPricing === 'verified' && allPricesIndependentlyVerified
        ? 'verified'
        : declaredPricing === 'source_backed' || declaredPricing === 'verified'
          ? 'source_backed'
          : 'preliminary'
  const estimateStatus: EstimateTruthStatus = declaredEstimate === 'needs_input'
    ? 'needs_input'
    : declaredEstimate === 'verified' && pricingStatus === 'verified'
      ? 'verified'
      : (declaredEstimate === 'source_backed' || declaredEstimate === 'verified')
        && (pricingStatus === 'source_backed' || pricingStatus === 'verified')
        ? 'source_backed'
        : 'preliminary'
  const dates = rows
    .filter(row => row.verified && row.evidence)
    .map(row => evidenceDate(row.evidence!))
    .filter((value): value is string => value !== null)
  return {
    estimateStatus,
    pricingStatus,
    totalPricedRows: rows.length,
    verifiedRows,
    dateLabel: dateRangeLabel(dates),
    rows,
  }
}

export function truthStatusClass(status: EstimateTruthStatus): string {
  if (status === 'verified') return 'verified'
  if (status === 'source_backed') return 'source-backed'
  if (status === 'needs_input') return 'needs-input'
  return 'preliminary'
}
