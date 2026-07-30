import { useState } from 'react'
import { MessageSquare, RotateCcw, Trash2, X } from 'lucide-react'
import type { Project } from '@/lib/api'
import { useLocale } from '@/features/localization'

interface HistoryPanelProps {
  open: boolean
  items: Project[]
  error: string | null
  onClose: () => void
  onSelect: (projectId: string) => void
  onDelete: (projectId: string) => Promise<Project>
  onRestore: (projectId: string) => Promise<Project>
}

export default function HistoryPanel({ open, items, error, onClose, onSelect, onDelete, onRestore }: HistoryPanelProps) {
  const { t } = useLocale()
  const [confirming, setConfirming] = useState<Project | null>(null)
  const [deleted, setDeleted] = useState<Project | null>(null)
  const [busy, setBusy] = useState(false)

  if (!open) return null

  const remove = async () => {
    if (!confirming || busy) return
    setBusy(true)
    try {
      setDeleted(await onDelete(confirming.id))
      setConfirming(null)
    } finally {
      setBusy(false)
    }
  }

  const undo = async () => {
    if (!deleted || busy) return
    setBusy(true)
    try {
      await onRestore(deleted.id)
      setDeleted(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[80]" role="dialog" aria-modal="true" aria-label={t('history.title')}>
      <button
        aria-label={t('history.close')}
        onClick={onClose}
        className="absolute inset-0 bg-[rgba(25,22,18,0.22)] backdrop-blur-[2px]"
      />
      <section className="absolute inset-x-0 bottom-0 max-h-[78dvh] rounded-t-[28px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] shadow-[var(--shadow-xl)] md:inset-y-3 md:left-auto md:right-3 md:w-[390px] md:max-h-none md:rounded-[24px]">
        <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-[var(--border-hover)] md:hidden" />
        <header className="flex h-16 items-center justify-between px-5">
          <div>
            <h2 className="text-[18px] font-semibold tracking-[-0.02em]">{t('history.title')}</h2>
            <p className="text-[13px] text-[var(--text-tertiary)]">{t('history.subtitle')}</p>
          </div>
          <button onClick={onClose} aria-label={t('common.close')} className="shell-icon-button"><X size={20} /></button>
        </header>
        <div className="h-px bg-[var(--border-subtle)]" />
        <div className="max-h-[calc(78dvh-76px)] overflow-y-auto p-3 md:max-h-[calc(100dvh-92px)]">
          {error && (
            <p role="status" className="mx-2 mb-2 rounded-xl bg-[var(--bg-elevated)] px-3 py-2 text-[13px] text-[var(--text-secondary)]">
              {t('history.unavailable')}
            </p>
          )}
          {deleted && (
            <div className="mx-2 mb-2 flex min-h-12 items-center gap-2 rounded-xl bg-[var(--bg-elevated)] px-3 py-2 text-[13px]">
              <span className="min-w-0 flex-1 truncate">{t('history.deleted', { title: deleted.title })}</span>
              <button type="button" disabled={busy} onClick={() => void undo()} className="flex min-h-10 items-center gap-1 rounded-lg px-2 font-medium text-[var(--accent-teal)]">
                <RotateCcw size={16} /> {t('history.restore')}
              </button>
            </div>
          )}
          {confirming && (
            <div className="mx-2 mb-2 rounded-xl border border-[var(--border-subtle)] p-3 text-[13px]">
              <p className="font-medium">{t('history.deleteConfirm', { title: confirming.title })}</p>
              <p className="mt-1 text-[var(--text-tertiary)]">{t('history.restoreHint')}</p>
              <div className="mt-3 flex justify-end gap-2">
                <button type="button" className="min-h-10 rounded-lg px-3" onClick={() => setConfirming(null)}>{t('common.cancel')}</button>
                <button type="button" disabled={busy} className="min-h-10 rounded-lg bg-[var(--text-primary)] px-3 text-[var(--bg-primary)]" onClick={() => void remove()}>{t('common.delete')}</button>
              </div>
            </div>
          )}
          {items.length === 0 ? (
            <div className="px-4 py-12 text-center">
              <p className="text-[15px] font-medium">{t('history.emptyTitle')}</p>
              <p className="mt-1 text-[13px] leading-5 text-[var(--text-tertiary)]">{t('history.emptyCopy')}</p>
            </div>
          ) : items.map(item => (
            <div key={item.id} className="group flex min-h-14 w-full items-center gap-2 rounded-2xl px-2 py-1.5 hover:bg-[var(--bg-hover)]">
              <button type="button" onClick={() => onSelect(item.id)} className="flex min-h-12 min-w-0 flex-1 items-center gap-3 rounded-xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-teal)]">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-elevated)] text-[var(--accent-teal)]">
                  <MessageSquare size={19} strokeWidth={1.8} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] font-medium text-[var(--text-primary)]">{item.title}</span>
                  <span className="block truncate text-[12px] text-[var(--text-tertiary)]">{t('history.messageCount', { count: item.message_count })}</span>
                </span>
              </button>
              <button type="button" aria-label={t('history.deleteProject', { title: item.title })} onClick={() => setConfirming(item)} className="shell-icon-button opacity-70 md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100">
                <Trash2 size={17} />
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
