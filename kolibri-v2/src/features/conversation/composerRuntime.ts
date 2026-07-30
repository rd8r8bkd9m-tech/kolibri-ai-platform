export interface BrowserSpeechRecognitionResult {
  0?: { transcript?: string }
}

export interface BrowserSpeechRecognitionEvent {
  results: ArrayLike<BrowserSpeechRecognitionResult>
}

export interface BrowserSpeechRecognition {
  continuous: boolean
  interimResults: boolean
  lang: string
  start: () => void
  stop: () => void
  onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
}

export type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition

interface SpeechRecognitionScope {
  SpeechRecognition?: BrowserSpeechRecognitionConstructor
  webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor
  isSecureContext?: boolean
  speechSynthesis?: unknown
  SpeechSynthesisUtterance?: unknown
}

export function getSpeechRecognitionConstructor(
  scope: unknown,
): BrowserSpeechRecognitionConstructor | null {
  if (!scope || typeof scope !== 'object') return null
  const candidate = scope as SpeechRecognitionScope
  return candidate.SpeechRecognition ?? candidate.webkitSpeechRecognition ?? null
}

export function canOfferLocalVoiceInput(scope: unknown): boolean {
  if (!scope || typeof scope !== 'object') return false
  const candidate = scope as SpeechRecognitionScope
  return candidate.isSecureContext !== false && getSpeechRecognitionConstructor(scope) !== null
}

export function canOfferSpeechOutput(scope: unknown): boolean {
  if (!scope || typeof scope !== 'object') return false
  const candidate = scope as SpeechRecognitionScope
  return candidate.isSecureContext !== false
    && Boolean(candidate.speechSynthesis)
    && typeof candidate.SpeechSynthesisUtterance === 'function'
}

export interface ComposerMediaEvidence {
  scope: unknown
  fileSearchLive?: boolean
  uploadCapabilityLive?: boolean
  uploadRendererReady?: boolean
  uploadTransportReady?: boolean
  realtimeVoiceCapabilityLive?: boolean
  realtimeVoiceRendererReady?: boolean
  realtimeVoiceTransportReady?: boolean
}

export interface ComposerMediaControls {
  voiceInput: boolean
  voiceConversation: boolean
  fileUpload: boolean
  cameraUpload: boolean
}

export function resolveComposerMediaControls(evidence: ComposerMediaEvidence): ComposerMediaControls {
  const voiceInput = canOfferLocalVoiceInput(evidence.scope)
  const uploadReady = Boolean(
    evidence.uploadCapabilityLive
    && evidence.uploadRendererReady
    && evidence.uploadTransportReady,
  )
  return {
    voiceInput,
    voiceConversation: Boolean(
      voiceInput
      && evidence.realtimeVoiceCapabilityLive
      && evidence.realtimeVoiceRendererReady
      && evidence.realtimeVoiceTransportReady,
    ),
    fileUpload: uploadReady,
    cameraUpload: uploadReady,
  }
}

export function getKeyboardInsetPx(
  layoutHeight: number,
  viewportHeight: number,
  viewportOffsetTop: number,
): number {
  if (![layoutHeight, viewportHeight, viewportOffsetTop].every(Number.isFinite)) {
    return 0
  }
  return Math.max(0, Math.round(layoutHeight - viewportHeight - viewportOffsetTop))
}

export function getAdaptiveKeyboardInsetPx(
  innerHeight: number,
  shellHeight: number | null,
  viewportHeight: number,
  viewportOffsetTop: number,
): number {
  const measuredShellHeight = typeof shellHeight === 'number' && Number.isFinite(shellHeight) && shellHeight > 0
    ? shellHeight
    : innerHeight
  // Android commonly resizes innerHeight, while iOS may keep the layout
  // viewport tall. The smaller measured layout prevents applying the keyboard
  // displacement twice when dynamic viewport units have already resized Shell.
  return getKeyboardInsetPx(
    Math.min(innerHeight, measuredShellHeight),
    viewportHeight,
    viewportOffsetTop,
  )
}
