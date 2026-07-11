import { useEffect, useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { loadControlSnapshot } from "../runtime/kolibriApi";
import { SystemBar } from "../shell/SystemBar";

export function ControlShell() {
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    loadControlSnapshot()
      .then((value) => active && setSnapshot(value))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const status = snapshot?.status?.value || {};
  const tasks = snapshot?.tasks?.value || [];
  const nodes = snapshot?.nodes?.value || [];
  const metrics = [
    ["Узлы online", status.online_nodes ?? nodes.length, status.total_nodes ? `из ${status.total_nodes}` : "фактический API"],
    ["В очереди", status.queue_size ?? tasks.filter((item) => ["queued", "ready"].includes(item.state)).length, "задач"],
    ["В работе", tasks.filter((item) => ["leased", "running", "review"].includes(item.state)).length, "активно"],
    ["Control Plane", status.control_plane?.status === "completed" ? "Home" : "Degraded", status.control_plane?.status || "нет доказательства"],
  ];

  return (
    <main className="control-shell">
      <SystemBar navigationLabel="Управление фабрикой" subtitle="Home Control Plane" title="Owner Control">
        <a href="/">Открыть Kolibri</a>
        <button aria-label="Дополнительно" type="button"><MoreHorizontal size={19} /></button>
      </SystemBar>
      <section className="control-content">
        <header>
          <span>Фактическое состояние</span>
          <h1>Фабрика Kolibri</h1>
          <p>{loading ? "Получаю данные Home…" : "Задачи, узлы и исполнительный контур без mock-значений."}</p>
        </header>
        <div className="control-metrics">
          {metrics.map(([label, value, hint]) => (
            <article key={label}><span>{label}</span><strong>{value}</strong><small>{hint}</small></article>
          ))}
        </div>
        <section className="control-board">
          <header>
            <div><span>Execution</span><h2>Последние задачи</h2></div>
            <span className={`live-state ${snapshot?.status?.available ? "is-online" : ""}`}>
              <i />{snapshot?.status?.available ? "Live" : "Degraded"}
            </span>
          </header>
          <div className="task-table">
            {tasks.slice(0, 14).map((item) => (
              <div key={item.task_id || item.id}>
                <span>{item.title || item.kind || "Задача"}</span>
                <small>{item.state || item.status}</small>
              </div>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}
