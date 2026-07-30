import type { Project, ProjectMessage } from '@/lib/api'

export function projectActivity(project: Project): number {
  return Date.parse(project.last_message_at ?? project.updated_at ?? project.created_at) || 0
}

export function sortProjects(items: Project[]): Project[] {
  return [...items].sort((a, b) => {
    const pinOrder = Number(b.metadata.pinned === true) - Number(a.metadata.pinned === true)
    return pinOrder || projectActivity(b) - projectActivity(a) || b.id.localeCompare(a.id)
  })
}

export function upsertProject(items: Project[], project: Project): Project[] {
  return sortProjects([project, ...items.filter(item => item.id !== project.id && item.deleted_at === null)])
}

export function removeProject(items: Project[], projectId: string): Project[] {
  return items.filter(item => item.id !== projectId)
}

export function serverMessageStatus(status: ProjectMessage['status']) {
  if (status === 'failed') return 'failed' as const
  if (status === 'cancelled') return 'cancelled' as const
  if (status === 'completed') return 'completed' as const
  if (status === 'streaming') return 'streaming' as const
  return 'dispatching' as const
}

export function latestResponseId(messages: ProjectMessage[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const responseId = messages[index]?.metadata.response_id
    if (typeof responseId === 'string' && responseId) return responseId
  }
  return null
}
