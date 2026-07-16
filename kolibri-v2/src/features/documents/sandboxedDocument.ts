const DOCUMENT_CSP = "default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; font-src data:; base-uri 'none'; form-action 'none'; frame-src 'none'"

export function sandboxedDocumentHtml(content: string): string {
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${DOCUMENT_CSP}"><meta name="referrer" content="no-referrer"><style>html{color-scheme:light}body{margin:0;padding:16px;font:14px/1.65 system-ui,sans-serif;color:#17201e;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse}th,td{border:1px solid #ddd;padding:6px;text-align:left}</style></head><body>${content}</body></html>`
}
