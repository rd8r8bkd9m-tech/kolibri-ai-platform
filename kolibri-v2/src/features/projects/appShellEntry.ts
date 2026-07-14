export function shouldRedirectAppEntry(search: string, hash: string): boolean {
  if (search) return true
  return Boolean(new URLSearchParams(hash.replace(/^#/, '')).get('handoff')?.trim())
}
