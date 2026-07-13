import { describe, expect, it } from 'vitest'
import { isFailedResponse, persistedResponseStatus, responseFailureMessage } from './responseState'

describe('image response fail-closed state', () => {
  it('treats structured capability unavailability as failed and recoverable UI state', () => {
    const response = {
      status: 'capability_unavailable',
      error_code: 'capability_unavailable',
      capability: 'image.generate',
    }
    expect(isFailedResponse(response)).toBe(true)
    expect(responseFailureMessage(response)).toContain('Генерация изображений сейчас недоступна')
    expect(persistedResponseStatus(response.status, false, responseFailureMessage(response))).toBe('failed')
  })

  it('never persists a provider success sentence after artifact verification failed', () => {
    expect(persistedResponseStatus('ready', true, 'Изображение создано.')).toBe('failed')
    expect(responseFailureMessage({
      status: 'failed',
      error_code: 'image_artifact_verification_failed',
      capability: 'image.generate',
    })).toContain('файл не прошёл проверку')
  })

  it('keeps a verified non-empty response completed', () => {
    expect(persistedResponseStatus('ready', false, 'Изображение создано и проверено.')).toBe('completed')
  })
})
