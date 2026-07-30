import { useState } from 'react'
import { CalendarDays, ChevronDown, CircleAlert, CircleHelp, Link2, MapPin, ShieldCheck } from 'lucide-react'
import type { Estimate } from '@/lib/api'
import { formatCurrency } from '@/lib/utils'
import {
  estimateEvidenceSummary,
  estimateTruthLabels,
  truthStatusClass,
} from './estimateEvidence'
import styles from './EstimateEvidencePanel.module.css'

interface EstimateEvidencePanelProps {
  estimate: Estimate
  compact?: boolean
  collapsible?: boolean
}

function cleanList(values: string[] | undefined): string[] {
  return (values ?? []).map(value => value.trim()).filter(Boolean)
}

function evidenceDate(value: { price_date?: string; observed_at?: string } | null): string | null {
  const raw = value?.price_date || value?.observed_at
  if (!raw || !Number.isFinite(Date.parse(raw))) return null
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Moscow',
  }).format(new Date(raw))
}

function manualPriceDate(value: string | null | undefined): string | null {
  if (!value || !Number.isFinite(Date.parse(value))) return null
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Moscow',
  }).format(new Date(`${value.slice(0, 10)}T12:00:00Z`))
}

export function EstimateTruthBadge({ status }: { status: ReturnType<typeof estimateEvidenceSummary>['estimateStatus'] }) {
  return <span className={`estimate-truth-badge ${truthStatusClass(status)}`}>{estimateTruthLabels[status]}</span>
}

export default function EstimateEvidencePanel({ estimate, compact = false, collapsible = false }: EstimateEvidencePanelProps) {
  const summary = estimateEvidenceSummary(estimate)
  const assumptions = cleanList(estimate.assumptions)
  const questions = cleanList(estimate.questions)
  const rows = compact ? summary.rows.slice(0, 5) : summary.rows
  const [expanded, setExpanded] = useState(!collapsible)
  const priceDate = summary.dateLabel || manualPriceDate(estimate.price_as_of)

  return (
    <section className={`estimate-evidence-panel${compact ? ' compact' : ''}${collapsible ? ' is-collapsible' : ''} ${expanded ? styles.expanded : ''}`} aria-labelledby={`estimate-evidence-${estimate.id}`}>
      <header className="estimate-evidence-header">
        <div>
          <span className="estimate-evidence-eyebrow">Достоверность сметы</span>
          <h2 id={`estimate-evidence-${estimate.id}`}>Цены и исходные данные</h2>
        </div>
        <div className="estimate-evidence-badges">
          <EstimateTruthBadge status={summary.estimateStatus} />
          {summary.pricingStatus !== summary.estimateStatus && (
            <span className={`estimate-truth-badge ${truthStatusClass(summary.pricingStatus)}`}>
              {estimateTruthLabels[summary.pricingStatus]}
            </span>
          )}
        </div>
      </header>

      <div className="estimate-evidence-meta estimate-evidence-summary">
        <span><MapPin size={16} aria-hidden="true" />{estimate.region || 'Регион не задан'}</span>
        <span><CalendarDays size={16} aria-hidden="true" />{priceDate ? `Цены на ${priceDate}` : 'Дата цен не указана'}</span>
        <span><ShieldCheck size={16} aria-hidden="true" />{summary.verifiedRows} из {summary.totalPricedRows} цен привязаны к проверенным источникам</span>
      </div>

      {collapsible && (
        <button
          type="button"
          className={styles.toggle}
          aria-expanded={expanded}
          aria-controls={`estimate-evidence-details-${estimate.id}`}
          onClick={() => setExpanded(value => !value)}
        >
          <span>{expanded ? 'Скрыть основания' : 'Показать основания и источники'}</span>
          <ChevronDown size={18} aria-hidden="true" />
        </button>
      )}

      <div id={`estimate-evidence-details-${estimate.id}`} className={styles.details} hidden={!expanded}>
        {estimate.source_note && <p className="estimate-evidence-note">{estimate.source_note}</p>}

        <div className="estimate-evidence-rows" aria-label="Источники цен по позициям">
          {rows.length ? rows.map(row => {
            const date = evidenceDate(row.evidence)
            return (
              <article key={row.position.id} className={`estimate-evidence-row ${row.verified ? 'verified' : 'unverified'}`}>
                <div className="estimate-evidence-row-title">
                  {row.verified ? <ShieldCheck size={17} aria-hidden="true" /> : <CircleAlert size={17} aria-hidden="true" />}
                  <span><strong>{row.position.name}</strong><small>{row.position.unit} · {formatCurrency(row.position.price)}</small></span>
                </div>
                {row.verified && row.evidence ? (
                  <div className="estimate-evidence-source">
                    <a href={row.evidence.url} target="_blank" rel="noreferrer">
                      <Link2 size={15} aria-hidden="true" />{row.evidence.source_title || row.evidence.url}
                    </a>
                    <small>{[row.evidence.region, date, row.evidence.vat_status].filter(Boolean).join(' · ')}</small>
                  </div>
                ) : (
                  <p>{row.reason}</p>
                )}
              </article>
            )
          }) : (
            <p className="estimate-evidence-empty">В смете пока нет ценовых строк для проверки.</p>
          )}
          {compact && summary.rows.length > rows.length && (
            <p className="estimate-evidence-more">Ещё {summary.rows.length - rows.length} позиций доступны в редакторе.</p>
          )}
        </div>

        {(assumptions.length > 0 || questions.length > 0) && (
          <div className="estimate-evidence-context">
            {assumptions.length > 0 && (
              <div>
                <h3><CircleAlert size={16} aria-hidden="true" />Допущения</h3>
                <ul>{(compact ? assumptions.slice(0, 3) : assumptions).map(item => <li key={item}>{item}</li>)}</ul>
              </div>
            )}
            {questions.length > 0 && (
              <div>
                <h3><CircleHelp size={16} aria-hidden="true" />Что нужно уточнить</h3>
                <ul>{(compact ? questions.slice(0, 3) : questions).map(item => <li key={item}>{item}</li>)}</ul>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
