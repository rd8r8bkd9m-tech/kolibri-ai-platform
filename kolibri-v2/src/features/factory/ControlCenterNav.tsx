import { Activity, BrainCircuit, Cpu, HardDrive, History, Network } from 'lucide-react'
import { NavLink } from 'react-router'

const items = [
  { to: '/control', end: true, label: 'Фабрика', icon: Activity },
  { to: '/control/servers', label: 'Серверы', icon: Network },
  { to: '/control/models', label: 'Модели', icon: Cpu },
  { to: '/control/local-models', label: 'Локальные LLM', icon: HardDrive },
  { to: '/control/learning', label: 'FormulaLM', icon: BrainCircuit },
  { to: '/control/audit', label: 'События', icon: History },
]

export default function ControlCenterNav() {
  return (
    <nav
      aria-label="Разделы фабрики"
      className="-mx-1 mb-6 flex gap-1 overflow-x-auto px-1 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {items.map(item => {
        const Icon = item.icon
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => [
              'inline-flex min-h-10 shrink-0 items-center gap-2 rounded-[var(--radius-md)] px-3 text-[13px] transition-colors',
              isActive
                ? 'bg-[var(--text-primary)] text-[var(--bg-primary)]'
                : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]',
            ].join(' ')}
          >
            <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
            <span>{item.label}</span>
          </NavLink>
        )
      })}
    </nav>
  )
}
