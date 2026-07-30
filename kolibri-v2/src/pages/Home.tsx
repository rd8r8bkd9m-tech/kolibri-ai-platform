import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { Calculator, FileCheck2, GitCompareArrows, Search, Upload } from 'lucide-react'
import { AssistantIntakeComposer } from '@/features/conversation/AssistantConversationThread'
import type { ComposerTool } from '@/features/conversation/composerTool'
import { capabilityIcons, capabilityPrompt, useCapabilities, type UiCapabilityKey } from '@/features/capabilities'
import { useLocale } from '@/features/localization'
import { useProjectHistory } from '@/features/projects/projectHistoryContext'
import { projectDocuments } from '@/lib/api'
import { useExecutionMode } from '@/features/shell/executionPolicyContext'

const QUICK_ACTIONS = [
  { key: 'create', icon: Calculator, labelKey: 'home.actionCreate', promptKey: 'home.promptCreate', requiresFiles: true },
  { key: 'check', icon: FileCheck2, labelKey: 'home.actionCheck', promptKey: 'home.promptCheck', requiresFiles: true },
  { key: 'price', icon: Search, labelKey: 'home.actionPrice', promptKey: 'home.promptPrice', requiresFiles: false },
  { key: 'compare', icon: GitCompareArrows, labelKey: 'home.actionCompare', promptKey: 'home.promptCompare', requiresFiles: true },
] as const

export default function Home() {
  const { t } = useLocale()
  const [pendingComposerText, setPendingComposerText] = useState('')
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [pendingFilePrompt, setPendingFilePrompt] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const intakeStartedRef = useRef(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { createProject } = useProjectHistory()
  const { mode, setMode } = useExecutionMode()
  const { menu: capabilityMenu } = useCapabilities()
  const composerTools = useMemo<ComposerTool[]>(() => capabilityMenu.map(item => ({
    key: item.key,
    title: item.title,
    description: item.description,
    icon: capabilityIcons[item.key],
  })), [capabilityMenu])
  const startConversation = (value: string) => {
    const prompt = value.trim()
    if (!prompt) return
    navigate(`/chat?q=${encodeURIComponent(prompt)}`)
  }

  const ingestFiles = useCallback(async (files: File[], requestedPrompt = pendingFilePrompt) => {
    if (!files.length || uploading) return
    setUploading(true)
    setUploadError('')
    try {
      const firstName = files[0].name.replace(/\.[^.]+$/, '').trim()
      const project = await createProject({
        title: firstName || t('home.uploadProjectTitle'),
        metadata: { workflow: 'estimate_intake' },
      })
      for (const file of files) await projectDocuments.upload(project.id, file)
      const nextPrompt = requestedPrompt || t('home.uploadPrompt')
      setPendingFilePrompt('')
      navigate(`/chat/${encodeURIComponent(project.id)}?q=${encodeURIComponent(nextPrompt)}`)
    } catch {
      setUploadError(t('home.uploadFailed'))
    } finally {
      setUploading(false)
    }
  }, [createProject, navigate, pendingFilePrompt, t, uploading])

  const uploadFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    void ingestFiles(files)
  }

  const dropFiles = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    setDragging(false)
    void ingestFiles(Array.from(event.dataTransfer.files))
  }

  useEffect(() => {
    const state = location.state as {
      intakeFiles?: File[]
      intakePrompt?: string
    } | null
    if (
      intakeStartedRef.current
      || !state?.intakeFiles?.length
    ) return
    intakeStartedRef.current = true
    setPendingFilePrompt(state.intakePrompt ?? '')
    void ingestFiles(state.intakeFiles, state.intakePrompt)
  }, [ingestFiles, location.state])

  return (
    <section
      className={`conversation-home ${dragging ? 'is-dragging-files' : ''}`}
      aria-labelledby="home-title"
      onDragEnter={event => { event.preventDefault(); setDragging(true) }}
      onDragOver={event => event.preventDefault()}
      onDragLeave={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false)
      }}
      onDrop={dropFiles}
    >
      {dragging && <div className="conversation-drop-overlay" aria-hidden="true"><Upload size={28} /><strong>{t('home.dropFiles')}</strong></div>}
      <div className="conversation-home-content">
        <div className="conversation-home-mode" role="group" aria-label={t('shell.responseMode')}>
          <button type="button" className={mode === 'fast' ? 'is-active' : ''} aria-pressed={mode === 'fast'} onClick={() => setMode('fast')}>{t('shell.mode.fast')}</button>
          <button type="button" className={mode === 'deep' ? 'is-active' : ''} aria-pressed={mode === 'deep'} onClick={() => setMode('deep')}>{t('shell.mode.deep')}</button>
        </div>
        <div className="conversation-home-heading">
          <h1 id="home-title">{t('home.workspaceTitle')}</h1>
          <p>{t('home.workspaceCopy')}</p>
        </div>

        <div className="conversation-home-composer">
          <AssistantIntakeComposer
            pendingComposerText={pendingComposerText}
            onPendingComposerTextApplied={() => setPendingComposerText('')}
            onSend={startConversation}
            tools={composerTools}
            onTool={(key: UiCapabilityKey) => setPendingComposerText(capabilityPrompt(key))}
            onAttach={() => fileInputRef.current?.click()}
            placeholder={t('home.workspacePlaceholder')}
            disabled={uploading}
          />
        </div>

        <div className="conversation-home-upload">
          <input
            ref={fileInputRef}
            className="sr-only"
            type="file"
            multiple
            accept=".pdf,.xlsx,.docx,.csv,.txt,.png,.jpg,.jpeg,.webp,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/csv,text/plain,image/png,image/jpeg,image/webp"
            onChange={uploadFiles}
          />
          <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
            <Upload size={17} aria-hidden="true" />
            {uploading ? t('home.uploading') : t('home.uploadFiles')}
          </button>
          <span>{t('home.uploadFormats')} · {t('home.dragHint')}</span>
        </div>
        {uploading && (
          <div className="conversation-intake-progress" role="status" aria-label={t('home.processingStatus')}>
            <span className="is-active">{t('home.stageUpload')}</span>
            <i aria-hidden="true" />
            <span>{t('home.stageRecognize')}</span>
            <i aria-hidden="true" />
            <span>{t('home.stageCheck')}</span>
            <i aria-hidden="true" />
            <span>{t('home.stageReady')}</span>
          </div>
        )}
        {uploadError && <p className="conversation-home-error" role="status">{uploadError}</p>}

        <nav className="conversation-suggestions" aria-label={t('home.quickActions')}>
          {QUICK_ACTIONS.map(action => {
            const Icon = action.icon
            return (
              <button key={action.key} type="button" onClick={() => {
                const actionPrompt = t(action.promptKey)
                if (action.requiresFiles) {
                  setPendingFilePrompt(actionPrompt)
                  fileInputRef.current?.click()
                  return
                }
                setPendingComposerText(actionPrompt)
              }}>
                <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
                <span>{t(action.labelKey)}</span>
              </button>
            )
          })}
        </nav>
      </div>
    </section>
  )
}
