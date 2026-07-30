export const RESPONSE_ACTIVITY_EVENT = 'kolibri:response-active'

export type ResponseActivityOutcome = 'completed' | 'failed' | 'cancelled'

export interface ResponseActivityDetail {
  id: string
  active: boolean
  projectId?: string
  startedAt?: number
  summary?: string
  outcome?: ResponseActivityOutcome
}

export interface ActiveResponseActivity {
  id: string
  projectId?: string
  startedAt: number
  summary?: string
}

const activeResponseActivities = new Map<string, ActiveResponseActivity>()

export function updateActiveResponseIds(
  current: ReadonlySet<string>,
  detail: Partial<ResponseActivityDetail> | null | undefined,
): Set<string> {
  const next = new Set(current)
  const id = typeof detail?.id === 'string' ? detail.id.trim() : ''
  if (!id || typeof detail?.active !== 'boolean') return next
  if (detail.active) next.add(id)
  else next.delete(id)
  return next
}

export function updateActiveResponseActivities(
  current: ReadonlyMap<string, ActiveResponseActivity>,
  detail: Partial<ResponseActivityDetail> | null | undefined,
): Map<string, ActiveResponseActivity> {
  const next = new Map(current)
  const id = typeof detail?.id === 'string' ? detail.id.trim() : ''
  if (!id || typeof detail?.active !== 'boolean') return next
  if (!detail.active) {
    next.delete(id)
    return next
  }
  const previous = next.get(id)
  const projectId = typeof detail.projectId === 'string' && detail.projectId.trim()
    ? detail.projectId.trim()
    : previous?.projectId
  const summary = typeof detail.summary === 'string' && detail.summary.trim()
    ? detail.summary.trim().slice(0, 240)
    : previous?.summary
  next.set(id, {
    id,
    projectId,
    summary,
    startedAt: typeof detail.startedAt === 'number' && Number.isFinite(detail.startedAt)
      ? detail.startedAt
      : previous?.startedAt ?? Date.now(),
  })
  return next
}

export function getActiveResponseActivities(): Map<string, ActiveResponseActivity> {
  return new Map(activeResponseActivities)
}

export function completionNotificationPayload(
  detail: Partial<ResponseActivityDetail> | null | undefined,
  permission: NotificationPermission,
): { title: string; options: NotificationOptions } | null {
  if (permission !== 'granted' || detail?.active !== false || detail.outcome !== 'completed') return null
  const id = typeof detail.id === 'string' ? detail.id.trim() : ''
  if (!id) return null
  return {
    title: 'Kolibri — ответ готов',
    options: {
      body: 'Задача завершена. Результат сохранён в чате.',
      tag: `kolibri-response-${id}`,
    },
  }
}

export function dispatchResponseActivity(
  id: string,
  active: boolean,
  options: Omit<ResponseActivityDetail, 'id' | 'active'> = {},
  target: EventTarget = window,
) {
  const detail: ResponseActivityDetail = { id, active, ...options }
  const next = updateActiveResponseActivities(activeResponseActivities, detail)
  activeResponseActivities.clear()
  next.forEach((activity, activityId) => activeResponseActivities.set(activityId, activity))
  target.dispatchEvent(new CustomEvent<ResponseActivityDetail>(RESPONSE_ACTIVITY_EVENT, {
    detail,
  }))
}
