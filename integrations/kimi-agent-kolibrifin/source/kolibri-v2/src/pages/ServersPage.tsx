import { Server, Circle, Cpu, HardDrive, Wifi } from 'lucide-react'

const nodes = Array.from({ length: 20 }, (_, i) => {
  const id = i + 1
  const regions = ['msk', 'spb', 'nsk', 'kzn']
  const statuses = ['healthy', 'healthy', 'healthy', 'healthy', 'healthy', 'healthy', 'healthy', 'degraded', 'degraded', 'offline']
  const status = statuses[i] || 'healthy'
  const seed = id * 13 + 7
  return {
    id: `node-${String(id).padStart(2, '0')}`,
    region: regions[i % 4],
    status,
    cpu: (seed * 17) % 85 + 10,
    ram: (seed * 31) % 70 + 20,
    disk: (seed * 7) % 60 + 30,
    agents: (seed * 3) % 15 + (status === 'healthy' ? 5 : 0),
    tasks: (seed * 5) % 30,
    ping: (seed * 2) % 100 + 5,
  }
})

const statusConfig: Record<string, { color: string; bg: string; label: string }> = {
  healthy: { color: 'text-emerald-600', bg: 'bg-emerald-50', label: 'Healthy' },
  degraded: { color: 'text-amber-600', bg: 'bg-amber-50', label: 'Degraded' },
  offline: { color: 'text-gray-500', bg: 'bg-gray-100', label: 'Offline' },
}

export default function ServersPage() {
  const online = nodes.filter(n => n.status === 'healthy').length
  const activeAgents = nodes.reduce((s, n) => s + n.agents, 0)
  const avgCpu = Math.round(nodes.filter(n => n.status === 'healthy').reduce((s, n) => s + n.cpu, 0) / online)

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-6">
        <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight mb-6">Серверы</h1>

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Онлайн', value: `${online}/20`, icon: Server, ok: true },
            { label: 'Агентов', value: activeAgents, icon: Cpu },
            { label: 'Задач', value: nodes.reduce((s, n) => s + n.tasks, 0), icon: Wifi },
            { label: 'CPU средн.', value: `${avgCpu}%`, icon: Cpu, warn: avgCpu > 60 },
          ].map(s => (
            <div key={s.label} className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
              <div className="flex items-center gap-2 mb-2">
                <s.icon size={14} strokeWidth={1.8} className={s.ok ? 'text-emerald-500' : s.warn ? 'text-amber-500' : 'text-[var(--text-tertiary)]'} />
                <span className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider">{s.label}</span>
              </div>
              <p className={`text-[22px] font-semibold ${s.ok ? 'text-emerald-600' : s.warn ? 'text-amber-600' : 'text-[var(--text-primary)]'}`}>{s.value}</p>
            </div>
          ))}
        </div>

        {/* Overall Resources */}
        <div className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] mb-6">
          <h3 className="text-[13px] font-medium text-[var(--text-secondary)] mb-3">Ресурсы кластера</h3>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'CPU', value: avgCpu, color: avgCpu > 70 ? 'bg-amber-500' : avgCpu > 85 ? 'bg-red-500' : 'bg-emerald-500' },
              { label: 'RAM', value: Math.round(nodes.filter(n => n.status === 'healthy').reduce((s, n) => s + n.ram, 0) / online), color: 'bg-[var(--accent-teal)]' },
              { label: 'Disk', value: Math.round(nodes.filter(n => n.status === 'healthy').reduce((s, n) => s + n.disk, 0) / online), color: 'bg-[var(--accent-lavender)]' },
            ].map(r => (
              <div key={r.label}>
                <div className="flex justify-between text-[12px] mb-1"><span className="text-[var(--text-secondary)]">{r.label}</span><span className="text-[var(--text-primary)] font-medium">{r.value}%</span></div>
                <div className="w-full h-2 bg-[var(--bg-elevated)] rounded-full overflow-hidden"><div className={`h-full ${r.color} rounded-full transition-all`} style={{ width: `${Math.min(r.value, 100)}%` }} /></div>
              </div>
            ))}
          </div>
        </div>

        {/* Nodes Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {nodes.map(node => {
            const sc = statusConfig[node.status]
            return (
              <div key={node.id} className={`p-4 rounded-[var(--radius-lg)] border transition-all ${node.status === 'offline' ? 'border-gray-200 bg-gray-50/50 opacity-60' : 'border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)]'}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Circle size={7} className={sc.color} fill="currentColor" />
                    <span className="text-[13px] font-medium text-[var(--text-primary)]">{node.id}</span>
                  </div>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${sc.bg} ${sc.color}`}>{sc.label}</span>
                </div>
                <div className="space-y-2 mb-3">
                  {[
                    { label: 'CPU', value: node.cpu },
                    { label: 'RAM', value: node.ram },
                    { label: 'Disk', value: node.disk },
                    { label: 'Net', value: node.ping, unit: 'ms' },
                  ].map(m => (
                    <div key={m.label} className="flex items-center gap-2">
                      <span className="text-[11px] text-[var(--text-tertiary)] w-8">{m.label}</span>
                      <div className="flex-1 h-1.5 bg-[var(--bg-elevated)] rounded-full overflow-hidden">
                        <div className="h-full bg-[var(--accent-teal)] rounded-full opacity-70" style={{ width: `${Math.min(m.value, 100)}%` }} />
                      </div>
                      <span className="text-[10px] text-[var(--text-secondary)] w-8 text-right">{m.unit ? `${m.value}${m.unit}` : `${m.value}%`}</span>
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-between text-[11px] text-[var(--text-tertiary)] pt-2 border-t border-[var(--border-subtle)]">
                  <span>{node.agents} агентов</span>
                  <span>{node.tasks} задач</span>
                  <span className="uppercase">{node.region}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
