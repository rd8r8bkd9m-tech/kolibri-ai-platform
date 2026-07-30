import { useRef, useState, type ChangeEvent } from 'react'
import { ArrowRight, Calculator, CheckCircle2, FileText, SearchCheck } from 'lucide-react'
import { useNavigate } from 'react-router'
import { AssistantIntakeComposer } from '@/features/conversation/AssistantConversationThread'
import type { ComposerTool } from '@/features/conversation/composerTool'
import PublicPortalFrame from '@/features/portal/PublicPortalFrame'

const quickTasks = [
  { key: 'estimate.create', icon: FileText, label: 'Смета по чертежам', prompt: 'Составь смету по чертежам проекта' },
  { key: 'file.search', icon: SearchCheck, label: 'Проверить готовую смету', prompt: 'Проверь готовую смету и найди риски' },
  { key: 'web.search', icon: Calculator, label: 'Сравнить цены', prompt: 'Сравни цены на работы и материалы' },
] as const

const landingTools: ComposerTool[] = quickTasks.map(item => ({
  key: item.key,
  title: item.label,
  description: item.prompt,
  icon: item.icon,
}))

export default function PublicLanding() {
  const navigate = useNavigate()
  const [pendingComposerText, setPendingComposerText] = useState('')
  const [pendingPrompt, setPendingPrompt] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  function startEstimate(value: string) {
    const task = value.trim()
    if (!task) return
    navigate(`/app?q=${encodeURIComponent(task)}`)
  }

  function selectTool(key: ComposerTool['key']) {
    if (key === 'file.search') {
      setPendingPrompt('Проверь готовую смету и найди риски')
      fileInputRef.current?.click()
      return
    }
    const task = quickTasks.find(item => item.key === key)
    if (task) setPendingComposerText(task.prompt)
  }

  function requestDocuments(taskPrompt: string) {
    setPendingPrompt(taskPrompt)
    fileInputRef.current?.click()
  }

  function continueWithFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    if (!files.length) return
    navigate('/app', {
      state: {
        intakeFiles: files,
        intakePrompt: pendingPrompt,
      },
    })
  }

  return (
    <PublicPortalFrame>
      <section className="kp-cinematic-hero" aria-labelledby="kp-title">
        <div className="kp-cinematic-copy">
          <p className="kp-cinematic-kicker">Цифровой генподрядчик</p>
          <h1 id="kp-title">Смета и документы — из одного сообщения</h1>
          <p className="kp-cinematic-lead">
            Kolibri связывает объёмы, цены, источники и документы в одном проекте.
          </p>
          <div className="kp-cinematic-evidence" aria-label="Проверяемые данные проекта">
            {['Объём', 'Цена', 'Источник'].map(item => (
              <span key={item}>{item}<CheckCircle2 aria-hidden="true" /></span>
            ))}
          </div>
          <button
            type="button"
            className="kp-cinematic-primary"
            onClick={() => startEstimate('Помоги составить смету и пакет документов по проекту')}
          >
            Создать смету
            <ArrowRight aria-hidden="true" />
          </button>
        </div>
        <figure className="kp-cinematic-art" aria-label="Связанные смета, договор и акт">
          <img
            src="/kolibri-landing-documents-neural.webp"
            alt="Смета, договор и акт, связанные единой системой Kolibri"
            width="1024"
            height="1024"
            fetchPriority="high"
          />
        </figure>
      </section>

      <section id="workflow" className="kp-cinematic-workflow" aria-labelledby="kp-workflow-title">
        <div className="kp-cinematic-workflow-copy">
          <p>Начните с задачи</p>
          <h2 id="kp-workflow-title">Что нужно посчитать?</h2>
          <span>Опишите объект или приложите чертежи — Kolibri продолжит работу в приложении.</span>
        </div>
        <div className="kp-cinematic-intake">
          <input
            ref={fileInputRef}
            className="sr-only"
            type="file"
            multiple
            accept=".pdf,.xlsx,.docx,.csv,.txt,.png,.jpg,.jpeg,.webp,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/csv,text/plain,image/png,image/jpeg,image/webp"
            onChange={continueWithFiles}
          />
          <div className="kp-native-composer">
            <AssistantIntakeComposer
              pendingComposerText={pendingComposerText}
              onPendingComposerTextApplied={() => setPendingComposerText('')}
              onSend={startEstimate}
              tools={landingTools}
              onTool={selectTool}
              onAttach={() => fileInputRef.current?.click()}
              placeholder="Опишите объект или задачу"
            />
          </div>
          <div className="kp-native-suggestions" aria-label="Примеры задач">
            {quickTasks.map(item => {
              const Icon = item.icon
              return (
                <button type="button" key={item.label} onClick={() => {
                  if (item.key === 'estimate.create' || item.key === 'file.search') {
                    requestDocuments(item.prompt)
                    return
                  }
                  setPendingComposerText('Укажи регион, виды работ, объёмы и уровень материалов для сравнения цен.')
                }}>
                  <Icon aria-hidden="true" />
                  <span>{item.label}</span>
                </button>
              )
            })}
          </div>
        </div>
      </section>
    </PublicPortalFrame>
  )
}
