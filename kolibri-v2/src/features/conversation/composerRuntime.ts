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
}

export function getSpeechRecognitionConstructor(
  scope: unknown,
): BrowserSpeechRecognitionConstructor | null {
  if (!scope || typeof scope !== 'object') return null
  const candidate = scope as SpeechRecognitionScope
  return candidate.SpeechRecognition ?? candidate.webkitSpeechRecognition ?? null
}

export function canOfferLocalVoiceInput(scope: unknown): boolean {
  return getSpeechRecognitionConstructor(scope) !== null
}

export interface ComposerMediaEvidence {
  scope: unknown
  fileSearchLive?: boolean
  uploadCapabilityLive?: boolean
  uploadRendererReady?: boolean
  uploadTransportReady?: boolean
}

export interface ComposerMediaControls {
  voiceInput: boolean
  fileUpload: boolean
  cameraUpload: boolean
}

export function resolveComposerMediaControls(evidence: ComposerMediaEvidence): ComposerMediaControls {
  const uploadReady = Boolean(
    evidence.uploadCapabilityLive
    && evidence.uploadRendererReady
    && evidence.uploadTransportReady,
  )
  return {
    voiceInput: canOfferLocalVoiceInput(evidence.scope),
    fileUpload: uploadReady,
    cameraUpload: uploadReady,
  }
}
