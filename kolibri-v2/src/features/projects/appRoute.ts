export function appRouteTarget(search: string): string {
  const params = new URLSearchParams(search)
  const projectId = params.get('project')?.trim() ?? ''
  const query = params.toString()
  const path = projectId ? `/chat/${encodeURIComponent(projectId)}` : '/chat'
  return query ? `${path}?${query}` : path
}
