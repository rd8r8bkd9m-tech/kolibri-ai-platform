import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { FileArtifact, ImageArtifact } from '@/lib/api'
import ArtifactCard from './ArtifactCard'

const image: ImageArtifact = {
  id: 'c1c4425b-b4ee-4bb9-83dc-2f78053c4348',
  type: 'image',
  revision: 1,
  title: 'Сгенерированное изображение',
  prompt: 'сгенерируй цветы',
  mime_type: 'image/png',
  size_bytes: 881_395,
  sha256: 'a'.repeat(64),
  model: 'codex-cli:account-default',
  created_at: '2026-07-14T12:00:00+03:00',
  updated_at: '2026-07-14T12:00:01+03:00',
  url: '/api/v1/artifacts/images/c1c4425b-b4ee-4bb9-83dc-2f78053c4348',
  download_url: '/api/v1/artifacts/images/c1c4425b-b4ee-4bb9-83dc-2f78053c4348?download=true',
  revision_url: '/api/v1/artifacts/c1c4425b-b4ee-4bb9-83dc-2f78053c4348?revision=1',
  revision_download_url: '/api/v1/artifacts/c1c4425b-b4ee-4bb9-83dc-2f78053c4348?revision=1&download=true',
  reopen_url: '/api/v1/artifacts/c1c4425b-b4ee-4bb9-83dc-2f78053c4348/reopen',
  history_url: '/api/v1/artifacts/c1c4425b-b4ee-4bb9-83dc-2f78053c4348/history',
}

describe('ArtifactCard image renderer', () => {
  it('renders the verified bytes URL and a real download action inline', () => {
    const verifiedImage = { ...image, object_url: 'blob:verified-image-bytes' }
    const html = renderToStaticMarkup(
      <ArtifactCard artifact={{ type: 'image', value: verifiedImage }} onOpen={vi.fn()} onRetry={vi.fn()} />,
    )

    expect(html).toContain(`src="${verifiedImage.object_url}"`)
    expect(html).toContain(`alt="${image.prompt}"`)
    expect(html).toContain(`href="${image.download_url.replaceAll('&', '&amp;')}"`)
    expect(html).not.toContain(`src="${image.url}"`)
    expect(html).not.toContain('codex-cli:account-default')
    expect(html).toContain(`data-artifact-id="${image.id}"`)
    expect(html).toContain(`data-artifact-reopen-url="${image.reopen_url}"`)
    expect(html).toContain(`data-artifact-download-url="${image.download_url.replaceAll('&', '&amp;')}"`)
    expect(html).toContain('data-artifact-download')
    expect(html).toContain('data-artifact-open')
    expect(html).toContain('байты проверены')
    expect(html).toContain('На весь экран')
    expect(html).toContain('Скачать')
    expect(html).toContain('Повторить')
  })

  it('renders no image card from metadata without verified runtime bytes', () => {
    const html = renderToStaticMarkup(
      <ArtifactCard artifact={{ type: 'image', value: image }} onOpen={vi.fn()} />,
    )

    expect(html).toBe('')
  })
})

const file: FileArtifact = {
  id: '33333333-3333-4333-8333-333333333333',
  type: 'document.pdf',
  revision: 1,
  title: 'Отчёт',
  filename: 'report.pdf',
  mime_type: 'application/pdf',
  size_bytes: 4096,
  sha256: 'b'.repeat(64),
  created_at: '2026-07-14T12:00:00+03:00',
  updated_at: '2026-07-14T12:00:01+03:00',
  metadata: {},
  url: '/api/v1/artifacts/33333333-3333-4333-8333-333333333333',
  download_url: '/api/v1/artifacts/33333333-3333-4333-8333-333333333333?download=true',
  revision_url: '/api/v1/artifacts/33333333-3333-4333-8333-333333333333?revision=1',
  revision_download_url: '/api/v1/artifacts/33333333-3333-4333-8333-333333333333?revision=1&download=true',
  reopen_url: '/api/v1/artifacts/33333333-3333-4333-8333-333333333333/reopen',
  history_url: '/api/v1/artifacts/33333333-3333-4333-8333-333333333333/history',
}

describe('ArtifactCard file renderer', () => {
  it('renders only a byte-verified file with real open and download controls', () => {
    const verified = { ...file, object_url: 'blob:verified-pdf' }
    const html = renderToStaticMarkup(
      <ArtifactCard artifact={{ type: 'file', value: verified }} onOpen={vi.fn()} />,
    )
    expect(html).toContain('PDF-документ')
    expect(html).toContain('SHA-256 проверен')
    expect(html).toContain('href="blob:verified-pdf"')
    expect(html).toContain('download="report.pdf"')
  })

  it('renders no file card from an unverified manifest', () => {
    expect(renderToStaticMarkup(
      <ArtifactCard artifact={{ type: 'file', value: file }} onOpen={vi.fn()} />,
    )).toBe('')
  })
})
