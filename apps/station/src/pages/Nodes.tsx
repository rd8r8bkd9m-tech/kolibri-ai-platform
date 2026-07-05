import { NodeTable } from "../components/NodeTable";
import type { NodeRow } from "../api/types";

const EMPTY: NodeRow[] = [];

export function NodesPage() {
  return (
    <section>
      <h2>Nodes</h2>
      <NodeTable nodes={EMPTY} />
    </section>
  );
}
