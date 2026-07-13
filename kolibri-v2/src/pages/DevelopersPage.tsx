import { ArrowRight, BookOpen, FlaskConical } from 'lucide-react'
import { Link } from 'react-router'
import DeveloperFrame from '@/features/developers/DeveloperFrame'
import ApiKeyPanel from '@/features/developers/ApiKeyPanel'
import { isDeveloperSurfaceLive } from '@/features/developers/developerCapabilities'
import { useCapabilities } from '@/features/capabilities'
import { useLocale } from '@/features/localization'
import type { AuthUser } from '@/lib/api'

export default function DevelopersPage({ user }: { user: AuthUser | null }) {
  const { t } = useLocale()
  const { catalog } = useCapabilities()
  const keyManagementLive = isDeveloperSurfaceLive(catalog, 'apiKeys')

  return (
    <DeveloperFrame title={t('developer.title')} copy={t('developer.copy')}>
      <div className="developer-card-grid">
        <Link to="/docs" className="developer-card">
          <BookOpen aria-hidden="true" />
          <div>
            <h2>{t('developer.docs')}</h2>
            <p>{t('developer.docsCopy')}</p>
          </div>
          <span>{t('developer.openDocs')} <ArrowRight aria-hidden="true" /></span>
        </Link>
        <Link to="/playground" className="developer-card">
          <FlaskConical aria-hidden="true" />
          <div>
            <h2>{t('developer.playground')}</h2>
            <p>{t('developer.playgroundCopy')}</p>
          </div>
          <span>{t('developer.openPlayground')} <ArrowRight aria-hidden="true" /></span>
        </Link>
      </div>

      {keyManagementLive && <ApiKeyPanel user={user} />}
    </DeveloperFrame>
  )
}
