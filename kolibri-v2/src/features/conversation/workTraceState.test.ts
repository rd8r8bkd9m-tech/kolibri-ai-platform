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

  it('never exposes provider or model names in the public compact line', () => {
    expect(workSummaryLabel(event({
      stage: 'provider_route',
      summary: 'Подключаю доступного исполнителя',
      provider: 'deepseek-v4-flash',
      model: 'deepseek-v4-flash',
    }))).toBe('Подключаю доступного исполнителя')
  })

  it('keeps a completed trace available after the answer finishes', () => {
    expect(shouldRenderWorkTrace('completed', false)).toBe(true)
    expect(shouldRenderWorkTrace('completed', true)).toBe(true)
    expect(shouldRenderWorkTrace('failed', false)).toBe(true)
  })

  it('replaces fragmented reasoning excerpts by summary id', () => {
    const result = dedupeWorkSummaries([
      event({
        kind: 'reasoning_excerpt', stage: 'reasoning_summary', summary_id: 'summary_1',
        response_id: 'resp_1', sequence: 4, summary: 'Сверяю',
      }),
      event({
        kind: 'reasoning_excerpt', stage: 'reasoning_summary', summary_id: 'summary_1',
        response_id: 'resp_1', sequence: 5, summary: 'Сверяю цены по региону объекта',
      }),
    ])

    expect(result).toEqual([
      event({
        kind: 'reasoning_excerpt', stage: 'reasoning_summary', summary_id: 'summary_1',
        response_id: 'resp_1', sequence: 5, summary: 'Сверяю цены по региону объекта',
      }),
    ])
  })

  it('ignores duplicate and out-of-order durable events', () => {
    const latest = event({
      kind: 'reasoning_excerpt', stage: 'reasoning_summary', summary_id: 'summary_1',
      response_id: 'resp_1', sequence: 8, summary: 'Проверяю итог',
    })
    const result = dedupeWorkSummaries([
      latest,
      latest,
      event({
        kind: 'reasoning_excerpt', stage: 'reasoning_summary', summary_id: 'summary_1',
        response_id: 'resp_1', sequence: 7, summary: 'Проверяю',
      }),
    ])
    expect(result).toEqual([latest])
  })
})
