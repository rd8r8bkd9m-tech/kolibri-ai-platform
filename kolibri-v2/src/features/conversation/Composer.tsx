import { useEffect, useRef, useState } from 'react'
import { ArrowUp, AudioLines, Blocks, Calculator, Code2, FileSearch, FileText, Globe2, Image as ImageIcon, Mic, Monitor, Plus, Square, X } from 'lucide-react'
import { useVisualViewportInset } from './useVisualViewportInset'
import ToolSheet from './ToolSheet'
import type { UiCapability, UiCapabilityKey } from '@/features/capabilities'
import { getSpeechRecognitionConstructor, resolveComposerMediaControls, type BrowserSpeechRecognition } from './composerRuntime'
import { useIsMobile } from '@/hooks/use-mobile'
import { useLocale } from '@/features/localization'

interface ComposerProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  onEstimate: () => void
  onDocument: () => void
  capabilities?: UiCapability[]
  onCapability?: (key: UiCapabilityKey) => void
  onCancel?: () => void
  busy?: boolean
  placeholder?: string
  autoFocus?: boolean
}

export default function Composer({
  value,
  onChange,
  onSend,
  onEstimate,
  onDocument,
  capabilities = [],
  onCapability = () => undefined,
  onCancel,
  busy = false,
  placeholder,
  autoFocus = false,
}: ComposerProps) {
  const { locale, t } = useLocale()
  const resolvedPlaceholder = placeholder ?? t('composer.defaultPlaceholder')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [voiceNotice, setVoiceNotice] = useState('')
  const [voiceModeActive, setVoiceModeActive] = useState(false)
  const [listening, setListening] = useState(false)
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null)
  const voiceBaseValueRef = useRef('')
  const mediaControls = resolveComposerMediaControls({ scope: window })
  const voiceAvailable = mediaControls.voiceInput
  const isMobile = useIsMobile()
  useVisualViewportInset()

  useEffect(() => () => {
    recognitionRef.current?.stop()
    window.dispatchEvent(new CustomEvent('kolibri:voice-mode', { detail: { active: false } }))
  }, [])

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 144)}px`
  }, [value])

  const submit = () => {
    if (!value.trim() || busy) return
    setToolsOpen(false)
    onSend()
  }

  const startVoiceInput = (continuous = false, openSurface = false) => {
    const SpeechRecognitionCtor = getSpeechRecognitionConstructor(window)
    if (!SpeechRecognitionCtor) return

    recognitionRef.current?.stop()
    if (openSurface) {
      setVoiceModeActive(true)
      window.dispatchEvent(new CustomEvent('kolibri:voice-mode', { detail: { active: true } }))
      setVoiceNotice('')
    }

    const recognition = new SpeechRecognitionCtor()
    recognition.continuous = continuous
    recognition.interimResults = false
    recognition.lang = locale === 'en' ? 'en-US' : 'ru-RU'
    voiceBaseValueRef.current = value.trim()
    recognition.onresult = event => {
      const transcript = Array.from(event.results).map(result => result[0]?.transcript ?? '').join(' ').trim()
      if (transcript) onChange([voiceBaseValueRef.current, transcript].filter(Boolean).join(' '))
    }
    recognition.onend = () => { recognitionRef.current = null; setListening(false); setVoiceNotice('') }
    recognition.onerror = () => { recognitionRef.current = null; setListening(false); setVoiceNotice(t('composer.voiceFailed')) }
    recognitionRef.current = recognition
    setListening(true)
    setVoiceNotice(t('composer.listening'))
    try {
      recognition.start()
    } catch {
      recognitionRef.current = null
      setListening(false)
      setVoiceNotice(t('composer.voiceRunning'))
    }
  }

  const stopVoiceMode = () => {
    recognitionRef.current?.stop()
    recognitionRef.current = null
    setListening(false)
    setVoiceModeActive(false)
    window.dispatchEvent(new CustomEvent('kolibri:voice-mode', { detail: { active: false } }))
    setVoiceNotice('')
  }

  return (
    <div className="conversation-composer-wrap">
      <ToolSheet
        open={toolsOpen && isMobile}
        capabilities={capabilities}
        onClose={() => setToolsOpen(false)}
        onEstimate={onEstimate}
        onDocument={onDocument}
        onCapability={onCapability}
      />
      {voiceNotice && <div className={voiceModeActive ? 'sr-only' : 'composer-voice-notice'} role="status">{voiceNotice}</div>}
      {toolsOpen && (
        <div className="conversation-tool-menu hidden md:grid" role="menu" aria-label={t('composer.tools')}>
          <button role="menuitem" onClick={() => { setToolsOpen(false); onEstimate() }}>
            <Calculator size={19} />
            <span><strong>{t('tool.estimate')}</strong><small>{t('tool.estimateDescription')}</small></span>
          </button>
          <button role="menuitem" onClick={() => { setToolsOpen(false); onDocument() }}>
            <FileText size={19} />
            <span><strong>{t('tool.document')}</strong><small>{t('tool.documentDescription')}</small></span>
          </button>
          {capabilities.map(item => {
            const icons: Record<UiCapabilityKey, typeof Globe2> = {
              'web.search': Globe2,
              'file.search': FileSearch,
              'code.execute': Code2,
              'image.generate': ImageIcon,
              'browser.use': Monitor,
              'mcp.invoke': Blocks,
            }
            const Icon = icons[item.key]
            return <button key={item.key} role="menuitem" onClick={() => {
              setToolsOpen(false)
              onCapability(item.key)
            }}>
              <Icon size={19} />
              <span><strong>{item.title}</strong><small>{item.description}</small></span>
            </button>
          })}
        </div>
      )}
      {voiceModeActive && voiceAvailable ? (
        <div className="composer-voice-surface" aria-label={t('composer.voiceMode')}>
          <div className="composer-voice-controls composer-voice-controls-left" aria-hidden="true" />
          <div className="composer-voice-live" aria-hidden="true">
            <AudioLines size={29} />
          </div>
          <div className="composer-voice-controls composer-voice-controls-right">
            <button type="button" aria-label={listening ? t('composer.microphoneOff') : t('composer.microphoneOn')} aria-pressed={listening} className={listening ? 'is-active' : ''} onClick={() => {
              if (listening) {
                recognitionRef.current?.stop()
                setListening(false)
              } else startVoiceInput(true)
            }}><Mic size={22} /></button>
            <button type="button" aria-label={t('composer.closeVoice')} onClick={stopVoiceMode}><X size={24} /></button>
          </div>
        </div>
      ) : <div className="conversation-composer">
        <button
          type="button"
          aria-label={toolsOpen ? t('composer.closeTools') : t('composer.openTools')}
          aria-expanded={toolsOpen}
          onClick={() => setToolsOpen(open => !open)}
          className="composer-tool-button"
        >
          {toolsOpen ? <X size={21} /> : <Plus size={22} />}
        </button>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={event => onChange(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
          placeholder={resolvedPlaceholder}
          rows={1}
          autoFocus={autoFocus}
          className="conversation-composer-input"
        />
        {busy && onCancel ? <button
            type="button"
            aria-label={t('composer.stop')}
            onClick={onCancel}
            className="composer-send-button"
          >
            <Square size={17} fill="currentColor" strokeWidth={1.8} />
          </button> : value.trim() ? <button
            type="button"
            aria-label={t('composer.send')}
            onClick={submit}
            disabled={busy}
            className="composer-send-button"
          >
            <ArrowUp size={22} strokeWidth={2.2} />
          </button> : voiceAvailable ? <>
            <button type="button" aria-label={t('composer.voiceInput')} className="composer-voice-button" onClick={() => startVoiceInput(false)}>
              <Mic size={22} strokeWidth={2.1} />
            </button>
            <button type="button" aria-label={t('composer.voiceMode')} className="composer-voice-mode-button" onClick={() => startVoiceInput(true, true)}>
              <AudioLines size={23} strokeWidth={2.1} />
            </button>
          </> : null}
      </div>}
      <p className="composer-disclaimer">{t('composer.disclaimer')}</p>
    </div>
  )
}
