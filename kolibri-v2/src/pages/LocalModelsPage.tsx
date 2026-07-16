import { useEffect, useState } from 'react'
import { CheckCircle2, CircleDashed, HardDrive, ShieldAlert, XCircle } from 'lucide-react'
import ControlCenterNav from '@/features/factory/ControlCenterNav'
import { factoryControl, type LocalModelsResponse } from '@/lib/api'

const gateIcon = {
  passed: CheckCircle2,
  failed: XCircle,
  pending: CircleDashed,
  unavailable: ShieldAlert,
}

export default function LocalModelsPage() {
  const [data, setData] = useState<LocalModelsResponse | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    void factoryControl.localModels()
      .then(value => { if (active) setData(value) })
      .catch(() => { if (active) setError(true) })
    return () => { active = false }
  }, [])

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1000px] px-4 py-6 sm:px-6">
        <ControlCenterNav />
        <div className="mb-6">
          <h1 className="text-[22px] font-semibold tracking-tight text-[var(--text-primary)] sm:text-[26px]">Локальные LLM</h1>
          <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">Модель становится маршрутом только после шести проверок. MacBook не используется как inference-host.</p>
        </div>

        {error && <div className="flex gap-3 rounded-[var(--radius-lg)] border border-amber-200 bg-amber-50 p-4 text-[13px] text-amber-800"><ShieldAlert size={18} className="mt-0.5 shrink-0" /><p>Home не вернул admission-данные локальных моделей. Они считаются недоступными.</p></div>}
        {!data && !error && <p className="py-16 text-center text-[13px] text-[var(--text-tertiary)]">Проверка узлов…</p>}
        {data && (
          <>
            <section className="mb-6 grid grid-cols-2 gap-3">
              <div className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4"><p className="text-[11px] text-[var(--text-tertiary)]">Кандидаты</p><p className="mt-1 text-[22px] font-semibold text-[var(--text-primary)]">{data.candidate_total}</p></div>
              <div className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4"><p className="text-[11px] text-[var(--text-tertiary)]">Допущены</p><p className="mt-1 text-[22px] font-semibold text-emerald-700">{data.admitted_total}</p></div>
            </section>
            <section className="space-y-3">
              {data.items.map(model => (
                <article key={model.id} className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
                  <div className="mb-4 flex items-center justify-between gap-3"><div className="flex min-w-0 items-center gap-3"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--bg-secondary)]"><HardDrive size={17} /></div><div className="min-w-0"><strong className="block truncate text-[13px] text-[var(--text-primary)]">{model.id}</strong><p className="truncate text-[11px] text-[var(--text-tertiary)]">{model.node_id} · {model.runtime}</p></div></div><span className="rounded-full border border-[var(--border-subtle)] px-2 py-1 text-[10px] text-[var(--text-secondary)]">{model.status}</span></div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {model.gates.map(gate => { const Icon = gateIcon[gate.status]; return <div key={gate.id} className="flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] px-3 py-2"><Icon size={14} className={gate.status === 'passed' ? 'text-emerald-600' : 'text-amber-600'} /><span className="min-w-0 flex-1 truncate text-[11px] text-[var(--text-secondary)]">{gate.label}</span><span className="text-[10px] text-[var(--text-tertiary)]">{gate.status}</span></div> })}
                  </div>
                </article>
              ))}
              {data.items.length === 0 && <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-subtle)] p-10 text-center text-[13px] text-[var(--text-tertiary)]">Ни один кластерный узел не заявил локальный LLM runtime.</div>}
            </section>
          </>
        )}
      </div>
    </div>
  )
}
