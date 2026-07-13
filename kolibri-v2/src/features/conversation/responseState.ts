import type { ChatResponse, ChatStreamEvent, ProjectMessageStatus } from '@/lib/api'
import type { Translate } from '@/features/localization'

const FAILED_STATUSES = new Set([
  'error',
  'failed',
  'incomplete',
  'unavailable',
  'capability_unavailable',
])

type FailureLike = Pick<ChatStreamEvent, 'status' | 'error_code' | 'capability'>
  | Pick<ChatResponse, 'status' | 'error_code' | 'capability'>

export function isFailedResponse(value: FailureLike): boolean {
  return FAILED_STATUSES.has(value.status ?? '') || Boolean(value.error_code)
}

export function responseFailureMessage(value: FailureLike, t?: Translate): string {
  if (value.error_code === 'capability_unavailable' && value.capability === 'image.generate') {
    return t?.('failure.imageUnavailable') ?? 'Генерация изображений сейчас недоступна. Попробуйте позже.'
  }
  if (value.error_code === 'image_artifact_verification_failed') {
    return t?.('failure.imageVerification') ?? 'Изображение не создано: файл не прошёл проверку.'
  }
  return t?.('failure.routes') ?? 'Не удалось завершить ответ через доступные маршруты. Повторите запрос.'
}

export function persistedResponseStatus(
  status: string | undefined,
  artifactFailed: boolean,
  content: string,
): ProjectMessageStatus {
  if (status === 'cancelled') return 'cancelled'
  if (artifactFailed || FAILED_STATUSES.has(status ?? '') || !content.trim()) return 'failed'
  return 'completed'
}
