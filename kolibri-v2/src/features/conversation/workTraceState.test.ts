import { describe, expect, it } from 'vitest'
import type { ChatWorkSummary } from '@/lib/api'
import {
  dedupeWorkSummaries,
  mergeReplayedWorkSummaries,
  shouldRenderWorkTrace,
  workSummaryLabel,
} from './workTraceState'

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

  it('does not regress a route lifecycle when replay delivers an older sequence', () => {
    const latest = event({
      stage: 'provider_route', status: 'completed', summary: 'Маршрут завершён',
      step_id: 'route_1', response_id: 'resp_1', sequence: 20,
    })
    const stale = event({
      stage: 'provider_route', status: 'active', summary: 'Подключаю исполнителя',
      step_id: 'route_1', response_id: 'resp_1', sequence: 10,
    })

    expect(mergeReplayedWorkSummaries([latest], [stale])).toEqual([latest])
  })

  it('keeps one canonical provider attempt when a legacy provider event is also delivered', () => {
    const canonical = event({
      stage: 'provider_attempt', status: 'failed', summary: 'Маршрут не ответил',
      step_id: 'provider_attempt_1', response_id: 'resp_1', sequence: 12,
    })
    const legacy = event({
      stage: 'provider_attempt', status: 'failed', summary: 'Переключаю маршрут',
      provider: 'legacy-provider', model: 'legacy-model',
    })

    expect(mergeReplayedWorkSummaries([canonical], [legacy])).toEqual([canonical])
    expect(mergeReplayedWorkSummaries([legacy], [canonical])).toEqual([canonical])
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

  it('merges replayed work summaries through the same durable identity contract', () => {
    const live = event({
      kind: 'reasoning_excerpt', stage: 'reasoning_summary', summary_id: 'summary_1',
      step_id: 'step_1', response_id: 'resp_1', sequence: 17, summary: 'Сверяю',
    })
    const replayed = event({
      kind: 'reasoning_excerpt', stage: 'reasoning_summary', summary_id: 'summary_1',
      step_id: 'step_1', response_id: 'resp_1', sequence: 18, summary: 'Сверяю цены по региону объекта',
    })

    expect(mergeReplayedWorkSummaries([live], [replayed])).toEqual([replayed])
  })

  it('keeps the latest replayed summary when a persisted replay repeats the live sequence', () => {
    const live = event({
      kind: 'reasoning_excerpt', stage: 'reasoning_summary', summary_id: 'summary_opaque',
      step_id: 'step_opaque', response_id: 'resp_1', sequence: 17, summary: 'Сверяю',
    })
    const replayed = event({
      kind: 'reasoning_excerpt', stage: 'reasoning_summary', summary_id: 'summary_opaque',
      step_id: 'step_opaque', response_id: 'resp_1', sequence: 17, summary: 'Сверяю цены по региону объекта',
    })

    expect(mergeReplayedWorkSummaries([live], [replayed])).toEqual([replayed])
  })
})
