import { ensureShellBootstrap, getAuthToken } from '@/lib/api'

type ExportFormat = 'pdf' | 'csv' | 'json' | 'xlsx'

interface ExportRuntime {
  fetch: typeof fetch
  ensureSession: (force?: boolean) => Promise<unknown>
  createObjectURL: (blob: Blob) => string
  revokeObjectURL: (url: string) => void
  createDownloadLink: () => {
    href: string
    download: string
    click: () => void
    remove: () => void
  }
  appendDownloadLink: (link: ReturnType<ExportRuntime['createDownloadLink']>) => void
  defer: (callback: () => void, delay: number) => unknown
}

export function browserRuntime(): ExportRuntime {
  return {
    // Safari/WebKit and some embedded browsers require the Window receiver;
    // passing the native method as a bare callback raises "Illegal invocation".
    fetch: (...args) => window.fetch(...args),
    ensureSession: ensureShellBootstrap,
    createObjectURL: blob => URL.createObjectURL(blob),
    revokeObjectURL: url => URL.revokeObjectURL(url),
    createDownloadLink: () => document.createElement('a'),
    appendDownloadLink: link => document.body.append(link as HTMLAnchorElement),
    defer: (callback, delay) => window.setTimeout(callback, delay),
  }
}

function requestHeaders(accept: string): HeadersInit {
  const token = getAuthToken()
  return token ? { Accept: accept, Authorization: `Bearer ${token}` } : { Accept: accept }
}

async function loadExport(url: string, accept: string, runtime: ExportRuntime): Promise<Blob> {
  const request = () => runtime.fetch(url, {
    method: 'GET',
    headers: requestHeaders(accept),
    credentials: 'include',
    cache: 'no-store',
  })
  await runtime.ensureSession()
  let response = await request()
  if (response.status === 428) {
    await runtime.ensureSession(true)
    response = await request()
  }
  if (!response.ok) throw new Error(`Export returned HTTP ${response.status}`)
  const contentType = response.headers.get('content-type')?.split(';', 1)[0]?.trim().toLowerCase()
  if (contentType !== accept) throw new Error('Export returned an unexpected file type')
  const bytes = await response.arrayBuffer()
  if (bytes.byteLength === 0) throw new Error('Export returned an empty file')
  return new Blob([bytes], { type: accept })
}

export function estimateExportFilename(title: string, version: number, format: ExportFormat): string {
  const withoutControlCharacters = Array.from(
    title.trim(),
    character => character.charCodeAt(0) < 32 ? ' ' : character,
  ).join('')
  const safeTitle = withoutControlCharacters
    .replace(/[<>:"/\\|?*]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 96)
  return `${safeTitle || 'Смета'} — версия ${version}.${format}`
}

const EXPORT_MIME: Record<ExportFormat, string> = {
  pdf: 'application/pdf',
  csv: 'text/csv',
  json: 'application/json',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}

/** Download without navigating the editor or creating a disposable blank tab. */
export async function downloadEstimateExport(
  url: string,
  filename: string,
  format: ExportFormat,
  runtime: ExportRuntime = browserRuntime(),
): Promise<void> {
  const blob = await loadExport(url, EXPORT_MIME[format], runtime)
  const objectUrl = runtime.createObjectURL(blob)
  const link = runtime.createDownloadLink()
  link.href = objectUrl
  link.download = filename
  runtime.appendDownloadLink(link)
  link.click()
  link.remove()
  runtime.defer(() => runtime.revokeObjectURL(objectUrl), 0)
}
