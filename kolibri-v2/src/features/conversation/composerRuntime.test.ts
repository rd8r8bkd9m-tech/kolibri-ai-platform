import { describe, expect, it } from 'vitest'
import {
  canOfferLocalVoiceInput,
  canOfferSpeechOutput,
  getAdaptiveKeyboardInsetPx,
  getKeyboardInsetPx,
  getSpeechRecognitionConstructor,
  resolveComposerMediaControls,
  type BrowserSpeechRecognition,
} from './composerRuntime'

class RecognitionStub implements BrowserSpeechRecognition {
  continuous = false
  interimResults = false
  lang = ''
  onresult = null
  onend = null
  onerror = null
  start() {}
  stop() {}
}

describe('composer runtime capability contract', () => {
  it('does not show voice controls when the browser has no invocable recognizer', () => {
    expect(canOfferLocalVoiceInput({})).toBe(false)
    expect(getSpeechRecognitionConstructor({})).toBeNull()
  })

  it('accepts both standard and Safari speech-recognition implementations', () => {
    expect(getSpeechRecognitionConstructor({ SpeechRecognition: RecognitionStub })).toBe(RecognitionStub)
    expect(getSpeechRecognitionConstructor({ webkitSpeechRecognition: RecognitionStub })).toBe(RecognitionStub)
    expect(canOfferLocalVoiceInput({ webkitSpeechRecognition: RecognitionStub })).toBe(true)
  })

  it('hides voice input in an explicitly insecure browser context', () => {
    expect(canOfferLocalVoiceInput({
      isSecureContext: false,
      webkitSpeechRecognition: RecognitionStub,
    })).toBe(false)
  })

  it('shows speech output only when the browser exposes both required APIs', () => {
    expect(canOfferSpeechOutput({})).toBe(false)
    expect(canOfferSpeechOutput({ speechSynthesis: {}, SpeechSynthesisUtterance: class {} })).toBe(true)
  })

  it('does not mistake file search for a working upload transport', () => {
    expect(resolveComposerMediaControls({
      scope: {},
      fileSearchLive: true,
    })).toEqual({
      voiceInput: false,
      voiceConversation: false,
      fileUpload: false,
      cameraUpload: false,
    })
  })

  it('requires capability, renderer, and transport evidence before upload controls can appear', () => {
    expect(resolveComposerMediaControls({
      scope: { SpeechRecognition: RecognitionStub },
      uploadCapabilityLive: true,
      uploadRendererReady: true,
      uploadTransportReady: false,
    })).toEqual({
      voiceInput: true,
      voiceConversation: false,
      fileUpload: false,
      cameraUpload: false,
    })
  })

  it('requires live capability, renderer, and transport for conversational voice', () => {
    const base = {
      scope: { SpeechRecognition: RecognitionStub },
      realtimeVoiceCapabilityLive: true,
      realtimeVoiceRendererReady: true,
    }
    expect(resolveComposerMediaControls(base).voiceConversation).toBe(false)
    expect(resolveComposerMediaControls({
      ...base,
      realtimeVoiceTransportReady: true,
    }).voiceConversation).toBe(true)
  })

  it('calculates visual viewport keyboard inset without negative values', () => {
    expect(getKeyboardInsetPx(800, 500, 0)).toBe(300)
    expect(getKeyboardInsetPx(800, 500, 24.4)).toBe(276)
    expect(getKeyboardInsetPx(600, 800, 0)).toBe(0)
    expect(getKeyboardInsetPx(800, Number.NaN, 0)).toBe(0)
  })

  it('does not double-raise the composer when dynamic viewport units already resized Shell', () => {
    expect(getAdaptiveKeyboardInsetPx(844, 500, 500, 0)).toBe(0)
    expect(getAdaptiveKeyboardInsetPx(500, 844, 500, 0)).toBe(0)
    expect(getAdaptiveKeyboardInsetPx(844, 844, 500, 0)).toBe(344)
    expect(getAdaptiveKeyboardInsetPx(844, 844, 500, 44)).toBe(300)
  })
})
