/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
const layout = readFileSync(new URL('../../components/Layout.tsx', import.meta.url), 'utf8')
const drawer = readFileSync(new URL('../shell/MobileNavigationDrawer.tsx', import.meta.url), 'utf8')
const rail = readFileSync(new URL('../shell/SystemRail.tsx', import.meta.url), 'utf8')

describe('owner Control Center surface contract', () => {
  it.each(['agents', 'control', 'servers'])('protects /%s at the route boundary', path => {
    expect(app).toContain(`path="${path}" element={<ProtectedOwnerRoute user={user}>`)
  })

  it.each([
    'control/servers',
    'control/models',
    'control/local-models',
    'control/learning',
    'control/audit',
    'control/tasks/:taskId',
  ])('protects /%s inside the same application', path => {
    expect(app).toContain(`path="${path}" element={<ProtectedOwnerRoute user={user}>`)
  })

  it('hides operator navigation unless the authenticated role is allowed', () => {
    expect(layout).toContain('showOwnerControl={isOwnerRole(user?.role)}')
    expect(drawer).toContain("...(showOwnerControl ? [{ label: t('drawer.agents'), icon: Bot, action: onAgents }] : [])")
  })

  it('keeps the desktop ChatGPT-like rail limited to chat history and settings', () => {
    expect(rail).not.toContain('/control')
    expect(rail).not.toContain('onAgents')
  })
})
