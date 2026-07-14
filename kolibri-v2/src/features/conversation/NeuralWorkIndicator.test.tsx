import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import NeuralWorkIndicator from './NeuralWorkIndicator'

function renderedNodeStates(html: string) {
  return [...html.matchAll(/neural-node is-(future|active|completed|failed)/g)].map(match => match[1])
}

describe('NeuralWorkIndicator', () => {
  it('shows exactly three connection dots before the first confirmed event', () => {
    const html = renderToStaticMarkup(
      <NeuralWorkIndicator state="connecting" events={[]} label="Подключаюсь" />,
    )
    expect(html).toContain('is-connecting')
    expect((html.match(/<span><\/span>/g) ?? [])).toHaveLength(3)
    expect(html).not.toContain('neural-stage-nodes')
  })

  it('morphs to five semantic nodes only after a real work event', () => {
    const html = renderToStaticMarkup(
      <NeuralWorkIndicator
        state="active"
        label="Сверяю источники"
        latestSummary="Сверяю источники"
        events={[{ stage: 'source_retrieval', status: 'active', summary: 'Сверяю источники' }]}
      />,
    )
    expect(html).toContain('is-staged')
    expect((html.match(/neural-node /g) ?? [])).toHaveLength(5)
    expect(renderedNodeStates(html)).toEqual(['future', 'active', 'future', 'future', 'future'])
    expect(html).toContain('aria-label="Сверяю источники"')
  })

  it('does not complete unobserved earlier groups when a later group becomes active', () => {
    const html = renderToStaticMarkup(
      <NeuralWorkIndicator
        state="active"
        label="Выполняю расчёт"
        events={[
          { stage: 'provider_route', status: 'completed', summary: 'Маршрут определён' },
          { stage: 'tool_execution', status: 'active', summary: 'Выполняю расчёт' },
        ]}
      />,
    )
    expect(renderedNodeStates(html)).toEqual(['future', 'completed', 'active', 'future', 'future'])
  })

  it('marks observed earlier active groups as completed when a later group becomes active', () => {
    const html = renderToStaticMarkup(
      <NeuralWorkIndicator
        state="active"
        label="Выполняю расчёт"
        events={[
          { stage: 'planning', status: 'active', summary: 'Планирую работу' },
          { stage: 'tool_execution', status: 'active', summary: 'Выполняю расчёт' },
        ]}
      />,
    )
    expect(renderedNodeStates(html)).toEqual(['completed', 'future', 'active', 'future', 'future'])
  })

  it('explicit failed status wins over completed', () => {
    const html = renderToStaticMarkup(
      <NeuralWorkIndicator
        state="active"
        label="Ошибка источника"
        events={[
          { stage: 'source_retrieval', status: 'failed', summary: 'Источник недоступен' },
          { stage: 'provider_attempt', status: 'completed', summary: 'Провайдер ответил' },
        ]}
      />,
    )
    expect(renderedNodeStates(html)).toEqual(['future', 'failed', 'future', 'future', 'future'])
  })

  it('terminal completion marks group 4 as completed while group 3 remains future', () => {
    const html = renderToStaticMarkup(
      <NeuralWorkIndicator
        state="completed"
        label="Ответ готов"
        events={[{ stage: 'tool_execution', status: 'completed', summary: 'Расчёт готов' }]}
      />,
    )
    expect(renderedNodeStates(html)).toEqual(['future', 'future', 'completed', 'future', 'completed'])
  })
})
