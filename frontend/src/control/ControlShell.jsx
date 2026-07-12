import { useEffect, useState } from "react";
import { loadControlSnapshot } from "../runtime/kolibriApi";
import { SystemBar } from "../shell/SystemBar";
import { buildControlView } from "./controlViewModel";

export function ControlShell() {
  const [snapshot, setSnapshot] = useState(null);
  const [phase, setPhase] = useState("loading");

  useEffect(() => {
    let active = true;
    loadControlSnapshot()
      .then((value) => {
        if (!active) return;
        setSnapshot(value);
        setPhase("ready");
      })
      .catch(() => {
        if (active) setPhase("unavailable");
      });
    return () => {
      active = false;
    };
  }, []);

  const view = buildControlView(snapshot, phase);

  return (
    <main className="control-shell">
      <SystemBar navigationLabel="Управление фабрикой" subtitle="Home Control Plane" title="Owner Control">
        <a href="/">Открыть Kolibri</a>
      </SystemBar>
      <section className="control-content">
        <header>
          <span>Фактическое состояние</span>
          <h1>Фабрика Kolibri</h1>
          <p>{view.intro}</p>
        </header>
        <div className="control-metrics">
          {view.metrics.map((metric) => (
            <article data-state={metric.state} key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.hint}</small></article>
          ))}
        </div>
        <section className="control-board">
          <header>
            <div><span>Execution</span><h2>Последние задачи</h2></div>
            <span aria-live="polite" className={`live-state is-${view.tasksState}`}>
              <i />{view.tasksState === "loading" ? "Загрузка" : view.tasksState === "live" ? "Live" : "Недоступно"}
            </span>
          </header>
          <div className="task-table">
            {view.tasks.slice(0, 14).map((item) => (
              <div key={item.task_id || item.id}>
                <span>{item.title || item.kind || "Задача"}</span>
                <small>{item.state || item.status}</small>
              </div>
            ))}
            {!view.tasks.length && <p className={`task-table-state is-${view.tasksState}`}>{view.tasksMessage}</p>}
          </div>
        </section>
      </section>
    </main>
  );
}
