import { useEffect, useState } from 'react'
import { Check, Copy, EyeOff, KeyRound, Trash2 } from 'lucide-react'
import { Link } from 'react-router'
import { useLocale } from '@/features/localization'
import {
  ApiError,
  developerApiKeys,
  type AuthUser,
  type DeveloperApiKey,
  type DeveloperApiKeyCreated,
} from '@/lib/api'
import { isOwnerRole } from '@/features/shell/releaseIdentity'

interface ApiKeyPanelProps {
  user: AuthUser | null
}

function keyMetadata(key: DeveloperApiKeyCreated): DeveloperApiKey {
  return {
    id: key.id,
    object: key.object,
    name: key.name,
    prefix: key.prefix,
    created_at: key.created_at,
    last_used_at: key.last_used_at,
    revoked: key.revoked,
    revoked_at: key.revoked_at,
  }
}

export default function ApiKeyPanel({ user }: ApiKeyPanelProps) {
  const { locale, t } = useLocale()
  const authorized = isOwnerRole(user?.role)
  const [keys, setKeys] = useState<DeveloperApiKey[]>([])
  const [name, setName] = useState('')
  const [created, setCreated] = useState<DeveloperApiKeyCreated | null>(null)
  const [loading, setLoading] = useState(Boolean(user && authorized))
  const [submitting, setSubmitting] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user || !authorized) return
    let active = true
    developerApiKeys.list()
      .then(result => {
        if (!active) return
        setKeys(result.data.filter(key => !key.revoked))
        setError('')
      })
      .catch(() => {
        if (!active) return
        setKeys([])
        setError(t('developer.keyRequestFailed'))
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [authorized, t, user])

  const handleOwnerRequestError = (reason: unknown) => {
    if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
      setKeys([])
      setCreated(null)
      setError(t('developer.keyRequestFailed'))
      return
    }
    setError(t('developer.keyRequestFailed'))
  }

  if (!user) {
    return (
      <section className="developer-panel" aria-labelledby="developer-api-key-title">
        <div className="developer-panel-heading">
          <KeyRound aria-hidden="true" />
          <div>
            <h2 id="developer-api-key-title">{t('developer.keysTitle')}</h2>
            <p>{t('developer.signInForKeys')}</p>
          </div>
        </div>
        <Link className="developer-primary-action is-inline" to="/login">{t('developer.signIn')}</Link>
      </section>
    )
  }

  if (!authorized) {
    return (
      <section className="developer-panel" aria-labelledby="developer-api-key-title">
        <div className="developer-panel-heading">
          <KeyRound aria-hidden="true" />
          <div>
            <h2 id="developer-api-key-title">{t('developer.keysTitle')}</h2>
            <p>Управление ключами доступно только владельцу платформы.</p>
          </div>
        </div>
        {error && <p className="developer-error" role="alert">{error}</p>}
      </section>
    )
  }

  const createKey = async () => {
    const safeName = name.trim()
    if (!safeName || submitting) return
    setSubmitting(true)
    setError('')
    setCopied(false)
    try {
      const result = await developerApiKeys.create(safeName)
      const metadata = keyMetadata(result)
      setKeys(current => [metadata, ...current.filter(key => key.id !== result.id)])
      setCreated(result)
      setName('')
    } catch (reason) {
      handleOwnerRequestError(reason)
    } finally {
      setSubmitting(false)
    }
  }

  const copyCreatedKey = async () => {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.secret)
      setCopied(true)
    } catch {
      setCopied(false)
      setError(t('developer.keyRequestFailed'))
    }
  }

  const revokeKey = async (key: DeveloperApiKey) => {
    if (!window.confirm(`${t('developer.revokeKey')}: ${key.name}?`)) return
    setError('')
    try {
      await developerApiKeys.revoke(key.id)
      setKeys(current => current.filter(item => item.id !== key.id))
      if (created?.id === key.id) setCreated(null)
    } catch (reason) {
      handleOwnerRequestError(reason)
    }
  }

  return (
    <section className="developer-panel" aria-labelledby="developer-api-key-title">
      <div className="developer-panel-titlebar">
        <div className="developer-panel-heading">
          <KeyRound aria-hidden="true" />
          <div>
            <h2 id="developer-api-key-title">{t('developer.keysTitle')}</h2>
            <p>{t('developer.keysCopy')}</p>
          </div>
        </div>
      </div>

      <form
        className="developer-key-form"
        onSubmit={event => { event.preventDefault(); void createKey() }}
      >
        <label htmlFor="developer-key-name">{t('developer.keyName')}</label>
        <div>
          <input
            id="developer-key-name"
            value={name}
            onChange={event => setName(event.target.value)}
            maxLength={80}
            autoComplete="off"
          />
          <button type="submit" disabled={!name.trim() || submitting}>
            {submitting ? t('developer.running') : t('developer.createKey')}
          </button>
        </div>
      </form>

      {created && (
        <div className="developer-created-key" role="status">
          <p>{t('developer.keyCreated')}</p>
          <code>{created.secret}</code>
          <div className="developer-created-key-actions">
            <button type="button" onClick={() => void copyCreatedKey()}>
              {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
              {copied ? t('developer.keyCopied') : t('developer.copyKey')}
            </button>
            <button type="button" onClick={() => setCreated(null)}>
              <EyeOff aria-hidden="true" />
              {t('developer.hideKey')}
            </button>
          </div>
        </div>
      )}

      {error && <p className="developer-error" role="alert">{error}</p>}

      <div className="developer-key-list" aria-live="polite">
        {loading && <p className="developer-muted">{t('developer.keysLoading')}</p>}
        {!loading && keys.length === 0 && <p className="developer-muted">{t('developer.keysEmpty')}</p>}
        {keys.map(key => (
          <article key={key.id} className="developer-key-row">
            <div>
              <strong>{key.name}</strong>
              <span>{key.prefix}… · {new Date(key.created_at * 1000).toLocaleDateString(locale)}</span>
            </div>
            <button type="button" onClick={() => void revokeKey(key)} aria-label={`${t('developer.revokeKey')}: ${key.name}`}>
              <Trash2 aria-hidden="true" />
              <span>{t('developer.revokeKey')}</span>
            </button>
          </article>
        ))}
      </div>
    </section>
  )
}
