import { useEffect, useMemo, useState } from 'react'
import { Building2, Check, LoaderCircle, Plus, UserRoundX, Users } from 'lucide-react'
import {
  ApiError,
  organizations as organizationsApi,
  type OrganizationMembership,
  type OrganizationRole,
  type OrganizationSummary,
  type CompanyProfile,
} from '@/lib/api'
import { useLocale, type TranslationKey } from '@/features/localization'

export type MemberAccessState = 'idle' | 'loading' | 'ready' | 'denied' | 'error'

interface OrganizationSettingsProps {
  userId: string
  items: OrganizationSummary[]
  loading: boolean
  listError: boolean
  onRefresh: () => Promise<void>
}

interface OrganizationSettingsViewProps {
  userId: string
  items: OrganizationSummary[]
  loading: boolean
  listError: boolean
  switchingId: string | null
  creating: boolean
  createOpen: boolean
  organizationName: string
  organizationSlug: string
  actionError: string
  memberAccess: MemberAccessState
  members: OrganizationMembership[]
  memberActionId: string | null
  inviteEmail: string
  inviteRole: Exclude<OrganizationRole, 'owner'>
  inviting: boolean
  onOpenCreate: () => void
  onOrganizationName: (value: string) => void
  onOrganizationSlug: (value: string) => void
  onCreate: () => void
  onSelect: (organizationId: string) => void
  onInviteEmail: (value: string) => void
  onInviteRole: (value: Exclude<OrganizationRole, 'owner'>) => void
  onInvite: () => void
  onRole: (membership: OrganizationMembership, role: OrganizationRole) => void
  onSuspend: (membership: OrganizationMembership) => void
}

const roleKey: Record<OrganizationRole, TranslationKey> = {
  owner: 'settings.roleOwner',
  admin: 'settings.roleAdmin',
  member: 'settings.roleMember',
}

function actionErrorKey(error: unknown): TranslationKey {
  if (!(error instanceof ApiError)) return 'settings.organizationActionFailed'
  if (error.detail === 'invitee_not_found') return 'settings.organizationActionFailed'
  return 'settings.organizationActionFailed'
}

export default function OrganizationSettings({
  userId,
  items,
  loading,
  listError,
  onRefresh,
}: OrganizationSettingsProps) {
  const { t } = useLocale()
  const active = useMemo(() => items.find(item => item.selected) ?? null, [items])
  const [switchingId, setSwitchingId] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [organizationName, setOrganizationName] = useState('')
  const [organizationSlug, setOrganizationSlug] = useState('')
  const [actionError, setActionError] = useState('')
  const [memberAccess, setMemberAccess] = useState<MemberAccessState>('idle')
  const [members, setMembers] = useState<OrganizationMembership[]>([])
  const [memberActionId, setMemberActionId] = useState<string | null>(null)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<Exclude<OrganizationRole, 'owner'>>('member')
  const [inviting, setInviting] = useState(false)

  useEffect(() => {
    let current = true
    if (!active) return () => { current = false }
    const initial = window.setTimeout(() => {
      if (!current) return
      setMemberAccess('loading')
      setMembers([])
      organizationsApi.memberships(active.id)
        .then(payload => {
          if (!current) return
          setMembers(payload.items)
          setMemberAccess('ready')
        })
        .catch(error => {
          if (!current) return
          setMemberAccess(error instanceof ApiError && [403, 404].includes(error.status) ? 'denied' : 'error')
        })
    }, 0)
    return () => {
      current = false
      window.clearTimeout(initial)
    }
  }, [active])

  const createOrganization = async () => {
    const name = organizationName.trim()
    if (!name || creating) return
    setCreating(true)
    setActionError('')
    try {
      await organizationsApi.create({
        name,
        ...(organizationSlug.trim() ? { slug: organizationSlug.trim().toLowerCase() } : {}),
      })
      setOrganizationName('')
      setOrganizationSlug('')
      setCreateOpen(false)
      await onRefresh()
    } catch (error) {
      setActionError(t(actionErrorKey(error)))
    } finally {
      setCreating(false)
    }
  }

  const selectOrganization = async (organizationId: string) => {
    if (switchingId) return
    setSwitchingId(organizationId)
    setActionError('')
    try {
      await organizationsApi.select(organizationId)
      window.location.reload()
    } catch (error) {
      setActionError(t(actionErrorKey(error)))
      setSwitchingId(null)
    }
  }

  const refreshMembers = async () => {
    if (!active) return
    const payload = await organizationsApi.memberships(active.id)
    setMembers(payload.items)
    setMemberAccess('ready')
  }

  const invite = async () => {
    if (!active || !inviteEmail.trim() || inviting || memberAccess !== 'ready') return
    setInviting(true)
    setActionError('')
    try {
      await organizationsApi.invite(active.id, { email: inviteEmail.trim(), role: inviteRole })
      setInviteEmail('')
      await refreshMembers()
    } catch (error) {
      setActionError(t(actionErrorKey(error)))
    } finally {
      setInviting(false)
    }
  }

  const changeRole = async (membership: OrganizationMembership, role: OrganizationRole) => {
    if (!active || memberAccess !== 'ready' || membership.role === role) return
    setMemberActionId(membership.id)
    setActionError('')
    try {
      const updated = await organizationsApi.changeRole(active.id, membership.id, role)
      setMembers(current => current.map(item => item.id === updated.id ? updated : item))
    } catch (error) {
      setActionError(t(actionErrorKey(error)))
    } finally {
      setMemberActionId(null)
    }
  }

  const suspend = async (membership: OrganizationMembership) => {
    if (!active || memberAccess !== 'ready' || membership.user.id === userId) return
    if (!window.confirm(t('settings.suspendConfirm'))) return
    setMemberActionId(membership.id)
    setActionError('')
    try {
      const updated = await organizationsApi.suspend(active.id, membership.id)
      setMembers(current => current.map(item => item.id === updated.id ? updated : item))
    } catch (error) {
      setActionError(t(actionErrorKey(error)))
    } finally {
      setMemberActionId(null)
    }
  }

  return (
    <div className="space-y-8">
      {active && <CompanyProfileForm key={`${active.id}:${JSON.stringify(active.company_profile || {})}`} organization={active} onRefresh={onRefresh} />}
      <OrganizationSettingsView
      userId={userId}
      items={items}
      loading={loading}
      listError={listError}
      switchingId={switchingId}
      creating={creating}
      createOpen={createOpen}
      organizationName={organizationName}
      organizationSlug={organizationSlug}
      actionError={actionError}
      memberAccess={memberAccess}
      members={members}
      memberActionId={memberActionId}
      inviteEmail={inviteEmail}
      inviteRole={inviteRole}
      inviting={inviting}
      onOpenCreate={() => setCreateOpen(value => !value)}
      onOrganizationName={setOrganizationName}
      onOrganizationSlug={setOrganizationSlug}
      onCreate={() => { void createOrganization() }}
      onSelect={organizationId => { void selectOrganization(organizationId) }}
      onInviteEmail={setInviteEmail}
      onInviteRole={setInviteRole}
      onInvite={() => { void invite() }}
      onRole={(membership, role) => { void changeRole(membership, role) }}
      onSuspend={membership => { void suspend(membership) }}
      />
    </div>
  )
}

const companyFields: Array<{ key: keyof CompanyProfile; label: string; placeholder?: string }> = [
  { key: 'legal_name', label: 'Юридическое наименование', placeholder: 'ООО «Компания»' },
  { key: 'inn', label: 'ИНН' },
  { key: 'kpp', label: 'КПП' },
  { key: 'ogrn', label: 'ОГРН / ОГРНИП' },
  { key: 'director_name', label: 'Руководитель' },
  { key: 'director_title', label: 'Должность руководителя' },
  { key: 'legal_address', label: 'Юридический адрес' },
  { key: 'actual_address', label: 'Фактический адрес' },
  { key: 'phone', label: 'Телефон' },
  { key: 'email', label: 'Электронная почта' },
  { key: 'bank_name', label: 'Банк' },
  { key: 'bik', label: 'БИК' },
  { key: 'checking_account', label: 'Расчётный счёт' },
  { key: 'correspondent_account', label: 'Корреспондентский счёт' },
]

function CompanyProfileForm({ organization, onRefresh }: { organization: OrganizationSummary; onRefresh: () => Promise<void> }) {
  const [profile, setProfile] = useState<CompanyProfile>(() => ({ ...(organization.company_profile || {}) }))
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const save = async () => {
    if (saving) return
    setSaving(true)
    setSaved(false)
    try {
      await organizationsApi.updateProfile(organization.id, profile)
      setSaved(true)
      await onRefresh()
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="company-profile-settings" aria-labelledby="company-profile-heading">
      <header><div><h2 id="company-profile-heading">Реквизиты компании</h2><p>Один раз заполните данные подрядчика — они автоматически попадут в КП, договоры и акты.</p></div>{saved && <span role="status"><Check size={15} />Сохранено</span>}</header>
      <div className="company-profile-grid">
        {companyFields.map(field => <label key={field.key}>{field.label}<input value={profile[field.key] || ''} placeholder={field.placeholder} onChange={event => setProfile(current => ({ ...current, [field.key]: event.target.value }))} /></label>)}
      </div>
      <button type="button" onClick={() => void save()} disabled={saving}>{saving ? 'Сохраняю…' : 'Сохранить реквизиты'}</button>
    </section>
  )
}

export function OrganizationSettingsView(props: OrganizationSettingsViewProps) {
  const { t } = useLocale()
  const active = props.items.find(item => item.selected) ?? null

  return (
    <div className="space-y-8" data-organization-settings>
      <section aria-labelledby="organization-heading">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 id="organization-heading" className="text-[16px] font-semibold text-[var(--text-primary)]">
              {t('settings.organization')}
            </h2>
            <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">{t('settings.organizationCopy')}</p>
          </div>
          <button
            type="button"
            onClick={props.onOpenCreate}
            className="inline-flex min-h-11 items-center gap-2 rounded-[var(--radius-md)] border border-[var(--border-subtle)] px-3 text-[13px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
          >
            <Plus size={15} aria-hidden="true" />
            <span className="hidden sm:inline">{t('settings.createOrganization')}</span>
            <span className="sm:hidden">{t('settings.createOrganization')}</span>
          </button>
        </div>

        {props.createOpen && (
          <div className="mb-5 grid gap-3 border-b border-[var(--border-subtle)] pb-5 sm:grid-cols-[1fr_0.8fr_auto]">
            <input
              value={props.organizationName}
              onChange={event => props.onOrganizationName(event.target.value)}
              placeholder={t('settings.organizationName')}
              className="min-h-11 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)]"
            />
            <input
              value={props.organizationSlug}
              onChange={event => props.onOrganizationSlug(event.target.value)}
              placeholder={t('settings.organizationSlug')}
              className="min-h-11 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)]"
            />
            <button
              type="button"
              disabled={!props.organizationName.trim() || props.creating}
              onClick={props.onCreate}
              className="min-h-11 rounded-[var(--radius-md)] bg-[var(--text-primary)] px-4 text-[13px] font-medium text-[var(--bg-primary)] disabled:opacity-40"
            >
              {props.creating ? t('settings.creatingOrganization') : t('settings.createOrganization')}
            </button>
          </div>
        )}

        {props.loading ? (
          <p className="py-4 text-[13px] text-[var(--text-tertiary)]">{t('app.loading')}</p>
        ) : props.listError ? (
          <p className="py-4 text-[13px] text-red-500">{t('settings.organizationListFailed')}</p>
        ) : props.items.length === 0 ? (
          <p className="py-4 text-[13px] text-[var(--text-tertiary)]">{t('settings.noOrganization')}</p>
        ) : (
          <div className="divide-y divide-[var(--border-subtle)] border-y border-[var(--border-subtle)]">
            {props.items.map(organization => (
              <div key={organization.id} className="flex min-h-16 items-center gap-3 py-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]">
                  <Building2 size={17} strokeWidth={1.7} aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-[13px] font-medium text-[var(--text-primary)]">{organization.name}</p>
                    {organization.selected && (
                      <span className="inline-flex items-center gap-1 text-[11px] text-[var(--accent-teal)]">
                        <Check size={12} aria-hidden="true" /> {t('settings.currentOrganization')}
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 truncate text-[11px] text-[var(--text-tertiary)]">
                    {organization.slug} · {t(roleKey[organization.role])}
                  </p>
                </div>
                {!organization.selected && (
                  <button
                    type="button"
                    disabled={Boolean(props.switchingId)}
                    onClick={() => props.onSelect(organization.id)}
                    className="min-h-11 shrink-0 rounded-[var(--radius-md)] px-3 text-[12px] font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] disabled:opacity-40"
                  >
                    {props.switchingId === organization.id ? t('settings.switchingOrganization') : t('settings.switchOrganization')}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {active && (
        <section aria-labelledby="members-heading">
          <div className="mb-4 flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-[var(--radius-md)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]">
              <Users size={17} strokeWidth={1.7} aria-hidden="true" />
            </span>
            <div>
              <h2 id="members-heading" className="text-[16px] font-semibold text-[var(--text-primary)]">{t('settings.members')}</h2>
              <p className="mt-0.5 text-[12px] text-[var(--text-tertiary)]">{t('settings.membersCopy')}</p>
            </div>
          </div>

          {props.memberAccess === 'loading' && (
            <p className="flex min-h-11 items-center gap-2 text-[13px] text-[var(--text-tertiary)]">
              <LoaderCircle size={15} className="animate-spin" aria-hidden="true" /> {t('settings.membersLoading')}
            </p>
          )}
          {props.memberAccess === 'denied' && (
            <p className="py-3 text-[13px] text-[var(--text-tertiary)]">{t('settings.membersDenied')}</p>
          )}
          {props.memberAccess === 'error' && (
            <p className="py-3 text-[13px] text-red-500">{t('settings.membersFailed')}</p>
          )}
          {props.memberAccess === 'ready' && (
            <>
              <div className="mb-5 grid gap-3 sm:grid-cols-[1fr_150px_auto]">
                <input
                  type="email"
                  value={props.inviteEmail}
                  onChange={event => props.onInviteEmail(event.target.value)}
                  placeholder={t('settings.memberEmail')}
                  className="min-h-11 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-teal)]"
                />
                <select
                  value={props.inviteRole}
                  onChange={event => props.onInviteRole(event.target.value as Exclude<OrganizationRole, 'owner'>)}
                  className="min-h-11 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-primary)] outline-none"
                >
                  <option value="member">{t('settings.roleMember')}</option>
                  <option value="admin">{t('settings.roleAdmin')}</option>
                </select>
                <button
                  type="button"
                  disabled={!props.inviteEmail.trim() || props.inviting}
                  onClick={props.onInvite}
                  className="min-h-11 rounded-[var(--radius-md)] bg-[var(--text-primary)] px-4 text-[13px] font-medium text-[var(--bg-primary)] disabled:opacity-40"
                >
                  {props.inviting ? t('settings.invitingMember') : t('settings.inviteMember')}
                </button>
              </div>

              <div className="divide-y divide-[var(--border-subtle)] border-y border-[var(--border-subtle)]">
                {props.members.map(membership => {
                  const isSelf = membership.user.id === props.userId
                  const suspended = membership.status === 'suspended'
                  return (
                    <div key={membership.id} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-medium text-[var(--text-primary)]">
                          {membership.user.name} {isSelf && <span className="font-normal text-[var(--text-tertiary)]">· {t('settings.you')}</span>}
                        </p>
                        <p className="mt-0.5 truncate text-[11px] text-[var(--text-tertiary)]">{membership.user.email}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        {suspended ? (
                          <span className="min-h-11 inline-flex items-center px-2 text-[12px] text-amber-600">{t('settings.statusSuspended')}</span>
                        ) : (
                          <select
                            aria-label={`${membership.user.name}: ${t('settings.organization')}`}
                            value={membership.role}
                            disabled={props.memberActionId === membership.id}
                            onChange={event => props.onRole(membership, event.target.value as OrganizationRole)}
                            className="min-h-11 min-w-32 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 text-[12px] text-[var(--text-primary)] outline-none"
                          >
                            <option value="member">{t('settings.roleMember')}</option>
                            <option value="admin">{t('settings.roleAdmin')}</option>
                            <option value="owner">{t('settings.roleOwner')}</option>
                          </select>
                        )}
                        {!suspended && !isSelf && (
                          <button
                            type="button"
                            disabled={props.memberActionId === membership.id}
                            onClick={() => props.onSuspend(membership)}
                            className="inline-flex min-h-11 items-center gap-1.5 rounded-[var(--radius-md)] px-2 text-[12px] text-[var(--text-tertiary)] hover:bg-red-500/10 hover:text-red-600 disabled:opacity-40"
                          >
                            <UserRoundX size={15} aria-hidden="true" />
                            <span className="hidden sm:inline">{t('settings.suspendMember')}</span>
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </section>
      )}

      {props.actionError && (
        <p role="alert" className="text-[13px] text-red-500">{props.actionError}</p>
      )}
    </div>
  )
}
