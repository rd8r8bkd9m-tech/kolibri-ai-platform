import { useEffect, useState } from 'react'
import { CheckCircle2, Cpu, Route, ShieldAlert } from 'lucide-react'
import ControlCenterNav from '@/features/factory/ControlCenterNav'
import { factoryControl, type FactoryModelsResponse } from '@/lib/api'

export default function ModelsPage() {
  const [data, setData] = useState<FactoryModelsResponse | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    void factoryControl.models()
      .then(value => { if (active) setData(value) })
      .catch(() => { if (active) setError(true) })
    return () => { active = false }
  }, [])

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1100px] px-4 py-6 sm:px-6">
        <ControlCenterNav />
        <div className="mb-6">
          <h1 className="text-[22px] font-semibold tracking-tight text-[var(--text-primary)] sm:text-[26px]">Модели и маршрутизация</h1>
          <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">Пользователь обращается только к модели «kolibri»; внутренние маршруты доступны владельцу как проверяемая инфраструктура.</p>
        </div>

        {error && (
          <div className="mb-6 flex gap-3 rounded-[var(--radius-lg)] border border-amber-200 bg-amber-50 p-4 text-[13px] text-amber-800">
            <ShieldAlert size={18} className="mt-0.5 shrink-0" />
            <p>Реестр маршрутов недоступен. Портал не подменяет отсутствие данных демонстрационными моделями.</p>
          </div>
        )}

        {!data && !error && <p className="py-16 text-center text-[13px] text-[var(--text-tertiary)]">Загрузка реестра…</p>}
        {data && (
          <>
            <section className="mb-6 grid gap-3 sm:grid-cols-3">
              <div className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
                <Cpu size={16} className="mb-3 text-[var(--accent-teal)]" />
                <p className="text-[11px] uppercase tracking-wider text-[var(--text-tertiary)]">Публичная модель</p>
                <p className="mt-1 text-[20px] font-semibold text-[var(--text-primary)]">{data.public_model}</p>
              </div>
              <div className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
                <Route size={16} className="mb-3 text-[var(--accent-teal)]" />
                <p className="text-[11px] uppercase tracking-wider text-[var(--text-tertiary)]">Маршруты</p>
                <p className="mt-1 text-[20px] font-semibold text-[var(--text-primary)]">{data.routes.length}</p>
              </div>
              <div className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
                <CheckCircle2 size={16} className="mb-3 text-emerald-600" />
                <p className="text-[11px] uppercase tracking-wider text-[var(--text-tertiary)]">Auto-routing</p>
                <p className="mt-1 text-[20px] font-semibold text-[var(--text-primary)]">{data.routing_status}</p>
              </div>
            </section>

            <section className="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
              {data.routes.map(route => (
                <article key={route.id} className="grid gap-3 border-b border-[var(--border-subtle)] p-4 last:border-0 sm:grid-cols-[minmax(0,1fr)_160px_140px] sm:items-center">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <strong className="truncate text-[13px] text-[var(--text-primary)]">{route.id}</strong>
                      <span className="rounded-full bg-[var(--bg-secondary)] px-2 py-0.5 text-[10px] text-[var(--text-tertiary)]">{route.public_name}</span>
                    </div>
                    <p className="mt-1 truncate text-[11px] text-[var(--text-tertiary)]">{route.capabilities.join(' · ') || 'capability не доказаны'}</p>
                  </div>
                  <span className="text-[12px] text-[var(--text-secondary)]">{route.provider || 'внутренний маршрут'}</span>
                  <span className={route.status === 'ready' ? 'text-[12px] text-emerald-700' : 'text-[12px] text-amber-700'}>{route.status}</span>
                </article>
              ))}
              {data.routes.length === 0 && <p className="p-8 text-center text-[13px] text-[var(--text-tertiary)]">Нет маршрутов, прошедших проверку.</p>}
            </section>
          </>
        )}
      </div>
    </div>
  )
}
