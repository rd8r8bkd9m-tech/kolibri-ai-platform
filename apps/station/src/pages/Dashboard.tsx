import { StatusCard } from "../components/StatusCard";

export type DashboardSummary = {
  totalNodes: number;
  onlineNodes: number;
  totalAgents: number;
  runningTasks: number;
  failedTasks: number;
};

export function DashboardPage({ summary }: { summary: DashboardSummary }) {
  return (
    <section>
      <h2>Dashboard</h2>
      <div className="card-grid">
        <StatusCard label="Всего узлов" value={summary.totalNodes} />
        <StatusCard label="Онлайн узлы" value={summary.onlineNodes} />
        <StatusCard label="Агенты" value={summary.totalAgents} />
        <StatusCard label="Запущенные задачи" value={summary.runningTasks} />
        <StatusCard label="Провальные задачи" value={summary.failedTasks} />
      </div>
      <p className="muted">Ниже в будущем появятся live метрики и статус locald.</p>
    </section>
  );
}
