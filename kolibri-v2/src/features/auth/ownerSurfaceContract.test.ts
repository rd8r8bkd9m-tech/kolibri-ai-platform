/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
const layout = readFileSync(new URL('../../components/Layout.tsx', import.meta.url), 'utf8')
const drawer = readFileSync(new URL('../shell/MobileNavigationDrawer.tsx', import.meta.url), 'utf8')

describe('owner Control Center surface contract', () => {
  it.each(['agents', 'control', 'servers'])('protects /%s at the route boundary', path => {
    expect(app).toContain(`path="${path}" element={<ProtectedOwnerRoute user={user}>`)
  })

  it('hides operator navigation unless the authenticated role is allowed', () => {
    expect(layout).toContain('showOwnerControl={isOwnerRole(user?.role)}')
    expect(drawer).toContain("...(showOwnerControl ? [{ label: t('drawer.agents'), icon: Bot, action: onAgents }] : [])")
  })
})
