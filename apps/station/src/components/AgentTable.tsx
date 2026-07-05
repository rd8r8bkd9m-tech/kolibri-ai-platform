import type { AgentRow } from "../api/types";

export function AgentTable({ agents }: { agents: AgentRow[] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Agent</th>
          <th>Node</th>
          <th>Status</th>
          <th>Task</th>
        </tr>
      </thead>
      <tbody>
        {agents.map((agent) => (
          <tr key={agent.id}>
            <td>{agent.name}</td>
            <td>{agent.node_id}</td>
            <td>{agent.status}</td>
            <td>{agent.current_task_id ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
