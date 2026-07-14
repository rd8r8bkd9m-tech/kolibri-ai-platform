import { useEffect, useState } from 'react'
import { Activity, Bot, ChevronDown, Circle, Play, ShieldCheck } from 'lucide-react'
import { agents, tasks, type Agent, type Task } from '@/lib/api'
import { evidenceLines, summarizeAgents } from '@/features/factory/factoryTruth'

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
  const stats = [
    { label: 'Membership hosts', value: valueOrUnknown(agentSummary?.membership), icon: Bot },
    { label: 'Исполнимые', value: valueOrUnknown(agentSummary?.executable), icon: Activity },
    { label: 'С активной задачей', value: valueOrUnknown(agentSummary?.active), icon: Play },
    { label: 'Проверенный результат', value: valueOrUnknown(agentSummary?.verified), icon: ShieldCheck, verified: true },
    { label: 'Выполняется задач', value: taskList ? visibleTasks.filter(task => task.state === 'running').length : '—', icon: Play },
    { label: 'В очереди', value: taskList ? visibleTasks.filter(task => task.state === 'queued').length : '—', icon: ChevronDown },
  ]

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-6">
        <div className="mb-6">
          <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight">Исполнители и задачи</h1>
          <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">Agent Host membership не считается работающим исполнителем без capability и proof</p>
        </div>

        {loadErrors.length > 0 && (
          <div className="mb-6 rounded-[var(--radius-lg)] border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
            Home Control Plane не вернул: {loadErrors.join(', ')}. Неизвестные значения показаны как «—», а не как ноль.
          </div>
        )}

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

        <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-3">Agent Hosts</h2>
        {agentList?.length === 0 && (
          <div className="mb-8 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 text-center text-[13px] text-[var(--text-tertiary)]">Home сообщил пустой membership исполнителей.</div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-8">
          {(agentList ?? []).map(agent => {
            const status = statusConfig[agent.status] ?? statusConfig.error
            const capabilities = agent.capabilities.execution ?? []
            const evidence = agent.verification.last_successful_task
            return (
              <article key={agent.id} className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)] transition-all">
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-8 h-8 rounded-[var(--radius-md)] bg-[var(--accent-teal)]/10 text-[var(--accent-teal)] flex items-center justify-center shrink-0">
                      <Bot size={16} strokeWidth={1.8} />
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-[13px] font-medium text-[var(--text-primary)] truncate">{agent.name}</h3>
                      <p className="text-[11px] text-[var(--text-tertiary)] truncate">{agent.node_id || 'node —'}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Circle size={7} className={status.color} fill="currentColor" />
                    <span className="text-[10px] text-[var(--text-tertiary)]">{status.label}</span>
                  </div>
                </div>

                <div className="flex flex-wrap gap-1.5 mb-3 text-[10px]">
                  <span className={`rounded-full border px-2 py-1 ${agent.connection.connected ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-amber-200 bg-amber-50 text-amber-700'}`}>{agent.connection.connected ? 'Связь online' : 'Связь не доказана'}</span>
                  <span className={`rounded-full border px-2 py-1 ${agent.freshness.fresh ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-amber-200 bg-amber-50 text-amber-700'}`}>{agent.freshness.fresh ? 'Heartbeat свежий' : `Heartbeat ${agent.freshness.status}`}</span>
                  {agent.execution.executable && <span className="rounded-full border border-violet-200 bg-violet-50 px-2 py-1 text-violet-700">Capability исполнима</span>}
                  {agent.verification.verified
                    ? <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-1 text-emerald-700">Proof verified</span>
                    : <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 py-1 text-[var(--text-tertiary)]">Proof {agent.verification.status}</span>}
                </div>

                {agent.current_task && (
                  <div className="mb-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] p-2.5">
                    <p className="text-[10px] uppercase tracking-wider text-[var(--text-tertiary)] mb-1">Активная задача</p>
                    <p className="text-[12px] text-[var(--text-secondary)] truncate" title={agent.current_task}>{agent.current_task}</p>
                    {typeof agent.progress === 'number' && (
                      <div className="w-full h-1.5 bg-[var(--bg-elevated)] rounded-full mt-1.5 overflow-hidden">
                        <div className="h-full bg-[var(--accent-teal)] rounded-full transition-all" style={{ width: `${Math.min(Math.max(agent.progress, 0), 100)}%` }} />
                      </div>
                    )}
                  </div>
                )}

                <div className="space-y-1.5 mb-3">
                  <p className="text-[10px] uppercase tracking-wider text-[var(--text-tertiary)]">Capability execution</p>
                  {capabilities.length ? capabilities.map(capability => (
                    <div key={capability.name} className="flex items-center justify-between gap-2 text-[11px]">
                      <span className="truncate text-[var(--text-secondary)]" title={capability.name}>{capability.name}</span>
                      <span className={capability.executable ? 'text-violet-700' : 'text-[var(--text-tertiary)]'}>{capability.executable ? 'готово' : capability.runner_status || 'не доказано'}</span>
                    </div>
                  )) : <p className="text-[11px] text-[var(--text-tertiary)]">Capability не заявлены</p>}
                </div>

                <div className="border-t border-[var(--border-subtle)] pt-3">
                  <p className="text-[10px] uppercase tracking-wider text-[var(--text-tertiary)] mb-1.5">Последний строгий proof</p>
                  {evidence ? (
                    <div className="space-y-1 text-[11px]">
                      <p className="truncate text-[var(--text-primary)]" title={evidence.task_id}>{evidence.task_id}</p>
                      {evidenceLines(evidence).map(line => (
                        <div key={line.label} className="flex justify-between gap-2">
                          <span className="text-[var(--text-tertiary)]">{line.label}</span>
                          <code className="text-[10px] text-[var(--text-secondary)]" title={line.raw}>{line.value}</code>
                        </div>
                      ))}
                    </div>
                  ) : <p className="text-[11px] text-[var(--text-tertiary)]">{agent.verification.status === 'unavailable' ? 'Fleet proof недоступен' : 'Проверенного результата нет'}</p>}
                </div>
              </article>
            )
          })}
        </div>

        <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-3">Задачи</h2>
        {taskList === null ? (
          <div className="border border-[var(--border-subtle)] rounded-[var(--radius-lg)] p-6 text-center text-[13px] text-[var(--text-tertiary)]">Данные задач недоступны</div>
        ) : (
          <div className="border border-[var(--border-subtle)] rounded-[var(--radius-lg)] overflow-hidden">
            <div className="hidden sm:grid sm:grid-cols-[1fr_140px_120px] gap-2 px-4 py-2.5 bg-[var(--bg-secondary)] text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider border-b border-[var(--border-subtle)]">
              <span>Название</span><span>Исполнитель</span><span>Статус</span>
            </div>
            {visibleTasks.map(task => (
              <div key={task.id} className="sm:grid sm:grid-cols-[1fr_140px_120px] gap-2 px-4 py-3 border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-[var(--bg-secondary)]/50 transition-colors">
                <span className="text-[13px] text-[var(--text-primary)] font-medium">{task.workflow_id}</span>
                <span className="text-[12px] text-[var(--text-secondary)]">{task.owner_agent_id || '—'}</span>
                <span className={`inline-flex px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium w-fit ${taskStatus[task.state]?.color || ''}`}>{taskStatus[task.state]?.label || task.state}</span>
              </div>
            ))}
            {visibleTasks.length === 0 && <p className="p-6 text-center text-[13px] text-[var(--text-tertiary)]">Home сообщил пустой список задач.</p>}
          </div>
        )}
      </div>
    </div>
  )
}
