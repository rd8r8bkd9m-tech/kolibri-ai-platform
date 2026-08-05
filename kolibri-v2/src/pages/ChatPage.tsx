import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Check, Copy, FileText, Image as ImageIcon, PencilLine, RotateCw, ThumbsDown, ThumbsUp } from 'lucide-react'
import AssistantConversationThread from '@/features/conversation/AssistantConversationThread'
import ConversationEstimateSheet from '@/features/conversation/ConversationEstimateSheet'
import MimoVoiceButton from '@/features/conversation/MimoVoiceButton'
import type { ComposerTool } from '@/features/conversation/composerTool'
import {
  actionMaterializationEvent,
  materializeConversationAction,
  providerAttemptEvent,
} from '@/features/conversation/actionMaterialization'
import ArtifactCard, { type ConversationArtifact } from '@/features/conversation/ArtifactCard'
import {
  expectsImageArtifact,
  isVerifiedImageArtifact,
  safeContentBeforeImageVerification,
  verifyImageArtifact,
} from '@/features/conversation/imageArtifact'
import { isVerifiedFileArtifact, verifyFileArtifact } from '@/features/conversation/fileArtifact'
import {
  estimateActionNeedsClarification,
  estimateClarificationQuestions,
  shouldAutoMaterializeAction,
} from '@/features/conversation/estimateActionPolicy'
import { isFailedResponse, persistedResponseStatus, responseFailureMessage } from '@/features/conversation/responseState'
import WorkTrace, { type WorkStage } from '@/features/conversation/WorkTrace'
import { requiresProjectDocuments } from '@/features/conversation/documentIntent'
import { mergeReplayedWorkSummaries, settleWorkSummaries } from '@/features/conversation/workTraceState'
import { capabilityIcons, capabilityPrompt, useCapabilities, type UiCapabilityKey } from '@/features/capabilities'
import { createExecutionPolicy } from '@/features/shell/executionPolicy'
import { useExecutionMode } from '@/features/shell/executionPolicyContext'
import { dispatchResponseActivity, type ResponseActivityOutcome } from '@/features/shell/responseActivity'
import { useProjectHistory } from '@/features/projects/projectHistoryContext'
import { latestResponseId, serverMessageStatus } from '@/features/projects/historyState'
import { conversationRouteAction, type ConversationRouteSnapshot } from '@/features/projects/conversationRoute'
import {
  buildPersistedConversationMetadata,
  hydratePersistedArtifact,
  normalizePersistedAction,
  restoreConversationMetadata,
  type PersistedArtifactReference,
} from '@/features/projects/persistedConversation'
import {
  chat,
  documents,
  estimates,
  projects as projectsApi,
  projectDocuments,
  resumeResponseAfterDisconnect,
  responses,
  type ChatAction,
  type ChatStreamEvent,
  type ChatWorkSummary,
  type Document,
  type Estimate,
  type Project,
  type ProjectMessage,
  type ProjectMessageStatus,
} from '@/lib/api'
import { createUuid } from '@/lib/uuid'
import { useLocale } from '@/features/localization'
import InPlaceDocumentWorkspace from '@/features/documents/InPlaceDocumentWorkspace'

const fallbackComposerTools: ComposerTool[] = [
  {
    key: 'file.search',
    title: 'Файлы',
    description: 'Добавить и проанализировать файлы',
    icon: capabilityIcons['file.search'],
  },
  {
    key: 'web.search',
    title: 'Интернет',
    description: 'Найти актуальные цены и источники',
    icon: capabilityIcons['web.search'],
  },
]

function appendWorkSummary(events: ChatWorkSummary[], next: ChatWorkSummary): ChatWorkSummary[] {
  return mergeReplayedWorkSummaries(events, [next])
}

interface Message {
  id: string
  serverId?: string
  role: 'user' | 'assistant'
  content: string
  actions?: ChatAction[]
  artifact?: ConversationArtifact
  artifactReference?: PersistedArtifactReference
  timestamp: Date
  work?: {
    stage: WorkStage
    startedAt: number
    elapsedSeconds: number
    events: ChatWorkSummary[]
  }
}

function isEstimateCreating(message: Message): boolean {
  if (message.artifact || message.role !== 'assistant') return false
  return message.work?.events?.some(
    event => event.stage === 'estimate_creation' && event.status === 'active'
  ) ?? false
}

function restoredMessage(message: ProjectMessage): Message | null {
  if (message.role !== 'user' && message.role !== 'assistant') return null
  const metadata = restoreConversationMetadata(message.metadata)
  const stage = message.role === 'assistant' ? serverMessageStatus(message.status) : undefined
  const startedAt = Date.parse(message.created_at) || Date.now()
  const finishedAt = Date.parse(message.updated_at) || startedAt
  return {
    id: message.id,
    serverId: message.id,
    role: message.role,
    content: message.content,
    actions: metadata.actions.length ? metadata.actions : undefined,
    artifact: undefined,
    artifactReference: metadata.artifact,
    timestamp: new Date(message.created_at),
    work: stage ? {
      stage,
      startedAt,
      elapsedSeconds: Math.max(0, Math.floor((finishedAt - startedAt) / 1000)),
      events: metadata.workEvents,
    } : undefined,
  }
}

function ActionButton({ action, onRun, busy }: { action: ChatAction; onRun: () => void; busy: boolean }) {
  const Icon = action.type === 'create_estimate' ? PencilLine : action.type === 'present_image' ? ImageIcon : FileText
  return (
    <button type="button" onClick={onRun} disabled={busy} className="conversation-action-button">
      <Icon size={18} strokeWidth={1.8} />
      <span>{action.label}</span>
    </button>
  )
}

function EstimateClarificationCard({ questions, onAnswer, onSkip }: { questions: string[]; onAnswer: (selected: string[]) => void; onSkip: () => void }) {
  const [selected, setSelected] = useState(() => new Set(questions))
  const selectedQuestions = questions.filter(question => selected.has(question))
  return (
    <section className="estimate-clarification-card" aria-label="Уточняющие вопросы для сметы">
      <div className="estimate-clarification-heading">
        <strong>Нужно уточнить данные</strong>
        <span>{questions.length} {questions.length === 1 ? 'вопрос' : questions.length < 5 ? 'вопроса' : 'вопросов'}</span>
      </div>
      <div className="estimate-clarification-options">
        {questions.map((question, index) => <label key={`${index}-${question}`}><input type="checkbox" checked={selected.has(question)} onChange={() => setSelected(current => {
          const next = new Set(current)
          if (next.has(question)) next.delete(question)
          else next.add(question)
          return next
        })} /><span>{question}</span></label>)}
      </div>
      <div className="estimate-clarification-actions">
        <button type="button" disabled={!selectedQuestions.length} onClick={() => onAnswer(selectedQuestions)}>Заполнить выбранное</button>
        <button type="button" onClick={onSkip}>Оставить пустым</button>
      </div>
    </section>
  )
}

function MessageActions({ messageId, content, onRetry }: { messageId: string; content: string; onRetry: () => void }) {
  const { t } = useLocale()
  const [rating, setRating] = useState<'up' | 'down' | null>(null)
  const [copied, setCopied] = useState(false)
  const [retrying, setRetrying] = useState(false)

  const copy = async () => {
    await navigator.clipboard.writeText(content)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }

  const retry = () => {
    setRetrying(true)
    onRetry()
    window.setTimeout(() => setRetrying(false), 1400)
  }

  const notice = copied
    ? t('chat.copied')
    : retrying
      ? t('chat.retrying')
      : rating === 'up'
        ? t('chat.feedbackHelpful')
        : rating === 'down'
          ? t('chat.feedbackInaccurate')
          : ''

  return (
    <div className="conversation-message-action-wrap">
      <div className="conversation-message-actions" aria-label={t('chat.answerActions')}>
        <button type="button" aria-label={t('chat.helpful')} aria-pressed={rating === 'up'} onClick={() => setRating(current => current === 'up' ? null : 'up')}><ThumbsUp size={21} fill={rating === 'up' ? 'currentColor' : 'none'} /></button>
        <button type="button" aria-label={t('chat.inaccurate')} aria-pressed={rating === 'down'} onClick={() => setRating(current => current === 'down' ? null : 'down')}><ThumbsDown size={21} fill={rating === 'down' ? 'currentColor' : 'none'} /></button>
        <button type="button" aria-label={retrying ? t('chat.retrying') : t('chat.retryAnswer')} aria-busy={retrying} onClick={retry}><RotateCw size={20} className={retrying ? 'is-spinning' : undefined} /></button>
        <button type="button" aria-label={copied ? t('chat.copied') : t('chat.copy')} onClick={() => void copy()}>{copied ? <Check size={20} /> : <Copy size={20} />}</button>
        <MimoVoiceButton messageId={messageId} content={content} />
      </div>
      <span className="conversation-action-feedback" role="status" aria-live="polite">{notice}</span>
    </div>
  )
}

function MessageRetryAction({ onRetry }: { onRetry: () => void }) {
  const { t } = useLocale()
  return (
    <button type="button" className="conversation-retry-action" onClick={onRetry}>
      <RotateCw size={18} aria-hidden="true" />
      <span>{t('chat.retryAnswer')}</span>
    </button>
  )
}

export default function ChatPage() {
  const { t } = useLocale()
  const [messages, setMessages] = useState<Message[]>([])
  const [project, setProject] = useState<Project | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [intakeNotice, setIntakeNotice] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [uploadingFiles, setUploadingFiles] = useState(false)
  const [attachedFileNames, setAttachedFileNames] = useState<string[]>([])
  const [actionBusy, setActionBusy] = useState<string | null>(null)
  const [activeEstimate, setActiveEstimate] = useState<Estimate | null>(null)
  const [activeDocument, setActiveDocument] = useState<Document | null>(null)
  const [openClarificationKey, setOpenClarificationKey] = useState<string | null>(null)
  const { menu: capabilityMenu, loading: capabilitiesLoading } = useCapabilities()
  const { mode } = useExecutionMode()
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!openClarificationKey) return
    const frame = window.requestAnimationFrame(() => {
      const scroller = document.querySelector<HTMLElement>('.assistant-ui-thread-viewport')
      const card = scroller?.querySelector<HTMLElement>('.estimate-clarification-card')
      if (scroller && card) {
        const top = card.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop
        scroller.scrollTop = Math.max(0, top - 12)
      }
    })
    return () => window.cancelAnimationFrame(frame)
  }, [openClarificationKey])
  const autoSentRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)
  const activeAssistantRef = useRef<string | null>(null)
  const activeServerMessageRef = useRef<string | null>(null)
  const activeProjectRef = useRef<string | null>(null)
  const activeResponseRef = useRef<string | null>(null)
  const cancelInFlightRef = useRef(false)
  const activeAssistantContentRef = useRef('')
  const previousResponseRef = useRef<string | null>(null)
  const draftProjectKeyRef = useRef(createUuid())
  const skipLoadProjectRef = useRef<string | null>(null)
  const routeSnapshotRef = useRef<ConversationRouteSnapshot>({ initialized: false, projectId: null })
  const verifiedObjectUrlsRef = useRef(new Set<string>())
  const navigate = useNavigate()
  const { projectId: routeProjectId } = useParams<{ projectId?: string }>()
  const [searchParams] = useSearchParams()
  const { createProject, remember, refresh } = useProjectHistory()
  useEffect(() => {
    window.dispatchEvent(new CustomEvent('kolibri:conversation-state', { detail: { populated: messages.length > 0 } }))
  }, [messages.length])

  useEffect(() => () => {
    window.dispatchEvent(new CustomEvent('kolibri:conversation-state', { detail: { populated: false } }))
  }, [])

  useEffect(() => {
    const activeUrls = new Set(messages.flatMap(message => {
      const artifact = message.artifact
      if (artifact?.type === 'image' && isVerifiedImageArtifact(artifact.value)) return [artifact.value.object_url]
      if (artifact?.type === 'file' && isVerifiedFileArtifact(artifact.value)) return [artifact.value.object_url]
      return []
    }))
    for (const url of verifiedObjectUrlsRef.current) {
      if (!activeUrls.has(url)) {
        URL.revokeObjectURL(url)
        verifiedObjectUrlsRef.current.delete(url)
      }
    }
    activeUrls.forEach(url => verifiedObjectUrlsRef.current.add(url))
  }, [messages])

  useEffect(() => () => {
    verifiedObjectUrlsRef.current.forEach(url => URL.revokeObjectURL(url))
    verifiedObjectUrlsRef.current.clear()
  }, [])

  useEffect(() => {
    let active = true
    const nextProjectId = routeProjectId ?? null
    const routeAction = conversationRouteAction(
      routeSnapshotRef.current,
      nextProjectId,
      skipLoadProjectRef.current,
    )
    routeSnapshotRef.current = { initialized: true, projectId: nextProjectId }
    if (routeAction === 'preserve') {
      if (routeProjectId && skipLoadProjectRef.current === routeProjectId) skipLoadProjectRef.current = null
      activeProjectRef.current = nextProjectId
      return () => { active = false }
    }
    if (routeProjectId && skipLoadProjectRef.current === routeProjectId) {
      skipLoadProjectRef.current = null
      activeProjectRef.current = routeProjectId
      return () => { active = false }
    }
    // Changing the visible chat must not cancel work that already belongs to
    // another durable project. The original request keeps persisting its
    // result while this screen loads the newly selected conversation.
    activeAssistantRef.current = null
    activeServerMessageRef.current = null
    activeProjectRef.current = routeProjectId ?? null
    if (routeAction === 'reset') {
      previousResponseRef.current = null
      draftProjectKeyRef.current = createUuid()
      queueMicrotask(() => {
        if (!active) return
        setProject(null)
        setMessages([])
        setHistoryError(null)
        setHistoryLoading(false)
        setLoading(false)
      })
      return () => { active = false }
    }
    queueMicrotask(() => {
      if (!active) return
      setProject(null)
      setMessages([])
      setHistoryLoading(true)
      setLoading(false)
    })
    const projectIdToLoad = nextProjectId
    if (!projectIdToLoad) return () => { active = false }
    Promise.all([projectsApi.get(projectIdToLoad), projectsApi.listMessages(projectIdToLoad, { limit: 500 })])
      .then(async ([loadedProject, loadedMessages]) => {
        if (!active) return
        const restored = loadedMessages.items
          .map(restoredMessage)
          .filter((value): value is Message => value !== null)
        const hydrated = await Promise.all(restored.map(async message => {
          const reference = message.artifactReference
          if (!reference || message.artifact) return message
          try {
            const artifact: ConversationArtifact = reference.type === 'image'
              ? { type: 'image', value: await verifyImageArtifact(reference.value) }
              : reference.type === 'file'
                ? { type: 'file', value: await verifyFileArtifact(reference.value) }
                : await hydratePersistedArtifact(reference, {
                estimate: estimates.get,
                document: documents.get,
              })
            return { ...message, artifact }
          } catch {
            // History remains readable if a referenced artifact was removed or
            // fails integrity checks. A fake card is never substituted.
            if (reference.type !== 'image') return message
            return {
              ...message,
              content: responseFailureMessage({
                status: 'failed',
                error_code: 'image_artifact_verification_failed',
                capability: 'image.generate',
              }, t),
              work: {
                stage: 'failed' as const,
                startedAt: message.work?.startedAt ?? Date.now(),
                elapsedSeconds: message.work?.elapsedSeconds ?? 0,
                events: appendWorkSummary(message.work?.events ?? [], {
                  stage: 'artifact_verification',
                  status: 'failed',
                  summary: t('trace.imageVerificationFailed'),
                  artifact_type: 'image',
                  artifact_id: reference.value.id,
                }),
              },
            }
          }
        }))
        let previousPromptExpectsImage = false
        const safeHydrated = hydrated.map(message => {
          if (message.role === 'user') {
            previousPromptExpectsImage = expectsImageArtifact(message.content)
            return message
          }
          if (!previousPromptExpectsImage
            || message.artifact?.type === 'image'
            || message.work?.stage !== 'completed') return message
          return {
            ...message,
            content: responseFailureMessage({
              status: 'failed',
              error_code: 'image_artifact_verification_failed',
              capability: 'image.generate',
            }, t),
            work: message.work ? { ...message.work, stage: 'failed' as const } : undefined,
          }
        })
        if (!active) return
        setProject(loadedProject)
        remember(loadedProject)
        setMessages(safeHydrated)
        previousResponseRef.current = latestResponseId(loadedMessages.items)
        setHistoryError(null)
      })
      .catch(cause => {
        if (!active) return
        setHistoryError(cause instanceof Error ? cause.message : 'Не удалось загрузить историю проекта')
      })
      .finally(() => { if (active) setHistoryLoading(false) })
    return () => { active = false }
  }, [remember, routeProjectId, t])

  useEffect(() => {
    if (!loading) return
    const timer = window.setInterval(() => {
      setMessages(current => current.map(message => message.work?.stage === 'dispatching' || message.work?.stage === 'streaming'
        ? { ...message, work: { ...message.work, elapsedSeconds: Math.floor((Date.now() - message.work.startedAt) / 1000) } }
        : message))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [loading])

  const handleSendMessage = useCallback(async (rawText: string) => {
    const text = rawText.trim()
    if (!text || loading) return
    if (requiresProjectDocuments(text)) {
      const sourceProjectId = project?.id ?? routeProjectId
      let hasDocuments = false
      if (sourceProjectId) {
        try {
          const sourceDocuments = await projectDocuments.list(sourceProjectId)
          hasDocuments = sourceDocuments.items.length > 0
        } catch {
          hasDocuments = false
        }
      }
      if (!hasDocuments) {
        setInput(text)
        setIntakeNotice(
          text.toLocaleLowerCase('ru-RU').includes('пров')
            ? 'Сначала выберите файл готовой сметы — без него проверка не начнётся.'
            : 'Сначала загрузите чертежи, PDF или таблицу — без исходного документа расчёт не начнётся.',
        )
        fileInputRef.current?.click()
        return
      }
    }
    const imageExpected = expectsImageArtifact(text)

    const userId = createUuid()
    const userMessage: Message = { id: userId, role: 'user', content: text, timestamp: new Date() }
    const assistantId = createUuid()
    const startedAt = Date.now()
    const assistantMessage: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      work: { stage: 'dispatching', startedAt, elapsedSeconds: 0, events: [] },
    }
    dispatchResponseActivity(assistantId, true, {
      projectId: project?.id ?? routeProjectId,
      startedAt,
    })
    const requestMessages = [...messages, userMessage].map(message => ({ role: message.role, content: message.content }))

    setMessages(current => [...current, userMessage, assistantMessage])
    setInput('')
    setLoading(true)
    const controller = new AbortController()
    abortRef.current = controller
    activeAssistantRef.current = assistantId
    activeResponseRef.current = null
    activeAssistantContentRef.current = ''
    let receivedDelta = false
    let durableProject = project
    let serverAssistantId: string | null = null
    let assistantContent = ''
    let assistantActions: ChatAction[] = []
    let materializedArtifact: ConversationArtifact | null = null
    let workEvents: ChatWorkSummary[] = []
    let artifactFailed = false
    let responseId = previousResponseRef.current
    let lastStreamingPatchAt = 0
    let patchSequence = 0
    let patchQueue: Promise<void> = Promise.resolve()
    let activityOutcome: ResponseActivityOutcome = 'failed'

    if (!durableProject && routeProjectId) {
      try {
        durableProject = await projectsApi.get(routeProjectId)
        setProject(durableProject)
        remember(durableProject)
      } catch (cause) {
        setHistoryError(cause instanceof Error ? cause.message : 'История проекта временно недоступна. Чат продолжает работать.')
      }
    }

    if (!durableProject && !routeProjectId) {
      try {
        durableProject = await createProject(
          { client_request_id: draftProjectKeyRef.current },
          `project:${draftProjectKeyRef.current}`,
        )
        setProject(durableProject)
        activeProjectRef.current = durableProject.id
        skipLoadProjectRef.current = durableProject.id
        navigate(`/chat/${encodeURIComponent(durableProject.id)}`, { replace: true })
      } catch (cause) {
        setHistoryError(cause instanceof Error ? cause.message : 'Не удалось сохранить проект. Чат продолжает работать.')
      }
    }

    if (durableProject) {
      dispatchResponseActivity(assistantId, true, {
        projectId: durableProject.id,
        startedAt,
      })
    }

    if (durableProject) {
      try {
        const persistedUser = await projectsApi.appendMessage(durableProject.id, {
          role: 'user',
          content: text,
          status: 'completed',
          client_message_id: userId,
        }, `message:${userId}`)
        const persistedAssistant = await projectsApi.appendMessage(durableProject.id, {
          role: 'assistant',
          content: '',
          status: 'pending',
          client_message_id: assistantId,
        }, `message:${assistantId}`)
        serverAssistantId = persistedAssistant.id
        activeServerMessageRef.current = persistedAssistant.id
        activeProjectRef.current = durableProject.id
        setMessages(current => current.map(message => {
          if (message.id === userId) return { ...message, serverId: persistedUser.id }
          if (message.id === assistantId) return { ...message, serverId: persistedAssistant.id }
          return message
        }))
        setHistoryError(null)
        void refresh().catch(() => undefined)
      } catch (cause) {
        setHistoryError(cause instanceof Error ? cause.message : 'История не сохранилась. Чат продолжает работать.')
      }
    }

    const persistAssistant = (
      status: ProjectMessageStatus,
      content: string,
      metadata: Record<string, unknown>,
    ) => {
      if (!durableProject || !serverAssistantId) return patchQueue
      const projectId = durableProject.id
      const messageId = serverAssistantId
      const key = `assistant:${messageId}:${status}:${++patchSequence}`
      patchQueue = patchQueue
        .then(() => projectsApi.updateMessage(projectId, messageId, { status, content, metadata }, key))
        .then(() => undefined)
        .catch(cause => {
          setHistoryError(cause instanceof Error ? cause.message : 'Не удалось обновить сохранённый ответ. Чат продолжает работать.')
        })
      return patchQueue
    }

    const persistStreaming = () => {
      const safeContent = safeContentBeforeImageVerification(assistantContent, imageExpected)
      if (!safeContent || Date.now() - lastStreamingPatchAt < 700) return
      lastStreamingPatchAt = Date.now()
      void persistAssistant('streaming', safeContent, buildPersistedConversationMetadata({
        responseId,
        workEvents,
      }))
    }

    const requestOptions = {
      policy: createExecutionPolicy(
        mode,
        capabilityMenu.map(item => item.capability.id),
        imageExpected ? ['image.generate'] : [],
      ),
      project_id: durableProject?.id,
      previous_response_id: previousResponseRef.current ?? undefined,
      idempotencyKey: `response:${assistantId}`,
    }

    let activeDurableResponseId: string | null = null
    let replayingDurableStream = false
    let replayedContent = ''
    const handleStreamEvent = (event: ChatStreamEvent) => {
        const ownsVisibleRequest = activeAssistantRef.current === assistantId
        if (event.response_id) {
          activeDurableResponseId = event.response_id
          responseId = event.response_id
          if (ownsVisibleRequest) {
            activeResponseRef.current = event.response_id
            previousResponseRef.current = event.response_id
          }
        }
        if (event.content) {
          if (replayingDurableStream && event.type === 'response.output_text.delta') {
            replayedContent += event.content
            assistantContent = replayedContent
          } else {
            assistantContent += event.content
          }
          if (ownsVisibleRequest) activeAssistantContentRef.current = assistantContent
          receivedDelta = true
        }
        if (event.actions?.length) {
          assistantActions = event.actions
            .map(normalizePersistedAction)
            .filter((action): action is ChatAction => action !== null)
        }
        const attempt = providerAttemptEvent(event, t)
        if (event.work_summary) workEvents = appendWorkSummary(workEvents, event.work_summary)
        else if (attempt) workEvents = appendWorkSummary(workEvents, attempt)
        if (event.work_summary) {
          dispatchResponseActivity(assistantId, true, {
            projectId: durableProject?.id ?? routeProjectId,
            startedAt,
            summary: event.work_summary.summary,
          })
        }
        const terminal = event.done === true
        const failed = terminal && isFailedResponse(event)
        if (failed && !assistantContent) {
          assistantContent = responseFailureMessage(event, t)
          if (ownsVisibleRequest) activeAssistantContentRef.current = assistantContent
        }
        setMessages(current => current.map(message => {
          if (message.id !== assistantId) return message
          return {
            ...message,
            content: failed
              ? assistantContent
              : safeContentBeforeImageVerification(assistantContent, imageExpected),
            actions: event.actions ? assistantActions : message.actions,
            work: {
              ...message.work!,
              stage: event.status === 'cancelled'
                ? 'cancelled'
                : failed
                  ? 'failed'
                  : terminal
                    ? 'completed'
                    : event.status === 'waiting_for_input' || event.status === 'approval_required'
                      ? 'waiting'
                      : event.work_summary?.stage === 'resuming'
                        ? 'recovering'
                        : 'streaming',
              elapsedSeconds: Math.floor((Date.now() - startedAt) / 1000),
              events: workEvents,
            },
          }
        }))
        if (!terminal) persistStreaming()
    }

    try {
      let finalEvent: ChatStreamEvent
      try {
        finalEvent = await chat.stream(requestMessages, handleStreamEvent, controller.signal, requestOptions)
      } catch (streamError) {
        if (controller.signal.aborted || !activeDurableResponseId) throw streamError
        replayingDurableStream = true
        replayedContent = ''
        finalEvent = await resumeResponseAfterDisconnect(activeDurableResponseId, handleStreamEvent, {
          signal: controller.signal,
        })
        replayingDurableStream = false
      }

      if (finalEvent.response_id) {
        responseId = finalEvent.response_id
        if (activeAssistantRef.current === assistantId) {
          previousResponseRef.current = finalEvent.response_id
        }
      }
      if (finalEvent.actions?.length) {
        assistantActions = finalEvent.actions
          .map(normalizePersistedAction)
          .filter((action): action is ChatAction => action !== null)
      }

      const action = assistantActions.find(shouldAutoMaterializeAction)
      if (action) {
        const startedMaterialization = actionMaterializationEvent(action, 'active', t)
        if (startedMaterialization) {
          workEvents = appendWorkSummary(workEvents, startedMaterialization)
          setMessages(current => current.map(message => message.id === assistantId ? {
            ...message,
            work: {
              ...message.work!,
              stage: 'streaming',
              events: workEvents,
            },
          } : message))
        }
        try {
          const artifact = await materializeConversationAction(action, {
            projectId: durableProject?.id,
            verificationSignal: controller.signal,
          })
          if (artifact) {
            materializedArtifact = artifact
            const completedMaterialization = actionMaterializationEvent(action, 'completed', t)
            if (completedMaterialization) workEvents = appendWorkSummary(workEvents, completedMaterialization)
            assistantActions = []
            setMessages(current => current.map(message => message.id === assistantId ? {
              ...message,
              content: assistantContent,
              artifact,
              actions: [],
              work: {
                ...message.work!,
                stage: 'completed',
                events: workEvents,
              },
            } : message))
          }
        } catch (error) {
          artifactFailed = true
          assistantActions = []
          assistantContent = action.type === 'present_image'
            ? responseFailureMessage({
              status: 'failed',
              error_code: 'image_artifact_verification_failed',
              capability: 'image.generate',
            }, t)
            : t('chat.artifactFailed')
          activeAssistantContentRef.current = assistantContent
          const failedMaterialization = actionMaterializationEvent(action, 'failed', t)
          if (failedMaterialization) {
            workEvents = appendWorkSummary(workEvents, failedMaterialization)
            setMessages(current => current.map(message => message.id === assistantId ? {
              ...message,
              content: assistantContent,
              work: {
                ...message.work!,
                stage: 'failed',
                events: workEvents,
              },
            } : message))
          }
          console.error('Artifact materialization failed', error)
        }
      }
      if (imageExpected && materializedArtifact?.type !== 'image' && !artifactFailed && !isFailedResponse(finalEvent)) {
        artifactFailed = true
        assistantActions = []
        assistantContent = responseFailureMessage({
          status: 'failed',
          error_code: 'image_artifact_verification_failed',
          capability: 'image.generate',
        }, t)
        activeAssistantContentRef.current = assistantContent
        workEvents = appendWorkSummary(workEvents, {
          stage: 'artifact_verification',
          status: 'failed',
          summary: t('trace.imageVerificationFailed'),
          artifact_type: 'image',
        })
        setMessages(current => current.map(message => message.id === assistantId ? {
          ...message,
          content: assistantContent,
          actions: [],
          work: {
            ...message.work!,
            stage: 'failed',
            events: workEvents,
          },
        } : message))
      }
      const finalStatus = persistedResponseStatus(finalEvent.status, artifactFailed, assistantContent, materializedArtifact !== null)
      workEvents = settleWorkSummaries(
        workEvents,
        finalStatus === 'completed'
          ? 'completed'
          : finalStatus === 'cancelled'
            ? 'cancelled'
            : 'failed',
      )
      const finalContent = assistantContent || (finalStatus === 'completed'
        ? assistantContent
        : finalStatus === 'cancelled' ? t('chat.cancelled') : responseFailureMessage(finalEvent, t))
      assistantContent = finalContent
      activeAssistantContentRef.current = finalContent
      setMessages(current => current.map(message => message.id === assistantId ? {
        ...message,
        content: finalContent,
        work: {
          ...message.work!,
          stage: finalStatus === 'completed'
            ? 'completed'
            : finalStatus === 'cancelled'
              ? 'cancelled'
              : 'failed',
          elapsedSeconds: Math.floor((Date.now() - startedAt) / 1000),
          events: workEvents,
        },
      } : message))
      await persistAssistant(finalStatus, finalContent, buildPersistedConversationMetadata({
        responseId,
        workEvents,
        actions: assistantActions,
        artifact: materializedArtifact,
      }))
      activityOutcome = finalStatus === 'completed'
        ? 'completed'
        : finalStatus === 'cancelled'
          ? 'cancelled'
          : 'failed'
    } catch (error) {
      if (controller.signal.aborted) {
        const cancelledContent = assistantContent || t('chat.cancelled')
        await persistAssistant('cancelled', cancelledContent, buildPersistedConversationMetadata({
          responseId,
          workEvents,
          actions: assistantActions,
          artifact: materializedArtifact,
        }))
        activityOutcome = 'cancelled'
        return
      }
      if (!receivedDelta) {
        try {
          const fallback = await chat.send(requestMessages, requestOptions)
          const fallbackFailed = isFailedResponse(fallback)
          assistantContent = fallback.content || responseFailureMessage(fallback, t)
          activeAssistantContentRef.current = assistantContent
          assistantActions = fallbackFailed ? [] : fallback.actions
            .map(normalizePersistedAction)
            .filter((action): action is ChatAction => action !== null)
          const fallbackAction = fallbackFailed
            ? undefined
            : assistantActions.find(shouldAutoMaterializeAction)
          let fallbackArtifact: ConversationArtifact | null = null
          let fallbackArtifactFailed = false
          if (fallbackAction) {
            try {
              const startedMaterialization = actionMaterializationEvent(fallbackAction, 'active', t)
              if (startedMaterialization) workEvents = appendWorkSummary(workEvents, startedMaterialization)
              fallbackArtifact = await materializeConversationAction(fallbackAction, {
                projectId: durableProject?.id,
                verificationSignal: controller.signal,
              })
              materializedArtifact = fallbackArtifact
              const completedMaterialization = actionMaterializationEvent(fallbackAction, 'completed', t)
              if (completedMaterialization) workEvents = appendWorkSummary(workEvents, completedMaterialization)
            } catch (cause) {
              fallbackArtifactFailed = true
              assistantActions = []
              assistantContent = fallbackAction.type === 'present_image'
                ? responseFailureMessage({
                  status: 'failed',
                  error_code: 'image_artifact_verification_failed',
                  capability: 'image.generate',
                }, t)
                : t('chat.artifactFailed')
              activeAssistantContentRef.current = assistantContent
              console.error('Fallback artifact materialization failed', cause)
            }
          }
          const fallbackMissingImage = imageExpected && fallbackArtifact?.type !== 'image' && !fallbackFailed
          if (fallbackMissingImage) {
            assistantActions = []
            assistantContent = responseFailureMessage({
              status: 'failed',
              error_code: 'image_artifact_verification_failed',
              capability: 'image.generate',
            }, t)
            activeAssistantContentRef.current = assistantContent
            workEvents = appendWorkSummary(workEvents, {
              stage: 'artifact_verification',
              status: 'failed',
              summary: t('trace.imageVerificationFailed'),
              artifact_type: 'image',
            })
          }
          const fallbackTerminalFailed = fallbackFailed || fallbackArtifactFailed || fallbackMissingImage
          setMessages(current => current.map(message => message.id === assistantId ? {
            ...message,
            content: assistantContent,
            actions: fallbackArtifact ? [] : assistantActions,
            artifact: fallbackArtifact ?? message.artifact,
            work: {
              ...message.work!,
              stage: fallbackTerminalFailed ? 'failed' : 'completed',
              elapsedSeconds: Math.floor((Date.now() - startedAt) / 1000),
              events: workEvents,
            },
          } : message))
          await persistAssistant(
            fallbackTerminalFailed ? 'failed' : 'completed',
            assistantContent,
            buildPersistedConversationMetadata({
              responseId,
              workEvents,
              actions: fallbackArtifact ? [] : assistantActions,
              artifact: fallbackArtifact,
            }),
          )
          activityOutcome = fallbackTerminalFailed ? 'failed' : 'completed'
          return
        } catch {
          // Keep the same assistant message and expose one recoverable state.
        }
      }
      setMessages(current => current.map(message => message.id === assistantId ? {
        ...message,
        content: message.content || t('chat.connectionLost'),
        work: { ...message.work!, stage: 'failed', elapsedSeconds: Math.floor((Date.now() - startedAt) / 1000) },
      } : message))
      const failedContent = assistantContent || t('chat.connectionLost')
      assistantContent = failedContent
      activeAssistantContentRef.current = failedContent
      await persistAssistant('failed', failedContent, buildPersistedConversationMetadata({
        responseId,
        workEvents,
        actions: assistantActions,
        artifact: materializedArtifact,
      }))
      activityOutcome = 'failed'
      console.error('Chat stream failed', error)
    } finally {
      await patchQueue
      dispatchResponseActivity(assistantId, false, {
        projectId: durableProject?.id,
        startedAt,
        outcome: activityOutcome,
      })
      if (durableProject) void refresh().catch(() => undefined)
      if (abortRef.current === controller) abortRef.current = null
      const ownsActiveRequest = activeAssistantRef.current === assistantId
      if (ownsActiveRequest) activeAssistantRef.current = null
      if (activeServerMessageRef.current === serverAssistantId) activeServerMessageRef.current = null
      if (ownsActiveRequest) {
        activeAssistantContentRef.current = ''
        activeResponseRef.current = null
        setLoading(false)
      }
    }
  }, [capabilityMenu, createProject, loading, messages, mode, navigate, project, refresh, remember, routeProjectId, setInput, t])

  const handleCancel = useCallback(async () => {
    if (cancelInFlightRef.current) return
    const assistantId = activeAssistantRef.current
    const responseId = activeResponseRef.current
    if (!assistantId || !responseId) {
      setHistoryError('Отмена станет доступна после подтверждения задачи сервером.')
      return
    }

    cancelInFlightRef.current = true
    try {
      const cancelled = await responses.cancel(responseId)
      if (cancelled.status !== 'cancelled') throw new Error('cancel_not_confirmed')
      if (activeAssistantRef.current !== assistantId || activeResponseRef.current !== responseId) return

      abortRef.current?.abort()
      abortRef.current = null
      setMessages(current => current.map(message => message.id === assistantId && message.work ? {
        ...message,
        content: message.content || t('chat.cancelled'),
        work: {
          ...message.work,
          stage: 'cancelled',
          elapsedSeconds: Math.floor((Date.now() - message.work.startedAt) / 1000),
          events: appendWorkSummary(message.work.events, {
            stage: 'cancelled',
            status: 'completed',
            summary: t('trace.cancelledByUser'),
          }),
        },
      } : message))
      setHistoryError(null)
      activeAssistantRef.current = null
      activeServerMessageRef.current = null
      activeAssistantContentRef.current = ''
      activeResponseRef.current = null
      setLoading(false)
    } catch (cause) {
      setHistoryError(cause instanceof Error && cause.message !== 'cancel_not_confirmed'
        ? cause.message
        : 'Сервер не подтвердил отмену. Задача продолжает выполняться.')
    } finally {
      cancelInFlightRef.current = false
    }
  }, [t])

  const selectCapability = (key: UiCapabilityKey) => {
    if (key === 'file.search') {
      fileInputRef.current?.click()
      return
    }
    setInput(capabilityPrompt(key))
  }

  const attachFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    if (!files.length || uploadingFiles) return
    setUploadingFiles(true)
    setHistoryError(null)
    setIntakeNotice(null)
    try {
      let durableProject = project
      if (!durableProject && routeProjectId) {
        durableProject = await projectsApi.get(routeProjectId)
      }
      if (!durableProject) {
        durableProject = await createProject(
          { client_request_id: draftProjectKeyRef.current },
          `project:${draftProjectKeyRef.current}`,
        )
        skipLoadProjectRef.current = durableProject.id
        navigate(`/chat/${encodeURIComponent(durableProject.id)}`, { replace: true })
      }
      setProject(durableProject)
      remember(durableProject)
      for (const file of files) {
        await projectDocuments.upload(durableProject.id, file)
      }
      setAttachedFileNames(files.map(file => file.name))
      setInput(current => current || capabilityPrompt('file.search'))
      setIntakeNotice(`Прикреплено файлов: ${files.length}. Теперь запрос можно отправить.`)
    } catch (cause) {
      setIntakeNotice(
        cause instanceof Error
          ? cause.message
          : 'Файлы не загрузились. Повторите попытку.',
      )
    } finally {
      setUploadingFiles(false)
    }
  }

  useEffect(() => {
    const prompt = searchParams.get('q')
    if (!prompt || autoSentRef.current || capabilitiesLoading || historyLoading) return
    autoSentRef.current = true
    void handleSendMessage(prompt)
  }, [capabilitiesLoading, handleSendMessage, historyLoading, searchParams])

  const handleAction = async (messageId: string, action: ChatAction) => {
    const actionKey = `${messageId}:${action.type}`
    if (actionBusy) return
    setActionBusy(actionKey)
    try {
      const validatedAction = normalizePersistedAction(action)
      if (!validatedAction?.data) return
      if (validatedAction.type === 'create_estimate') {
        if (estimateActionNeedsClarification(validatedAction)) {
          setOpenClarificationKey(current => current === actionKey ? null : actionKey)
          return
        }
      }
      const artifact = await materializeConversationAction(validatedAction, {
        projectId: project?.id,
      })
      if (!artifact) return
      setMessages(current => current.map(message => message.id === messageId ? {
        ...message,
        artifact,
        actions: [],
      } : message))
      if (artifact.type === 'estimate') setActiveEstimate(artifact.value)
      if (artifact.type === 'document') setActiveDocument(artifact.value)
    } finally {
      setActionBusy(null)
    }
  }
  const composerTools: ComposerTool[] = capabilityMenu.length > 0
    ? capabilityMenu.map(item => ({
        key: item.key,
        title: item.title,
        description: item.description,
        icon: capabilityIcons[item.key],
      }))
    : fallbackComposerTools

  return (
    <section className={`conversation-page ${loading ? 'is-working' : ''}`}>
      <header className="conversation-project-header">
        <div>
          <p>{t('chat.currentProject')}</p>
          <h1>{project?.title ?? (messages.length ? t('chat.newProject') : 'Kolibri')}</h1>
        </div>
      </header>

      <input
        ref={fileInputRef}
        className="sr-only"
        type="file"
        multiple
        accept=".pdf,.xlsx,.docx,.csv,.txt,.png,.jpg,.jpeg,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/csv,text/plain,image/png,image/jpeg"
        onChange={event => void attachFiles(event)}
      />
      <AssistantConversationThread
        messages={messages}
        busy={loading}
        sendDisabled={uploadingFiles || capabilitiesLoading || historyLoading}
        pendingComposerText={input}
        onPendingComposerTextApplied={() => setInput('')}
        onSend={handleSendMessage}
        onCancel={handleCancel}
        tools={composerTools}
        onTool={selectCapability}
        onAttach={() => fileInputRef.current?.click()}
        placeholder={uploadingFiles ? 'Загружаю файлы…' : t('composer.placeholder')}
        emptyState={(
          <div className="conversation-empty">
            <h2>{t('home.title')}</h2>
          </div>
        )}
        statusArea={(
          <>
            {historyLoading && (
              <p role="status" className="mx-auto w-full max-w-3xl px-5 py-2 text-[13px] text-[var(--text-tertiary)]">{t('chat.loadingHistory')}</p>
            )}
            {historyError && (
              <div role="status" className="mx-auto flex w-full max-w-3xl items-center gap-3 px-5 py-2 text-[13px] text-[var(--text-secondary)]">
                <span className="min-w-0 flex-1">{t('chat.historyUnavailable')}</span>
                <button type="button" className="shrink-0 font-medium text-[var(--text-primary)]" onClick={() => void refresh().catch(() => undefined)}>{t('common.retry')}</button>
              </div>
            )}
            {intakeNotice && (
              <div role="status" className="mx-auto w-full max-w-3xl px-5 py-2 text-[14px] text-[var(--text-secondary)]">
                {intakeNotice}
              </div>
            )}
          </>
        )}
        composerPrefix={attachedFileNames.length > 0 ? (
          <div className="conversation-attachment-list" role="status" aria-live="polite">
            {attachedFileNames.map(name => (
              <span key={name}><FileText size={15} aria-hidden="true" />{name}</span>
            ))}
          </div>
        ) : undefined}
        renderMessage={(message, messageIndex) => (
          <article key={message.id} className={`conversation-message ${message.role}`}>
                <div className="conversation-message-meta">{message.role === 'user' ? t('chat.you') : 'Kolibri'}</div>
                {message.work && <WorkTrace stage={message.work.stage} elapsedSeconds={message.work.elapsedSeconds} events={message.work.events} />}
                {message.content && (
                  message.role === 'assistant'
                    ? <div className="conversation-message-content conversation-message-markdown"><ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          table: ({ children }) => (
                            <div className="conversation-markdown-table-scroll">
                              <table>{children}</table>
                            </div>
                          ),
                        }}
                      >{message.content}</ReactMarkdown></div>
                    : <p className="conversation-message-content">{message.content}</p>
                )}
                {!message.artifact && isEstimateCreating(message) && (
                  <div className="artifact-card artifact-card--loading" data-testid="estimate-loading-card">
                    <div className="artifact-card-header">
                      <PencilLine size={18} />
                      <span className="artifact-card-title">Смета</span>
                      <span className="artifact-card-status artifact-card-status--loading">Формируется...</span>
                    </div>
                    <div className="artifact-card-body">
                      <div className="artifact-card-skeleton" />
                      <div className="artifact-card-skeleton artifact-card-skeleton--short" />
                      <div className="artifact-card-skeleton artifact-card-skeleton--medium" />
                    </div>
                  </div>
                )}
                {message.artifact && (
                  <ArtifactCard
                    artifact={message.artifact}
                    onUpdate={artifact => {
                      setMessages(current => current.map(item => item.id === message.id ? { ...item, artifact } : item))
                      if (artifact.type === 'estimate') setActiveEstimate(current => current?.id === artifact.value.id ? artifact.value : current)
                    }}
                    onOpen={() => {
                      if (!message.artifact) return
                      if (message.artifact.type === 'image') {
                        if (isVerifiedImageArtifact(message.artifact.value)) {
                          window.open(message.artifact.value.object_url, '_blank', 'noopener,noreferrer')
                        }
                      } else if (message.artifact.type === 'file') {
                        if (isVerifiedFileArtifact(message.artifact.value)) {
                          window.open(message.artifact.value.preview_url || message.artifact.value.object_url, '_blank', 'noopener,noreferrer')
                        }
                      } else if (message.artifact.type === 'estimate') {
                        setActiveEstimate(message.artifact.value)
                      } else {
                        setActiveDocument(message.artifact.value)
                      }
                    }}
                    onRetry={message.artifact.type === 'image' ? () => {
                      const previous = messages.slice(0, messageIndex).reverse().find(item => item.role === 'user')
                      if (previous) void handleSendMessage(previous.content)
                    } : undefined}
                  />
                )}
                {message.actions?.some(action => action.type !== 'present_image') && (
                  <div className="conversation-actions">
                    {message.actions.filter(action => action.type !== 'present_image').map((action, index) => (
                      <div className="conversation-action-group" key={`${action.type}-${index}`}>
                        <ActionButton
                          action={action}
                          busy={actionBusy === `${message.id}:${action.type}`}
                          onRun={() => void handleAction(message.id, action)}
                        />
                        {action.type === 'create_estimate'
                          && estimateActionNeedsClarification(action)
                          && openClarificationKey === `${message.id}:${action.type}` && (
                            <EstimateClarificationCard
                              questions={estimateClarificationQuestions(action)}
                              onAnswer={selected => {
                                setInput(`Заполню выбранные данные:\n${selected.map(question => `• ${question}`).join('\n')}\n`)
                                document.querySelector<HTMLTextAreaElement>('.conversation-composer-input')?.focus()
                              }}
                              onSkip={() => {
                                setInput('Продолжай без недостающих данных. Оставь незаполненные поля пустыми.')
                                document.querySelector<HTMLTextAreaElement>('.conversation-composer-input')?.focus()
                              }}
                            />
                          )}
                      </div>
                    ))}
                  </div>
                )}
                {message.role === 'assistant' && message.content && message.work?.stage === 'completed' && message.artifact?.type !== 'image' && (
                  <>
                    <MessageActions
                      messageId={message.id}
                      content={message.content}
                      onRetry={() => {
                        const previous = messages.slice(0, messageIndex).reverse().find(item => item.role === 'user')
                        if (previous) void handleSendMessage(previous.content)
                      }}
                    />
                    <p className="conversation-answer-disclaimer">{t('chat.disclaimer')}</p>
                  </>
                )}
                {message.role === 'assistant' && (message.work?.stage === 'failed' || message.work?.stage === 'cancelled') && (
                  <MessageRetryAction
                    onRetry={() => {
                      const previous = messages.slice(0, messageIndex).reverse().find(item => item.role === 'user')
                      if (previous) void handleSendMessage(previous.content)
                    }}
                  />
                )}
          </article>
        )}
      />
      {activeEstimate && <ConversationEstimateSheet estimate={activeEstimate} onClose={() => setActiveEstimate(null)} />}
      {activeDocument && (
        <InPlaceDocumentWorkspace
          document={activeDocument}
          onClose={() => setActiveDocument(null)}
          onSaved={setActiveDocument}
        />
      )}
    </section>
  )
}
