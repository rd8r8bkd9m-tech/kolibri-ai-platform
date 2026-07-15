import { normalizePersistedAction } from '@/features/projects/persistedConversation'
import type { ChatAction } from '@/lib/api'

const FALLBACK_QUESTION = 'Уточните состав работ, объёмы и возможность подбора актуальных региональных цен.'

function normalizedEstimate(action: ChatAction): ChatAction | null {
  const normalized = normalizePersistedAction(action)
  return normalized?.type === 'create_estimate' ? normalized : null
}

export function estimateActionNeedsClarification(action: ChatAction): boolean {
  const normalized = normalizedEstimate(action)
  if (!normalized?.data) return false
  return normalized.data.estimate_status === 'needs_input'
    || normalized.data.pricing_status === 'needs_input'
}

export function shouldAutoMaterializeAction(action: ChatAction): boolean {
  const normalized = normalizePersistedAction(action)
  if (!normalized) return false
  return normalized.type !== 'create_estimate'
    || !estimateActionNeedsClarification(normalized)
}

export function estimateClarificationQuestions(action: ChatAction): string[] {
  const normalized = normalizedEstimate(action)
  const rawQuestions = Array.isArray(normalized?.data?.questions)
    ? normalized.data.questions
    : []
  const questions = rawQuestions
    .filter((value): value is string => typeof value === 'string' && Boolean(value.trim()))
    .slice(0, 5)
    .map(value => value.trim().slice(0, 280))
  return questions.length ? questions : [FALLBACK_QUESTION]
}

export function estimateClarificationPrompt(action: ChatAction): string {
  const visibleQuestions = estimateClarificationQuestions(action).slice(0, 3)
  return [
    'Уточнение для сметы:',
    ...visibleQuestions.map((question, index) => `${index + 1}. ${question}`),
  ].join('\n')
}
