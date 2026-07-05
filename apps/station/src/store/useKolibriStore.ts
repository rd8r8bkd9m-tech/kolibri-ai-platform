import { useCallback, useEffect, useState } from "react";
import type { NodeRow, AgentRow, TaskRow, EventRow } from "../api/types";
import { localdApi } from "../api/client";

export function useKolibriStore() {
  const [nodes, setNodes] = useState<NodeRow[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [events, setEvents] = useState<EventRow[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [nodesPayload, agentsPayload, tasksPayload, eventsPayload] = await Promise.all([
        localdApi.nodes(),
        localdApi.agents(),
        localdApi.tasks(),
        localdApi.events(),
      ]);
      setNodes(nodesPayload);
      setAgents(agentsPayload);
      setTasks(tasksPayload);
      setEvents(eventsPayload);
    } catch (error) {
      // intentionally no noisy diagnostics while disconnected
      console.warn("locald unavailable");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { nodes, agents, tasks, events, refresh };
}
