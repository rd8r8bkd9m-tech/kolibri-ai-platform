export interface ImageArtifactBrowserEvidence {
  rendered: boolean
  artifact_id: string
  revision: number | null
  sha256: string
  preview_src: string
  download_href: string
  download_url: string
  reopen_url: string
  has_blob_preview: boolean
  has_download_control: boolean
  has_open_control: boolean
  verified_label_visible: boolean
}

/**
 * Small DOM-only collector intended for Playwright `page.evaluate`.
 * It records only public artifact facts and browser-rendering state.
 */
export function collectImageArtifactBrowserEvidence(root: ParentNode = document): ImageArtifactBrowserEvidence {
  const text = (value: string | undefined | null, maximum = 2_000): string =>
    typeof value === 'string' && value.length <= maximum ? value : ''
  const card = root.querySelector<HTMLElement>('[data-artifact-kind="image"]')
  const image = card?.querySelector<HTMLImageElement>('.artifact-image-preview img') ?? null
  const download = card?.querySelector<HTMLAnchorElement>('[data-artifact-download]') ?? null
  const open = card?.querySelector<HTMLButtonElement>('[data-artifact-open]') ?? null
  const previewSrc = text(image?.getAttribute('src'))
  const downloadHref = text(download?.getAttribute('href'))
  const revision = Number(card?.dataset.artifactRevision)

  return {
    rendered: Boolean(card && image && previewSrc),
    artifact_id: text(card?.dataset.artifactId, 80),
    revision: Number.isSafeInteger(revision) && revision > 0 ? revision : null,
    sha256: text(card?.dataset.artifactSha256, 64),
    preview_src: previewSrc,
    download_href: downloadHref,
    download_url: text(card?.dataset.artifactDownloadUrl),
    reopen_url: text(card?.dataset.artifactReopenUrl),
    has_blob_preview: previewSrc.startsWith('blob:'),
    has_download_control: Boolean(download && downloadHref === card?.dataset.artifactDownloadUrl),
    has_open_control: Boolean(open),
    verified_label_visible: Boolean(card?.textContent?.includes('байты проверены')),
  }
}
