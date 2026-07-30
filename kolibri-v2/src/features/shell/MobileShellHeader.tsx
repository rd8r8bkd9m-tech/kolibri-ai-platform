import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { useExecutionMode } from './executionPolicyContext'
import { useLocale } from '@/features/localization'
import MobileNavigationTrigger from './MobileNavigationTrigger'

interface MobileShellHeaderProps {
  open: boolean
  title: string
  conversationSurface?: boolean
  conversationHome?: boolean
  conversationHasContent?: boolean
  voiceModeActive?: boolean
  onToggle: () => void
  onNewConversation?: () => void
  onHistory?: () => void
  onFiles?: () => void
}

export default function MobileShellHeader({
  open,
  title,
  conversationSurface = false,
  conversationHasContent = false,
  onToggle,
}: MobileShellHeaderProps) {
  const { t } = useLocale()
  const [modeOpen, setModeOpen] = useState(false)
  const { mode, setMode } = useExecutionMode()

  return (
    <header
      className={`shell-mobile-header ${conversationSurface ? 'is-conversation-surface' : ''}`}
      data-mobile-navigation={open ? 'open' : 'closed'}
    >
      <MobileNavigationTrigger
        open={open}
        conversationSurface={conversationSurface}
        conversationHasContent={conversationHasContent}
        openLabel={t('shell.openMenu')}
        closeLabel={t('shell.closeMenu')}
        onToggle={onToggle}
      />

      {conversationSurface ? (
        <div className="shell-mobile-mode-wrap">
          <button
            type="button"
            className="shell-mobile-mode"
            aria-expanded={modeOpen}
            onClick={() => setModeOpen(value => !value)}
          >
            <strong>Kolibri</strong>
            <ChevronDown size={14} strokeWidth={2.1} />
          </button>
          {modeOpen && (
            <div className="shell-mobile-mode-menu" role="menu" aria-label={t('shell.responseMode')}>
              <button type="button" role="menuitem" onClick={() => { setMode('fast'); setModeOpen(false) }}>
                <strong>{t('shell.mode.fast')}</strong>
                <span>{t('shell.mode.fastDescription')}</span>
              </button>
              <button type="button" role="menuitem" onClick={() => { setMode('deep'); setModeOpen(false) }}>
                <strong>{t('shell.mode.deep')}</strong>
                <span>{t('shell.mode.deepDescription')}</span>
              </button>
              <span className="sr-only" aria-live="polite">{mode === 'deep' ? t('shell.mode.deep') : t('shell.mode.fast')}</span>
            </div>
          )}
        </div>
      ) : (
        <h1 className="shell-mobile-page-title">{title}</h1>
      )}

      <span className="shell-mobile-balance" aria-hidden="true" />
    </header>
  )
}
