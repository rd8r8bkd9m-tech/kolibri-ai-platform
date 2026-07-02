import { useState, useEffect } from 'react'
import { Bot, Activity, Circle, ChevronDown, Play, Pause, RotateCcw, Plus, Trash2 } from 'lucide-react'
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
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newRole, setNewRole] = useState('')
  const [newModel, setNewModel] = useState('')

  useEffect(() => {
    Promise.all([
      agents.list({ page_size: 50 }),
      tasks.list({ page_size: 50 }),
    ]).then(([a, t]) => {
      setAgentList(a.items)
      setTaskList(t.items)
    }).catch(e => console.error('Failed to load agents/tasks', e))
    .finally(() => setLoading(false))
  }, [])

  const handleToggleAgent = async (agent: Agent) => {
    const newStatus = agent.status === 'active' ? 'paused' : 'active'
    try {
      await agents.update(agent.id, { status: newStatus })
      setAgentList(prev => prev.map(a => a.id === agent.id ? { ...a, status: newStatus } : a))
    } catch (e) { console.error('Failed to update agent', e) }
  }

  const handleRestartAgent = async (agent: Agent) => {
    try {
      await agents.update(agent.id, { status: 'active', progress: 0 })
      setAgentList(prev => prev.map(a => a.id === agent.id ? { ...a, status: 'active', progress: 0 } : a))
    } catch (e) { console.error('Failed to restart agent', e) }
  }

  const handleCancelTask = async (task: Task) => {
    try {
      await tasks.update(task.id, { state: 'cancelled' })
      setTaskList(prev => prev.map(t => t.id === task.id ? { ...t, state: 'cancelled' } : t))
    } catch (e) { console.error('Failed to cancel task', e) }
  }

  const handleCreateAgent = async () => {
    if (!newName.trim()) return
    try {
      const created = await agents.create({ name: newName, role: newRole, model: newModel || undefined })
      setAgentList(prev => [...prev, created])
      setShowCreate(false)
      setNewName(''); setNewRole(''); setNewModel('')
    } catch (e) { console.error('Failed to create agent', e) }
  }

  const handleDeleteAgent = async (agent: Agent) => {
    try {
      await agents.delete(agent.id)
      setAgentList(prev => prev.filter(a => a.id !== agent.id))
    } catch (e) { console.error('Failed to delete agent', e) }
  }

  const activeCount = agentList.filter(a => a.status === 'active').length

  if (loading) {
    return <div className="flex items-center justify-center h-full text-[var(--text-tertiary)]">Загрузка...</div>
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight">Агенты и задачи</h1>
          <button onClick={() => setShowCreate(true)} className="h-9 px-3 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors flex items-center gap-1.5">
            <Plus size={15} /> <span className="hidden sm:inline">Новый агент</span>
          </button>
        </div>

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
              <div className="flex gap-1 mt-2">
                <button onClick={() => handleToggleAgent(agent)} className="h-7 px-2 rounded-[var(--radius-sm)] border border-[var(--border-subtle)] text-[11px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1">
                  {agent.status === 'active' ? <><Pause size={11} /> Пауза</> : <><Play size={11} /> Старт</>}
                </button>
                <button onClick={() => handleRestartAgent(agent)} className="h-7 px-2 rounded-[var(--radius-sm)] border border-[var(--border-subtle)] text-[11px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1"><RotateCcw size={11} /> Перезапуск</button>
                <button onClick={() => handleDeleteAgent(agent)} className="h-7 px-2 rounded-[var(--radius-sm)] border border-[var(--border-subtle)] text-[11px] text-[var(--text-tertiary)] hover:bg-red-50 hover:text-red-500 hover:border-red-200 transition-colors flex items-center gap-1"><Trash2 size={11} /></button>
              </div>
            </div>
          ))}
        </div>

        <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-3">Задачи</h2>
        <div className="border border-[var(--border-subtle)] rounded-[var(--radius-lg)] overflow-hidden">
          <div className="hidden sm:grid sm:grid-cols-[1fr_140px_120px_100px] gap-2 px-4 py-2.5 bg-[var(--bg-secondary)] text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider border-b border-[var(--border-subtle)]">
            <span>Название</span><span>Агент</span><span>Статус</span><span className="text-right">Действия</span>
          </div>
          {taskList.map(task => (
            <div key={task.id} className="sm:grid sm:grid-cols-[1fr_140px_120px_100px] gap-2 px-4 py-3 border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-[var(--bg-secondary)]/50 transition-colors">
              <span className="text-[13px] text-[var(--text-primary)] font-medium">{task.workflow_id}</span>
              <span className="text-[12px] text-[var(--text-secondary)]">{task.owner_agent_id || '—'}</span>
              <span className={`inline-flex px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium w-fit ${taskStatus[task.state]?.color || ''}`}>{taskStatus[task.state]?.label || task.state}</span>
              <div className="flex justify-end gap-1">
                <button onClick={() => handleCancelTask(task)} className="w-7 h-7 flex items-center justify-center rounded-[var(--radius-sm)] text-[var(--text-tertiary)] hover:bg-[var(--bg-hover)] transition-colors"><Pause size={13} /></button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Create agent modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" onClick={() => setShowCreate(false)}>
          <div className="bg-[var(--bg-primary)] rounded-[var(--radius-xl)] shadow-xl max-w-[400px] w-full p-6" onClick={e => e.stopPropagation()}>
            <h2 className="text-[18px] font-semibold text-[var(--text-primary)] mb-4">Новый агент</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-[12px] text-[var(--text-tertiary)] mb-1">Имя</label>
                <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Название агента" className="w-full h-9 px-3 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] outline-none focus:border-[var(--accent-teal)]" />
              </div>
              <div>
                <label className="block text-[12px] text-[var(--text-tertiary)] mb-1">Роль</label>
                <input value={newRole} onChange={e => setNewRole(e.target.value)} placeholder="estimate_analyst, document_writer..." className="w-full h-9 px-3 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] outline-none focus:border-[var(--accent-teal)]" />
              </div>
              <div>
                <label className="block text-[12px] text-[var(--text-tertiary)] mb-1">Модель</label>
                <input value={newModel} onChange={e => setNewModel(e.target.value)} placeholder="gpt-4, claude, kimi..." className="w-full h-9 px-3 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-[var(--radius-md)] text-[13px] outline-none focus:border-[var(--accent-teal)]" />
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <button onClick={handleCreateAgent} disabled={!newName.trim()} className="flex-1 h-9 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[13px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors disabled:opacity-50">Создать</button>
              <button onClick={() => setShowCreate(false)} className="h-9 px-3 rounded-[var(--radius-md)] text-[13px] text-[var(--text-tertiary)] hover:bg-[var(--bg-hover)] transition-colors">Отмена</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
