/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const chat = readFileSync(new URL('../../pages/ChatPage.tsx', import.meta.url), 'utf8')
const estimates = readFileSync(new URL('../../pages/EstimatesPage.tsx', import.meta.url), 'utf8')
const drawer = readFileSync(new URL('../shell/MobileNavigationDrawer.tsx', import.meta.url), 'utf8')
const layout = readFileSync(new URL('../../components/Layout.tsx', import.meta.url), 'utf8')
const styles = readFileSync(new URL('../../index.css', import.meta.url), 'utf8')

describe('mobile estimate navigation contract', () => {
  it('keeps chat as the primary context and preserves legacy return navigation', () => {
    expect(chat).toContain('<ConversationEstimateSheet')
    expect(chat).toContain('setActiveEstimate(message.artifact.value)')
    expect(chat).not.toContain("navigate(`/estimates?edit=${message.artifact.value.id}`")
    expect(estimates).toContain("const sourceChatPath")
    expect(estimates).toContain("if (sourceChatPath) navigate(-1)")
    expect(estimates).toContain("sourceChatPath ? 'Вернуться в чат' : 'К списку смет'")
    expect(styles).toMatch(/@media \(max-width: 767px\)[\s\S]*\.estimate-mobile-back\s*\{[^}]*display:\s*inline-flex;/s)
  })

  it('keeps estimates directly reachable from the mobile drawer', () => {
    // estimate drawer button removed — feature disabled in kolibriai.ru
    expect(drawer).not.toContain('onEstimates')
    expect(layout).not.toContain("onEstimates")
  })
})
