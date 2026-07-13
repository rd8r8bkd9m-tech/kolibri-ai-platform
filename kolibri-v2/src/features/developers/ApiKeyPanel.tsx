import { useEffect, useState } from 'react'
import { Check, Copy, KeyRound, Trash2 } from 'lucide-react'
import { Link } from 'react-router'
import { useLocale } from '@/features/localization'
import { developerApiKeys, type AuthUser, type DeveloperApiKey, type DeveloperApiKeyCreated } from '@/lib/api'

interface ApiKeyPanelProps {
  user: AuthUser | null
}

function idempotencyKey(): string {
  return `developer-key:${globalThis.crypto.randomUUID()}`
}

export default function ApiKeyPanel({ user }: ApiKeyPanelProps) {
  const { locale, t } = useLocale()
  const [keys, setKeys] = useState<DeveloperApiKey[]>([])
  const [name, setName] = useState('')
  const [created, setCreated] = useState<DeveloperApiKeyCreated | null>(null)
  const [loading, setLoading] = useState(Boolean(user))
  const [submitting, setSubmitting] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user) return
    let active = true
    developerApiKeys.list()
      .then(result => { if (active) setKeys(result.items.filter(key => !key.revoked_at)) })
      .catch(() => { if (active) setError(t('developer.keyRequestFailed')) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [t, user])

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

  const createKey = async () => {
    const safeName = name.trim()
    if (!safeName || submitting) return
    setSubmitting(true)
    setError('')
    setCopied(false)
    try {
      const result = await developerApiKeys.create(safeName, idempotencyKey())
      setKeys(current => [result, ...current.filter(key => key.id !== result.id)])
      setCreated(result)
      setName('')
    } catch {
      setError(t('developer.keyRequestFailed'))
    } finally {
      setSubmitting(false)
    }
  }

  const copyCreatedKey = async () => {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.key)
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
    } catch {
      setError(t('developer.keyRequestFailed'))
    }
  }

  return (
    <section className="developer-panel" aria-labelledby="developer-api-key-title">
      <div className="developer-panel-heading">
        <KeyRound aria-hidden="true" />
        <div>
          <h2 id="developer-api-key-title">{t('developer.keysTitle')}</h2>
          <p>{t('developer.keysCopy')}</p>
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
          <code>{created.key}</code>
          <button type="button" onClick={() => void copyCreatedKey()}>
            {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
            {copied ? t('developer.keyCopied') : t('developer.copyKey')}
          </button>
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
              <span>{key.prefix}… · {new Date(key.created_at).toLocaleDateString(locale)}</span>
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
