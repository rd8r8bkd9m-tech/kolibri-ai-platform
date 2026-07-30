/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
const landing = readFileSync(new URL('../../pages/PublicLanding.tsx', import.meta.url), 'utf8')
const publicInfo = readFileSync(new URL('../../pages/PublicInfoPage.tsx', import.meta.url), 'utf8')
const portalFrame = readFileSync(new URL('./PublicPortalFrame.tsx', import.meta.url), 'utf8')
const styles = readFileSync(new URL('../../index.css', import.meta.url), 'utf8')
const robots = readFileSync(new URL('../../../public/robots.txt', import.meta.url), 'utf8')
const sitemap = readFileSync(new URL('../../../public/sitemap.xml', import.meta.url), 'utf8')
const nginx = readFileSync(new URL('../../../nginx.conf', import.meta.url), 'utf8')

describe('public portal release contract', () => {
  it.each(['pricing', 'security', 'privacy', 'terms'])('mounts /%s outside the shell bootstrap boundary', route => {
    const routeIndex = app.indexOf(`path="${route}"`)
    const boundaryIndex = app.indexOf('<Route element={<ShellBootstrapBoundary />}>')
    expect(routeIndex).toBeGreaterThan(-1)
    expect(routeIndex).toBeLessThan(boundaryIndex)
  })

  it('keeps the public landing independent from private API data', () => {
    expect(landing).not.toContain("from '@/lib/api'")
    expect(landing).not.toMatch(/project_id|workspace_id|access_token|user\.name/)
  })

  it('uses the official bird and the application-native visual system on the public home', () => {
    expect(portalFrame).toContain("pathname === '/' ? ' is-home' : ''")
    expect(portalFrame).toContain('<CartoonMascot size={38} />')
    expect(landing).toContain("import { AssistantIntakeComposer } from '@/features/conversation/AssistantConversationThread'")
    expect(styles).toContain('.kp-cinematic-hero')
    expect(styles).toContain('.kp-native-suggestions')
  })

  it('keeps public and developer portals vertically scrollable inside the fixed app root', () => {
    expect(styles).toMatch(/\.public-landing\s*\{[^}]*height:\s*100dvh;[^}]*overflow-y:\s*auto;/s)
    expect(styles).toMatch(/\.developer-portal\s*\{[^}]*height:\s*100dvh;[^}]*overflow-y:\s*auto;/s)
  })

  it('keeps the estimating hero functional without unsupported vanity metrics', () => {
    expect(landing).toContain('className="kp-cinematic-hero"')
    expect(landing).toContain('Смета и документы — из одного сообщения')
    expect(landing).toContain('Объём')
    expect(landing).toContain('Источник')
    expect(landing).toContain('Смета по чертежам')
    expect(landing).toContain('Проверить готовую смету')
    expect(landing).toContain('Сравнить цены')
    expect(landing).toContain('navigate(`/app?q=${encodeURIComponent(task)}`)')
    expect(landing).not.toMatch(/500\+|50\+|98%|24\/7/)
  })

  it('keeps the wider portal navigation while limiting home to one focused workflow', () => {
    for (const label of ['Продукт', 'Тарифы', 'API', 'Документация', 'Безопасность']) {
      expect(portalFrame).toContain(`label: '${label}'`)
    }
    expect(landing).not.toContain('kp-cycle')
    expect(landing).not.toContain('kp-how')
    expect(landing).not.toContain('kp-audience')
    expect(landing).toContain('id="workflow"')
    expect(publicInfo).toContain('Т-Банк · ЮKassa · СБП QR')
    expect(publicInfo).toContain('<strong>Не подключено</strong>')
  })

  it('excludes application routes from robots and sitemap', () => {
    for (const path of ['/app', '/chat', '/settings', '/control']) {
      expect(robots).toContain(`Disallow: ${path}`)
      expect(sitemap).not.toContain(`<loc>https://kolibriai.ru${path}`)
    }
    for (const path of ['/', '/pricing', '/security', '/privacy', '/terms', '/developers', '/docs']) {
      expect(sitemap).toContain(`<loc>https://kolibriai.ru${path}</loc>`)
    }
  })

  it('adds an HTTP noindex header to private SPA routes', () => {
    expect(nginx).toContain('location ~ ^/(app|chat|library|apps|estimates|documents|contracts|agents|control|servers|settings|login|playground|share)(/|$)')
    expect(nginx).toContain('add_header X-Robots-Tag "noindex, nofollow, noarchive" always;')
  })
})
