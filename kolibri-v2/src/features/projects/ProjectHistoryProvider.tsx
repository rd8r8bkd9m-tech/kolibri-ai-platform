import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { projects as projectsApi, type Project } from '@/lib/api'
import { removeProject, sortProjects, upsertProject } from './historyState'
import { ProjectHistoryContext, type ProjectHistoryContextValue } from './projectHistoryContext'

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'История временно недоступна'
}

export function ProjectHistoryProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const response = await projectsApi.list({ page_size: 100 })
      setItems(sortProjects(response.items.filter(item => item.deleted_at === null)))
      setError(null)
    } catch (cause) {
      setError(message(cause))
      throw cause
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let active = true
    projectsApi.list({ page_size: 100 })
      .then(response => {
        if (!active) return
        setItems(sortProjects(response.items.filter(item => item.deleted_at === null)))
        setError(null)
      })
      .catch(cause => {
        if (active) setError(message(cause))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [])

  const remember = useCallback((project: Project) => {
    setItems(current => upsertProject(current, project))
  }, [])

  const createProject = useCallback(async (
    data: { title?: string; metadata?: Record<string, unknown>; client_request_id?: string } = {},
    idempotencyKey?: string,
  ) => {
    const project = await projectsApi.create(data, idempotencyKey)
    remember(project)
    setError(null)
    return project
  }, [remember])

  const deleteProject = useCallback(async (projectId: string) => {
    const deleted = await projectsApi.delete(projectId)
    setItems(current => removeProject(current, projectId))
    setError(null)
    return deleted
  }, [])

  const restoreProject = useCallback(async (projectId: string) => {
    const restored = await projectsApi.restore(projectId)
    remember(restored)
    setError(null)
    return restored
  }, [remember])

  const value = useMemo<ProjectHistoryContextValue>(() => ({
    projects: items,
    loading,
    error,
    refresh,
    remember,
    createProject,
    deleteProject,
    restoreProject,
  }), [createProject, deleteProject, error, items, loading, refresh, remember, restoreProject])

  return <ProjectHistoryContext.Provider value={value}>{children}</ProjectHistoryContext.Provider>
}
