import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Copy, FileText, Image as ImageIcon, PencilLine, RotateCw, ThumbsDown, ThumbsUp, Volume2 } from 'lucide-react'
import Composer from '@/features/conversation/Composer'
import ArtifactCard, { type ConversationArtifact } from '@/features/conversation/ArtifactCard'
import { normalizeImageArtifact } from '@/features/conversation/imageArtifact'
import { isFailedResponse, persistedResponseStatus, responseFailureMessage } from '@/features/conversation/responseState'
import WorkTrace, { type WorkStage } from '@/features/conversation/WorkTrace'
import CartoonMascot from '@/components/CartoonMascot'
import { capabilityPrompt, useCapabilities, type UiCapabilityKey } from '@/features/capabilities'
import { createExecutionPolicy } from '@/features/shell/executionPolicy'
import { useExecutionMode } from '@/features/shell/executionPolicyContext'
import { useProjectHistory } from '@/features/projects/projectHistoryContext'
import { latestResponseId, serverMessageStatus } from '@/features/projects/historyState'
import { conversationRouteAction, type ConversationRouteSnapshot } from '@/features/projects/conversationRoute'
import {
  buildPersistedConversationMetadata,
  hydratePersistedArtifact,
  imageArtifactFromReference,
  normalizePersistedAction,
  restoreConversationMetadata,
  type PersistedArtifactReference,
} from '@/features/projects/persistedConversation'
import {
  chat,
  documents,
  estimates,
  projects as projectsApi,
  responses,
  type ChatAction,
  type ChatStreamEvent,
  type ChatWorkSummary,
  type Project,
  type ProjectMessage,
  type ProjectMessageStatus,
} from '@/lib/api'
import { createUuid } from '@/lib/uuid'
import { LocalizedMultiline, useLocale, type Translate } from '@/features/localization'

function normalizeEstimateAction(data: Record<string, unknown>): Parameters<typeof estimates.create>[0] {
  const sections = Array.isArray(data.sections) ? data.sections : []
  return {
    title: String(data.title || 'Предварительная смета'),
    client: typeof data.client === 'string' ? data.client : '',
    object_name: typeof data.object_name === 'string' ? data.object_name : '',
    region: typeof data.region === 'string' ? data.region : '',
    currency: typeof data.currency === 'string' ? data.currency : 'RUB',
    overhead_rate: typeof data.overhead_rate === 'string' ? data.overhead_rate : '0',
    vat_rate: typeof data.vat_rate === 'string' ? data.vat_rate : '22',
    sections: sections.map(sectionValue => {
      const section = sectionValue && typeof sectionValue === 'object' ? sectionValue as Record<string, unknown> : {}
      const positions = Array.isArray(section.positions) ? section.positions : []
      return {
        title: String(section.title || 'Раздел'),
        positions: positions.map(positionValue => {
          const position = positionValue && typeof positionValue === 'object' ? positionValue as Record<string, unknown> : {}
          return {
            code: String(position.code || ''),
            name: String(position.name || 'Позиция'),
            unit: String(position.unit || 'шт'),
            quantity: String(position.quantity ?? '0'),
            price: String(position.price ?? '0'),
            source: typeof position.source === 'string' ? position.source : '',
            comment: typeof position.comment === 'string' ? position.comment : '',
          }
        }),
      }
    }),
  }
}

async function materializeAction(action: ChatAction): Promise<ConversationArtifact | null> {
  const validatedAction = normalizePersistedAction(action)
  if (!validatedAction?.data) return null
  if (validatedAction.type === 'create_estimate') {
    return { type: 'estimate', value: await estimates.create(normalizeEstimateAction(validatedAction.data)) }
  }
  if (validatedAction.type === 'create_document') {
    return { type: 'document', value: await documents.create(validatedAction.data as unknown as Parameters<typeof documents.create>[0]) }
  }
  if (validatedAction.type === 'present_image') {
    return { type: 'image', value: normalizeImageArtifact(validatedAction.data) }
  }
  return null
}

function appendWorkSummary(events: ChatWorkSummary[], next: ChatWorkSummary): ChatWorkSummary[] {
  const previous = events.at(-1)
  if (previous
    && previous.stage === next.stage
    && previous.status === next.status
    && previous.summary === next.summary
    && previous.provider === next.provider
    && previous.model === next.model
    && previous.artifact_id === next.artifact_id) {
    return events
  }
  return [...events, next]
}

function artifactMaterializationEvent(
  action: ChatAction,
  status: ChatWorkSummary['status'],
  t: Translate,
): ChatWorkSummary | null {
  if (action.type === 'create_estimate') {
    return {
      stage: 'artifact_materialization',
      status,
      summary: status === 'active'
        ? t('trace.estimateSaving')
        : status === 'completed'
          ? t('trace.estimateSaved')
          : t('trace.estimateSaveFailed'),
      artifact_type: 'estimate',
    }
  }
  if (action.type === 'create_document') {
    return {
      stage: 'artifact_materialization',
      status,
      summary: status === 'active'
        ? t('trace.documentSaving')
        : status === 'completed'
          ? t('trace.documentSaved')
          : t('trace.documentSaveFailed'),
      artifact_type: 'document',
    }
  }
  if (action.type === 'present_image' && status === 'failed') {
    return {
      stage: 'artifact_verification',
      status: 'failed',
      summary: t('trace.imageVerificationFailed'),
      artifact_type: 'image',
      artifact_id: typeof action.data?.id === 'string' ? action.data.id : undefined,
    }
  }
  return null
}

function providerAttemptEvent(event: ChatStreamEvent, t: Translate): ChatWorkSummary | null {
  if (!event.provider_event || event.provider_event.type !== 'provider.attempt.failed') return null
  return {
    stage: 'provider_attempt',
    status: 'failed',
    summary: event.provider_event.will_retry
      ? t('trace.routeRetrying')
      : t('trace.routeFailed'),
    provider: event.provider_event.provider,
    model: event.provider_event.model,
  }
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

function restoredMessage(message: ProjectMessage): Message | null {
  if (message.role !== 'user' && message.role !== 'assistant') return null
  const metadata = restoreConversationMetadata(message.metadata)
  const stage = message.role === 'assistant' ? serverMessageStatus(message.status) : undefined
  return {
    id: message.id,
    serverId: message.id,
    role: message.role,
    content: message.content,
    actions: metadata.actions.length ? metadata.actions : undefined,
    artifact: imageArtifactFromReference(metadata.artifact),
    artifactReference: metadata.artifact,
    timestamp: new Date(message.created_at),
    work: stage ? {
      stage,
      startedAt: Date.parse(message.created_at) || Date.now(),
      elapsedSeconds: 0,
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

function MessageActions({ content, onRetry }: { content: string; onRetry: () => void }) {
  const { locale, t } = useLocale()
  const [rating, setRating] = useState<'up' | 'down' | null>(null)
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    await navigator.clipboard.writeText(content)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }

  const speak = () => {
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(content)
    utterance.lang = locale === 'en' ? 'en-US' : 'ru-RU'
    window.speechSynthesis.speak(utterance)
  }

  return (
    <div className="conversation-message-actions" aria-label={t('chat.answerActions')}>
      <button type="button" aria-label={t('chat.helpful')} aria-pressed={rating === 'up'} onClick={() => setRating(current => current === 'up' ? null : 'up')}><ThumbsUp size={21} /></button>
      <button type="button" aria-label={t('chat.inaccurate')} aria-pressed={rating === 'down'} onClick={() => setRating(current => current === 'down' ? null : 'down')}><ThumbsDown size={21} /></button>
      <button type="button" aria-label={t('chat.retryAnswer')} onClick={onRetry}><RotateCw size={20} /></button>
      <button type="button" aria-label={copied ? t('chat.copied') : t('chat.copy')} onClick={() => void copy()}><Copy size={20} /></button>
      <button type="button" aria-label={t('chat.speak')} onClick={speak}><Volume2 size={22} /></button>
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
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [actionBusy, setActionBusy] = useState<string | null>(null)
  const { menu: capabilityMenu, loading: capabilitiesLoading } = useCapabilities()
  const { mode } = useExecutionMode()
  const bottomRef = useRef<HTMLDivElement>(null)
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
  const navigate = useNavigate()
  const { projectId: routeProjectId } = useParams<{ projectId?: string }>()
  const [searchParams] = useSearchParams()
  const { createProject, remember, refresh } = useProjectHistory()
  const suggestions = [t('home.suggestionEstimate'), t('home.suggestionContract')]

  useEffect(() => {
    window.dispatchEvent(new CustomEvent('kolibri:conversation-state', { detail: { populated: messages.length > 0 } }))
  }, [messages.length])

  useEffect(() => () => {
    window.dispatchEvent(new CustomEvent('kolibri:conversation-state', { detail: { populated: false } }))
  }, [])

  useEffect(() => () => abortRef.current?.abort(), [])

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
    abortRef.current?.abort()
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
            const artifact = await hydratePersistedArtifact(reference, {
              estimate: estimates.get,
              document: documents.get,
            })
            return { ...message, artifact }
          } catch {
            // History remains readable if a referenced artifact was removed or
            // fails integrity checks. A fake card is never substituted.
            return message
          }
        }))
        if (!active) return
        setProject(loadedProject)
        remember(loadedProject)
        setMessages(hydrated)
        previousResponseRef.current = latestResponseId(loadedMessages.items)
        setHistoryError(null)
      })
      .catch(cause => {
        if (!active) return
        setHistoryError(cause instanceof Error ? cause.message : 'Не удалось загрузить историю проекта')
      })
      .finally(() => { if (active) setHistoryLoading(false) })
    return () => { active = false }
  }, [remember, routeProjectId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: loading ? 'auto' : 'smooth' })
  }, [messages, loading])

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
      if (!assistantContent || Date.now() - lastStreamingPatchAt < 700) return
      lastStreamingPatchAt = Date.now()
      void persistAssistant('streaming', assistantContent, buildPersistedConversationMetadata({
        responseId,
        workEvents,
      }))
    }

    const requestOptions = {
      policy: createExecutionPolicy(mode, capabilityMenu.map(item => item.capability.id)),
      project_id: durableProject?.id,
      previous_response_id: previousResponseRef.current ?? undefined,
      idempotencyKey: `response:${assistantId}`,
    }

    try {
      const finalEvent = await chat.stream(requestMessages, event => {
        if (event.response_id) {
          responseId = event.response_id
          activeResponseRef.current = event.response_id
          previousResponseRef.current = event.response_id
        }
        if (event.content) {
          assistantContent += event.content
          activeAssistantContentRef.current = assistantContent
          receivedDelta = true
        }
        if (event.actions) {
          assistantActions = event.actions
            .map(normalizePersistedAction)
            .filter((action): action is ChatAction => action !== null)
        }
        const attempt = providerAttemptEvent(event, t)
        if (event.work_summary) workEvents = appendWorkSummary(workEvents, event.work_summary)
        else if (attempt) workEvents = appendWorkSummary(workEvents, attempt)
        const terminal = event.done === true
        const failed = terminal && isFailedResponse(event)
        if (failed && !assistantContent) {
          assistantContent = responseFailureMessage(event, t)
          activeAssistantContentRef.current = assistantContent
        }
        setMessages(current => current.map(message => {
          if (message.id !== assistantId) return message
          return {
            ...message,
            content: assistantContent,
            actions: event.actions ? assistantActions : message.actions,
            work: {
              ...message.work!,
              stage: event.status === 'cancelled' ? 'cancelled' : failed ? 'failed' : terminal ? 'completed' : 'streaming',
              elapsedSeconds: Math.floor((Date.now() - startedAt) / 1000),
              events: workEvents,
            },
          }
        }))
        if (!terminal) persistStreaming()
      }, controller.signal, requestOptions)

      if (finalEvent.response_id) {
        responseId = finalEvent.response_id
        previousResponseRef.current = finalEvent.response_id
      }
      if (finalEvent.actions) {
        assistantActions = finalEvent.actions
          .map(normalizePersistedAction)
          .filter((action): action is ChatAction => action !== null)
      }

      const action = assistantActions.find(item => ['create_estimate', 'create_document', 'present_image'].includes(item.type))
      if (action) {
        const startedMaterialization = artifactMaterializationEvent(action, 'active', t)
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
          const artifact = await materializeAction(action)
          if (artifact) {
            materializedArtifact = artifact
            const completedMaterialization = artifactMaterializationEvent(action, 'completed', t)
            if (completedMaterialization) workEvents = appendWorkSummary(workEvents, completedMaterialization)
            assistantActions = []
            setMessages(current => current.map(message => message.id === assistantId ? {
              ...message,
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
          const failedMaterialization = artifactMaterializationEvent(action, 'failed', t)
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
      const finalStatus = persistedResponseStatus(finalEvent.status, artifactFailed, assistantContent)
      const finalContent = assistantContent || (finalStatus === 'completed'
        ? assistantContent
        : finalStatus === 'cancelled' ? t('chat.cancelled') : responseFailureMessage(finalEvent, t))
      assistantContent = finalContent
      activeAssistantContentRef.current = finalContent
      await persistAssistant(finalStatus, finalContent, buildPersistedConversationMetadata({
        responseId,
        workEvents,
        actions: assistantActions,
        artifact: materializedArtifact,
      }))
    } catch (error) {
      if (controller.signal.aborted) {
        const cancelledContent = assistantContent || t('chat.cancelled')
        await persistAssistant('cancelled', cancelledContent, buildPersistedConversationMetadata({
          responseId,
          workEvents,
          actions: assistantActions,
          artifact: materializedArtifact,
        }))
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
            : assistantActions.find(item => ['create_estimate', 'create_document', 'present_image'].includes(item.type))
          let fallbackArtifact: ConversationArtifact | null = null
          let fallbackArtifactFailed = false
          if (fallbackAction) {
            try {
              fallbackArtifact = await materializeAction(fallbackAction)
              materializedArtifact = fallbackArtifact
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
          const fallbackTerminalFailed = fallbackFailed || fallbackArtifactFailed
          setMessages(current => current.map(message => message.id === assistantId ? {
            ...message,
            content: assistantContent,
            actions: fallbackArtifact ? [] : assistantActions,
            artifact: fallbackArtifact ?? message.artifact,
            work: { ...message.work!, stage: fallbackTerminalFailed ? 'failed' : 'completed', elapsedSeconds: Math.floor((Date.now() - startedAt) / 1000) },
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
      console.error('Chat stream failed', error)
    } finally {
      await patchQueue
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
  }, [capabilityMenu, createProject, loading, messages, mode, navigate, project, refresh, remember, routeProjectId, t])

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
    setInput(capabilityPrompt(key))
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
      if (action.type === 'create_estimate' && action.data) {
        const created = await estimates.create(action.data as unknown as Parameters<typeof estimates.create>[0])
        navigate(`/estimates?edit=${created.id}`)
      } else if (action.type === 'create_document' && action.data) {
        const created = await documents.create(action.data as unknown as Parameters<typeof documents.create>[0])
        navigate(`/documents?edit=${created.id}`)
      } else if (action.type === 'present_image' && action.data) {
        window.open(normalizeImageArtifact(action.data).url, '_blank', 'noopener,noreferrer')
      }
    } finally {
      setActionBusy(null)
    }
  }

  return (
    <section className={`conversation-page ${loading ? 'is-working' : ''}`}>
      <header className="conversation-project-header">
        <div>
          <p>{t('chat.currentProject')}</p>
          <h1>{project?.title ?? (messages.length ? t('chat.newProject') : 'Kolibri')}</h1>
        </div>
      </header>

      {historyLoading && (
        <p role="status" className="mx-auto w-full max-w-3xl px-5 py-2 text-[13px] text-[var(--text-tertiary)]">{t('chat.loadingHistory')}</p>
      )}
      {historyError && (
        <div role="status" className="mx-auto flex w-full max-w-3xl items-center gap-3 px-5 py-2 text-[13px] text-[var(--text-secondary)]">
          <span className="min-w-0 flex-1">{t('chat.historyUnavailable')}</span>
          <button type="button" className="shrink-0 font-medium text-[var(--accent-teal)]" onClick={() => void refresh().catch(() => undefined)}>{t('common.retry')}</button>
        </div>
      )}

      <div className="conversation-scroll">
        {messages.length === 0 ? (
          <div className="conversation-empty">
            <p className="conversation-eyebrow">{t('chat.newProject')}</p>
            <CartoonMascot size={34} className="conversation-empty-mascot" />
            <h2><span className="conversation-empty-desktop-title">{t('chat.start')}</span><span className="conversation-empty-mobile-title"><LocalizedMultiline text={t('chat.mobileStart')} /></span></h2>
            <p>{t('chat.emptyCopy')}</p>
            <div className="conversation-suggestions">
              {suggestions.map(suggestion => (
                <button key={suggestion} type="button" onClick={() => void handleSendMessage(suggestion)}>{suggestion}</button>
              ))}
            </div>
          </div>
        ) : (
          <div className="conversation-thread">
            {messages.map((message, messageIndex) => (
              <article key={message.id} className={`conversation-message ${message.role}`}>
                <div className="conversation-message-meta">{message.role === 'user' ? t('chat.you') : 'Kolibri'}</div>
                {message.work && <WorkTrace stage={message.work.stage} elapsedSeconds={message.work.elapsedSeconds} events={message.work.events} />}
                {message.content && (
                  message.role === 'assistant'
                    ? <div className="conversation-message-content conversation-message-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div>
                    : <p className="conversation-message-content">{message.content}</p>
                )}
                {message.artifact && (
                  <ArtifactCard
                    artifact={message.artifact}
                    onOpen={() => {
                      if (!message.artifact) return
                      if (message.artifact.type === 'image') {
                        window.open(message.artifact.value.url, '_blank', 'noopener,noreferrer')
                      } else {
                        navigate(message.artifact.type === 'estimate'
                          ? `/estimates?edit=${message.artifact.value.id}`
                          : `/documents?edit=${message.artifact.value.id}`)
                      }
                    }}
                  />
                )}
                {message.actions && message.actions.length > 0 && (
                  <div className="conversation-actions">
                    {message.actions.map((action, index) => (
                      <ActionButton
                        key={`${action.type}-${index}`}
                        action={action}
                        busy={actionBusy === `${message.id}:${action.type}`}
                        onRun={() => void handleAction(message.id, action)}
                      />
                    ))}
                  </div>
                )}
                {message.role === 'assistant' && message.content && message.work?.stage === 'completed' && (
                  <>
                    <MessageActions
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
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="conversation-dock">
        <Composer
          value={input}
          onChange={setInput}
          onSend={() => void handleSendMessage(input)}
          onEstimate={() => setInput(`${t('home.suggestionEstimate')}: `)}
          onDocument={() => setInput(`${t('home.suggestionContract')}: `)}
          capabilities={capabilityMenu}
          onCapability={selectCapability}
          onCancel={handleCancel}
          busy={loading}
          placeholder={t('composer.placeholder')}
        />
      </div>
    </section>
  )
}
