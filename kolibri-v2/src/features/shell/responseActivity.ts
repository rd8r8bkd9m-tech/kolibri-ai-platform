export const RESPONSE_ACTIVITY_EVENT = 'kolibri:response-active'

export interface ResponseActivityDetail {
  id: string
  active: boolean
}

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

export function dispatchResponseActivity(id: string, active: boolean, target: EventTarget = window) {
  target.dispatchEvent(new CustomEvent<ResponseActivityDetail>(RESPONSE_ACTIVITY_EVENT, {
    detail: { id, active },
  }))
}
