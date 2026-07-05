import type { NodeRow, AgentRow, TaskRow, EventRow } from "./types";

const API = "http://127.0.0.1:8081";

async function getJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) {
    throw new Error(`request failed: ${response.status}`);
  }
  return response.json();
}

export const localdApi = {
  status: () => getJSON<{ status: string }>(`/v1/status`),
  nodes: () => getJSON<NodeRow[]>(`/v1/nodes`),
  agents: () => getJSON<AgentRow[]>(`/v1/agents`),
  tasks: () => getJSON<TaskRow[]>(`/v1/tasks`),
  events: () => getJSON<EventRow[]>(`/v1/events/recent`),
  submitTask: (body: { title: string; description: string }) =>
    getJSON<Record<string, string>>(`/v1/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};
