import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { Activity, Bot, ChevronDown, Circle, Play, Send, ShieldCheck } from 'lucide-react'
import { agents, tasks, type Agent, type Task } from '@/lib/api'
import { summarizeAgents } from '@/features/factory/factoryTruth'
import ControlCenterNav from '@/features/factory/ControlCenterNav'
import { createUuid } from '@/lib/uuid'

const statusConfig: Record<string, { color: string; label: string }> = {
  active: { color: 'text-violet-600', label: 'Есть активная задача' },
  idle: { color: 'text-gray-400', label: 'Активной задачи нет' },
  paused: { color: 'text-amber-500', label: 'Пауза' },
  error: { color: 'text-red-500', label: 'Недоступен' },
}

const taskStatus: Record<string, { color: string; label: string }> = {
  running: { color: 'text-violet-700 bg-violet-50', label: 'Выполняется' },
  queued: { color: 'text-gray-600 bg-gray-100', label: 'В очереди' },
  completed: { color: 'text-blue-600 bg-blue-50', label: 'Завершено' },
  failed: { color: 'text-red-600 bg-red-50', label: 'Ошибка' },
  created: { color: 'text-gray-500 bg-gray-50', label: 'Создана' },
  assigned: { color: 'text-purple-600 bg-purple-50', label: 'Назначена' },
  waiting: { color: 'text-amber-600 bg-amber-50', label: 'Ожидание' },
  cancelled: { color: 'text-gray-400 bg-gray-50', label: 'Отменена' },
}

export default function AgentsPage() {
  const [agentList, setAgentList] = useState<Agent[] | null>(null)
  const [taskList, setTaskList] = useState<Task[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadErrors, setLoadErrors] = useState<string[]>([])
  const [objective, setObjective] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    Promise.allSettled([
      agents.list({ page_size: 50 }),
      tasks.list({ page_size: 50 }),
    ]).then(([agentResult, taskResult]) => {
      const errors: string[] = []
      if (agentResult.status === 'fulfilled') setAgentList(agentResult.value.items)
      else {
        console.error('Failed to load agents', agentResult.reason)
        errors.push('исполнители')
      }
      if (taskResult.status === 'fulfilled') setTaskList(taskResult.value.items)
      else {
        console.error('Failed to load tasks', taskResult.reason)
        errors.push('задачи')
      }
      setLoadErrors(errors)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="flex items-center justify-center h-full text-[var(--text-tertiary)]">Загрузка...</div>
  }

  const agentSummary = agentList ? summarizeAgents(agentList) : null
  const valueOrUnknown = (value: number | undefined) => value === undefined ? '—' : value
  const visibleTasks = taskList ?? []
  const recentTasks = visibleTasks.slice(0, 30)
  const stats = [
    { label: 'Membership hosts', value: valueOrUnknown(agentSummary?.membership), icon: Bot },
    { label: 'Исполнимые', value: valueOrUnknown(agentSummary?.executable), icon: Activity },
    { label: 'С активной задачей', value: valueOrUnknown(agentSummary?.active), icon: Play },
    { label: 'Проверенный результат', value: valueOrUnknown(agentSummary?.verified), icon: ShieldCheck, verified: true },
    { label: 'Выполняется задач', value: taskList ? visibleTasks.filter(task => task.state === 'running').length : '—', icon: Play },
    { label: 'В очереди', value: taskList ? visibleTasks.filter(task => task.state === 'queued').length : '—', icon: ChevronDown },
  ]

  const submitTask = async (event: FormEvent) => {
    event.preventDefault()
    const value = objective.trim()
    if (!value || submitting) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const created = await tasks.create(value, `portal-${createUuid()}`)
      setTaskList(current => current ? [created, ...current] : [created])
      setObjective('')
    } catch (error) {
      console.error('Failed to submit factory task', error)
      setSubmitError('Home Control Plane не принял задачу. Проверьте защищённое подключение и повторите.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-6">
        <ControlCenterNav />
        <div className="mb-6">
          <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight">Фабрика</h1>
          <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">Agent Host membership не считается работающим исполнителем без capability и proof</p>
        </div>

        {loadErrors.length > 0 && (
          <div className="mb-6 rounded-[var(--radius-lg)] border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
            Home Control Plane не вернул: {loadErrors.join(', ')}. Неизвестные значения показаны как «—», а не как ноль.
          </div>
        )}

        <form onSubmit={submitTask} className="mb-6 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 sm:p-4">
          <label htmlFor="factory-objective" className="mb-2 block text-[12px] font-medium text-[var(--text-secondary)]">Новое задание фабрике</label>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <textarea
              id="factory-objective"
              value={objective}
              onChange={event => setObjective(event.target.value)}
              placeholder="Например: проверь экспорт сметы, исправь ошибку и приложи доказательства тестов"
              rows={3}
              maxLength={8000}
              className="min-h-24 flex-1 resize-y rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2.5 text-[13px] text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-tertiary)] focus:border-[var(--accent-teal)] sm:min-h-20"
            />
            <button
              type="submit"
              disabled={!objective.trim() || submitting}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-[var(--radius-md)] bg-[var(--text-primary)] px-4 text-[13px] font-medium text-[var(--bg-primary)] transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send size={15} aria-hidden="true" />
              {submitting ? 'Отправляю…' : 'Поставить задачу'}
            </button>
          </div>
          <p className="mt-2 text-[11px] text-[var(--text-tertiary)]">Задача получает idempotency-key, один запуск и строгую проверку результата.</p>
          {submitError && <p className="mt-2 text-[12px] text-red-600">{submitError}</p>}
        </form>

        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
          {stats.map(stat => (
            <div key={stat.label} className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
              <div className="flex items-center gap-2 mb-2">
                <stat.icon size={14} className={stat.verified ? 'text-emerald-600' : 'text-[var(--text-tertiary)]'} strokeWidth={1.8} />
                <span className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider">{stat.label}</span>
              </div>
              <p className={`text-[22px] font-semibold ${stat.verified ? 'text-emerald-700' : 'text-[var(--text-primary)]'}`}>{stat.value}</p>
            </div>
          ))}
        </div>

        <details className="group mb-8 overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 text-[13px] font-medium text-[var(--text-primary)] marker:hidden [&::-webkit-details-marker]:hidden">
            <span className="flex items-center gap-2"><Bot size={16} className="text-[var(--text-tertiary)]" />Исполнители <span className="font-normal text-[var(--text-tertiary)]">{agentList?.length ?? '—'}</span></span>
            <ChevronDown size={16} className="text-[var(--text-tertiary)] transition-transform group-open:rotate-180" />
          </summary>
          <div className="border-t border-[var(--border-subtle)]">
            {(agentList ?? []).map(agent => {
              const status = statusConfig[agent.status] ?? statusConfig.error
              const executableCount = (agent.capabilities.execution ?? []).filter(capability => capability.executable).length
              return (
                <div key={agent.id} className="grid gap-2 border-b border-[var(--border-subtle)] px-4 py-3 last:border-0 sm:grid-cols-[minmax(0,1fr)_150px_130px_120px] sm:items-center">
                  <div className="min-w-0"><p className="truncate text-[12px] font-medium text-[var(--text-primary)]">{agent.name}</p><p className="truncate text-[10px] text-[var(--text-tertiary)]">{agent.node_id || 'node —'}</p></div>
                  <span className="flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)]"><Circle size={7} className={status.color} fill="currentColor" />{status.label}</span>
                  <span className="text-[11px] text-[var(--text-secondary)]">{executableCount} capability</span>
                  <span className={agent.verification.verified ? 'text-[11px] text-emerald-700' : 'text-[11px] text-[var(--text-tertiary)]'}>{agent.verification.verified ? 'Proof verified' : `Proof ${agent.verification.status}`}</span>
                </div>
              )
            })}
            {agentList?.length === 0 && <p className="p-6 text-center text-[13px] text-[var(--text-tertiary)]">Home сообщил пустой membership исполнителей.</p>}
          </div>
        </details>

        <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-3">Задачи</h2>
        {taskList === null ? (
          <div className="border border-[var(--border-subtle)] rounded-[var(--radius-lg)] p-6 text-center text-[13px] text-[var(--text-tertiary)]">Данные задач недоступны</div>
        ) : (
          <div className="border border-[var(--border-subtle)] rounded-[var(--radius-lg)] overflow-hidden">
            <div className="hidden sm:grid sm:grid-cols-[1fr_140px_120px] gap-2 px-4 py-2.5 bg-[var(--bg-secondary)] text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider border-b border-[var(--border-subtle)]">
              <span>Название</span><span>Исполнитель</span><span>Статус</span>
            </div>
            {recentTasks.map(task => (
              <div key={task.id} className="sm:grid sm:grid-cols-[1fr_140px_120px] gap-2 px-4 py-3 border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-[var(--bg-secondary)]/50 transition-colors">
                <Link to={`/control/tasks/${encodeURIComponent(task.id)}`} title={task.workflow_id} className="block truncate text-[13px] text-[var(--text-primary)] font-medium hover:underline">{task.workflow_id}</Link>
                <span className="text-[12px] text-[var(--text-secondary)]">{task.owner_agent_id || '—'}</span>
                <span className={`inline-flex px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium w-fit ${taskStatus[task.state]?.color || ''}`}>{taskStatus[task.state]?.label || task.state}</span>
              </div>
            ))}
            {recentTasks.length === 0 && <p className="p-6 text-center text-[13px] text-[var(--text-tertiary)]">Home сообщил пустой список задач.</p>}
            {visibleTasks.length > recentTasks.length && <p className="border-t border-[var(--border-subtle)] px-4 py-3 text-center text-[11px] text-[var(--text-tertiary)]">Показаны последние {recentTasks.length} из {visibleTasks.length}. Полный журнал доступен в разделе «События».</p>}
          </div>
        )}
      </div>
    </div>
  )
}
