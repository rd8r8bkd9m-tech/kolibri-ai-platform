import { useCallback, useEffect, useState } from 'react'
import { Activity, Cpu, RefreshCw, Server, ShieldAlert, ShieldCheck, Wifi } from 'lucide-react'
import { nodes, type FactoryListTruth, type Node } from '@/lib/api'
import {
  evidenceLines,
  freshResourceNodes,
  nodeTruthBadges,
  summarizeNodes,
  type TruthBadge,
} from '@/features/factory/factoryTruth'
import ControlCenterNav from '@/features/factory/ControlCenterNav'

const toneClass: Record<TruthBadge['tone'], string> = {
  neutral: 'border-[var(--border-subtle)] text-[var(--text-tertiary)] bg-[var(--bg-secondary)]',
  info: 'border-blue-200 text-blue-700 bg-blue-50',
  active: 'border-violet-200 text-violet-700 bg-violet-50',
  verified: 'border-emerald-200 text-emerald-700 bg-emerald-50',
  warning: 'border-amber-200 text-amber-700 bg-amber-50',
  danger: 'border-red-200 text-red-700 bg-red-50',
}

function metric(value: string | number): number | null {
  const parsed = typeof value === 'number' ? value : Number.parseFloat(value)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null
}

function average(values: Array<number | null>): number | null {
  const available = values.filter((value): value is number => value !== null)
  return available.length
    ? Math.round(available.reduce((sum, value) => sum + value, 0) / available.length)
    : null
}

export default function ServersPage() {
  const [nodeList, setNodeList] = useState<Node[] | null>(null)
  const [totalCount, setTotalCount] = useState<number | null>(null)
  const [listTruth, setListTruth] = useState<FactoryListTruth | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const applyResult = useCallback((data: Awaited<ReturnType<typeof nodes.list>>) => {
    setNodeList(data.items)
    setTotalCount(data.total)
    setListTruth(data.truth ?? null)
  }, [])

  const loadNodes = useCallback(async () => {
    setRefreshing(true)
    setLoadError(null)
    try {
      applyResult(await nodes.list({ page_size: 100 }))
    } catch (error) {
      console.error('Failed to load nodes', error)
      setLoadError('Данные Home Control Plane временно недоступны')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [applyResult])

  useEffect(() => {
    let active = true
    void nodes.list({ page_size: 100 })
      .then(data => {
        if (active) applyResult(data)
      })
      .catch(error => {
        if (!active) return
        console.error('Failed to load nodes', error)
        setLoadError('Данные Home Control Plane временно недоступны')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [applyResult])

  if (loading) {
    return <div className="flex items-center justify-center h-full text-[var(--text-tertiary)]">Загрузка...</div>
  }

  const dataAvailable = nodeList !== null
  const items = nodeList ?? []
  const summary = dataAvailable ? summarizeNodes(items) : null
  const canonicalTotal = typeof listTruth?.membership?.canonical_total === 'number'
    ? listTruth.membership.canonical_total
    : totalCount
  const fullPage = dataAvailable && totalCount === items.length
  const ratio = (value: number | undefined) => {
    if (value === undefined || !dataAvailable) return '—'
    if (fullPage && canonicalTotal !== null) return `${value}/${canonicalTotal}`
    return `${value}/${items.length} показ.`
  }

  const resourceNodes = freshResourceNodes(items)
  const avgCpu = average(resourceNodes.map(node => metric(node.cpu_percent)))
  const avgRam = average(resourceNodes.map(node => metric(node.ram_percent)))
  const avgDisk = average(resourceNodes.map(node => metric(node.disk_percent)))

  const stats = [
    { label: 'Membership', value: dataAvailable ? canonicalTotal ?? items.length : '—', icon: Server },
    { label: 'Связь online', value: ratio(summary?.connected), icon: Wifi },
    { label: 'Свежие', value: ratio(summary?.fresh), icon: Activity },
    { label: 'Исполнимые', value: ratio(summary?.executable), icon: Cpu },
    { label: 'С активной задачей', value: ratio(summary?.active), icon: Activity },
    { label: 'Проверенный результат', value: ratio(summary?.verified), icon: ShieldCheck, verified: true },
    { label: 'Заблокированы', value: summary ? summary.blocked : '—', icon: ShieldAlert, danger: Boolean(summary?.blocked) },
    { label: 'Карантин', value: summary ? summary.quarantined : '—', icon: ShieldAlert, danger: Boolean(summary?.quarantined) },
  ]

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-6">
        <ControlCenterNav />
        <div className="flex items-start justify-between gap-4 mb-6">
          <div>
            <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight">Серверы</h1>
            <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">
              Membership, связь, свежесть, исполнение и доказательство показаны отдельно
              {listTruth?.as_of ? ` · ${new Date(listTruth.as_of).toLocaleString('ru-RU')}` : ''}
            </p>
          </div>
          <button onClick={loadNodes} disabled={refreshing} className="h-9 px-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors flex items-center gap-1.5 disabled:opacity-50">
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> Обновить
          </button>
        </div>

        {loadError && (
          <div className="mb-6 rounded-[var(--radius-lg)] border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
            {loadError}. Последние полученные значения сохранены; отсутствующие значения не заменены нулями.
          </div>
        )}

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          {stats.map(stat => (
            <div key={stat.label} className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
              <div className="flex items-center gap-2 mb-2">
                <stat.icon size={14} strokeWidth={1.8} className={stat.danger ? 'text-red-500' : stat.verified ? 'text-emerald-600' : 'text-[var(--text-tertiary)]'} />
                <span className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wider">{stat.label}</span>
              </div>
              <p className={`text-[22px] font-semibold ${stat.danger ? 'text-red-600' : stat.verified ? 'text-emerald-700' : 'text-[var(--text-primary)]'}`}>{stat.value}</p>
            </div>
          ))}
        </div>

        <div className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] mb-6">
          <div className="flex items-center justify-between gap-3 mb-3">
            <h2 className="text-[13px] font-medium text-[var(--text-secondary)]">Ресурсы по свежим online-отчётам</h2>
            <span className="text-[11px] text-[var(--text-tertiary)]">{dataAvailable ? `${resourceNodes.length} узл.` : '—'}</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { label: 'CPU', value: avgCpu, color: avgCpu !== null && avgCpu > 70 ? 'bg-amber-500' : 'bg-emerald-500' },
              { label: 'RAM', value: avgRam, color: 'bg-[var(--accent-teal)]' },
              { label: 'Disk', value: avgDisk, color: 'bg-[var(--accent-lavender)]' },
            ].map(resource => (
              <div key={resource.label}>
                <div className="flex justify-between text-[12px] mb-1">
                  <span className="text-[var(--text-secondary)]">{resource.label}</span>
                  <span className="text-[var(--text-primary)] font-medium">{resource.value === null ? '—' : `${resource.value}%`}</span>
                </div>
                <div className="w-full h-2 bg-[var(--bg-elevated)] rounded-full overflow-hidden">
                  {resource.value !== null && <div className={`h-full ${resource.color} rounded-full transition-all`} style={{ width: `${Math.min(resource.value, 100)}%` }} />}
                </div>
              </div>
            ))}
          </div>
        </div>

        {dataAvailable && items.length === 0 && (
          <div className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-8 text-center text-[13px] text-[var(--text-tertiary)]">
            Home сообщил пустой membership. Рабочие узлы не предполагаются.
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {items.map(node => {
            const capabilityRows = node.capabilities.execution ?? []
            const evidence = node.verification.last_successful_task
            return (
              <article key={node.id} className="p-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-sm)] transition-all">
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <h3 className="text-[14px] font-semibold text-[var(--text-primary)] truncate">{node.name}</h3>
                    <p className="mt-0.5 text-[11px] text-[var(--text-tertiary)] truncate">{node.id} · {node.ip_address || 'IP —'}</p>
                  </div>
                  <span className="shrink-0 rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[10px] text-[var(--text-tertiary)]">{node.status}</span>
                </div>

                <div className="flex flex-wrap gap-1.5 mb-4">
                  {nodeTruthBadges(node).map(badge => (
                    <span key={badge.key} className={`rounded-full border px-2 py-1 text-[10px] font-medium ${toneClass[badge.tone]}`}>{badge.label}</span>
                  ))}
                </div>

                <div className="space-y-2 mb-4">
                  {[
                    { label: 'CPU', value: metric(node.cpu_percent) },
                    { label: 'RAM', value: metric(node.ram_percent) },
                    { label: 'Disk', value: metric(node.disk_percent) },
                  ].map(row => (
                    <div key={row.label} className="flex items-center gap-2">
                      <span className="text-[11px] text-[var(--text-tertiary)] w-8">{row.label}</span>
                      <div className="flex-1 h-1.5 bg-[var(--bg-elevated)] rounded-full overflow-hidden">
                        {row.value !== null && <div className="h-full bg-[var(--accent-teal)] rounded-full opacity-70" style={{ width: `${Math.min(row.value, 100)}%` }} />}
                      </div>
                      <span className="text-[10px] text-[var(--text-secondary)] w-10 text-right">{row.value === null ? '—' : `${row.value}%`}</span>
                    </div>
                  ))}
                </div>

                <div className="rounded-[var(--radius-md)] bg-[var(--bg-secondary)] p-3 mb-3">
                  <p className="text-[10px] uppercase tracking-wider text-[var(--text-tertiary)] mb-2">Capability execution</p>
                  {capabilityRows.length ? (
                    <div className="space-y-1.5">
                      {capabilityRows.map(capability => (
                        <div key={capability.name} className="flex items-center justify-between gap-3 text-[11px]">
                          <span className="text-[var(--text-secondary)] truncate" title={capability.name}>{capability.name}</span>
                          <span className={capability.executable ? 'text-violet-700' : 'text-[var(--text-tertiary)]'}>
                            {capability.executable ? 'исполняется' : capability.runner_status || 'не доказано'}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[11px] text-[var(--text-tertiary)]">Capability не заявлены</p>
                  )}
                </div>

                <div className="rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-3">
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <p className="text-[10px] uppercase tracking-wider text-[var(--text-tertiary)]">Последний строгий proof</p>
                    <span className={node.verification.verified ? 'text-[10px] text-emerald-700' : 'text-[10px] text-[var(--text-tertiary)]'}>{node.verification.status}</span>
                  </div>
                  {evidence ? (
                    <div className="space-y-1.5 text-[11px]">
                      <p className="font-medium text-[var(--text-primary)] truncate" title={evidence.task_id}>{evidence.task_id}</p>
                      {evidenceLines(evidence).map(line => (
                        <div key={line.label} className="flex items-center justify-between gap-3">
                          <span className="text-[var(--text-tertiary)]">{line.label}</span>
                          <code className="text-[10px] text-[var(--text-secondary)]" title={line.raw}>{line.value}</code>
                        </div>
                      ))}
                      <p className="text-[10px] text-[var(--text-tertiary)] truncate">verifier: {evidence.verifier}</p>
                    </div>
                  ) : (
                    <p className="text-[11px] text-[var(--text-tertiary)]">
                      {node.verification.status === 'unavailable' ? 'Fleet proof недоступен' : 'Строго проверенного результата нет'}
                    </p>
                  )}
                </div>

                <div className="mt-3 pt-3 border-t border-[var(--border-subtle)] flex items-center justify-between gap-3 text-[10px] text-[var(--text-tertiary)]">
                  <span>Heartbeat: {node.freshness.heartbeat_age_seconds === null ? '—' : `${node.freshness.heartbeat_age_seconds} сек.`}</span>
                  <span className="truncate">Задача: {node.execution.active_task_id || '—'}</span>
                </div>
              </article>
            )
          })}
        </div>
      </div>
    </div>
  )
}
