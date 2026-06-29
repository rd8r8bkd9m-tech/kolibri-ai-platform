import { Skeleton } from "../ui/Skeleton"

function NodeIcon({ role }) {
  const paths = {
    training: "M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2zM22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z",
    "api-gateway": "M12 2a10 10 0 100 20 10 10 0 000-20zM2 12h20M12 2a15 15 0 014 10 15 15 0 01-4 10 15 15 0 01-4-10A15 15 0 0112 2z",
    rag: "M4 19.5A2.5 2.5 0 016.5 17H20zM6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z",
    agent: "M12 2a2 2 0 100 4 2 2 0 000-4zM6 11h12a2 2 0 012 2v7a2 2 0 01-2 2H6a2 2 0 01-2-2v-7a2 2 0 012-2z",
    inference: "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
  }
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={paths[role] || paths["api-gateway"]}/></svg>
}

export function ClusterPanel({ status, onRefresh }) {
  if (!status) {
    return (
      <div className="control-empty">
        <div className="skeleton-grid">
          {[1,2,3].map(i => <Skeleton key={i} className="skeleton-card" />)}
        </div>
      </div>
    )
  }

  const nodes = Array.isArray(status.nodes)
    ? status.nodes.map(node => [node.node_id || node.id || node.hostname, node])
    : Object.entries(status.nodes || {})

  return (
    <div className="control-section">
      <div className="control-section-head">
        <h3>Сеть Kolibri</h3>
        <button className="refresh-btn" onClick={onRefresh} title="Обновить">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="23,4 23,10 17,10"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
        </button>
      </div>
      <div className="cluster-stats compact">
        {[
          { label: "Онлайн", value: `${status.online_nodes}/${status.total_nodes}`, color: "var(--accent)" },
          { label: "RAM", value: `${status.free_ram_gb} GB`, color: "var(--success)" },
          { label: "CPU", value: `${status.avg_cpu_percent}%`, color: "var(--text-primary)" },
          { label: "Очередь", value: status.queue_size || 0, color: "var(--warning)" },
        ].map(item => (
          <div key={item.label} className="stat-card">
            <div className="stat-value" style={{ color: item.color }}>{item.value}</div>
            <div className="stat-label">{item.label}</div>
          </div>
        ))}
      </div>
      <div className="doc-list">
        {nodes.map(([name, node]) => (
          <div key={name} className="doc-item node-card">
            <div className="doc-icon" style={{
              background: node.status === "online" ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
              color: node.status === "online" ? "var(--success)" : "var(--error)"
            }}>
              <NodeIcon role={node.role} />
            </div>
            <div className="doc-info">
              <div className="doc-name" style={{ textTransform: "capitalize" }}>{name}</div>
              <div className="doc-meta">{node.role} · {node.hostname || node.ip || node.agent_id || "internal"}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: "13px", fontWeight: "600" }}>CPU {node.cpu == null ? "n/a" : node.cpu}</div>
              <div className="ram-bar">
                <div className="ram-bar-fill" style={{ width: `${node.ram_total_gb ? Math.min(100, ((node.ram_total_gb - node.ram_available_gb) / node.ram_total_gb) * 100) : Math.min(100, (parseFloat(node.ram || 0) / 16) * 100)}%` }} />
              </div>
              <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>{node.ram || `${node.ram_available_gb || 0}/${node.ram_total_gb || 0} GB`}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
