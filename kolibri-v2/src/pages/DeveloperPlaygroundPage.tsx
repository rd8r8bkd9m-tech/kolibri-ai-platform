import { useState } from 'react'
import DeveloperFrame from '@/features/developers/DeveloperFrame'
import { isDeveloperSurfaceLive } from '@/features/developers/developerCapabilities'
import { useCapabilities } from '@/features/capabilities'
import { useLocale } from '@/features/localization'
import { chat } from '@/lib/api'

export default function DeveloperPlaygroundPage() {
  const { t } = useLocale()
  const { catalog } = useCapabilities()
  const available = isDeveloperSurfaceLive(catalog, 'chat')
  const [prompt, setPrompt] = useState('')
  const [result, setResult] = useState('')
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)

  const run = async () => {
    const input = prompt.trim()
    if (!available || !input || running) return
    setRunning(true)
    setError('')
    setResult('')
    try {
      const response = await chat.send([{ role: 'user', content: input }])
      if (!response.content.trim() || ['failed', 'error', 'unavailable', 'capability_unavailable'].includes(response.status)) {
        throw new Error('unavailable')
      }
      setResult(response.content)
    } catch {
      setError(t('developer.requestFailed'))
    } finally {
      setRunning(false)
    }
  }

  return (
    <DeveloperFrame title={t('developer.playground')} copy={t('developer.playgroundCopy')}>
      {!available ? (
        <section className="developer-panel">
          <p className="developer-muted">{t('developer.routeUnavailable')}</p>
        </section>
      ) : (
        <section className="developer-panel developer-playground" aria-label={t('developer.playground')}>
          <form onSubmit={event => { event.preventDefault(); void run() }}>
            <label htmlFor="developer-playground-prompt">{t('developer.prompt')}</label>
            <textarea
              id="developer-playground-prompt"
              value={prompt}
              onChange={event => setPrompt(event.target.value)}
              rows={6}
            />
            <button type="submit" disabled={!prompt.trim() || running}>
              {running ? t('developer.running') : t('developer.run')}
            </button>
          </form>
          {error && <p className="developer-error" role="alert">{error}</p>}
          {result && (
            <div className="developer-playground-result" aria-live="polite">
              <h2>{t('developer.result')}</h2>
              <p>{result}</p>
            </div>
          )}
        </section>
      )}
    </DeveloperFrame>
  )
}
