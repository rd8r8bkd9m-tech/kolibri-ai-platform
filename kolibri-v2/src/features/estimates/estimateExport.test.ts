import { describe, expect, it, vi } from 'vitest'
import { browserRuntime, downloadEstimateExport, estimateExportFilename } from './estimateExport'

function runtime(response: Response) {
  const link = { href: '', download: '', click: vi.fn(), remove: vi.fn() }
  return {
    link,
    value: {
      fetch: vi.fn().mockResolvedValue(response),
      ensureSession: vi.fn().mockResolvedValue({}),
      createObjectURL: vi.fn().mockReturnValue('blob:estimate-export'),
      revokeObjectURL: vi.fn(),
      createDownloadLink: vi.fn().mockReturnValue(link),
      appendDownloadLink: vi.fn(),
      defer: vi.fn(),
    },
  }
}

describe('estimate export UX', () => {
  it('keeps the Window receiver when invoking the native browser fetch', async () => {
    const fakeWindow = {
      fetch: vi.fn(function (this: unknown) {
        expect(this).toBe(fakeWindow)
        return Promise.resolve(new Response('ok'))
      }),
      setTimeout: vi.fn(),
    }
    vi.stubGlobal('window', fakeWindow)

    try {
      await browserRuntime().fetch('/api/health')
      expect(fakeWindow.fetch).toHaveBeenCalledOnce()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('downloads XLSX through a temporary link without opening a tab', async () => {
    const test = runtime(new Response(new Uint8Array([0x50, 0x4b, 0x03, 0x04]), {
      headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
    }))

    await downloadEstimateExport('/api/v1/estimates/e-1/export/xlsx?version=2', 'Смета.xlsx', 'xlsx', test.value)

    expect(test.link.href).toBe('blob:estimate-export')
    expect(test.link.download).toBe('Смета.xlsx')
    expect(test.value.appendDownloadLink).toHaveBeenCalledWith(test.link)
    expect(test.link.click).toHaveBeenCalledOnce()
    expect(test.link.remove).toHaveBeenCalledOnce()
  })

  it('creates a safe readable filename', () => {
    expect(estimateExportFilename(' Смета: дом / Казань? ', 3, 'xlsx'))
      .toBe('Смета дом Казань — версия 3.xlsx')
  })
})
