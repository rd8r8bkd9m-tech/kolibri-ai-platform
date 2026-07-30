import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { LocaleContext } from '@/features/localization/localeContext'
import { translate } from '@/features/localization/locale'
import type { OrganizationMembership, OrganizationSummary } from '@/lib/api'
import { OrganizationSettingsView, type MemberAccessState } from './OrganizationSettings'

const organizations: OrganizationSummary[] = [
  {
    id: 'org_1',
    name: 'Строй Профи',
    slug: 'stroy-profi',
    status: 'active',
    role: 'owner',
    membership_status: 'active',
    selected: true,
  },
  {
    id: 'org_2',
    name: 'Монолит',
    slug: 'monolit',
    status: 'active',
    role: 'member',
    membership_status: 'active',
    selected: false,
  },
]

const members: OrganizationMembership[] = [
  {
    id: 'membership_1',
    organization_id: 'org_1',
    user: { id: 'user_1', email: 'owner@example.ru', name: 'Анна' },
    role: 'owner',
    status: 'active',
    created_at: '2026-07-16T10:00:00Z',
    updated_at: '2026-07-16T10:00:00Z',
  },
  {
    id: 'membership_2',
    organization_id: 'org_1',
    user: { id: 'user_2', email: 'member@example.ru', name: 'Иван' },
    role: 'member',
    status: 'active',
    created_at: '2026-07-16T10:00:00Z',
    updated_at: '2026-07-16T10:00:00Z',
  },
]

function render(memberAccess: MemberAccessState) {
  const noop = vi.fn()
  return renderToStaticMarkup(
    <LocaleContext.Provider value={{ locale: 'ru', setLocale: noop, t: (key, params) => translate('ru', key, params) }}>
      <OrganizationSettingsView
        userId="user_1"
        items={organizations}
        loading={false}
        listError={false}
        switchingId={null}
        creating={false}
        createOpen={false}
        organizationName=""
        organizationSlug=""
        actionError=""
        memberAccess={memberAccess}
        members={members}
        memberActionId={null}
        inviteEmail=""
        inviteRole="member"
        inviting={false}
        onOpenCreate={noop}
        onOrganizationName={noop}
        onOrganizationSlug={noop}
        onCreate={noop}
        onSelect={noop}
        onInviteEmail={noop}
        onInviteRole={noop}
        onInvite={noop}
        onRole={noop}
        onSuspend={noop}
      />
    </LocaleContext.Provider>,
  )
}

describe('OrganizationSettingsView', () => {
  it('keeps member mutation controls hidden until the server grants membership access', () => {
    const denied = render('denied')

    expect(denied).toContain('Управление участниками доступно владельцу или администратору')
    expect(denied).not.toContain('type="email"')
    expect(denied).not.toContain('Пригласить')
    expect(denied).not.toContain('Приостановить')
  })

  it('renders active organization and server-authorized member controls without a dashboard', () => {
    const ready = render('ready')

    expect(ready).toContain('Строй Профи')
    expect(ready).toContain('Текущая')
    expect(ready).toContain('owner@example.ru')
    expect(ready).toContain('member@example.ru')
    expect(ready).toContain('Добавить участника')
    expect(ready).toContain('Приостановить')
    expect(ready).not.toContain('dashboard')
  })

  it('uses stacked mobile rows and touch-sized controls without horizontal table scrolling', () => {
    const ready = render('ready')

    expect(ready).toContain('flex-col gap-3 py-3 sm:flex-row')
    expect(ready).toContain('min-h-11')
    expect(ready).not.toContain('overflow-x-auto')
    expect(ready).not.toContain('<table')
  })
})
