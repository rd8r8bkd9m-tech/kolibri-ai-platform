import { useEffect, useState } from 'react'
import { FileJson, FileSpreadsheet, History, LoaderCircle } from 'lucide-react'
import { estimates, type EstimateRevisionSummary } from '@/lib/api'
import { formatDate, formatNum } from '@/lib/utils'

interface EstimateRevisionHistoryProps {
  estimateId: string
  currentVersion: number
  refreshToken: number
  onPreviewPdf: (version: number) => void
  onPreviewWorkbook: (version: number) => void
}

export default function EstimateRevisionHistory({
  estimateId,
  currentVersion,
  refreshToken,
  onPreviewPdf,
  onPreviewWorkbook,
}: EstimateRevisionHistoryProps) {
  const [items, setItems] = useState<EstimateRevisionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    void estimates.revisions(estimateId)
      .then(result => {
        if (!active) return
        setItems(result.items)
        setError(false)
      })
      .catch(() => { if (active) setError(true) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [estimateId, refreshToken])

  return (
    <section className="mt-4 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)]" aria-labelledby="estimate-revisions-title">
      <div className="flex min-h-14 items-center gap-2 border-b border-[var(--border-subtle)] px-4">
        <History size={16} className="text-[var(--text-secondary)]" aria-hidden="true" />
        <h2 id="estimate-revisions-title" className="text-[14px] font-semibold text-[var(--text-primary)]">История версий</h2>
        <span className="ml-auto text-[12px] text-[var(--text-tertiary)]">Текущая версия {currentVersion}</span>
      </div>

      {loading ? (
        <div className="flex min-h-20 items-center justify-center gap-2 text-[13px] text-[var(--text-tertiary)]" role="status">
          <LoaderCircle size={15} className="animate-spin" /> Загружаю версии
        </div>
      ) : error ? (
        <p className="px-4 py-4 text-[13px] text-red-600" role="alert">Историю версий не удалось загрузить.</p>
      ) : items.length === 0 ? (
        <p className="px-4 py-4 text-[13px] text-[var(--text-tertiary)]">Сохранённых версий пока нет.</p>
      ) : (
        <div className="divide-y divide-[var(--border-subtle)]">
          {items.map(item => (
            <div key={item.id} className="flex flex-wrap items-center gap-2 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-[var(--text-primary)]">
                  Версия {item.version}{item.version === currentVersion ? ' · текущая' : ''}
                </p>
                <p className="text-[12px] text-[var(--text-tertiary)]">{formatDate(item.created_at)} · {formatNum(item.total)} ₽</p>
              </div>
              <button
                type="button"
                onClick={() => onPreviewPdf(item.version)}
                aria-label={`Открыть PDF версии ${item.version} внутри Kolibri`}
                className="inline-flex min-h-10 items-center rounded-lg px-3 text-[12px] font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
              >
                PDF
              </button>
              <button
                type="button"
                onClick={() => onPreviewWorkbook(item.version)}
                aria-label={`Открыть XLSX версии ${item.version} внутри Kolibri`}
                className="inline-flex min-h-10 items-center gap-1.5 rounded-lg px-3 text-[12px] font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
              >
                <FileSpreadsheet size={14} aria-hidden="true" /> XLSX
              </button>
              <a
                href={estimates.exportUrl(estimateId, 'json', item.version)}
                target="_blank"
                rel="noreferrer"
                aria-label={`Скачать JSON версии ${item.version}`}
                className="inline-flex min-h-10 items-center gap-1.5 rounded-lg px-3 text-[12px] font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
              >
                <FileJson size={14} aria-hidden="true" /> JSON
              </a>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
