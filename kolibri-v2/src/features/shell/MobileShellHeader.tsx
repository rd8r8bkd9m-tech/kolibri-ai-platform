import { ChevronDown, Ellipsis, NotebookTabs, Pencil } from 'lucide-react'
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
  conversationHome = false,
  conversationHasContent = false,
  voiceModeActive = false,
  onToggle,
  onNewConversation,
  onHistory,
  onFiles,
}: MobileShellHeaderProps) {
  const { t } = useLocale()
  const [modeOpen, setModeOpen] = useState(false)
  const [actionsOpen, setActionsOpen] = useState(false)
  const { mode, setMode } = useExecutionMode()

  return (
    <header className={`shell-mobile-header md:hidden ${conversationSurface ? 'is-conversation-surface' : ''}`}>
      <MobileNavigationTrigger
        open={open}
        conversationSurface={conversationSurface}
        conversationHasContent={conversationHasContent}
        openLabel={t('shell.openMenu')}
        closeLabel={t('shell.closeMenu')}
        onToggle={onToggle}
      />

      {conversationSurface && !voiceModeActive ? (
        <div className="shell-mobile-mode-wrap">
          <button
            type="button"
            className="shell-mobile-mode"
            aria-expanded={modeOpen}
            onClick={() => setModeOpen(value => !value)}
          >
            <strong>Kolibri</strong>
            <span>{mode === 'deep' ? t('shell.mode.deep') : t('shell.mode.fast')}</span>
            <ChevronDown size={19} strokeWidth={2.1} />
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
            </div>
          )}
        </div>
      ) : !conversationSurface ? (
        <h1 className="min-w-0 flex-1 truncate text-center text-[18px] font-semibold tracking-[-0.025em]">{title}</h1>
      ) : <span className="shell-mobile-voice-spacer" aria-hidden="true" />}

      {conversationSurface ? (
        <div className={`shell-mobile-actions ${conversationHome && !voiceModeActive ? 'is-home' : ''}`}>
          <button type="button" aria-label={voiceModeActive ? t('shell.openProjectMaterials') : t('shell.newProject')} onClick={voiceModeActive ? onFiles : onNewConversation}>
            {voiceModeActive ? <NotebookTabs size={25} strokeWidth={1.8} /> : <Pencil size={25} strokeWidth={1.9} />}
          </button>
          {(!conversationHome || voiceModeActive) && <button type="button" aria-label={t('shell.moreActions')} aria-expanded={actionsOpen} onClick={() => setActionsOpen(value => !value)}>
            <Ellipsis size={25} strokeWidth={2.1} />
          </button>}
          {actionsOpen && <div className="shell-mobile-actions-menu" role="menu">
            <button type="button" role="menuitem" onClick={() => { setActionsOpen(false); onHistory?.() }}>{t('shell.history')}</button>
            <button type="button" role="menuitem" onClick={() => { setActionsOpen(false); onFiles?.() }}>{t('shell.files')}</button>
          </div>}
        </div>
      ) : <span className="h-12 w-12" aria-hidden="true" />}
    </header>
  )
}
