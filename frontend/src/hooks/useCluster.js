import { useState } from "react"

export function useCluster({ API_BASE }) {
  const [clusterStatus, setClusterStatus] = useState(null)

  const fetchCluster = async () => {
    try {
      const r = await fetch(`${API_BASE}/cluster/status`)
      if (r.ok) setClusterStatus(await r.json())
    } catch (e) { console.error("Cluster unavailable", e) }
  }

  return { clusterStatus, fetchCluster }
}
