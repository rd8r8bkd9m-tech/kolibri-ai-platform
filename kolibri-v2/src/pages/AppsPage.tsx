import { useState } from 'react'
import { useNavigate } from 'react-router'
import { Calculator, FileText, BarChart3, Code2, Bot, FlaskConical, X, ChevronRight } from 'lucide-react'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'

const apps = [
  { id: 'estimates', name: 'Сметы', description: 'Создавайте, проверяйте и редактируйте строительные сметы с AI-помощником', icon: Calculator, color: 'bg-[#e8f8f7] text-[#3ABAB4]', route: '/estimates', ready: true },
  { id: 'documents', name: 'Документы', description: 'Договоры, акты, письма и коммерческие предложения', icon: FileText, color: 'bg-[#f0edfe] text-[#7c6df1]', route: '/documents', ready: true },
  { id: 'agents', name: 'Агентная фабрика', description: 'Запускайте и контролируйте распределённые AI-задачи', icon: Bot, color: 'bg-[#fde8f4] text-[#e85aa3]', route: '/agents', ready: true },
  { id: 'analytics', name: 'Аналитика', description: 'Сравнивайте данные, цены, документы и отчёты', icon: BarChart3, color: 'bg-[#fef3e8] text-[#f59e0b]', route: '#', ready: false },
  { id: 'code', name: 'Kimi Code', description: 'Партнёр программиста — работа с GitHub, кодом, PR', icon: Code2, color: 'bg-[#e8eef8] text-[#3b82f6]', route: '#', ready: false },
  { id: 'formulalm', name: 'FormulaLM Lab', description: 'Эксперименты, модели, checkpoints и метрики', icon: FlaskConical, color: 'bg-[#f0f0f0] text-[#6b7280]', route: '#', ready: false },
]

export default function AppsPage() {
  const [selectedApp, setSelectedApp] = useState<typeof apps[0] | null>(null)
  const navigate = useNavigate()

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[900px] mx-auto px-4 sm:px-6 py-6">
        <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text-primary)] tracking-tight mb-2">Приложения</h1>
        <p className="text-[14px] text-[var(--text-secondary)] mb-6">Профессиональные AI-инструменты для ваших задач</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {apps.map(app => {
            const card = (
              <button
                key={app.id}
                onClick={() => app.ready ? setSelectedApp(app) : undefined}
                className={`group text-left p-5 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-surface)] transition-all ${app.ready ? 'hover:border-[var(--border-hover)] hover:shadow-[var(--shadow-md)]' : 'opacity-70 cursor-default'}`}
              >
                <div className={`w-10 h-10 rounded-[var(--radius-md)] ${app.color} flex items-center justify-center mb-3`}>
                  <app.icon size={20} strokeWidth={1.8} />
                </div>
                <h3 className="text-[15px] font-medium text-[var(--text-primary)] mb-1 group-hover:text-[var(--accent-teal)] transition-colors">
                  {app.name}
                  {!app.ready && <span className="ml-2 text-[10px] text-[var(--text-tertiary)] bg-[var(--bg-elevated)] px-1.5 py-0.5 rounded-full">Скоро</span>}
                </h3>
                <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">{app.description}</p>
                {app.ready && (
                  <div className="flex items-center gap-1 mt-3 text-[13px] text-[var(--accent-teal)] opacity-0 group-hover:opacity-100 transition-opacity">
                    <span>Открыть</span>
                    <ChevronRight size={14} />
                  </div>
                )}
              </button>
            )

            if (!app.ready) {
              return (
                <Tooltip key={app.id}>
                  <TooltipTrigger asChild>{card}</TooltipTrigger>
                  <TooltipContent side="top">Скоро будет доступно</TooltipContent>
                </Tooltip>
              )
            }
            return card
          })}
        </div>

        {/* Modal */}
        {selectedApp && (
          <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" onClick={() => setSelectedApp(null)}>
            <div className="bg-[var(--bg-primary)] rounded-[var(--radius-xl)] shadow-xl max-w-[440px] w-full p-6" onClick={e => e.stopPropagation()}>
              <div className="flex items-start justify-between mb-4">
                <div className={`w-12 h-12 rounded-[var(--radius-lg)] ${selectedApp.color} flex items-center justify-center`}>
                  <selectedApp.icon size={24} strokeWidth={1.8} />
                </div>
                <button onClick={() => setSelectedApp(null)} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-[var(--bg-hover)] transition-colors">
                  <X size={18} />
                </button>
              </div>
              <h2 className="text-[18px] font-semibold text-[var(--text-primary)] mb-2">{selectedApp.name}</h2>
              <p className="text-[14px] text-[var(--text-secondary)] mb-4">{selectedApp.description}</p>
              {!selectedApp.ready && (
                <div className="mb-6 p-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)]">
                  <p className="text-[12px] text-[var(--text-tertiary)] leading-relaxed">
                    {selectedApp.id === 'analytics' && 'Дашборды, графики, сравнение цен по регионам, экспорт отчётов в PDF/XLSX. Интеграция с каталогом из 1M+ позиций.'}
                    {selectedApp.id === 'code' && 'Интеграция с GitHub, ревью кода, генерация PR, автодеплой. Поддержка Python, TypeScript, Go, Rust.'}
                    {selectedApp.id === 'formulalm' && 'ML-пайплайны, A/B тесты, версионирование моделей, метрики обучения. Интеграция с Ollama и HuggingFace.'}
                  </p>
                </div>
              )}
              <div className="flex gap-2">
                {selectedApp.ready ? (
                  <button
                    onClick={() => { navigate(selectedApp.route); setSelectedApp(null) }}
                    className="flex-1 h-10 bg-[var(--accent-teal)] text-white rounded-[var(--radius-md)] text-[14px] font-medium hover:bg-[var(--accent-teal-hover)] transition-colors"
                  >
                    Открыть приложение
                  </button>
                ) : (
                  <button disabled className="flex-1 h-10 bg-[var(--bg-elevated)] text-[var(--text-tertiary)] rounded-[var(--radius-md)] text-[14px] font-medium cursor-not-allowed">
                    Скоро будет доступно
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
