import { useMemo, useState } from "react";
import "./styles/global.css";
import { DashboardPage, DashboardSummary } from "./pages/Dashboard";
import { NodesPage } from "./pages/Nodes";
import { AgentsPage } from "./pages/Agents";
import { TasksPage } from "./pages/Tasks";
import { EventsPage } from "./pages/Events";
import { TerminalPage } from "./pages/Terminal";

function App() {
  const [screen, setScreen] = useState("dashboard");

  const nav = useMemo(
    () => [
      "dashboard",
      "nodes",
      "agents",
      "tasks",
      "events",
      "terminal",
    ],
    [],
  );

  const summary: DashboardSummary = {
    totalNodes: 0,
    onlineNodes: 0,
    totalAgents: 0,
    runningTasks: 0,
    failedTasks: 0,
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Kolibri Control Station</h1>
        <p>Ключевые статусы инфраструктуры и очереди задач</p>
      </header>

      <nav className="app-nav">
        {nav.map((item) => (
          <button
            key={item}
            className={screen === item ? "active" : ""}
            onClick={() => setScreen(item)}
          >
            {item}
          </button>
        ))}
      </nav>

      <main>
        {screen === "dashboard" && <DashboardPage summary={summary} />}
        {screen === "nodes" && <NodesPage />}
        {screen === "agents" && <AgentsPage />}
        {screen === "tasks" && <TasksPage />}
        {screen === "events" && <EventsPage />}
        {screen === "terminal" && <TerminalPage />}
      </main>
    </div>
  );
}

export default App;
