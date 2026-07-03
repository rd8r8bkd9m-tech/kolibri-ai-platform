import { useState, useEffect, useRef, useCallback, Component } from "react"
import { motion, AnimatePresence } from "framer-motion"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import "./App.css"
import { KolibriBird } from "./components/KolibriBird"

const IS_LOCAL = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
const API_BASE = IS_LOCAL ? `http://${window.location.hostname}:8000` : ""
const WS_HOST = IS_LOCAL ? `${window.location.hostname}:8000` : window.location.host

class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary">
          <KolibriBird size={64} state="error" />
          <h2>Что-то пошло не так</h2>
          <p>{this.state.error.message}</p>
          <button className="upload-btn" onClick={() => { this.setState({ error: null }); window.location.reload() }}>
            Перезагрузить
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function parseThinking(text) {
  const match = text.match(/<thinking>([\s\S]*?)<\/thinking>/)
  if (match) return { thinking: match[1].trim(), content: text.replace(/<thinking>[\s\S]*?<\/thinking>/, "").trim() }
  return { thinking: null, content: text }
}

function ThinkingBlock({ text, isStreaming }) {
  const [expanded, setExpanded] = useState(isStreaming)
  useEffect(() => { if (isStreaming) setExpanded(true) }, [isStreaming])
  useEffect(() => {
    if (!isStreaming && text) { const t = setTimeout(() => setExpanded(false), 2000); return () => clearTimeout(t) }
  }, [isStreaming, text])
  if (!text) return null
  return (
    <motion.div className="thinking-block" onClick={() => setExpanded(!expanded)}
      initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} transition={{ duration: 0.3 }}>
      <div className="thinking-header">
        {isStreaming && <div className="spinner"></div>}
        <span>{isStreaming ? "Думаю..." : "Рассуждения"}</span>
        <span style={{ marginLeft: "auto", fontSize: "10px" }}>{expanded ? "▲" : "▼"}</span>
      </div>
      {expanded && <div className="thinking-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div>}
    </motion.div>
  )
}

function Skeleton({ className }) {
  return <div className={`skeleton ${className || ""}`} />
}

function iconPath(name) {
  const paths = {
    activity: "M22 12h-4l-3 8L9 4l-3 8H2",
    server: "M4 4h16v6H4zM4 14h16v6H4zM7 7h.01M7 17h.01",
    queue: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
    shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
    alert: "M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01",
    search: "M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z",
    refresh: "M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15",
    chevron: "M9 18l6-6-6-6",
  }
  return paths[name]
}

function Icon({ name, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d={iconPath(name)} />
    </svg>
  )
}

function flattenTopology(node, depth = 0, rows = []) {
  if (!node) return rows
  rows.push({ ...node, depth })
  ;(node.children || []).forEach(child => flattenTopology(child, depth + 1, rows))
  return rows
}

function findTopologyNode(node, id) {
  if (!node) return null
  if (node.id === id) return node
  for (const child of node.children || []) {
    const found = findTopologyNode(child, id)
    if (found) return found
  }
  return null
}

function readNocParams() {
  const params = new URLSearchParams(window.location.search)
  return {
    aggregate: params.get("aggregate") || "global:kolibri-ai",
    view: params.get("noc") || "fleet",
    target: params.get("target") || "",
    filter: params.get("filter") || "",
    q: params.get("q") || "",
    page: Math.max(0, Number.parseInt(params.get("page") || "0", 10) || 0),
  }
}

function taskLabel(task) {
  return task?.task_id || task?.id || task?.kind || "task"
}

function ClusterView({ status, onRefresh }) {
  const initialNocParams = readNocParams()
  const [selectedId, setSelectedId] = useState(initialNocParams.aggregate)
  const [query, setQuery] = useState(initialNocParams.q)
  const [page, setPage] = useState(initialNocParams.page)
  const [drilldown, setDrilldown] = useState({
    view: initialNocParams.view,
    target: initialNocParams.target,
    filter: initialNocParams.filter,
    label: initialNocParams.target || initialNocParams.filter || "Fleet overview",
  })

  useEffect(() => {
    const onPopState = () => {
      const params = readNocParams()
      setSelectedId(params.aggregate)
      setQuery(params.q)
      setPage(params.page)
      setDrilldown({
        view: params.view,
        target: params.target,
        filter: params.filter,
        label: params.target || params.filter || "Fleet overview",
      })
    }
    window.addEventListener("popstate", onPopState)
    return () => window.removeEventListener("popstate", onPopState)
  }, [])

  if (!status) return (
    <div className="noc-shell">
      <div className="skeleton-grid">
        {[1,2,3,4].map(i => <Skeleton key={i} className="skeleton-card" />)}
      </div>
    </div>
  )

  const freshness = status.node_freshness || {}
  const attention = status.owner_attention || {}
  const queue = status.queue_pressure || {}
  const telegram = status.telegram_ha || {}
  const topology = status.topology || null
  const selected = findTopologyNode(topology, selectedId) || topology
  const allRows = flattenTopology(topology).filter(row => row.level !== "task")
  const children = selected?.children || []
  const aggregateRows = children.filter(row => row.level !== "task")
  const nodeList = Array.isArray(status.node_list) ? status.node_list : Object.values(status.nodes || {})
  const normalizedQuery = query.trim().toLowerCase()
  const nodeMatchesFilter = (node, filter) => {
    if (!filter) return false
    if (filter === "fresh") return node.freshness === "fresh"
    if (filter === "degraded") return node.freshness === "degraded"
    if (filter === "stale") return node.freshness === "stale"
    if (filter === "offline") return node.status === "offline" || node.reported_health === "offline" || node.freshness === "offline"
    if (filter === "problems") return ["degraded", "stale", "offline"].includes(node.freshness) || node.status === "offline" || node.reported_health === "offline"
    if (filter === "agents") return Boolean(node.agent_id)
    if (filter === "control-plane") return node.role === "Директор" || String(node.node_id || "").includes("primary") || String(node.name || "").toLowerCase().includes("control")
    return false
  }
  const nodeFilterActive = ["fresh", "degraded", "stale", "offline", "problems", "agents", "control-plane"].includes(drilldown.filter)
  const searchedNodes = normalizedQuery
    ? nodeList.filter(node => [
      node.node_id,
      node.name,
      node.hostname,
      node.agent_id,
      node.role,
      node.status,
      node.freshness,
      node.topology?.region,
      node.topology?.provider,
      node.topology?.cluster,
      node.topology?.cell,
    ].some(value => String(value || "").toLowerCase().includes(normalizedQuery)))
    : nodeFilterActive
      ? nodeList.filter(node => nodeMatchesFilter(node, drilldown.filter))
    : []
  const pageSize = 25
  const pageCount = Math.max(1, Math.ceil(searchedNodes.length / pageSize))
  const pageNodes = searchedNodes.slice(page * pageSize, page * pageSize + pageSize)
  const agentCount = nodeList.filter(node => Boolean(node.agent_id)).length
  const activeTasks = status.active_tasks || []
  const activeRepairs = status.active_repairs || []
  const authBlocks = status.runner_auth_blocks || []
  const tasks = [...activeTasks, ...activeRepairs, ...authBlocks]
    .filter((task, index, list) => list.findIndex(item => taskLabel(item) === taskLabel(task)) === index)
    .slice(0, 12)
  const problemNodes = nodeList
    .filter(node => nodeMatchesFilter(node, "problems"))
    .slice(0, 8)
  const incidentRows = [
    { id: "degraded", label: "Degraded servers", value: attention.degraded_nodes || freshness.degraded || 0, view: "alerts", filter: "degraded" },
    { id: "stale", label: "Stale servers", value: attention.stale_nodes || freshness.stale || 0, view: "alerts", filter: "stale" },
    { id: "offline", label: "Offline servers", value: attention.offline_nodes || freshness.offline || 0, view: "alerts", filter: "offline" },
    { id: "repairs", label: "Active repairs", value: status.active_repair_count || 0, view: "repairs", filter: "repairs" },
    { id: "auth", label: "Runner/auth blocks", value: status.runner_auth_block_count || 0, view: "alerts", filter: "auth" },
  ].filter(row => row.value > 0)

  const writeNocUrl = ({ aggregate = selectedId, view = drilldown.view, target = drilldown.target, filter = drilldown.filter, q = query, nextPage = page }, replace = false) => {
    const params = new URLSearchParams(window.location.search)
    params.set("tab", "cluster")
    params.set("noc", view || "fleet")
    if (aggregate) params.set("aggregate", aggregate); else params.delete("aggregate")
    if (target) params.set("target", target); else params.delete("target")
    if (filter) params.set("filter", filter); else params.delete("filter")
    if (q) params.set("q", q); else params.delete("q")
    if (nextPage > 0) params.set("page", String(nextPage)); else params.delete("page")
    const nextUrl = `${window.location.pathname}?${params.toString()}${window.location.hash}`
    window.history[replace ? "replaceState" : "pushState"]({}, "", nextUrl)
  }

  const selectDrilldown = ({ view, target = "", filter = "", q = "", label, aggregate = selectedId }) => {
    setSelectedId(aggregate)
    setQuery(q)
    setPage(0)
    setDrilldown({ view, target, filter, label: label || target || filter || view })
    writeNocUrl({ aggregate, view, target, filter, q, nextPage: 0 })
  }

  const healthCards = [
    { label: "Control Plane", value: status.control_plane?.status || status.status || "unknown", tone: status.status === "online" ? "good" : "bad", icon: "activity", view: "control-plane", filter: "control-plane" },
    { label: "Fleet Total", value: status.total_nodes ?? 0, tone: "neutral", icon: "server", view: "servers", filter: "problems", detail: "drill into problem servers" },
    { label: "Свежие", value: `${freshness.fresh ?? status.fresh_nodes ?? 0}/${status.total_nodes ?? 0}`, tone: "good", icon: "activity", view: "servers", filter: "fresh" },
    { label: "Деградируют", value: freshness.degraded ?? status.degraded_nodes ?? 0, tone: "warn", icon: "alert", view: "alerts", filter: "degraded" },
    { label: "Устарели", value: freshness.stale ?? status.stale_nodes ?? 0, tone: "bad", icon: "alert", view: "alerts", filter: "stale" },
    { label: "Offline", value: freshness.offline ?? status.offline_nodes ?? 0, tone: "bad", icon: "server", view: "alerts", filter: "offline" },
    { label: "Queue Pressure", value: queue.level || "normal", detail: `${status.queue_size || 0} queued/running`, tone: queue.level === "critical" || queue.level === "high" ? "bad" : queue.level === "elevated" ? "warn" : "neutral", icon: "queue", view: "queues", target: "factory-queue" },
    { label: "Owner Attention", value: attention.count ?? 0, tone: (attention.count || 0) > 0 ? "bad" : "good", icon: "shield", view: "alerts", filter: "problems" },
  ]

  const selectAggregate = (id) => {
    setSelectedId(id)
    setPage(0)
    setDrilldown({ view: "topology", target: id, filter: "", label: id })
    writeNocUrl({ aggregate: id, view: "topology", target: id, filter: "", q: "", nextPage: 0 })
  }

  return (
    <motion.div key="cluster" className="noc-shell" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <div className="noc-header">
        <div>
          <div className="noc-eyebrow">Kolibri AI Control Center</div>
          <h1>Server NOC Home</h1>
          <p>Control Plane health, fleet pressure, active work, repair blocks, Telegram HA, and owner attention.</p>
        </div>
        <button className="refresh-btn" onClick={onRefresh} title="Refresh NOC status"><Icon name="refresh" size={16} /></button>
      </div>

      <div className="noc-kpi-grid">
        {healthCards.map((card, i) => (
          <motion.button key={card.label} type="button" className={`noc-kpi noc-control ${card.tone}`}
            aria-label={`Open ${card.label} drilldown`}
            data-noc-control={`kpi-${card.label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
            onClick={() => selectDrilldown({ view: card.view, target: card.target || "", filter: card.filter || "", label: card.label })}
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
            <div className="noc-kpi-icon"><Icon name={card.icon} size={16} /></div>
            <div className="noc-kpi-value">{card.value}</div>
            <div className="noc-kpi-label">{card.label}</div>
            {card.detail && <div className="noc-kpi-detail">{card.detail}</div>}
          </motion.button>
        ))}
      </div>

      <div className="noc-attention-strip">
        <button type="button" className="noc-control" onClick={() => selectDrilldown({ view: "tasks", target: "active", label: "Active tasks" })} aria-label="Open active tasks drilldown">Active tasks <strong>{status.active_task_count || 0}</strong></button>
        <button type="button" className="noc-control" onClick={() => selectDrilldown({ view: "agents", target: "registered", filter: "agents", label: "Agents" })} aria-label="Open agents drilldown">Agents <strong>{agentCount}</strong></button>
        <button type="button" className="noc-control" onClick={() => selectDrilldown({ view: "repairs", target: "active", label: "Active repairs" })} aria-label="Open active repairs drilldown">Active repairs <strong>{status.active_repair_count || 0}</strong></button>
        <button type="button" className="noc-control" onClick={() => selectDrilldown({ view: "alerts", target: "runner-auth", filter: "auth", label: "Runner/auth blocks" })} aria-label="Open runner and auth blocks drilldown">Runner/auth blocks <strong>{status.runner_auth_block_count || 0}</strong></button>
        <button type="button" className="noc-control" onClick={() => selectDrilldown({ view: "control-plane", target: "telegram-ha", label: "Telegram HA" })} aria-label="Open Telegram HA drilldown">Telegram HA <strong>{telegram.status || "unknown"}</strong></button>
      </div>

      <div className="noc-drilldown-banner" role="status" aria-live="polite" data-noc-drilldown>
        <strong>Drilldown</strong>
        <span>{drilldown.label}</span>
        <small>view={drilldown.view}{drilldown.filter ? ` · filter=${drilldown.filter}` : ""}{drilldown.target ? ` · target=${drilldown.target}` : ""}</small>
      </div>

      <div className="noc-workspace">
        <section className="noc-topology">
          <div className="noc-section-head">
            <div>
              <h2>Aggregate Topology</h2>
              <p>global → region → provider → cluster → cell → node → agent → task</p>
            </div>
          </div>
          <div className="noc-breadcrumb">
            {(selected?.path || ["kolibri-ai"]).map((part, index, parts) => (
              <button key={`${part}-${index}`} onClick={() => {
                const row = allRows.find(item => (item.path || []).join("/") === parts.slice(0, index + 1).join("/"))
                if (row) selectAggregate(row.id)
              }}>{part}</button>
            ))}
          </div>
          <div className="noc-aggregate-list">
            {(aggregateRows.length ? aggregateRows : [selected]).map(row => {
              const rollup = row.rollup || {}
              return (
                <button key={row.id} type="button" className={`noc-aggregate-row noc-control ${selected?.id === row.id ? "active" : ""}`} onClick={() => selectAggregate(row.id)} aria-label={`Open ${row.level} drilldown for ${row.name}`} data-noc-control="aggregate-row">
                  <span className="noc-row-chevron"><Icon name="chevron" size={14} /></span>
                  <span className="noc-row-main">
                    <strong>{row.name}</strong>
                    <small>{row.level}</small>
                  </span>
                  <span>{rollup.total || 0} nodes</span>
                  <span className="good">{rollup.fresh || 0} fresh</span>
                  <span className="warn">{rollup.degraded || 0} degraded</span>
                  <span className="bad">{(rollup.stale || 0) + (rollup.offline || 0)} stale/offline</span>
                  <span>{rollup.active_tasks || 0} active</span>
                </button>
              )
            })}
          </div>
        </section>

        <aside className="noc-side">
          <div className="noc-section-head compact"><h2>Owner Attention</h2></div>
          <div className="noc-owner-grid">
            {[
              ["Stale", attention.stale_nodes || 0, "stale", "alerts"],
              ["Degraded", attention.degraded_nodes || 0, "degraded", "alerts"],
              ["Offline", attention.offline_nodes || 0, "offline", "alerts"],
              ["Repairs", attention.active_repairs || 0, "repairs", "repairs"],
              ["Auth", attention.runner_auth_blocks || 0, "auth", "alerts"],
            ].map(([label, value, filter, view]) => (
              <button key={label} type="button" className="noc-control" onClick={() => selectDrilldown({ view, target: label.toLowerCase(), filter, label })} aria-label={`Open ${label} attention drilldown`}>
                <strong>{value}</strong><span>{label}</span>
              </button>
            ))}
          </div>
          <button type="button" className="noc-telegram noc-control" onClick={() => selectDrilldown({ view: "control-plane", target: "telegram-ha", label: "Telegram HA" })} aria-label="Open Telegram HA control plane drilldown">
            <strong>Telegram HA</strong>
            <span>primary: {telegram.primary || "unknown"}</span>
            <span>standby: {telegram.standby || "unknown"}</span>
            <span>promotion: {telegram.promotion || "unknown"}</span>
          </button>
          <div className="noc-section-head compact"><h2>Problem Servers</h2></div>
          <div className="noc-problem-list">
            {problemNodes.length ? problemNodes.map(node => (
              <button key={node.node_id} type="button" className="noc-problem-row noc-control" data-noc-control="problem-server-row" onClick={() => selectDrilldown({ view: "servers", target: node.node_id, filter: "problems", q: node.node_id, label: node.node_id })} aria-label={`Open problem server ${node.node_id}`}>
                <strong>{node.node_id}</strong>
                <span>{node.freshness || node.status || "unknown"} · {node.topology?.provider || "provider"} / {node.topology?.cluster || "cluster"}</span>
              </button>
            )) : <div className="noc-empty-state small">No degraded, stale, or offline servers reported.</div>}
          </div>
          <div className="noc-section-head compact"><h2>Incident Queue</h2></div>
          <div className="noc-problem-list">
            {incidentRows.length ? incidentRows.map(row => (
              <button key={row.id} type="button" className="noc-problem-row noc-control" data-noc-control="incident-row" onClick={() => selectDrilldown({ view: row.view, target: row.id, filter: row.filter, label: row.label })} aria-label={`Open incident ${row.label}`}>
                <strong>{row.label}</strong>
                <span>{row.value} affected</span>
              </button>
            )) : <div className="noc-empty-state small">No incident rows reported.</div>}
          </div>
        </aside>
      </div>

      <div className="noc-workspace bottom">
        <section className="noc-table-panel">
          <div className="noc-section-head">
            <div>
              <h2>Drilldown Search</h2>
              <p>Search paginates nodes for 100k+ server fleets instead of rendering a flat root table.</p>
            </div>
            <div className="noc-search">
              <Icon name="search" size={16} />
              <input value={query} onChange={e => {
                setQuery(e.target.value)
                setPage(0)
                setDrilldown({ view: "servers", target: e.target.value, filter: "", label: e.target.value || "Node search" })
                writeNocUrl({ view: "servers", target: e.target.value, filter: "", q: e.target.value, nextPage: 0 }, true)
              }} placeholder="node, agent, provider, health..." aria-label="Search node and agent drilldowns" />
            </div>
          </div>
          {(normalizedQuery || nodeFilterActive) ? (
            <>
              <div className="noc-node-table">
                {pageNodes.map(node => (
                  <button key={node.node_id} type="button" className="noc-node-row noc-control" data-noc-control="node-row" onClick={() => selectDrilldown({ view: "servers", target: node.node_id, filter: drilldown.filter, q: node.node_id, label: node.node_id })} aria-label={`Open server ${node.node_id}`}>
                    <strong>{node.node_id}</strong>
                    <span>{node.role || "agent"}</span>
                    <span>{node.topology?.provider || "provider"} / {node.topology?.cluster || "cluster"} / {node.topology?.cell || "cell"}</span>
                    <span className={node.freshness === "fresh" ? "good" : node.freshness === "degraded" ? "warn" : "bad"}>{node.freshness || node.status}</span>
                    <span>CPU {node.cpu == null ? "n/a" : node.cpu}</span>
                    <span>{node.ram || "RAM n/a"}</span>
                  </button>
                ))}
              </div>
              <div className="noc-pagination">
                <button disabled={page === 0} onClick={() => { const nextPage = Math.max(0, page - 1); setPage(nextPage); writeNocUrl({ nextPage }, true) }}>Previous</button>
                <span>Page {page + 1} / {pageCount} · {searchedNodes.length} matches</span>
                <button disabled={page + 1 >= pageCount} onClick={() => { const nextPage = Math.min(pageCount - 1, page + 1); setPage(nextPage); writeNocUrl({ nextPage }, true) }}>Next</button>
              </div>
            </>
          ) : (
            <div className="noc-empty-state">Select an aggregate above or search before loading node-level rows.</div>
          )}
        </section>

        <aside className="noc-side">
          <div className="noc-section-head compact"><h2>Active Work</h2></div>
          <div className="noc-task-list">
            {tasks.length ? tasks.map(task => (
              <button key={taskLabel(task)} type="button" className="noc-task-row noc-control" data-noc-control="task-row" onClick={() => selectDrilldown({ view: String(task.kind || "").includes("repair") ? "repairs" : "tasks", target: taskLabel(task), label: taskLabel(task) })} aria-label={`Open task ${taskLabel(task)}`}>
                <strong>{taskLabel(task)}</strong>
                <span>{task.state} · {task.kind}</span>
                {task.blocked_reason && <small>{task.blocked_reason}</small>}
              </button>
            )) : <div className="noc-empty-state small">No active tasks or repair/auth blocks reported.</div>}
          </div>
        </aside>
      </div>
    </motion.div>
  )
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [ws, setWs] = useState(null)
  const [connected, setConnected] = useState(false)
  const [providers, setProviders] = useState([])
  const [selectedProvider, setSelectedProvider] = useState("mimo")
  const [sidebar, setSidebar] = useState(false)
  const [theme, setTheme] = useState(() => localStorage.getItem("kolibri-theme") || "dark")
  const [activeTab, setActiveTab] = useState("cluster")
  const [documents, setDocuments] = useState([])
  const [docLoading, setDocLoading] = useState(false)
  const [docError, setDocError] = useState("")
  const [uploading, setUploading] = useState(false)
  const [clusterStatus, setClusterStatus] = useState(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState([])
  const [searchLoading, setSearchLoading] = useState(false)
  const messagesEnd = useRef(null)
  const inputRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove("theme-dark", "theme-light")
    root.classList.add(theme === "dark" ? "theme-dark" : "theme-light")
    localStorage.setItem("kolibri-theme", theme)
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#0a0a0f" : "#f0f4f8")
  }, [theme])

  useEffect(() => {
    fetch(`${API_BASE}/api/providers`).then(r => r.json()).then(setProviders).catch(() => {})
    connectWS()
    fetchCluster()
    const ci = setInterval(fetchCluster, 15000)
    return () => { if (ws) ws.close(); clearInterval(ci) }
  }, [])

  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: "smooth" }) }, [messages])

  const fetchCluster = async () => {
    try {
      const r = await fetch(`${API_BASE}/api/factory/status`)
      setClusterStatus(await r.json())
    } catch {}
  }

  const fetchDocuments = async () => {
    setDocLoading(true); setDocError("")
    try {
      const r = await fetch(`${API_BASE}/api/knowledge`)
      const d = await r.json()
      setDocuments(d.documents || d.items || [])
    } catch { setDocError("Не удалось загрузить документы") }
    setDocLoading(false)
  }

  useEffect(() => { if (activeTab === "documents") fetchDocuments() }, [activeTab])

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return
    setUploading(true)
    try {
      const fd = new FormData(); fd.append("file", file)
      await fetch(`${API_BASE}/api/knowledge/upload`, { method: "POST", body: fd })
      await fetchDocuments()
    } catch { setDocError("Ошибка загрузки") }
    setUploading(false)
  }

  const connectWS = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    let socket
    try { socket = new WebSocket(`${proto}//${WS_HOST}/ws/chat`) } catch { return }
    socket.onopen = () => setConnected(true)
    socket.onclose = () => { setConnected(false); setTimeout(connectWS, 3000) }
    socket.onmessage = (e) => {
      const data = JSON.parse(e.data)
      setMessages(prev => {
        const n = [...prev]
        const last = n[n.length - 1]
        if (last && last.role === "assistant" && last.streaming) {
          last.content = data.response || data.content || ""
          last.provider = data.provider
          last.streaming = false
        }
        return [...n]
      })
      setLoading(false)
    }
    setWs(socket)
  }, [])

  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const userMsg = { role: "user", content: input, timestamp: Date.now() }
    const newMsgs = [...messages, userMsg]
    setMessages(newMsgs); setInput(""); setLoading(true)
    setMessages([...newMsgs, { role: "assistant", content: "", streaming: true, provider: "", timestamp: Date.now() }])
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ messages: newMsgs.map(m => ({ role: m.role, content: m.content })), provider: selectedProvider }))
    } else {
      try {
        const r = await fetch(`${API_BASE}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: newMsgs, provider: selectedProvider }) })
        const d = await r.json()
        setMessages([...newMsgs, { role: "assistant", content: d.response, provider: d.provider, timestamp: Date.now() }])
      } catch { setMessages([...newMsgs, { role: "assistant", content: "Ошибка подключения к серверу.", timestamp: Date.now() }]) }
      setLoading(false)
    }
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setSearchLoading(true)
    try {
      const r = await fetch(`${API_BASE}/rag/search`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: searchQuery, limit: 5 }) })
      const d = await r.json()
      setSearchResults(d.results || [])
    } catch { setSearchResults([]) }
    setSearchLoading(false)
  }

  const handleKeyDown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage() } }

  const quickActions = [
    { id: "cluster", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="2" width="6" height="6" rx="1"/><rect x="16" y="2" width="6" height="6" rx="1"/><rect x="9" y="16" width="6" height="6" rx="1"/><path d="M5 8v3a2 2 0 002 2h10a2 2 0 002-2V8"/></svg>, title: "Control Center", desc: "NOC monitor", color: "blue", prompt: "" },
    { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>, title: "Чат с AI", desc: "Operator query", color: "green", prompt: "" },
    { id: "search", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>, title: "Поиск", desc: "Knowledge base", color: "orange", prompt: "" },
  ]

  const birdState = loading ? "thinking" : connected ? "idle" : "error"

  return (
    <ErrorBoundary>
      <div className="app">
        <div className={`sidebar-overlay ${sidebar ? "open" : ""}`} onClick={() => setSidebar(false)} />

        <aside className={`sidebar ${sidebar ? "open" : ""}`}>
          <div className="sidebar-header">
            <div className="sidebar-logo">
              <KolibriBird size={36} state={birdState} />
              <span className="sidebar-logo-text">Kolibri</span>
              <span className="sidebar-logo-badge">NOC</span>
            </div>
            <motion.button className="new-chat-btn" onClick={() => { setMessages([]); setActiveTab("chat") }}
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              Новый чат
            </motion.button>
          </div>

          <nav className="sidebar-nav">
            {[
              { id: "cluster", label: "Control Center", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="2" width="6" height="6" rx="1"/><rect x="16" y="2" width="6" height="6" rx="1"/><rect x="9" y="16" width="6" height="6" rx="1"/><path d="M5 8v3a2 2 0 002 2h10a2 2 0 002-2V8"/></svg> },
              { id: "chat", label: "Чат", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg> },
              { id: "documents", label: "Документы", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/></svg> },
              { id: "search", label: "Поиск", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> },
            ].map(item => (
              <motion.button key={item.id} className={`sidebar-nav-item ${activeTab === item.id ? "active" : ""}`}
                onClick={() => { setActiveTab(item.id); setSidebar(false) }}
                whileHover={{ x: 2 }} whileTap={{ scale: 0.98 }}>
                {item.icon}{item.label}
                {item.id === "cluster" && clusterStatus && (
                  <span className="nav-badge">{clusterStatus.online_nodes}</span>
                )}
              </motion.button>
            ))}
          </nav>

          <div className="sidebar-section">
            <div className="sidebar-label">Модель</div>
            <select className="sidebar-select" value={selectedProvider} onChange={e => setSelectedProvider(e.target.value)}>
              {providers.filter(p => p.available).map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
              {providers.length === 0 && <option value="mimo">mimo-auto</option>}
            </select>
          </div>

          <div className="sidebar-section">
            <div className="sidebar-label">Тема</div>
            <motion.div className="theme-switch" onClick={() => setTheme(theme === "light" ? "dark" : "light")}
              whileTap={{ scale: 0.98 }}>
              <span className="theme-switch-label">{theme === "light" ? "Светлая" : "Тёмная"}</span>
              <div className={`theme-switch-toggle ${theme === "dark" ? "active" : ""}`}></div>
            </motion.div>
          </div>

          <div className="sidebar-footer">
            <div className="connection-status">
              <motion.div className={`connection-dot ${connected ? "connected" : ""}`}
                animate={connected ? { scale: [1, 1.3, 1] } : {}}
                transition={{ duration: 2, repeat: Infinity }} />
              {connected ? "Фабрика онлайн" : "Связь с фабрикой потеряна"}
            </div>
          </div>
        </aside>

        <div className="main-content">
          <header className="header">
            <div className="header-left">
              <button className="header-btn mobile-menu" onClick={() => setSidebar(!sidebar)}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
                </svg>
              </button>
              <div>
                <div className="header-title">Kolibri AI Control Center</div>
                <div className="header-subtitle">
                  {clusterStatus ? (
                    <span className="header-cluster">
                      <span className="pulse-dot" />
                      {clusterStatus.online_nodes}/{clusterStatus.total_nodes} online · queue {clusterStatus.queue_size || 0} · attention {clusterStatus.owner_attention?.count || 0}
                    </span>
                  ) : "Загрузка..."}
                </div>
              </div>
            </div>
            <div className="header-right">
              <motion.button className="header-btn" onClick={fetchCluster} title="Обновить"
                whileHover={{ rotate: 90 }} transition={{ duration: 0.2 }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="23,4 23,10 17,10"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
                </svg>
              </motion.button>
            </div>
          </header>

          <div className="chat-container">
            <AnimatePresence mode="wait">
              {activeTab === "chat" && (
                <motion.div key="chat" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }} style={{ display: "flex", flexDirection: "column", flex: 1 }}>
                  <div className="messages">
                    {messages.length === 0 && (
                      <motion.div className="welcome" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
                        <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                          transition={{ type: "spring", stiffness: 200, delay: 0.1 }}>
                          <KolibriBird size={90} state="idle" />
                        </motion.div>
                        <motion.h1 className="welcome-title" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: 0.3 }}>Kolibri AI</motion.h1>
                        <motion.p className="welcome-subtitle" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                          transition={{ delay: 0.4 }}>
                          Control Plane · {clusterStatus ? `${clusterStatus.online_nodes}/${clusterStatus.total_nodes} online · ${clusterStatus.total_ram_gb} GB RAM` : "loading"}
                        </motion.p>
                        <div className="quick-actions">
                          {quickActions.map((a, i) => (
                            <motion.button key={a.title} className="quick-action"
                              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                              transition={{ delay: 0.5 + i * 0.08, type: "spring", stiffness: 200 }}
                              whileHover={{ scale: 1.03, y: -3 }} whileTap={{ scale: 0.97 }}
                              onClick={() => {
                                if (a.id === "search" || a.id === "cluster") { setActiveTab(a.id); return }
                                setInput(a.prompt); inputRef.current?.focus()
                              }}>
                              <div className={`quick-action-icon ${a.color}`}>{a.icon}</div>
                              <div className="quick-action-text">
                                <div className="quick-action-title">{a.title}</div>
                                <div className="quick-action-desc">{a.desc}</div>
                              </div>
                            </motion.button>
                          ))}
                        </div>
                      </motion.div>
                    )}
                    {messages.map((msg, i) => {
                      const { thinking, content } = msg.role === "assistant" ? parseThinking(msg.content || "") : { thinking: null, content: msg.content }
                      return (
                        <motion.div key={i} className={`message ${msg.role}`}
                          initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                          transition={{ duration: 0.25, type: "spring", stiffness: 200 }}>
                          <div className={`message-avatar ${msg.role}`}>
                            {msg.role === "assistant" ? <KolibriBird size={20} state={msg.streaming ? "thinking" : "happy"} /> : "U"}
                          </div>
                          <div className="message-bubble">
                            {msg.role === "assistant" && <ThinkingBlock text={thinking} isStreaming={msg.streaming} />}
                            {msg.role === "assistant" ? (
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || (msg.streaming ? "..." : "")}</ReactMarkdown>
                            ) : <p>{msg.content}</p>}
                            {msg.provider && msg.role === "assistant" && (
                              <motion.div className="provider-badge" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}>
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> {msg.provider}
                              </motion.div>
                            )}
                          </div>
                        </motion.div>
                      )
                    })}
                    {loading && messages[messages.length-1]?.streaming && (
                      <motion.div className="message assistant" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <div className="message-avatar assistant"><KolibriBird size={20} state="thinking" /></div>
                        <div className="message-bubble typing-indicator">
                          <span></span><span></span><span></span>
                        </div>
                      </motion.div>
                    )}
                    <div ref={messagesEnd} />
                  </div>

                  <div className="input-area">
                    <div className="input-wrapper">
                      <textarea ref={inputRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown}
                        placeholder="Спросите что угодно..." rows={1} disabled={loading}
                        onInput={e => { e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px" }} />
                      <motion.button onClick={sendMessage} disabled={loading || !input.trim()} className="send-btn"
                        whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }}>
                        {loading ? (
                          <motion.svg className="spinner-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                            animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: "linear" }}>
                            <path d="M21 12a9 9 0 11-6.219-8.56"/>
                          </motion.svg>
                        ) : (
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                        )}
                      </motion.button>
                    </div>
                  </div>
                </motion.div>
              )}

              {activeTab === "documents" && (
                <motion.div key="docs" className="documents-panel" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                  <div className="documents-header">
                    <h2>Документы</h2>
                    <input ref={fileInputRef} type="file" onChange={handleFileUpload} style={{display:"none"}} accept=".pdf,.txt,.md,.doc,.docx,.csv,.json" />
                    <motion.button className="upload-btn" onClick={() => fileInputRef.current?.click()} disabled={uploading}
                      whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
                      {uploading ? "Загрузка..." : "+ Загрузить"}
                    </motion.button>
                  </div>
                  {docError && <div className="doc-error">{docError}</div>}
                  {docLoading ? (
                    <div className="skeleton-list">{[1,2,3].map(i => <Skeleton key={i} className="skeleton-item" />)}</div>
                  ) : documents.length === 0 ? (
                    <div className="doc-empty">
                      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{opacity:0.3,marginBottom:16}}>
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/>
                      </svg>
                      <p>Нет документов</p>
                      <p className="doc-empty-hint">Загрузите файлы для анализа</p>
                    </div>
                  ) : (
                    <div className="doc-list">
                      {documents.map((doc, i) => (
                        <motion.div key={i} className="doc-item" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.05 }} whileHover={{ x: 4 }}>
                          <div className="doc-icon">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/>
                            </svg>
                          </div>
                          <div className="doc-info">
                            <div className="doc-name">{doc.filename || doc.name || `Документ ${i+1}`}</div>
                            <div className="doc-meta">{doc.size || ""}</div>
                          </div>
                          {doc.status === "processed" && <span className="doc-badge ready">Готов</span>}
                        </motion.div>
                      ))}
                    </div>
                  )}
                </motion.div>
              )}

              {activeTab === "cluster" && <ClusterView status={clusterStatus} onRefresh={fetchCluster} />}

              {activeTab === "search" && (
                <motion.div key="search" className="documents-panel" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                  <div className="documents-header"><h2>Поиск</h2></div>
                  <div style={{ marginBottom: "20px" }}>
                    <div className="input-wrapper" style={{ maxWidth: "600px" }}>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" style={{ flexShrink: 0 }}>
                        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                      </svg>
                      <input type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                        onKeyDown={e => e.key === "Enter" && handleSearch()}
                        placeholder="Поиск по базе знаний..."
                        style={{ flex:1, border:"none", background:"transparent", color:"var(--text-primary)", fontSize:"14px", fontFamily:"var(--font-ui)", outline:"none", padding:"8px 0" }} />
                      <motion.button className="send-btn" style={{ width:"36px", height:"36px" }} onClick={handleSearch}
                        whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }}>
                        {searchLoading ? (
                          <motion.svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                            animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: "linear" }}>
                            <path d="M21 12a9 9 0 11-6.219-8.56"/>
                          </motion.svg>
                        ) : (
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                        )}
                      </motion.button>
                    </div>
                  </div>
                  {searchLoading ? (
                    <div className="skeleton-list">{[1,2,3].map(i => <Skeleton key={i} className="skeleton-item" />)}</div>
                  ) : searchResults.length > 0 ? (
                    <div className="doc-list">
                      {searchResults.map((r, i) => (
                        <motion.div key={i} className="doc-item" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                          transition={{ delay: i * 0.05 }} whileHover={{ x: 4 }}>
                          <div className="doc-icon" style={{ background:"var(--accent-soft)", color:"var(--accent)" }}>
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                            </svg>
                          </div>
                          <div className="doc-info">
                            <div className="doc-name">{r.title || r.filename || `Результат ${i+1}`}</div>
                            <div className="doc-meta">{r.content?.substring(0, 120)}...</div>
                          </div>
                          {r.score && <span className="doc-badge ready">{Math.round(r.score * 100)}%</span>}
                        </motion.div>
                      ))}
                    </div>
                  ) : (
                    <div className="doc-empty">
                      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{opacity:0.3,marginBottom:16}}>
                        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                      </svg>
                      <p>Семантический поиск</p>
                      <p className="doc-empty-hint">Введите запрос для поиска по базе знаний</p>
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </ErrorBoundary>
  )
}
