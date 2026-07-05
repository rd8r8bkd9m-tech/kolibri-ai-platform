import type { NodeRow } from "../api/types";

export function NodeTable({ nodes }: { nodes: NodeRow[] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Hostname</th>
          <th>Регион</th>
          <th>Статус</th>
          <th>Last seen</th>
        </tr>
      </thead>
      <tbody>
        {nodes.map((node) => (
          <tr key={node.id}>
            <td>{node.hostname}</td>
            <td>{node.region}</td>
            <td>{node.status}</td>
            <td>{node.last_seen_at ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
