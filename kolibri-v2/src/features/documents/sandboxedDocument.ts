const DOCUMENT_CSP = "default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; font-src data:; base-uri 'none'; form-action 'none'; frame-src 'none'"

const DOCUMENT_BASE_STYLES = `
html{color-scheme:light;background:#f5f5f3}
body{box-sizing:border-box;min-height:100vh;margin:0;padding:32px 40px;font:15px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#17201e;background:#fff;overflow-wrap:anywhere}
table{width:100%;border-collapse:collapse;margin:18px 0}
th,td{border:1px solid #d8dcda;padding:8px 10px;text-align:left;vertical-align:top}
th{background:#f5f7f6;font-weight:650}
h1,h2,h3{line-height:1.25;color:#111614}
h1{font-size:28px;margin:0 0 22px}
h2{font-size:20px;margin:28px 0 12px}
h3{font-size:16px;margin:22px 0 8px}
p{margin:0 0 12px}
ul,ol{padding-left:24px}
img{max-width:100%;height:auto}
@media(max-width:640px){body{padding:22px 18px;font-size:16px}table{font-size:13px}th,td{padding:7px}}
`

export function editableDocumentFragment(content: string): string {
  const body = /<body\b[^>]*>([\s\S]*?)<\/body>/i.exec(content)?.[1]
  if (body === undefined) return content
  const styles = [...content.matchAll(/<style\b[^>]*>[\s\S]*?<\/style>/gi)].map(match => match[0]).join('')
  return `${styles}${body}`
}

export function sandboxedDocumentHtml(content: string): string {
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${DOCUMENT_CSP}"><meta name="referrer" content="no-referrer"><style>${DOCUMENT_BASE_STYLES}</style></head><body>${editableDocumentFragment(content)}</body></html>`
}

export function editableDocumentHtml(content: string): string {
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${DOCUMENT_CSP}"><meta name="referrer" content="no-referrer"><style>${DOCUMENT_BASE_STYLES}body{outline:none;caret-color:#111614}body:focus{box-shadow:inset 0 0 0 2px #111614}td:focus,th:focus{background:#fffbe8}</style></head><body contenteditable="true" spellcheck="true" aria-label="Содержимое документа">${editableDocumentFragment(content)}</body></html>`
}
