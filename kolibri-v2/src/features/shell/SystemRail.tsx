import { Clock3, Files, PanelLeft, Plus, Search, Settings } from 'lucide-react'
import CartoonMascot from '@/components/CartoonMascot'
import { useLocale } from '@/features/localization'

interface SystemRailProps {
  expanded: boolean
  pinned: boolean
  onExpandedChange: (expanded: boolean) => void
  onPinnedChange: (pinned: boolean) => void
  onNew: () => void
  onHistory: () => void
  onSearch: () => void
  onFiles: () => void
  onSettings: () => void
}

const RailAction = ({
  icon: Icon,
  label,
  expanded,
  onClick,
}: {
  icon: typeof Plus
  label: string
  expanded: boolean
  onClick: () => void
}) => (
  <button onClick={onClick} aria-label={label} title={expanded ? undefined : label} className="shell-rail-action">
    <Icon size={20} strokeWidth={1.75} />
    <span className={expanded ? 'opacity-100' : 'pointer-events-none opacity-0'}>{label}</span>
  </button>
)

export default function SystemRail({
  expanded,
  pinned,
  onExpandedChange,
  onPinnedChange,
  onNew,
  onHistory,
  onSearch,
  onFiles,
  onSettings,
}: SystemRailProps) {
  const { t } = useLocale()
  return (
    <aside
      className={`shell-system-rail ${expanded ? 'is-expanded' : ''}`}
      onMouseEnter={() => onExpandedChange(true)}
      onMouseLeave={() => { if (!pinned) onExpandedChange(false) }}
      aria-label={t('shell.navigation')}
    >
      <div className="flex h-16 items-center px-[10px]">
        <button
          onClick={() => onPinnedChange(!pinned)}
          className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl hover:bg-[var(--bg-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-teal)]"
          aria-label={pinned ? t('shell.unpinMenu') : t('shell.pinMenu')}
        >
          <CartoonMascot size={34} />
        </button>
        <div className={`ml-2 min-w-0 flex-1 transition-opacity ${expanded ? 'opacity-100' : 'opacity-0'}`}>
          <p className="truncate text-[15px] font-semibold tracking-[-0.02em]">Kolibri</p>
          <p className="truncate text-[11px] text-[var(--text-tertiary)]">{t('shell.workspace')}</p>
        </div>
        {expanded && (
          <button onClick={() => onPinnedChange(!pinned)} className="shell-icon-button" aria-label={t('shell.pinMenu')}>
            <PanelLeft size={18} />
          </button>
        )}
      </div>
      <nav className="flex flex-1 flex-col gap-1 px-[10px] py-3">
        <RailAction icon={Plus} label={t('shell.newProject')} expanded={expanded} onClick={onNew} />
        <RailAction icon={Clock3} label={t('shell.recent')} expanded={expanded} onClick={onHistory} />
        <RailAction icon={Search} label={t('shell.search')} expanded={expanded} onClick={onSearch} />
        <RailAction icon={Files} label={t('shell.files')} expanded={expanded} onClick={onFiles} />
      </nav>
      <div className="px-[10px] pb-3">
        <RailAction icon={Settings} label={t('common.settings')} expanded={expanded} onClick={onSettings} />
      </div>
    </aside>
  )
}
