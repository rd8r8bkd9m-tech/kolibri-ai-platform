import { describe, expect, it } from 'vitest'
import type { ChatAction } from '@/lib/api'
import {
  estimateActionNeedsClarification,
  estimateClarificationPrompt,
  estimateClarificationQuestions,
  shouldAutoMaterializeAction,
} from './estimateActionPolicy'

function estimateAction(price: string, status: string = 'needs_input'): ChatAction {
  return {
    type: 'create_estimate',
    label: status === 'needs_input' ? 'Уточнить данные для сметы' : 'Открыть смету',
    data: {
      title: 'Смета на забор',
      estimate_status: status,
      pricing_status: status,
      questions: ['Уточните материал секций и тип фундамента.'],
      sections: [{
        title: 'Забор',
        positions: [{
          code: 'ЗБ-1',
          name: 'Монтаж секций',
          unit: 'м',
          quantity: '9',
          price,
        }],
      }],
    },
  }
}

describe('estimate clarification action policy', () => {
  it('materializes a zero-priced needs-input estimate as an editable draft', () => {
    const action = estimateAction('0')

    expect(estimateActionNeedsClarification(action)).toBe(true)
    expect(shouldAutoMaterializeAction(action)).toBe(true)
    expect(estimateClarificationQuestions(action)).toEqual([
      'Уточните материал секций и тип фундамента.',
    ])
    expect(estimateClarificationPrompt(action)).toBe(
      'Уточнение для сметы:\n1. Уточните материал секций и тип фундамента.',
    )
  })

  it('materializes an all-zero draft while normalization keeps its truth status blocked', () => {
    const action = estimateAction('0', 'source_backed')

    expect(estimateActionNeedsClarification(action)).toBe(true)
    expect(shouldAutoMaterializeAction(action)).toBe(true)
  })

  it('allows a positive estimate draft to cross the explicit materialization boundary', () => {
    const action = estimateAction('2500', 'source_backed')

    expect(estimateActionNeedsClarification(action)).toBe(false)
    expect(shouldAutoMaterializeAction(action)).toBe(true)
  })
})
