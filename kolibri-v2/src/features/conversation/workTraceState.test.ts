import { describe, expect, it } from 'vitest'
import type { ChatWorkSummary } from '@/lib/api'
import { dedupeWorkSummaries, shouldRenderWorkTrace, workSummaryLabel } from './workTraceState'

function event(value: Partial<ChatWorkSummary> & Pick<ChatWorkSummary, 'stage' | 'summary'>): ChatWorkSummary {
  return { status: 'active', ...value }
}

describe('public work trace state', () => {
  it('keeps one accepted row and replaces it with its newest safe state', () => {
    const result = dedupeWorkSummaries([
      event({ stage: 'accepted', summary: 'Запрос принят' }),
      event({ stage: 'accepted', summary: 'Запрос принят' }),
      event({ stage: 'accepted', status: 'completed', summary: 'Запрос принят' }),
    ])

    expect(result).toEqual([
      event({ stage: 'accepted', status: 'completed', summary: 'Запрос принят' }),
    ])
  })

  it('deduplicates lifecycle updates per provider route without merging different routes', () => {
    const result = dedupeWorkSummaries([
      event({ stage: 'provider_route', summary: 'Подключаю исполнителя', provider: 'deepseek', model: 'deepseek-v4-flash' }),
      event({ stage: 'provider_route', status: 'completed', summary: 'Маршрут исполнителя завершён', provider: 'deepseek', model: 'deepseek-v4-flash' }),
      event({ stage: 'provider_route', summary: 'Подключаю исполнителя', provider: 'mimo', model: 'mimo-code' }),
    ])

    expect(result).toHaveLength(2)
    expect(result[0]).toMatchObject({ status: 'completed', provider: 'deepseek' })
    expect(result[1]).toMatchObject({ status: 'active', provider: 'mimo' })
  })

  it('does not repeat equal provider and model names in the compact line', () => {
    expect(workSummaryLabel(event({
      stage: 'provider_route',
      summary: 'Подключаю доступного исполнителя',
      provider: 'deepseek-v4-flash',
      model: 'deepseek-v4-flash',
    }))).toBe('Подключаю доступного исполнителя · deepseek-v4-flash')
  })

  it('hides a completed trace unless the user had explicitly opened its details', () => {
    expect(shouldRenderWorkTrace('completed', false)).toBe(false)
    expect(shouldRenderWorkTrace('completed', true)).toBe(true)
    expect(shouldRenderWorkTrace('failed', false)).toBe(true)
  })
})
