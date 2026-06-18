import { motion } from "framer-motion"
import { Skeleton } from "./Skeleton"

export function ClusterView({ status, onRefresh }) {
  if (!status) return (
    <div className="documents-panel">
      <div className="skeleton-grid">
        {[1,2,3].map(i => <Skeleton key={i} className="skeleton-card" />)}
      </div>
    </div>
  )

  const NodeIcon = ({ role }) => {
    const paths = {
      training: "M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2zM22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z",
      "api-gateway": "M12 2a10 10 0 100 20 10 10 0 000-20zM2 12h20M12 2a15 15 0 014 10 15 15 0 01-4 10 15 15 0 01-4-10A15 15 0 0112 2z",
      rag: "M4 19.5A2.5 2.5 0 016.5 17H20zM6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z",
      agent: "M12 2a2 2 0 100 4 2 2 0 000-4zM6 11h12a2 2 0 012 2v7a2 2 0 01-2 2H6a2 2 0 01-2-2v-7a2 2 0 012-2z",
      inference: "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
    }
    const d = paths[role] || paths["api-gateway"]
    return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>
  }

  return (
    <motion.div key="cluster" className="documents-panel" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <div className="documents-header">
        <h2>Сеть Kolibri</h2>
        <button className="refresh-btn" onClick={onRefresh}>
          <motion.svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            whileHover={{ rotate: 180 }} transition={{ duration: 0.3 }}>
            <polyline points="23,4 23,10 17,10"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </motion.svg>
        </button>
      </div>

      <div className="cluster-stats">
        {[
          { label: "Узлов онлайн", value: `${status.online_nodes}/${status.total_nodes}`, icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>, color: "var(--accent)" },
          { label: "RAM свободно", value: `${status.free_ram_gb} GB`, icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 12h4"/><path d="M14 12h4"/></svg>, color: "var(--success)" },
          { label: "CPU средний", value: `${status.avg_cpu_percent}%`, icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>, color: "var(--text-primary)" },
          { label: "Задач в очереди", value: status.queue_size || 0, icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/></svg>, color: "var(--warning)" },
        ].map((s, i) => (
          <motion.div key={s.label} className="stat-card"
            initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.08, type: "spring", stiffness: 200 }}>
            <div className="stat-icon">{s.icon}</div>
            <div className="stat-value" style={{ color: s.color }}>{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </motion.div>
        ))}
      </div>

      <div className="doc-list">
        {Object.entries(status.nodes || {}).map(([name, node], i) => (
          <motion.div key={name} className="doc-item node-card"
            initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 + i * 0.06, type: "spring", stiffness: 150 }}
            whileHover={{ scale: 1.01, x: 4 }}>
            <div className="doc-icon" style={{
              background: node.status === "online" ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
              color: node.status === "online" ? "var(--success)" : "var(--error)"
            }}>
              <NodeIcon role={node.role} />
            </div>
            <div className="doc-info">
              <div className="doc-name" style={{ textTransform: "capitalize" }}>{name}</div>
              <div className="doc-meta">{node.role} · {node.ip}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: "13px", fontWeight: "600" }}>CPU {node.cpu}%</div>
              <div className="ram-bar">
                <div className="ram-bar-fill" style={{ width: `${Math.min(100, (parseFloat(node.ram) / 16) * 100)}%` }} />
              </div>
              <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>{node.ram}</div>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  )
}
