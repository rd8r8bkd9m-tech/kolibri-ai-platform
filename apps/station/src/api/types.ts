export type NodeRow = {
  id: string;
  hostname: string;
  status: "online" | "offline";
  region: string;
  last_seen_at: string | null;
};

export type AgentRow = {
  id: string;
  name: string;
  node_id: string;
  status: "idle" | "busy" | "offline";
  current_task_id: string | null;
};

export type TaskRow = {
  id: string;
  title: string;
  status: string;
  project_id: string | null;
  priority: string;
  created_at: string;
};

export type EventRow = {
  id: string;
  subject: string;
  event_type: string;
  payload_json: Record<string, unknown>;
  created_at: string;
};
