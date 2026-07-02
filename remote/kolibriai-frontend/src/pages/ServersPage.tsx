import { useState, useEffect, useCallback } from 'react'
import { Server, Circle, Cpu, Wifi, RefreshCw, MoreVertical, RotateCcw, Shield, Power } from 'lucide-react'
import { nodes, type Node } from '@/lib/api'

const statusConfig: Record<string, { color: string; bg: string; label: string }> = {
  healthy: { color: 'text-emerald-600', bg: 'bg-emerald-50', label: 'Healthy' },
  degraded: { color: 'text-amber-600', bg: 'bg-amber-50', label: 'Degraded' },
  draining: { color: 'text-blue-600', bg: 'bg-blue-50', label: 'Draining' },
  quarantined: { color: 'text-orange-600', bg: 'bg-orange-50', label: 'Quarantined' },
  offline: { color: 'text-gray-500', bg: 'bg-gray-100', label: 'Offline' },
}

export default function ServersPage() {
  const [nodeList, setNodeList] = useState<Node[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [menuNode, setMenuNode] = useState<string | null>(null)

  const loadNodes = useCallback(async () => {
    setRefreshing(true)
    try {
      const data = await nodes.list({ page_size: 100 })
      setNodeList(data.items)
    } catch (e) { console.error('Failed to load nodes', e) }
    finally { setLoading(false); setRefreshing(false) }
  }, [])

  useEffect(() => { loadNodes() }, [loadNodes])

  const handleNodeAction = async (nodeId: string, action: 'restart' | 'drain' | 'quarantine') => {
    setMenuNode(null)
    try {
      const statusMap = { restart: 'healthy', drain: 'draining', quarantine: 'quarantined' }
      await nodes.update(nodeId, { status: statusMap[action] })
      loadNodes()
    } catch (e) { console.error('Node action failed', e) }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-full text-[var(--text-tertiary)]">Загрузка...</div>
  }

  const online = nodeList.filter(n => n.status === 'healthy').length
  const activeAgents = nodeList.reduce((s, n) => s + n.agent_count, 0)
  const avgCpu = online > 0 ? Math.round(nodeList.filter(n => n.status === 'healthy').reduce((s, n) => s + parseFloat(n.cpu_percent), 0) / online) : 0
  const avgRam = online > 0 ? Math.round(nodeList.filter(n => n.status === 'healthy').reduce((s, n) => s + parseFloat(n.ram_percent), 0) / online) : 0
  const avgDisk = online > 0 ? Math.round(nodeList.filter(n => n.status === 'healthy').reduce((s, n) => s + parseFloat(n.disk_percent), 0) / online) : 0

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight">Серверы</h1>
          <button onClick={loadNodes} disabled={refreshing} className="h-8 px-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1.5 disabled:opacity-50">
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> Обновить
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Онлайн', value: `${online}/${nodeList.length}`, icon: Server, ok: true },
            { label: 'Агентов', value: activeAgents, icon: Cpu },
            { label: 'Задач', value: nodeList.reduce((s, n) => s + n.task_count, 0), icon: Wifi },
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

        <div className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] mb-6">
          <h3 className="text-[13px] font-medium text-[var(--text-secondary)] mb-3">Ресурсы кластера</h3>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'CPU', value: avgCpu, color: avgCpu > 70 ? 'bg-amber-500' : 'bg-emerald-500' },
              { label: 'RAM', value: avgRam, color: 'bg-[var(--accent-teal)]' },
              { label: 'Disk', value: avgDisk, color: 'bg-[var(--accent-lavender)]' },
            ].map(r => (
              <div key={r.label}>
                <div className="flex justify-between text-[12px] mb-1"><span className="text-[var(--text-secondary)]">{r.label}</span><span className="text-[var(--text-primary)] font-medium">{r.value}%</span></div>
                <div className="w-full h-2 bg-[var(--bg-elevated)] rounded-full overflow-hidden"><div className={`h-full ${r.color} rounded-full transition-all`} style={{ width: `${Math.min(r.value, 100)}%` }} /></div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {nodeList.map(node => {
            const sc = statusConfig[node.status] || statusConfig.offline
            return (
              <div key={node.id} className={`p-4 rounded-[var(--radius-lg)] border transition-all ${node.status === 'offline' ? 'border-gray-200 bg-gray-50/50 opacity-60' : 'border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)]'}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Circle size={7} className={sc.color} fill="currentColor" />
                    <span className="text-[13px] font-medium text-[var(--text-primary)]">{node.name}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${sc.bg} ${sc.color}`}>{sc.label}</span>
                    <div className="relative">
                      <button onClick={() => setMenuNode(menuNode === node.id ? null : node.id)} className="w-6 h-6 flex items-center justify-center rounded hover:bg-[var(--bg-hover)] transition-colors">
                        <MoreVertical size={14} className="text-[var(--text-tertiary)]" />
                      </button>
                      {menuNode === node.id && (
                        <>
                          <div className="fixed inset-0 z-40" onClick={() => setMenuNode(null)} />
                          <div className="absolute right-0 top-8 z-50 w-44 bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-[var(--radius-lg)] shadow-lg py-1">
                            <button onClick={() => handleNodeAction(node.id, 'restart')} className="w-full flex items-center gap-2 px-3 py-2 text-[12px] text-[var(--text-primary)] hover:bg-[var(--bg-hover)]">
                              <RotateCcw size={13} /> Перезапустить
                            </button>
                            <button onClick={() => handleNodeAction(node.id, 'drain')} className="w-full flex items-center gap-2 px-3 py-2 text-[12px] text-[var(--text-primary)] hover:bg-[var(--bg-hover)]">
                              <Power size={13} /> Выгрузить
                            </button>
                            <button onClick={() => handleNodeAction(node.id, 'quarantine')} className="w-full flex items-center gap-2 px-3 py-2 text-[12px] text-[var(--text-primary)] hover:bg-[var(--bg-hover)]">
                              <Shield size={13} /> Карантин
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="space-y-2 mb-3">
                  {[
                    { label: 'CPU', value: parseFloat(node.cpu_percent) },
                    { label: 'RAM', value: parseFloat(node.ram_percent) },
                    { label: 'Disk', value: parseFloat(node.disk_percent) },
                    { label: 'Net', value: node.ping_ms, unit: 'ms' },
                  ].map(m => (
                    <div key={m.label} className="flex items-center gap-2">
                      <span className="text-[11px] text-[var(--text-tertiary)] w-8">{m.label}</span>
                      <div className="flex-1 h-1.5 bg-[var(--bg-elevated)] rounded-full overflow-hidden">
                        <div className="h-full bg-[var(--accent-teal)] rounded-full opacity-70" style={{ width: `${Math.min(m.unit ? m.value : m.value, 100)}%` }} />
                      </div>
                      <span className="text-[10px] text-[var(--text-secondary)] w-8 text-right">{m.unit ? `${m.value}${m.unit}` : `${m.value}%`}</span>
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-between text-[11px] text-[var(--text-tertiary)] pt-2 border-t border-[var(--border-subtle)]">
                  <span>{node.agent_count} агентов</span>
                  <span>{node.task_count} задач</span>
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
