import { describe, expect, it } from 'vitest'
import { canOfferLocalVoiceInput, getSpeechRecognitionConstructor, resolveComposerMediaControls, type BrowserSpeechRecognition } from './composerRuntime'

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

  it('does not mistake file search for a working upload transport', () => {
    expect(resolveComposerMediaControls({
      scope: {},
      fileSearchLive: true,
    })).toEqual({
      voiceInput: false,
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
      fileUpload: false,
      cameraUpload: false,
    })
  })
})
