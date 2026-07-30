import { useEffect, useMemo, useState } from 'react'
import { ArrowUpRight, LoaderCircle } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router'
import {
  completionNotificationPayload,
  getActiveResponseActivities,
  RESPONSE_ACTIVITY_EVENT,
  updateActiveResponseActivities,
  type ActiveResponseActivity,
  type ResponseActivityDetail,
} from './responseActivity'

export default function BackgroundResponseStatus() {
  const navigate = useNavigate()
  const location = useLocation()
  const [activities, setActivities] = useState<ReadonlyMap<string, ActiveResponseActivity>>(
    () => getActiveResponseActivities(),
  )

  useEffect(() => {
    const onResponseState = (event: Event) => {
      const detail = (event as CustomEvent<Partial<ResponseActivityDetail>>).detail
      setActivities(current => updateActiveResponseActivities(current, detail))

      if (typeof Notification === 'undefined') return
      const payload = completionNotificationPayload(detail, Notification.permission)
      if (payload) {
        try {
          new Notification(payload.title, payload.options)
        } catch {
          // A browser-level notification failure must never interrupt the saved response lifecycle.
        }
      }
    }
    window.addEventListener(RESPONSE_ACTIVITY_EVENT, onResponseState)
    return () => window.removeEventListener(RESPONSE_ACTIVITY_EVENT, onResponseState)
  }, [])

  const active = useMemo(
    () => [...activities.values()].filter(activity => (
      !activity.projectId
      || location.pathname !== `/chat/${encodeURIComponent(activity.projectId)}`
    )),
    [activities, location.pathname],
  )
  if (active.length === 0) return null

  const latest = active.at(-1)
  const label = active.length === 1
    ? latest?.summary || 'Kolibri отвечает'
    : `Kolibri выполняет ${active.length} задачи`

  return (
    <aside className="background-response-status" role="status" aria-live="polite" aria-label={label}>
      <LoaderCircle className="background-response-spinner" size={17} aria-hidden="true" />
      <span>{label}</span>
      {latest?.projectId && (
        <button
          type="button"
          onClick={() => navigate(`/chat/${encodeURIComponent(latest.projectId!)}`)}
          aria-label="Открыть выполняющийся чат"
        >
          Открыть
          <ArrowUpRight size={15} aria-hidden="true" />
        </button>
      )}
    </aside>
  )
}
