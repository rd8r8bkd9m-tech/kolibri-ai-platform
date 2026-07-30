import { KOLIBRI_BUILD_RELEASE_ID } from './releaseIdentity'
import { useLocale } from '@/features/localization'

export default function OwnerBuildDiagnostics() {
  const { t } = useLocale()
  if (!KOLIBRI_BUILD_RELEASE_ID) return null

  return (
    <section className="owner-build-diagnostics" aria-label={t('settings.buildDiagnostics')}>
      <span>{t('settings.releaseId')}</span>
      <code>{KOLIBRI_BUILD_RELEASE_ID}</code>
    </section>
  )
}
