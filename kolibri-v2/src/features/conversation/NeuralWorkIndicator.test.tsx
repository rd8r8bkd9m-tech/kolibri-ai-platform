import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import NeuralWorkIndicator from './NeuralWorkIndicator'
import { NEURAL_NODE_LAYOUT } from './neuralWorkIndicatorLayout'

function renderedNodeStates(html: string) {
  return [...html.matchAll(/neural-node is-(future|active|completed|failed)/g)].map(match => match[1])
}

describe('NeuralWorkIndicator', () => {
  it('shows a changing neural sphere before the first confirmed event', () => {
    const html = renderToStaticMarkup(
      <NeuralWorkIndicator state="connecting" events={[]} label="Подключаюсь" />,
    )
    expect(html).toContain('is-animated')
    expect(html).toContain('neural-sphere is-forming')
    expect((html.match(/<i><\/i>/g) ?? [])).toHaveLength(6)
    expect(html).toContain('neural-sphere-core')
    expect(html).not.toContain('neural-stage-nodes')
  })

  it('keeps the animated neural sphere visible while real work events arrive', () => {
    const html = renderToStaticMarkup(
      <NeuralWorkIndicator
        state="active"
        label="Сверяю источники"
        latestSummary="Сверяю источники"
        events={[{ stage: 'source_retrieval', status: 'active', summary: 'Сверяю источники' }]}
      />,
    )
    expect(html).toContain('is-animated')
    expect(html).toContain('neural-sphere is-forming')
    expect((html.match(/<i><\/i>/g) ?? [])).toHaveLength(6)
    expect(html).toContain('Сверяю источники: Данные и источники: выполняется')
    expect(html).not.toContain('neural-stage-nodes')
  })

  it('places terminal stage nodes on a compact orbit instead of a horizontal row', () => {
    expect(NEURAL_NODE_LAYOUT).toHaveLength(5)
    expect(new Set(NEURAL_NODE_LAYOUT.map(point => point.x)).size).toBeGreaterThan(3)
    expect(new Set(NEURAL_NODE_LAYOUT.map(point => point.y)).size).toBeGreaterThan(2)

    const html = renderToStaticMarkup(
      <NeuralWorkIndicator
        state="completed"
        label="Проверяю"
        events={[{ stage: 'verification', status: 'active', summary: 'Проверяю' }]}
      />,
    )
    expect((html.match(/--neural-node-x:/g) ?? [])).toHaveLength(5)
    expect((html.match(/--neural-node-y:/g) ?? [])).toHaveLength(5)
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
    expect(html).toContain('neural-sphere is-forming')
    expect(html).not.toContain('neural-stage-nodes')
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
    expect(html).toContain('neural-sphere is-forming')
    expect(html).not.toContain('neural-stage-nodes')
  })

  it('a later completed fallback repairs an earlier failure in the same stage', () => {
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
    expect(html).toContain('neural-sphere is-forming')
    expect(html).not.toContain('neural-stage-nodes')
  })

  it('keeps a later failure after an earlier successful attempt', () => {
    const html = renderToStaticMarkup(
      <NeuralWorkIndicator
        state="active"
        label="Ошибка источника"
        events={[
          { stage: 'provider_attempt', status: 'completed', summary: 'Провайдер ответил' },
          { stage: 'source_retrieval', status: 'failed', summary: 'Источник недоступен' },
        ]}
      />,
    )
    expect(html).toContain('neural-sphere is-forming')
    expect(html).not.toContain('neural-stage-nodes')
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

  it('labels the staged timeline without adding fake progress', () => {
    const html = renderToStaticMarkup(
      <NeuralWorkIndicator
        state="completed"
        label="Выполняю расчёт"
        events={[{ stage: 'tool_execution', status: 'active', summary: 'Выполняю расчёт' }]}
      />,
    )
    expect(html).toContain('role="list"')
    expect(html).toContain('role="listitem"')
    expect(html).toContain('aria-label="Этапы выполнения"')
    expect(html).toContain('aria-label="Понимаю запрос: ожидание"')
    expect(html).toContain('aria-label="Инструменты и расчёты: выполняется"')
    expect(html).toContain('aria-label="Ответ и артефакты: завершено"')
    expect(renderedNodeStates(html)).toEqual(['future', 'future', 'active', 'future', 'completed'])
  })

  it('stays in connecting mode when no confirmed event has arrived', () => {
    const html = renderToStaticMarkup(
      <NeuralWorkIndicator state="recovering" events={[]} label="Восстановление" />,
    )
    expect(html).toContain('is-animated')
    expect(html).toContain('role="status"')
    expect(html).toContain('aria-label="Восстановление"')
    expect(html).not.toContain('neural-stage-nodes')
    expect(html).not.toContain('role="img"')
  })

  it('announces waiting and failed states without relying on colour alone', () => {
    const waiting = renderToStaticMarkup(
      <NeuralWorkIndicator
        state="waiting"
        label="Нужно уточнение"
        events={[{ stage: 'planning', status: 'active', summary: 'Нужно уточнение' }]}
      />,
    )
    const failed = renderToStaticMarkup(
      <NeuralWorkIndicator
        state="failed"
        label="Не удалось завершить"
        events={[{ stage: 'verification', status: 'failed', summary: 'Проверка не пройдена' }]}
      />,
    )
    expect(waiting).toContain('state-waiting')
    expect(waiting).toContain('Ожидание')
    expect(failed).toContain('state-failed')
    expect(failed).toContain('ошибка')
  })
})
