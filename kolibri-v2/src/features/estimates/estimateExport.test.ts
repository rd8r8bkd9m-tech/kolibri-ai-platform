import { describe, expect, it, vi } from 'vitest'
import { downloadEstimateExport, estimateExportFilename, previewEstimatePdf } from './estimateExport'

function runtime(response: Response) {
  const preview = {
    opener: {} as unknown,
    close: vi.fn(),
    document: { title: '', body: { textContent: null as string | null } },
    location: { replace: vi.fn() },
  }
  const link = { href: '', download: '', click: vi.fn(), remove: vi.fn() }
  return {
    preview,
    link,
    value: {
      fetch: vi.fn().mockResolvedValue(response),
      ensureSession: vi.fn().mockResolvedValue({}),
      open: vi.fn().mockReturnValue(preview),
      createObjectURL: vi.fn().mockReturnValue('blob:estimate-export'),
      revokeObjectURL: vi.fn(),
      createDownloadLink: vi.fn().mockReturnValue(link),
      appendDownloadLink: vi.fn(),
      defer: vi.fn(),
    },
  }
}

describe('estimate export UX', () => {
  it('opens PDF bytes in a browser preview instead of downloading the API response', async () => {
    const test = runtime(new Response('%PDF-1.7\n', {
      headers: { 'Content-Type': 'application/pdf; charset=binary' },
    }))

    await previewEstimatePdf('/api/v1/estimates/e-1/pdf?version=2', test.value)

    expect(test.value.open).toHaveBeenCalledWith('', '_blank')
    expect(test.preview.opener).toBeNull()
    expect(test.preview.location.replace).toHaveBeenCalledWith('blob:estimate-export')
    expect(test.value.createDownloadLink).not.toHaveBeenCalled()
    expect(test.value.fetch).toHaveBeenCalledWith(
      '/api/v1/estimates/e-1/pdf?version=2',
      expect.objectContaining({ credentials: 'include', cache: 'no-store' }),
    )
    expect(test.value.ensureSession).toHaveBeenCalledOnce()
  })

  it('downloads XLSX through a temporary link without opening a tab', async () => {
    const test = runtime(new Response(new Uint8Array([0x50, 0x4b, 0x03, 0x04]), {
      headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
    }))

    await downloadEstimateExport('/api/v1/estimates/e-1/export/xlsx?version=2', 'Смета.xlsx', 'xlsx', test.value)

    expect(test.value.open).not.toHaveBeenCalled()
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

  it('closes the preview when the server returns a non-PDF response', async () => {
    const test = runtime(new Response('{"detail":"failed"}', {
      headers: { 'Content-Type': 'application/json' },
    }))

    await expect(previewEstimatePdf('/api/pdf', test.value)).rejects.toThrow('unexpected file type')
    expect(test.preview.close).toHaveBeenCalledOnce()
    expect(test.preview.location.replace).not.toHaveBeenCalled()
  })

  it('renews the shell bootstrap once after 428 and then opens the PDF', async () => {
    const test = runtime(new Response('%PDF-1.7\n', {
      headers: { 'Content-Type': 'application/pdf' },
    }))
    test.value.fetch
      .mockResolvedValueOnce(new Response('{"detail":"session_bootstrap_required"}', {
        status: 428,
        headers: { 'Content-Type': 'application/json' },
      }))
      .mockResolvedValueOnce(new Response('%PDF-1.7\n', {
        headers: { 'Content-Type': 'application/pdf' },
      }))

    await previewEstimatePdf('/api/pdf', test.value)

    expect(test.value.ensureSession).toHaveBeenNthCalledWith(1)
    expect(test.value.ensureSession).toHaveBeenNthCalledWith(2, true)
    expect(test.value.fetch).toHaveBeenCalledTimes(2)
    expect(test.preview.location.replace).toHaveBeenCalledWith('blob:estimate-export')
  })
})
