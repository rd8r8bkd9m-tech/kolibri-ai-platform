import { useCallback, useRef } from "react";

export function useProjectRequestLifecycle(dispatch) {
  const requests = useRef(new Map());

  const beginProjectRequest = useCallback((projectId) => {
    requests.current.get(projectId)?.controller.abort();
    const controller = new AbortController();
    const token = Symbol(projectId);
    requests.current.set(projectId, { controller, token });
    dispatch({ type: "SET_PROJECT_BUSY", projectId, busy: true });
    return { signal: controller.signal, token };
  }, [dispatch]);

  const endProjectRequest = useCallback((projectId, token) => {
    if (requests.current.get(projectId)?.token !== token) return;
    requests.current.delete(projectId);
    dispatch({ type: "SET_PROJECT_BUSY", projectId, busy: false });
  }, [dispatch]);

  return { beginProjectRequest, endProjectRequest };
}
