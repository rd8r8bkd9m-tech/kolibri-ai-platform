import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import NeuralWorkIndicator from './NeuralWorkIndicator'

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
    expect(html).toContain('neural-node is-active')
    expect(html).toContain('aria-label="Сверяю источники"')
  })
})
