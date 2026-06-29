export function getNodeSummary(status) {
  const summary = status?.node_summary || {}
  const registeredNodes = summary.registered_nodes ?? status?.total_nodes ?? 0
  const canonicalNodes = summary.canonical_nodes ?? status?.canonical_nodes ?? registeredNodes
  const freshNodes = summary.fresh_nodes ?? status?.online_nodes ?? 0
  const freshNonDrainingNodes = summary.fresh_non_draining_nodes ?? status?.fresh_non_draining_nodes ?? freshNodes
  const readyGenericNodes = summary.fresh_canonical_generic_implementation_nodes ?? status?.ready_generic_implementation_nodes ?? 0
  const staleNodes = summary.stale_nodes ?? status?.stale_nodes ?? Math.max(registeredNodes - freshNodes, 0)
  const drainingNodes = summary.draining_nodes ?? status?.draining_nodes ?? 0
  const meshShadowDuplicates = summary.mesh_shadow_duplicates ?? status?.mesh_shadow_duplicates ?? 0
  const duplicateNodes = summary.duplicate_nodes ?? status?.duplicate_nodes ?? Math.max(registeredNodes - canonicalNodes, meshShadowDuplicates)

  return {
    registeredNodes,
    canonicalNodes,
    freshNodes,
    freshNonDrainingNodes,
    readyGenericNodes,
    staleNodes,
    drainingNodes,
    meshShadowDuplicates,
    duplicateNodes,
  }
}

export function getFactoryHealth(status) {
  if (!status) return { state: "loading", label: "Загрузка фабрики" }
  if (status.status === "online" && getNodeSummary(status).freshNodes > 0) {
    return { state: "online", label: "Фабрика online" }
  }
  return { state: "degraded", label: "Фабрика degraded" }
}

export function getFactoryIssue(status) {
  if (!status) return ""
  if (status.error) return status.error
  if (status.control_plane?.status === "unavailable") return "Control Plane недоступен"
  if (getNodeSummary(status).freshNodes === 0) return "Нет свежих heartbeat от рабочих узлов"
  return ""
}

export function formatClusterSignal(status) {
  if (!status) return "статус фабрики загружается"
  const { freshNodes, canonicalNodes, registeredNodes } = getNodeSummary(status)
  if (getFactoryHealth(status).state === "degraded") {
    return `degraded · ${freshNodes} fresh · ${canonicalNodes} канон.`
  }
  return `${freshNodes} fresh · ${canonicalNodes} канон. · ${registeredNodes} рег.`
}
