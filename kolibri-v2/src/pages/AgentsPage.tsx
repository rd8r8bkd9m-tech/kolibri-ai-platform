import { useState, useEffect } from 'react'
import { Bot, Activity, Circle, ChevronDown, Play } from 'lucide-react'
import { agents, tasks, type Agent, type Task } from '@/lib/api'

const statusConfig: Record<string, { color: string; label: string }> = {
  active: { color: 'bg-emerald-500', label: 'Активен' },
  idle: { color: 'bg-gray-400', label: 'Ожидает' },
  paused: { color: 'bg-amber-500', label: 'Пауза' },
  error: { color: 'bg-red-500', label: 'Ошибка' },
}

const taskStatus: Record<string, { color: string; label: string }> = {
  running: { color: 'text-emerald-600 bg-emerald-50', label: 'Выполняется' },
  queued: { color: 'text-gray-600 bg-gray-100', label: 'В очереди' },
  completed: { color: 'text-blue-600 bg-blue-50', label: 'Завершено' },
  failed: { color: 'text-red-600 bg-red-50', label: 'Ошибка' },
  created: { color: 'text-gray-500 bg-gray-50', label: 'Создана' },
  assigned: { color: 'text-purple-600 bg-purple-50', label: 'Назначена' },
  waiting: { color: 'text-amber-600 bg-amber-50', label: 'Ожидание' },
  cancelled: { color: 'text-gray-400 bg-gray-50', label: 'Отменена' },
}

export default function AgentsPage() {
  const [agentList, setAgentList] = useState<Agent[]>([])
  const [taskList, setTaskList] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      agents.list({ page_size: 50 }),
      tasks.list({ page_size: 50 }),
    ]).then(([a, t]) => {
      setAgentList(a.items)
      setTaskList(t.items)
    }).catch(e => {
      console.error('Failed to load agents/tasks', e)
      setLoadError('Данные Home Control Plane временно недоступны')
    })
    .finally(() => setLoading(false))
  }, [])

  const activeCount = agentList.filter(a => a.status === 'active').length

  if (loading) {
    return <div className="flex items-center justify-center h-full text-[var(--text-tertiary)]">Загрузка...</div>
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-6">
        <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight mb-6">Агенты и задачи</h1>

        {loadError && (
          <div className="mb-6 rounded-[var(--radius-lg)] border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
            {loadError}. Неподтверждённые агенты и задачи не показываются.
          </div>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Всего агентов', value: agentList.length, icon: Bot },
            { label: 'Активные', value: activeCount, icon: Activity, accent: true },
            { label: 'Выполняется задач', value: taskList.filter(t => t.state === 'running').length, icon: Play },
            { label: 'В очереди', value: taskList.filter(t => t.state === 'queued').length, icon: ChevronDown },
          ].map(stat => (
            <div key={stat.label} className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
              <div className="flex items-center gap-2 mb-2">
                <stat.icon size={14} className={stat.accent ? 'text-[var(--accent-teal)]' : 'text-[var(--text-tertiary)]'} strokeWidth={1.8} />
                <span className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider">{stat.label}</span>
              </div>
              <p className={`text-[22px] font-semibold ${stat.accent ? 'text-[var(--accent-teal)]' : 'text-[var(--text-primary)]'}`}>{stat.value}</p>
            </div>
          ))}
        </div>

        <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-3">Агенты</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-8">
          {agentList.map(agent => (
            <div key={agent.id} className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)] transition-all">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-[var(--radius-md)] bg-[var(--accent-teal)]/10 text-[var(--accent-teal)] flex items-center justify-center">
                    <Bot size={16} strokeWidth={1.8} />
                  </div>
                  <div>
                    <h3 className="text-[13px] font-medium text-[var(--text-primary)]">{agent.name}</h3>
                    <p className="text-[11px] text-[var(--text-tertiary)]">{agent.model || '—'} · {agent.node_id || '—'}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <Circle size={6} className={statusConfig[agent.status]?.color || 'bg-gray-400'} fill="currentColor" />
                  <span className="text-[11px] text-[var(--text-tertiary)]">{statusConfig[agent.status]?.label || agent.status}</span>
                </div>
              </div>
              {agent.current_task && (
                <div className="mb-2">
                  <p className="text-[12px] text-[var(--text-secondary)] truncate">{agent.current_task}</p>
                  <div className="w-full h-1.5 bg-[var(--bg-elevated)] rounded-full mt-1.5 overflow-hidden">
                    <div className="h-full bg-[var(--accent-teal)] rounded-full transition-all" style={{ width: `${agent.progress}%` }} />
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-3">Задачи</h2>
        <div className="border border-[var(--border-subtle)] rounded-[var(--radius-lg)] overflow-hidden">
          <div className="hidden sm:grid sm:grid-cols-[1fr_140px_120px] gap-2 px-4 py-2.5 bg-[var(--bg-secondary)] text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider border-b border-[var(--border-subtle)]">
            <span>Название</span><span>Агент</span><span>Статус</span>
          </div>
          {taskList.map(task => (
            <div key={task.id} className="sm:grid sm:grid-cols-[1fr_140px_120px] gap-2 px-4 py-3 border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-[var(--bg-secondary)]/50 transition-colors">
              <span className="text-[13px] text-[var(--text-primary)] font-medium">{task.workflow_id}</span>
              <span className="text-[12px] text-[var(--text-secondary)]">{task.owner_agent_id || '—'}</span>
              <span className={`inline-flex px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium w-fit ${taskStatus[task.state]?.color || ''}`}>{taskStatus[task.state]?.label || task.state}</span>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}
