import { useEffect, useState } from 'react'
import { History, ShieldAlert } from 'lucide-react'
import ControlCenterNav from '@/features/factory/ControlCenterNav'
import { factoryControl, type FactoryTaskEvent, type FactoryTaskSummary } from '@/lib/api'

export default function FactoryEventsPage() {
  const [events, setEvents] = useState<FactoryTaskEvent[] | null>(null)
  const [summary, setSummary] = useState<FactoryTaskSummary | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    void Promise.all([factoryControl.events({ limit: 100 }), factoryControl.summary()])
      .then(([eventPage, taskSummary]) => {
        if (!active) return
        setEvents(eventPage.items)
        setSummary(taskSummary)
      })
      .catch(() => { if (active) setError(true) })
    return () => { active = false }
  }, [])

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1100px] px-4 py-6 sm:px-6">
        <ControlCenterNav />
        <div className="mb-6">
          <h1 className="text-[22px] font-semibold tracking-tight text-[var(--text-primary)] sm:text-[26px]">События задач</h1>
          <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">Неизменяемая последовательность: постановка, аренда, выполнение, проверка и завершение.</p>
        </div>

        {summary && (
          <section className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ['Всего', summary.total],
              ['В очереди', summary.queued],
              ['В работе', summary.running],
              ['Ошибки', summary.failed + summary.dead_letter],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4"><p className="text-[11px] text-[var(--text-tertiary)]">{label}</p><p className="mt-1 text-[22px] font-semibold text-[var(--text-primary)]">{value}</p></div>
            ))}
          </section>
        )}

        {error && (
          <div className="flex gap-3 rounded-[var(--radius-lg)] border border-amber-200 bg-amber-50 p-4 text-[13px] text-amber-800"><ShieldAlert size={18} className="mt-0.5 shrink-0" /><p>Журнал Home Control Plane недоступен. Портал не реконструирует события из приблизительных статусов.</p></div>
        )}
        {!events && !error && <p className="py-16 text-center text-[13px] text-[var(--text-tertiary)]">Загрузка журнала…</p>}
        {events && (
          <section className="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
            {events.map(event => (
              <article key={event.event_id} className="grid gap-2 border-b border-[var(--border-subtle)] p-4 last:border-0 sm:grid-cols-[36px_minmax(0,1fr)_180px] sm:items-center">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--bg-secondary)] text-[var(--text-secondary)]"><History size={15} /></div>
                <div className="min-w-0"><p className="truncate text-[13px] font-medium text-[var(--text-primary)]">{event.event_type}</p><p className="mt-0.5 truncate text-[11px] text-[var(--text-tertiary)]">{event.task_id} · {event.node_id || 'Home'} · #{event.sequence}</p></div>
                <time className="text-[11px] text-[var(--text-tertiary)]">{new Date(event.occurred_at).toLocaleString('ru-RU')}</time>
              </article>
            ))}
            {events.length === 0 && <p className="p-8 text-center text-[13px] text-[var(--text-tertiary)]">Событий пока нет.</p>}
          </section>
        )}
      </div>
    </div>
  )
}
