import { createContext, useContext } from 'react'
import type { Project } from '@/lib/api'

export interface ProjectHistoryContextValue {
  projects: Project[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  remember: (project: Project) => void
  createProject: (data?: { title?: string; metadata?: Record<string, unknown>; client_request_id?: string }, idempotencyKey?: string) => Promise<Project>
  deleteProject: (projectId: string) => Promise<Project>
  restoreProject: (projectId: string) => Promise<Project>
}

export const ProjectHistoryContext = createContext<ProjectHistoryContextValue | null>(null)

export function useProjectHistory() {
  const value = useContext(ProjectHistoryContext)
  if (!value) throw new Error('useProjectHistory must be used inside ProjectHistoryProvider')
  return value
}
