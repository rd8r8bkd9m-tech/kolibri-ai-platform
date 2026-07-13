import { describe, expect, it } from 'vitest'
import { createExecutionPolicy } from './executionPolicy'

describe('execution policy', () => {
  it('makes fast mode a low-latency server policy', () => {
    expect(createExecutionPolicy('fast', ['web.search'])).toEqual({
      mode: 'fast',
      reasoning_effort: 'low',
      tool_choice: 'auto',
      background: false,
      allowed_capabilities: ['web.search'],
    })
  })

  it('makes deep mode resumable and preserves proved capability ids', () => {
    expect(createExecutionPolicy('deep', ['code.execute', 'mcp.invoke'])).toEqual({
      mode: 'deep',
      reasoning_effort: 'high',
      tool_choice: 'auto',
      background: true,
      allowed_capabilities: ['code.execute', 'mcp.invoke'],
    })
  })
})
