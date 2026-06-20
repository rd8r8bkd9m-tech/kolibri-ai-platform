import { useMemo, useState } from "react"
import { motion } from "framer-motion"
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  FileText,
  Lock,
  RefreshCw,
  Server,
  ShieldCheck,
  Users,
  WifiOff,
} from "lucide-react"
import { agentRoster, operatorReports, serverFleet, statusTone, taskQueue } from "../data/agentOps"

const VIEW_TITLES = {
  overview: "Операционный обзор",
  agents: "Агенты",
  tasks: "Задачи",
  servers: "Серверы",
  reports: "Отчеты",
}

const statusLabel = {
  online: "online",
  offline: "offline",
  ready: "ready",
  completed: "done",
  queued: "queued",
  gated: "gated",
  reviewing: "review",
  blocked: "blocked",
  scheduled: "scheduled",
  "event-driven": "event",
}

function normalizeClusterNodes(status) {
  if (!status?.nodes) return serverFleet
  return Object.entries(status.nodes).map(([name, node]) => ({
    name,
    role: node.role || "unknown",
    status: node.status || "unknown",
    ip: node.ip || "n/a",
    disk: node.disk || "not reported",
    ram: node.ram || "not reported",
    network: node.status === "online" ? "cluster" : "unreachable",
    cpu: node.cpu,
  }))
}

function Badge({ status, children }) {
  const tone = statusTone[status] || "muted"
  return <span className={`ops-badge ops-badge--${tone}`}>{children || statusLabel[status] || status}</span>
}

function SectionHeader({ eyebrow, title, subtitle, action }) {
  return (
    <div className="ops-section-header">
      <div>
        {eyebrow && <div className="ops-eyebrow">{eyebrow}</div>}
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

function StatTile({ icon: Icon, label, value, detail, tone = "info" }) {
  return (
    <div className="ops-stat">
      <div className={`ops-stat-icon ops-stat-icon--${tone}`}><Icon size={18} /></div>
      <div>
        <div className="ops-stat-value">{value}</div>
        <div className="ops-stat-label">{label}</div>
        {detail && <div className="ops-stat-detail">{detail}</div>}
      </div>
    </div>
  )
}

function EmptyState({ icon: Icon, title, copy }) {
  return (
    <div className="ops-empty">
      <Icon size={24} />
      <div>
        <strong>{title}</strong>
        <span>{copy}</span>
      </div>
    </div>
  )
}

function Overview({ clusterStatus, servers, setView, onRefresh, connected }) {
  const onlineCount = servers.filter(server => server.status === "online").length
  const blockedTasks = taskQueue.filter(task => ["blocked", "failed"].includes(task.status)).length
  const gatedTasks = taskQueue.filter(task => ["queued", "gated"].includes(task.status)).length
  const readyAgents = agentRoster.filter(agent => ["ready", "reviewing"].includes(agent.status)).length

  return (
    <>
      <div className="ops-hero">
        <div>
          <div className="ops-eyebrow">Kolibri Agent Fleet</div>
          <h1>Операционная консоль разработки</h1>
          <p>
            Единый экран для Codex review, MiMo Code задач, OpenClaw UI-патчей,
            server health, QA evidence и release blockers.
          </p>
        </div>
        <div className="ops-hero-actions">
          <button className="ops-icon-button" onClick={onRefresh} title="Обновить статус">
            <RefreshCw size={18} />
          </button>
          <button className="ops-primary-action" onClick={() => setView("tasks")}>
            <ClipboardList size={16} />
            Очередь задач
          </button>
        </div>
      </div>

      <div className="ops-stat-grid">
        <StatTile icon={Server} label="Серверы онлайн" value={`${onlineCount}/${servers.length}`} detail={clusterStatus ? "cluster/status live" : "inventory fallback"} tone="success" />
        <StatTile icon={Users} label="Готовые агенты" value={`${readyAgents}/${agentRoster.length}`} detail="Codex gate active" tone="info" />
        <StatTile icon={ClipboardList} label="Задачи в gate" value={gatedTasks} detail="manifest controlled" tone="warning" />
        <StatTile icon={AlertTriangle} label="Блокеры" value={blockedTasks} detail={connected ? "AI channel online" : "AI channel offline"} tone={blockedTasks ? "danger" : "success"} />
      </div>

      <div className="ops-dashboard-grid">
        <div className="ops-card ops-card--wide">
          <SectionHeader
            eyebrow="Active work"
            title="Frontend quality lane"
            subtitle="Claw работает автономно только до draft patch, Codex принимает diff."
            action={<Badge status="gated">Codex review</Badge>}
          />
          <div className="ops-timeline">
            {taskQueue.map((task, index) => (
              <button key={task.id} className="ops-timeline-item" onClick={() => setView("tasks")}>
                <span className="ops-timeline-index">{index + 1}</span>
                <div>
                  <strong>{task.title}</strong>
                  <span>{task.summary}</span>
                </div>
                <Badge status={task.status} />
              </button>
            ))}
          </div>
        </div>

        <div className="ops-card">
          <SectionHeader eyebrow="Risk board" title="Главные риски" />
          <div className="ops-risk-list">
            <div className="ops-risk-item ops-risk-item--danger">
              <WifiOff size={16} />
              <span>kolibri-inference-recovery unreachable</span>
            </div>
            <div className="ops-risk-item ops-risk-item--warning">
              <Lock size={16} />
              <span>OpenClaw требует auth + budget guard</span>
            </div>
            <div className="ops-risk-item ops-risk-item--info">
              <ShieldCheck size={16} />
              <span>Mutation tasks ограничены allowed_paths</span>
            </div>
          </div>
        </div>
      </div>

      <div className="ops-card">
        <SectionHeader
          eyebrow="Fleet"
          title="Server health snapshot"
          subtitle="Actions disabled until a manifest and Codex approval exist."
          action={<button className="ops-secondary-action" onClick={() => setView("servers")}>Открыть серверы <ChevronRight size={15} /></button>}
        />
        <div className="ops-server-strip">
          {servers.slice(0, 6).map(server => (
            <div key={server.name} className="ops-server-chip">
              <span className={`ops-dot ops-dot--${statusTone[server.status] || "muted"}`} />
              <div>
                <strong>{server.name}</strong>
                <span>{server.role}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

function Agents() {
  return (
    <div className="ops-grid-list">
      {agentRoster.map(agent => (
        <div key={agent.id} className="ops-card ops-agent-card">
          <div className="ops-card-title-row">
            <div className="ops-avatar"><Bot size={18} /></div>
            <div>
              <h3>{agent.name}</h3>
              <p>{agent.role}</p>
            </div>
            <Badge status={agent.status} />
          </div>
          <dl className="ops-definition-list">
            <div><dt>Backend</dt><dd>{agent.backend}</dd></div>
            <div><dt>Focus</dt><dd>{agent.focus}</dd></div>
            <div><dt>Worktree</dt><dd>{agent.worktree}</dd></div>
            <div><dt>Gate</dt><dd>{agent.risk}</dd></div>
          </dl>
        </div>
      ))}
    </div>
  )
}

function Tasks() {
  const [filter, setFilter] = useState("all")
  const filteredTasks = filter === "all" ? taskQueue : taskQueue.filter(task => task.status === filter)
  const filters = ["all", "queued", "gated", "ready", "blocked"]

  return (
    <>
      <div className="ops-toolbar">
        <div className="ops-segmented" role="tablist" aria-label="Фильтр задач">
          {filters.map(item => (
            <button
              key={item}
              className={filter === item ? "active" : ""}
              onClick={() => setFilter(item)}
              type="button"
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      {filteredTasks.length === 0 ? (
        <EmptyState icon={ClipboardList} title="Нет задач в этом статусе" copy="Очередь обновится после следующего agent report." />
      ) : (
        <div className="ops-task-list">
          {filteredTasks.map(task => (
            <div key={task.id} className="ops-card ops-task-card">
              <div className="ops-task-header">
                <div>
                  <div className="ops-mono">{task.id}</div>
                  <h3>{task.title}</h3>
                  <p>{task.summary}</p>
                </div>
                <Badge status={task.status} />
              </div>

              <div className="ops-result-grid">
                <div><span>status</span><strong>{task.status}</strong></div>
                <div><span>agent</span><strong>{task.agent}</strong></div>
                <div><span>mode</span><strong>{task.mode}</strong></div>
                <div><span>server</span><strong>{task.server}</strong></div>
              </div>

              <div className="ops-result-columns">
                <div>
                  <h4>changed_files</h4>
                  {task.changed_files.length ? task.changed_files.map(file => <code key={file}>{file}</code>) : <span className="ops-muted">[]</span>}
                </div>
                <div>
                  <h4>checks</h4>
                  {task.checks.length ? task.checks.map(check => <code key={check}>{check}</code>) : <span className="ops-muted">not declared</span>}
                </div>
                <div>
                  <h4>risks</h4>
                  {task.risks.length ? task.risks.map(risk => <code key={risk}>{risk}</code>) : <span className="ops-muted">none</span>}
                </div>
                <div>
                  <h4>artifacts</h4>
                  {task.artifacts.map(artifact => <code key={artifact}>{artifact}</code>)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

function Servers({ servers, onRefresh }) {
  return (
    <div className="ops-card">
      <SectionHeader
        eyebrow="Fleet health"
        title="Серверы и роли"
        subtitle="Mutation controls are locked until a task manifest exists."
        action={<button className="ops-secondary-action" onClick={onRefresh}><RefreshCw size={15} /> Refresh</button>}
      />
      <div className="ops-table-wrap">
        <table className="ops-table">
          <thead>
            <tr>
              <th>Server</th>
              <th>Role</th>
              <th>Health</th>
              <th>Disk</th>
              <th>Network</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {servers.map(server => (
              <tr key={server.name}>
                <td>
                  <strong>{server.name}</strong>
                  <span>{server.ip}</span>
                </td>
                <td>{server.role}</td>
                <td><Badge status={server.status}>{server.status}</Badge></td>
                <td>{server.disk}</td>
                <td>{server.network}</td>
                <td>
                  <button className="ops-locked-action" disabled title="Requires manifest and Codex approval">
                    <Lock size={14} />
                    Locked
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Reports() {
  return (
    <div className="ops-dashboard-grid">
      <div className="ops-card ops-card--wide">
        <SectionHeader eyebrow="Reporting" title="Регулярные отчеты Codex" subtitle="Формат отчета уже соответствует agent structured result и health gates." />
        <div className="ops-report-list">
          {operatorReports.map(report => (
            <div key={report.id} className="ops-report-item">
              <FileText size={18} />
              <div>
                <strong>{report.title}</strong>
                <span>{report.summary}</span>
              </div>
              <Badge status={report.status}>{report.status}</Badge>
            </div>
          ))}
        </div>
      </div>

      <div className="ops-card">
        <SectionHeader eyebrow="Required payload" title="Что должен видеть Codex" />
        <div className="ops-checklist">
          {["active tasks", "failed checks", "server health", "merged work", "risks", "next actions"].map(item => (
            <div key={item}><CheckCircle2 size={15} /><span>{item}</span></div>
          ))}
        </div>
      </div>
    </div>
  )
}

export function AgentOpsView({ view = "overview", clusterStatus, connected, onRefresh, setView }) {
  const servers = useMemo(() => normalizeClusterNodes(clusterStatus), [clusterStatus])

  const subtitle = clusterStatus
    ? `${clusterStatus.online_nodes}/${clusterStatus.total_nodes} nodes online · ${clusterStatus.free_ram_gb} GB free RAM`
    : "Live cluster unavailable, showing last known fleet inventory"

  const content = {
    overview: <Overview clusterStatus={clusterStatus} servers={servers} setView={setView} onRefresh={onRefresh} connected={connected} />,
    agents: <Agents />,
    tasks: <Tasks />,
    servers: <Servers servers={servers} onRefresh={onRefresh} />,
    reports: <Reports />,
  }[view] || <Overview clusterStatus={clusterStatus} servers={servers} setView={setView} onRefresh={onRefresh} connected={connected} />

  return (
    <motion.div
      key={view}
      className="ops-panel"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2 }}
    >
      <div className="ops-page-header">
        <div>
          <div className="ops-eyebrow">Agent Ops</div>
          <h1>{VIEW_TITLES[view] || VIEW_TITLES.overview}</h1>
          <p>{subtitle}</p>
        </div>
        <div className="ops-page-status">
          <Badge status={connected ? "online" : "offline"}>{connected ? "AI online" : "AI offline"}</Badge>
          <Badge status={clusterStatus ? "online" : "gated"}>{clusterStatus ? "live data" : "fallback"}</Badge>
        </div>
      </div>
      {content}
    </motion.div>
  )
}
