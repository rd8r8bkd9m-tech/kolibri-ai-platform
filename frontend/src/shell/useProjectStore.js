import { useCallback, useEffect, useState } from "react";
import { ACTIVE_PROJECT_STORAGE_KEY, PROJECTS_STORAGE_KEY } from "../app/constants";
import { createProject, readProjects } from "../app/utils";

export function useProjectStore() {
  const [projects, setProjects] = useState(readProjects);
  const [activeProjectId, setActiveProjectId] = useState(() => {
    const saved = globalThis.localStorage.getItem(ACTIVE_PROJECT_STORAGE_KEY) || "";
    return projects.some((project) => project.id === saved) ? saved : projects[0]?.id || "";
  });
  const [busyProjects, setBusyProjects] = useState({});

  const updateProject = useCallback((projectId, updater) => {
    setProjects((current) => current.map((project) => {
      if (project.id !== projectId) return project;
      const next = typeof updater === "function" ? updater(project) : { ...project, ...updater };
      return { ...next, updatedAt: new Date().toISOString() };
    }));
  }, []);

  const addProject = useCallback(() => {
    const project = createProject();
    setProjects((current) => [project, ...current]);
    return project;
  }, []);

  const setProjectBusy = useCallback((projectId, busy) => {
    setBusyProjects((current) => ({ ...current, [projectId]: busy }));
  }, []);

  useEffect(() => {
    globalThis.localStorage.setItem(PROJECTS_STORAGE_KEY, JSON.stringify(projects));
  }, [projects]);

  useEffect(() => {
    if (activeProjectId) globalThis.localStorage.setItem(ACTIVE_PROJECT_STORAGE_KEY, activeProjectId);
  }, [activeProjectId]);

  return {
    activeProjectId,
    addProject,
    busyProjects,
    projects,
    setActiveProjectId,
    setProjectBusy,
    updateProject,
  };
}
