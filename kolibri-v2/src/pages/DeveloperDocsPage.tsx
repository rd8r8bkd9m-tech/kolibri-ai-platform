import DeveloperFrame from '@/features/developers/DeveloperFrame'
import { liveDeveloperEndpoints } from '@/features/developers/developerCapabilities'
import { useCapabilities } from '@/features/capabilities'
import { useLocale } from '@/features/localization'

export default function DeveloperDocsPage() {
  const { t } = useLocale()
  const { catalog } = useCapabilities()
  const endpoints = liveDeveloperEndpoints(catalog)

  return (
    <DeveloperFrame title={t('developer.docs')} copy={t('developer.docsCopy')}>
      <section className="developer-panel" aria-labelledby="developer-endpoints-title">
        <div className="developer-panel-heading">
          <div>
            <h2 id="developer-endpoints-title">{t('developer.liveEndpoints')}</h2>
            <p>{endpoints.length ? t('developer.copy') : t('developer.noEndpoints')}</p>
          </div>
        </div>
        {endpoints.length > 0 && (
          <div className="developer-endpoint-list">
            {endpoints.map(endpoint => (
              <div key={endpoint.path} className="developer-endpoint-row">
                <span>{endpoint.method}</span>
                <code>{endpoint.path}</code>
              </div>
            ))}
          </div>
        )}
      </section>
    </DeveloperFrame>
  )
}
