import { useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router'
import Composer from '@/features/conversation/Composer'
import CartoonMascot from '@/components/CartoonMascot'
import { capabilityPrompt, useCapabilities, type UiCapabilityKey } from '@/features/capabilities'
import { LocalizedMultiline, useLocale } from '@/features/localization'
import { verifiedFirstName, type ShellOutletContext } from '@/features/auth/shellIdentity'

export default function Home() {
  const { t } = useLocale()
  const { user } = useOutletContext<ShellOutletContext>()
  const firstName = verifiedFirstName(user)
  const [input, setInput] = useState('')
  const navigate = useNavigate()
  const { menu: capabilityMenu } = useCapabilities()
  const suggestions = [t('home.suggestionEstimate'), t('home.suggestionContract'), t('home.suggestionResearch')]

  const startConversation = (value = input) => {
    const prompt = value.trim()
    if (!prompt) return
    navigate(`/chat?q=${encodeURIComponent(prompt)}`)
  }

  return (
    <section className="conversation-home" aria-labelledby="home-title">
      <div className="conversation-home-content">
        <CartoonMascot size={58} className="conversation-home-mascot" />
        <p className="conversation-eyebrow">{t('shell.workspace')}</p>
        <h1 id="home-title"><span className="conversation-home-desktop-title">{t('home.title')}</span><span className="conversation-home-mobile-title"><LocalizedMultiline text={firstName
          ? t('home.mobileTitleKnown', { name: firstName })
          : t('home.mobileTitleGuest')
        } /></span></h1>
        <p className="conversation-home-copy">
          {t('home.copy')}
        </p>

        <div className="conversation-home-composer">
          <Composer
            value={input}
            onChange={setInput}
            onSend={() => startConversation()}
            capabilities={capabilityMenu}
            onCapability={(key: UiCapabilityKey) => setInput(capabilityPrompt(key))}
            placeholder={t('composer.placeholder')}
          />
        </div>

        <div className="conversation-suggestions" aria-label={t('home.examples')}>
          {suggestions.map(suggestion => (
            <button key={suggestion} type="button" onClick={() => startConversation(suggestion)}>
              {suggestion}
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}
