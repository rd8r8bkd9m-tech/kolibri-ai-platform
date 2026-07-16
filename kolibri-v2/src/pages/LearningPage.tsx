import { useEffect, useState } from 'react'
import { BrainCircuit, CheckCircle2, CircleDashed, ShieldAlert, XCircle } from 'lucide-react'
import ControlCenterNav from '@/features/factory/ControlCenterNav'
import { factoryControl, type FormulaLearningStatus } from '@/lib/api'

const gateIcon = {
  passed: CheckCircle2,
  failed: XCircle,
  pending: CircleDashed,
  unavailable: ShieldAlert,
}

export default function LearningPage() {
  const [data, setData] = useState<FormulaLearningStatus | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    void factoryControl.learning()
      .then(value => { if (active) setData(value) })
      .catch(() => { if (active) setError(true) })
    return () => { active = false }
  }, [])

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1000px] px-4 py-6 sm:px-6">
        <ControlCenterNav />
        <div className="mb-6">
          <h1 className="text-[22px] font-semibold tracking-tight text-[var(--text-primary)] sm:text-[26px]">FormulaLM</h1>
          <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">Дистилляция создаёт только кандидата. Рабочая модель не заменяется без всех проверок и отдельного подтверждения.</p>
        </div>

        {error && (
          <div className="flex gap-3 rounded-[var(--radius-lg)] border border-amber-200 bg-amber-50 p-4 text-[13px] text-amber-800">
            <ShieldAlert size={18} className="mt-0.5 shrink-0" />
            <p>Контур FormulaLM не подтвердил готовность. Обучение и продвижение модели считаются выключенными.</p>
          </div>
        )}

        {!data && !error && <p className="py-16 text-center text-[13px] text-[var(--text-tertiary)]">Проверка контура…</p>}
        {data && (
          <>
            <section className="mb-6 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-md)] bg-[var(--accent-teal)]/10 text-[var(--accent-teal)]"><BrainCircuit size={20} /></div>
                  <div>
                    <p className="text-[11px] uppercase tracking-wider text-[var(--text-tertiary)]">Режим</p>
                    <p className="text-[15px] font-medium text-[var(--text-primary)]">{data.mode}</p>
                  </div>
                </div>
                <span className="w-fit rounded-full border border-[var(--border-subtle)] px-3 py-1 text-[11px] text-[var(--text-secondary)]">{data.candidate_only ? 'только кандидат' : 'promotion разрешён'}</span>
              </div>
              <div className="mt-5 grid gap-3 border-t border-[var(--border-subtle)] pt-4 sm:grid-cols-2">
                <div><p className="text-[11px] text-[var(--text-tertiary)]">Активная модель</p><p className="mt-1 text-[13px] text-[var(--text-primary)]">{data.active_model || 'не заявлена'}</p></div>
                <div><p className="text-[11px] text-[var(--text-tertiary)]">Кандидат</p><p className="mt-1 text-[13px] text-[var(--text-primary)]">{data.candidate_model || 'нет кандидата'}</p></div>
              </div>
            </section>

            <section className="space-y-2">
              {data.gates.map(gate => {
                const Icon = gateIcon[gate.status]
                return (
                  <article key={gate.id} className="flex items-start gap-3 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
                    <Icon size={18} className={gate.status === 'passed' ? 'mt-0.5 text-emerald-600' : gate.status === 'failed' ? 'mt-0.5 text-red-600' : 'mt-0.5 text-amber-600'} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3"><strong className="text-[13px] text-[var(--text-primary)]">{gate.label}</strong><span className="text-[11px] text-[var(--text-tertiary)]">{gate.status}</span></div>
                      {gate.reason && <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">{gate.reason}</p>}
                      {gate.evidence_sha256 && <code className="mt-2 block truncate text-[10px] text-[var(--text-secondary)]" title={gate.evidence_sha256}>sha256:{gate.evidence_sha256}</code>}
                    </div>
                  </article>
                )
              })}
            </section>
          </>
        )}
      </div>
    </div>
  )
}
