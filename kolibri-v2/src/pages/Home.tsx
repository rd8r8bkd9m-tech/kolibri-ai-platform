import { useState } from 'react'
import { useNavigate } from 'react-router'
import Composer from '@/features/conversation/Composer'
import { capabilityPrompt, useCapabilities, type UiCapabilityKey } from '@/features/capabilities'
import { useLocale } from '@/features/localization'

export default function Home() {
  const { t } = useLocale()
  const [input, setInput] = useState('')
  const navigate = useNavigate()
  const { menu: capabilityMenu } = useCapabilities()
  const startConversation = (value = input) => {
    const prompt = value.trim()
    if (!prompt) return
    navigate(`/chat?q=${encodeURIComponent(prompt)}`)
  }

  return (
    <section className="conversation-home" aria-labelledby="home-title">
      <div className="conversation-home-content">
        <h1 id="home-title">{t('home.title')}</h1>

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
      </div>
    </section>
  )
}
