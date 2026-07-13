export interface ConversationRouteSnapshot {
  initialized: boolean
  projectId: string | null
}

export type ConversationRouteAction = 'preserve' | 'reset' | 'load'

export function conversationRouteAction(
  previous: ConversationRouteSnapshot,
  nextProjectId: string | null,
  skipProjectId: string | null,
): ConversationRouteAction {
  if (skipProjectId && skipProjectId === nextProjectId) return 'preserve'
  if (!previous.initialized) return nextProjectId ? 'load' : 'preserve'
  if (previous.projectId === nextProjectId) return 'preserve'
  return nextProjectId ? 'load' : 'reset'
}
