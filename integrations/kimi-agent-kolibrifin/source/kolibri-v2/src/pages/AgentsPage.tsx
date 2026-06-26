import { Bot, Activity, Circle, ChevronDown, Play, Pause, RotateCcw } from 'lucide-react'

const agents = [
  { id: 'a1', name: 'Сметчик-аналитик', role: 'estimate', status: 'active', task: 'Смета на электромонтаж', progress: 78, model: 'Kimi K2.6', node: 'node-01' },
  { id: 'a2', name: 'Документолог', role: 'document', status: 'active', task: 'Договор подряда', progress: 45, model: 'Kimi K2.6', node: 'node-02' },
  { id: 'a3', name: 'Code Reviewer', role: 'code', status: 'idle', task: null, progress: 0, model: 'MiMo', node: 'node-03' },
  { id: 'a4', name: 'Тестировщик', role: 'test', status: 'active', task: 'Golden tests', progress: 92, model: 'Kimi K2.6', node: 'node-01' },
  { id: 'a5', name: 'DevOps агент', role: 'devops', status: 'paused', task: 'Deploy staging', progress: 30, model: 'Qwen', node: 'node-04' },
  { id: 'a6', name: 'FormulaLM Trainer', role: 'ml', status: 'active', task: 'Fine-tune checkpoint', progress: 15, model: 'MiMo', node: 'node-05' },
]

const tasks = [
  { id: 't1', name: 'Смета на электромонтаж', agent: 'Сметчик-аналитик', status: 'running', priority: 'high' },
  { id: 't2', name: 'Договор подряда №45', agent: 'Документолог', status: 'running', priority: 'high' },
  { id: 't3', name: 'Golden estimate tests', agent: 'Тестировщик', status: 'running', priority: 'medium' },
  { id: 't4', name: 'Deploy to staging', agent: 'DevOps агент', status: 'queued', priority: 'low' },
  { id: 't5', name: 'FormulaLM checkpoint v3', agent: 'FormulaLM Trainer', status: 'running', priority: 'medium' },
  { id: 't6', name: 'Code review PR #128', agent: 'Code Reviewer', status: 'completed', priority: 'medium' },
]

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
}

export default function AgentsPage() {
  const activeCount = agents.filter(a => a.status === 'active').length

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-6">
        <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight mb-6">Агенты и задачи</h1>

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Всего агентов', value: agents.length, icon: Bot },
            { label: 'Активные', value: activeCount, icon: Activity, accent: true },
            { label: 'Выполняется задач', value: tasks.filter(t => t.status === 'running').length, icon: Play },
            { label: 'В очереди', value: tasks.filter(t => t.status === 'queued').length, icon: ChevronDown },
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

        {/* Agents Grid */}
        <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-3">Агенты</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-8">
          {agents.map(agent => (
            <div key={agent.id} className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)] transition-all">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-[var(--radius-md)] bg-[var(--accent-teal)]/10 text-[var(--accent-teal)] flex items-center justify-center">
                    <Bot size={16} strokeWidth={1.8} />
                  </div>
                  <div>
                    <h3 className="text-[13px] font-medium text-[var(--text-primary)]">{agent.name}</h3>
                    <p className="text-[11px] text-[var(--text-tertiary)]">{agent.model} · {agent.node}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <Circle size={6} className={statusConfig[agent.status]?.color} fill="currentColor" />
                  <span className="text-[11px] text-[var(--text-tertiary)]">{statusConfig[agent.status]?.label}</span>
                </div>
              </div>
              {agent.task && (
                <div className="mb-2">
                  <p className="text-[12px] text-[var(--text-secondary)] truncate">{agent.task}</p>
                  <div className="w-full h-1.5 bg-[var(--bg-elevated)] rounded-full mt-1.5 overflow-hidden">
                    <div className="h-full bg-[var(--accent-teal)] rounded-full transition-all" style={{ width: `${agent.progress}%` }} />
                  </div>
                </div>
              )}
              <div className="flex gap-1 mt-2">
                <button className="h-7 px-2 rounded-[var(--radius-sm)] border border-[var(--border-subtle)] text-[11px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1"><Pause size={11} /> Пауза</button>
                <button className="h-7 px-2 rounded-[var(--radius-sm)] border border-[var(--border-subtle)] text-[11px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1"><RotateCcw size={11} /> Перезапуск</button>
              </div>
            </div>
          ))}
        </div>

        {/* Tasks Table */}
        <h2 className="text-[16px] font-semibold text-[var(--text-primary)] mb-3">Задачи</h2>
        <div className="border border-[var(--border-subtle)] rounded-[var(--radius-lg)] overflow-hidden">
          <div className="hidden sm:grid sm:grid-cols-[1fr_140px_120px_100px] gap-2 px-4 py-2.5 bg-[var(--bg-secondary)] text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider border-b border-[var(--border-subtle)]">
            <span>Название</span><span>Агент</span><span>Статус</span><span className="text-right">Действия</span>
          </div>
          {tasks.map(task => (
            <div key={task.id} className="sm:grid sm:grid-cols-[1fr_140px_120px_100px] gap-2 px-4 py-3 border-b border-[var(--border-subtle)] last:border-0 items-center hover:bg-[var(--bg-secondary)]/50 transition-colors">
              <span className="text-[13px] text-[var(--text-primary)] font-medium">{task.name}</span>
              <span className="text-[12px] text-[var(--text-secondary)]">{task.agent}</span>
              <span className={`inline-flex px-2 py-0.5 rounded-[var(--radius-pill)] text-[11px] font-medium w-fit ${taskStatus[task.status]?.color || ''}`}>{taskStatus[task.status]?.label}</span>
              <div className="flex justify-end gap-1">
                <button className="w-7 h-7 flex items-center justify-center rounded-[var(--radius-sm)] text-[var(--text-tertiary)] hover:bg-[var(--bg-hover)] transition-colors"><Pause size={13} /></button>
                <button className="w-7 h-7 flex items-center justify-center rounded-[var(--radius-sm)] text-[var(--text-tertiary)] hover:bg-[var(--bg-hover)] transition-colors"><RotateCcw size={13} /></button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
