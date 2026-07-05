import { AgentTable } from "../components/AgentTable";
import type { AgentRow } from "../api/types";

const EMPTY: AgentRow[] = [];

export function AgentsPage() {
  return (
    <section>
      <h2>Agents</h2>
      <AgentTable agents={EMPTY} />
    </section>
  );
}
