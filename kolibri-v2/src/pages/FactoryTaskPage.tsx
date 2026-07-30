import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, Ban, CheckCircle2, Clock3, RefreshCw, ShieldCheck } from 'lucide-react'
import { Link, useParams } from 'react-router'
import ControlCenterNav from '@/features/factory/ControlCenterNav'
import { tasks, type FactoryTaskEvent, type TaskDetail } from '@/lib/api'

const terminalStates = new Set(['completed', 'failed', 'cancelled', 'dead_letter'])

export default function FactoryTaskPage() {
  const { taskId = '' } = useParams()
  const [task, setTask] = useState<TaskDetail | null>(null)
  const [events, setEvents] = useState<FactoryTaskEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [cancelling, setCancelling] = useState(false)

  const load = useCallback(async () => {
    if (!taskId) return
    try {
      const [detail, timeline] = await Promise.all([
        tasks.get(taskId),
        tasks.events(taskId, { limit: 200 }),
      ])
      setTask(detail)
      setEvents(timeline.items)
      setError(false)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [taskId])

  useEffect(() => {
    const initial = window.setTimeout(() => { void load() }, 0)
    const timer = window.setInterval(() => { void load() }, 5000)
    return () => {
      window.clearTimeout(initial)
      window.clearInterval(timer)
    }
  }, [load])

  const cancel = async () => {
    if (!task || cancelling) return
    setCancelling(true)
    try {
      await tasks.cancel(task.id)
      await load()
    } finally {
      setCancelling(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1000px] px-4 py-6 sm:px-6">
        <ControlCenterNav />
        <Link to="/control" className="mb-4 inline-flex min-h-10 items-center gap-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"><ArrowLeft size={15} />К задачам</Link>
        {loading && <p className="py-16 text-center text-[13px] text-[var(--text-tertiary)]">Загрузка задачи…</p>}
        {error && !task && <div className="rounded-[var(--radius-lg)] border border-amber-200 bg-amber-50 p-4 text-[13px] text-amber-800">Home Control Plane не вернул задачу или журнал событий.</div>}
        {task && (
          <>
            <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0"><p className="mb-1 text-[11px] uppercase tracking-wider text-[var(--text-tertiary)]">{task.kind}</p><h1 className="break-words text-[22px] font-semibold tracking-tight text-[var(--text-primary)] sm:text-[26px]">{task.objective || task.workflow_id}</h1><p className="mt-2 break-all font-mono text-[10px] text-[var(--text-tertiary)]">{task.id}</p></div>
              <div className="flex shrink-0 gap-2"><button onClick={() => void load()} className="inline-flex min-h-10 items-center gap-2 rounded-[var(--radius-md)] border border-[var(--border-subtle)] px-3 text-[12px] text-[var(--text-secondary)]"><RefreshCw size={14} />Обновить</button>{!terminalStates.has(task.state) && <button onClick={cancel} disabled={cancelling} className="inline-flex min-h-10 items-center gap-2 rounded-[var(--radius-md)] border border-red-200 px-3 text-[12px] text-red-700 disabled:opacity-50"><Ban size={14} />{cancelling ? 'Отменяю…' : 'Отменить'}</button>}</div>
            </header>

            <section className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ['Статус', task.state],
                ['Попытка', `${task.attempts}/${task.max_retries + 1}`],
                ['Исполнитель', task.owner_agent_id || 'не назначен'],
                ['Проверка', task.verification.verdict || 'ожидается'],
              ].map(([label, value]) => <div key={label} className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4"><p className="text-[11px] text-[var(--text-tertiary)]">{label}</p><p className="mt-1 truncate text-[13px] font-medium text-[var(--text-primary)]" title={value}>{value}</p></div>)}
            </section>

            {(task.verification.result_sha256 || task.verification.binding_sha256) && <section className="mb-6 rounded-[var(--radius-lg)] border border-emerald-200 bg-emerald-50 p-4"><div className="mb-3 flex items-center gap-2 text-emerald-800"><ShieldCheck size={17} /><strong className="text-[13px]">Проверка результата</strong></div>{task.verification.result_sha256 && <p className="truncate font-mono text-[10px] text-emerald-800" title={task.verification.result_sha256}>result sha256:{task.verification.result_sha256}</p>}{task.verification.binding_sha256 && <p className="mt-1 truncate font-mono text-[10px] text-emerald-800" title={task.verification.binding_sha256}>binding sha256:{task.verification.binding_sha256}</p>}</section>}

            <section>
              <h2 className="mb-3 text-[16px] font-semibold text-[var(--text-primary)]">Ход выполнения</h2>
              <div className="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
                {events.map(event => <article key={event.event_id} className="grid gap-2 border-b border-[var(--border-subtle)] p-4 last:border-0 sm:grid-cols-[32px_minmax(0,1fr)_170px] sm:items-center"><div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--bg-secondary)]">{event.state === 'completed' ? <CheckCircle2 size={15} className="text-emerald-600" /> : <Clock3 size={15} className="text-[var(--text-secondary)]" />}</div><div className="min-w-0"><p className="truncate text-[13px] font-medium text-[var(--text-primary)]">{event.event_type}</p><p className="mt-0.5 text-[11px] text-[var(--text-tertiary)]">{event.state || 'без смены состояния'} · #{event.sequence}</p></div><time className="text-[11px] text-[var(--text-tertiary)]">{new Date(event.occurred_at).toLocaleString('ru-RU')}</time></article>)}
                {events.length === 0 && <p className="p-8 text-center text-[13px] text-[var(--text-tertiary)]">События ещё не записаны.</p>}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  )
}
