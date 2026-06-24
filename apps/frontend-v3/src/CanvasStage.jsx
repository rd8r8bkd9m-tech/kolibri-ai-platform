import { useEffect, useMemo, useRef, useState } from "react"

const MASCOT_URL = "/kolibri-mascot.png"
const DEFAULT_CANVAS_THEME = {
  name: "day",
  mode: "light",
  backgroundStops: ["#fbfdff", "#f7fbff", "#d7f3ff", "#93dcff"],
  accent: "#18b8c8",
  accentSoft: "rgba(24, 184, 200, 0.18)",
  text: "#0d2b34",
  textMuted: "rgba(13, 43, 52, 0.66)",
  panelFill: "rgba(255, 255, 255, 0.7)",
  panelStroke: "rgba(24, 184, 200, 0.22)",
  auroraA: "rgba(53, 227, 229, 0.22)",
  auroraB: "rgba(91, 161, 255, 0.13)",
  auroraC: "rgba(255, 255, 255, 0.18)",
  grid: "rgba(25, 94, 115, 0.045)",
  horizonA: "rgba(255,255,255,0.26)",
  horizonB: "rgba(214,246,255,0.2)",
  horizonC: "rgba(84,183,218,0.22)",
  showStatusPanel: false,
}
const MOBILE_COMPOSER_RESERVE = 118
const DESKTOP_COMPOSER_RESERVE = 106

export function CanvasStage({
  canvas,
  birdStatus,
  actions,
  showActions,
  pendingApproval,
  visibleTurns = [],
  runtimeProgress = null,
  canvasTheme = DEFAULT_CANVAS_THEME,
  busy,
  onAction,
  onApproveAction,
  onCancelApproval,
}) {
  const canvasRef = useRef(null)
  const imageRef = useRef(null)
  const hitsRef = useRef([])
  const dragRef = useRef(null)
  const [manifestScroll, setManifestScroll] = useState(0)
  const [manifestScrollMax, setManifestScrollMax] = useState(0)
  const manifestScrollMaxRef = useRef(0)
  const manifest = canvas?.manifest || null
  const blocks = useMemo(() => manifest?.blocks || [], [manifest])
  const qaState = buildCanvasQaState({ canvas, manifest, birdStatus, actions, pendingApproval, visibleTurns, runtimeProgress, canvasTheme, busy, manifestScroll })

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setManifestScroll(0))
    return () => window.cancelAnimationFrame(frame)
  }, [manifest?.id, manifest?.version])

  useEffect(() => {
    const image = new Image()
    image.src = MASCOT_URL
    image.onload = () => {
      imageRef.current = image
    }
  }, [])

  useEffect(() => {
    const element = canvasRef.current
    if (!element) return undefined

    let frame = 0
    let disposed = false
    const context = element.getContext("2d")

    function resize() {
      const rect = element.getBoundingClientRect()
      const ratio = window.devicePixelRatio || 1
      const width = Math.max(1, Math.floor(rect.width * ratio))
      const height = Math.max(1, Math.floor(rect.height * ratio))
      if (element.width !== width || element.height !== height) {
        element.width = width
        element.height = height
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
      return rect
    }

    function tick(now) {
      if (disposed) return
      const rect = resize()
      const nextScrollMax = estimateManifestScrollMax(manifest, blocks, rect.width, rect.height)
      if (Math.round(nextScrollMax) !== Math.round(manifestScrollMaxRef.current)) {
        manifestScrollMaxRef.current = nextScrollMax
        setManifestScrollMax(nextScrollMax)
      }
      if (manifestScroll > nextScrollMax) setManifestScroll(nextScrollMax)
      paint(context, {
        width: rect.width,
        height: rect.height,
        canvas,
        manifest,
        blocks,
        birdStatus,
        actions,
        showActions,
        pendingApproval,
        visibleTurns,
        runtimeProgress,
        canvasTheme,
        manifestScroll,
        busy,
        image: imageRef.current,
        time: now,
        hitsRef,
      })
      frame = window.requestAnimationFrame(tick)
    }

    frame = window.requestAnimationFrame(tick)
    return () => {
      disposed = true
      window.cancelAnimationFrame(frame)
    }
  }, [actions, birdStatus, blocks, busy, canvas, canvasTheme, manifest, manifestScroll, pendingApproval, runtimeProgress, showActions, visibleTurns])

  function currentScrollMax() {
    return manifestScrollMaxRef.current
  }

  function updateScroll(nextValue) {
    const max = currentScrollMax()
    setManifestScroll(clamp(nextValue, 0, max))
  }

  function handlePointerDown(event) {
    const rect = event.currentTarget.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top
    const hit = hitsRef.current.find(item => x >= item.x && x <= item.x + item.width && y >= item.y && y <= item.y + item.height)
    if (hit?.command === "approve") onApproveAction?.()
    if (hit?.command === "cancel") onCancelApproval?.()
    if (hit?.action) onAction(hit.action)
    if (!hit && currentScrollMax() > 0) {
      dragRef.current = { pointerId: event.pointerId, y, startScroll: manifestScroll }
      event.currentTarget.setPointerCapture?.(event.pointerId)
    }
  }

  function handlePointerMove(event) {
    const drag = dragRef.current
    if (!drag) return
    const rect = event.currentTarget.getBoundingClientRect()
    const y = event.clientY - rect.top
    updateScroll(drag.startScroll + drag.y - y)
  }

  function handlePointerUp(event) {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null
      event.currentTarget.releasePointerCapture?.(event.pointerId)
    }
  }

  function handleWheel(event) {
    if (currentScrollMax() <= 0) return
    event.preventDefault()
    updateScroll(manifestScroll + event.deltaY)
  }

  function handleKeyDown(event) {
    if (currentScrollMax() <= 0) return
    const deltaByKey = {
      ArrowDown: 42,
      ArrowUp: -42,
      PageDown: 260,
      PageUp: -260,
      Home: -Infinity,
      End: Infinity,
    }
    if (!Object.hasOwn(deltaByKey, event.key)) return
    event.preventDefault()
    const delta = deltaByKey[event.key]
    if (delta === Infinity) updateScroll(currentScrollMax())
    else if (delta === -Infinity) updateScroll(0)
    else updateScroll(manifestScroll + delta)
  }

  return (
    <>
      <canvas
        ref={canvasRef}
        className="kolibri-canvas"
        data-testid="kolibri-canvas"
        data-canvas-title={qaState.title}
        data-canvas-state={qaState.canvasState}
        data-bird-state={qaState.birdState}
        data-bird-summary={qaState.birdSummary}
        data-actions-count={qaState.actionsCount}
        data-approval-mode={qaState.approvalMode}
        data-pending-action={qaState.pendingAction}
        data-turns-count={qaState.turnsCount}
        data-last-turn-text={qaState.lastTurnText}
        data-progress-stage={qaState.progressStage}
        data-progress-label={qaState.progressLabel}
        data-canvas-theme={qaState.canvasTheme}
        data-runtime-status={qaState.runtimeStatus}
        data-last-user-text={qaState.lastUserText}
        data-manifest-scroll={String(Math.round(manifestScroll))}
        data-manifest-scroll-max={String(Math.round(manifestScrollMax))}
        aria-label={qaState.ariaLabel}
        tabIndex={0}
        onKeyDown={handleKeyDown}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onWheel={handleWheel}
      />
      {showActions && actions?.map(action => (
        <button
          key={action.id}
          type="button"
          className="sr-only-action"
          aria-label={action.label}
          onClick={() => onAction?.(action)}
        />
      ))}
      {pendingApproval && (
        <>
          <button type="button" className="sr-only-action" aria-label="Отмена" onClick={() => onCancelApproval?.()} />
          <button type="button" className="sr-only-action" aria-label="Подтвердить" onClick={() => onApproveAction?.()} />
        </>
      )}
    </>
  )
}

function buildCanvasQaState({ canvas, manifest, birdStatus, actions, pendingApproval, visibleTurns, runtimeProgress, canvasTheme, busy, manifestScroll }) {
  const title = String(manifest?.title || "")
  const birdState = String(birdStatus?.state || (busy ? "thinking" : "ready"))
  const birdSummary = publicBirdSummary(birdStatus)
  const birdLabel = publicBirdLabel(birdStatus, busy)
  const actionsCount = String(Array.isArray(actions) ? actions.length : 0)
  const lastTurn = Array.isArray(visibleTurns) && visibleTurns.length ? visibleTurns[visibleTurns.length - 1] : null
  const runtimeStatus = String(canvas?.runtimeStatus || canvas?.errors?.[0]?.code || "")
  const lastUserText = String(canvas?.lastUserText || "")
  const ariaParts = [
    "Canvas Колибри",
    title,
    lastTurn?.text ? `запрос ${lastTurn.text}` : "",
    runtimeProgress?.label ? `ход ${runtimeProgress.label}` : "",
    birdLabel ? `статус ${birdLabel}` : "",
    birdSummary,
    runtimeStatus ? `ошибка ${runtimeStatus}` : "",
  ].filter(Boolean)
  return {
    title,
    canvasState: String(manifest?.state || ""),
    birdState,
    birdSummary,
    actionsCount,
    approvalMode: pendingApproval ? "pending" : "",
    pendingAction: String(pendingApproval?.id || pendingApproval?.intent || ""),
    turnsCount: String(Array.isArray(visibleTurns) ? visibleTurns.length : 0),
    lastTurnText: String(lastTurn?.text || ""),
    progressStage: String(runtimeProgress?.stage || ""),
    progressLabel: String(runtimeProgress?.label || ""),
    canvasTheme: String(canvasTheme?.name || ""),
    runtimeStatus,
    lastUserText,
    manifestScroll: String(Math.round(manifestScroll || 0)),
    ariaLabel: ariaParts.join(". "),
  }
}

function paint(context, state) {
  const { width, height, canvas, manifest, birdStatus, actions, showActions, pendingApproval, visibleTurns, runtimeProgress, canvasTheme, manifestScroll, busy, image, time, hitsRef } = state
  hitsRef.current = []
  context.clearRect(0, 0, width, height)
  paintBackground(context, width, height, time, canvasTheme)
  const layout = canvasLayout(width, height)
  const overlays = createOverlayStack(layout)
  if (manifest && manifest.display?.mode !== "bird_only") {
    paintManifest(context, { ...state, layout, manifestScroll })
  } else {
    paintBird(context, width, height, image, time, busy, birdStatus, canvasTheme)
  }
  if (shouldPaintTurnLog({ manifest, busy, runtimeProgress }) && visibleTurns?.length) {
    paintTurnLog(context, width, height, visibleTurns, canvasTheme, layout)
  }
  if (showActions && actions?.length) {
    paintActions(context, width, height, actions, hitsRef, canvasTheme, layout, overlays)
  }
  if (pendingApproval) {
    paintApprovalPanel(context, width, height, pendingApproval, hitsRef, canvasTheme, layout, overlays)
  }
  if (canvas?.errors?.length) {
    paintRuntimeErrors(context, width, height, canvas.errors, canvasTheme, layout, overlays)
  }
  if ((busy || shouldPaintRuntimeProgress(runtimeProgress)) && !canvas?.errors?.length) {
    paintRuntimeProgress(context, width, height, runtimeProgress, busy, time, canvasTheme, layout, overlays)
  }
  if (shouldPaintBirdStatus({ birdStatus, busy, showActions, pendingApproval, canvas })) {
    paintBirdStatus(context, width, height, birdStatus, { showActions, busy }, canvasTheme, overlays)
  }
}

function paintTurnLog(context, width, height, visibleTurns, canvasTheme = DEFAULT_CANVAS_THEME, layout = canvasLayout(width, height)) {
  const turns = visibleTurns.slice(-1)
  const maxWidth = Math.min(width - 48, width < 760 ? width - 48 : 560)
  let y = width < 760 ? 30 : 42
  const scale = readableScale(width, "turn")

  turns.forEach(turn => {
    const text = trimText(turn.text, width < 760 ? 180 : 260)
    const lines = wrapLines(context, text, maxWidth, { size: scale.body, weight: 560, maxLines: width < 760 ? 3 : 4 })
    const rowHeight = 28 + lines.length * scale.line
    const rightEdge = width - (width < 760 ? 24 : 42)
    const x = rightEdge - maxWidth
    const status = turnStatusLabel(turn.status)

    paintText(context, "Вы", x + maxWidth - 26, y, {
      size: scale.meta,
      weight: 760,
      color: canvasTheme.accent,
      maxWidth: 26,
    })
    let lineY = y + 31
    lines.forEach(line => {
      paintText(context, line, x, lineY, {
        size: scale.body,
        weight: 560,
        color: canvasTheme.text,
        maxWidth,
      })
      lineY += scale.line
    })
    paintText(context, status, x, Math.min(layout.contentBottom - 10, y + rowHeight), {
      size: scale.meta,
      weight: 620,
      color: canvasTheme.textMuted,
      maxWidth,
    })
    y += rowHeight + 24
  })
}

function paintRuntimeProgress(context, width, height, runtimeProgress, busy, time, canvasTheme = DEFAULT_CANVAS_THEME, layout = canvasLayout(width, height), overlays = createOverlayStack(layout)) {
  const label = String(runtimeProgress?.label || (busy ? "Жду ответ" : ""))
  if (!label) return
  const maxWidth = Math.min(width - 36, 520)
  const x = (width - maxWidth) / 2
  const y = overlays.reserve(58)
  const accent = runtimeProgress?.stage === "error" ? "#fb7185" : runtimeProgress?.stage === "stopped" ? "#facc15" : canvasTheme.accent

  roundRect(context, x, y, maxWidth, 58, 20)
  context.fillStyle = canvasTheme.panelFill
  context.fill()
  context.strokeStyle = withAlpha(accent, 0.38)
  context.lineWidth = 1
  context.stroke()

  paintTriangleDots(context, x + 18, y + 15, time, accent)
  const scale = readableScale(width, "overlay")
  paintText(context, "Ход выполнения", x + 70, y + 24, {
    size: scale.meta,
    weight: 760,
    color: canvasTheme.textMuted,
    maxWidth: maxWidth - 92,
  })
  paintText(context, label, x + 70, y + 43, {
    size: scale.body,
    weight: 700,
    color: canvasTheme.text,
    maxWidth: maxWidth - 92,
  })
}

function turnStatusLabel(status) {
  return {
    queued: "принят",
    done: "отвечено",
    error: "ошибка",
  }[status] || "в работе"
}

function trimText(text, maxLength) {
  const value = String(text || "").replace(/\s+/g, " ").trim()
  if (value.length <= maxLength) return value
  return `${value.slice(0, Math.max(0, maxLength - 1))}…`
}

function paintBackground(context, width, height, time, canvasTheme = DEFAULT_CANVAS_THEME) {
  const gradient = context.createLinearGradient(0, 0, 0, height)
  const stops = canvasTheme.backgroundStops || DEFAULT_CANVAS_THEME.backgroundStops
  stops.forEach((stop, index) => {
    gradient.addColorStop(stops.length === 1 ? 1 : index / (stops.length - 1), stop)
  })
  context.fillStyle = gradient
  context.fillRect(0, 0, width, height)

  paintPremiumAurora(context, width, height, time, canvasTheme)
  paintMaterialGrid(context, width, height, time, canvasTheme)
  paintAtmosphericVignette(context, width, height, canvasTheme)
  paintFineTexture(context, width, height, canvasTheme)
}

function paintPremiumAurora(context, width, height, time, canvasTheme = DEFAULT_CANVAS_THEME) {
  const phase = time / 9000
  context.save()
  context.globalAlpha = canvasTheme.mode === "dark" ? 0.88 : 0.72
  context.globalCompositeOperation = "screen"
  paintAuroraBand(context, width, height, {
    baseY: height * 0.12 + Math.sin(phase * Math.PI * 2) * 14,
    thickness: clamp(height * 0.18, 96, 210),
    phase,
    start: canvasTheme.auroraA,
    middle: canvasTheme.auroraB,
    end: canvasTheme.auroraC,
  })
  paintAuroraBand(context, width, height, {
    baseY: height * 0.88 + Math.cos(phase * Math.PI * 1.7) * 18,
    thickness: clamp(height * 0.22, 120, 260),
    phase: phase + 0.38,
    start: canvasTheme.horizonA,
    middle: canvasTheme.auroraA,
    end: canvasTheme.auroraB,
  })
  context.restore()
}

function paintAuroraBand(context, width, height, options) {
  const { baseY, thickness, phase, start, middle, end } = options
  const wave = Math.sin(phase * Math.PI * 2) * width * 0.035
  const gradient = context.createLinearGradient(0, baseY - thickness, width, baseY + thickness)
  gradient.addColorStop(0, start)
  gradient.addColorStop(0.5, middle)
  gradient.addColorStop(1, end)

  context.beginPath()
  context.moveTo(-width * 0.12, baseY - thickness * 0.42)
  context.bezierCurveTo(width * 0.22 + wave, baseY - thickness * 0.92, width * 0.5 - wave, baseY + thickness * 0.05, width * 1.12, baseY - thickness * 0.34)
  context.lineTo(width * 1.12, baseY + thickness * 0.44)
  context.bezierCurveTo(width * 0.66 - wave, baseY + thickness * 0.9, width * 0.33 + wave, baseY + thickness * 0.04, -width * 0.12, baseY + thickness * 0.56)
  context.closePath()
  context.fillStyle = gradient
  context.fill()
}

function paintMaterialGrid(context, width, height, time, canvasTheme = DEFAULT_CANVAS_THEME) {
  const step = width < 760 ? 42 : 56
  const lower = height * 0.58
  const sway = Math.sin(time / 5200) * 7

  context.save()
  context.globalAlpha = canvasTheme.mode === "dark" ? 0.62 : 0.42
  context.lineWidth = 1
  context.strokeStyle = canvasTheme.grid
  for (let x = -step * 2; x < width + step * 2; x += step) {
    context.beginPath()
    context.moveTo(x + sway, lower)
    context.bezierCurveTo(
      x + width * 0.04,
      lower + height * 0.12,
      x + width * 0.1,
      height * 0.82,
      x + width * 0.16,
      height,
    )
    context.stroke()
  }
  for (let y = lower; y < height; y += step * 0.82) {
    context.beginPath()
    context.moveTo(0, y)
    context.bezierCurveTo(width * 0.28, y - 5, width * 0.7, y + 7, width, y + Math.sin((y + time / 200) / 72) * 4)
    context.stroke()
  }
  context.restore()
}

function paintAtmosphericVignette(context, width, height, canvasTheme = DEFAULT_CANVAS_THEME) {
  context.save()
  const gradient = context.createLinearGradient(0, 0, 0, height)
  if (canvasTheme.mode === "dark") {
    gradient.addColorStop(0, "rgba(0, 0, 0, 0.08)")
    gradient.addColorStop(0.5, "rgba(0, 0, 0, 0)")
    gradient.addColorStop(1, "rgba(0, 0, 0, 0.2)")
  } else {
    gradient.addColorStop(0, "rgba(255, 255, 255, 0.18)")
    gradient.addColorStop(0.48, "rgba(255, 255, 255, 0)")
    gradient.addColorStop(1, "rgba(255, 255, 255, 0.24)")
  }
  context.fillStyle = gradient
  context.fillRect(0, 0, width, height)
  context.restore()
}

function paintFineTexture(context, width, height, canvasTheme = DEFAULT_CANVAS_THEME) {
  context.save()
  context.globalAlpha = canvasTheme.mode === "dark" ? 0.045 : 0.018
  context.fillStyle = canvasTheme.mode === "dark" ? "#ffffff" : "#0b4b4f"
  for (let y = 0; y < height; y += 7) {
    for (let x = (y % 14) / 2; x < width; x += 13) {
      context.fillRect(x, y, 1, 1)
    }
  }
  context.restore()
}

function paintBird(context, width, height, image, time, busy, birdStatus, canvasTheme = DEFAULT_CANVAS_THEME) {
  const size = clamp(Math.min(width, height) * 0.3, 132, 220)
  const x = width / 2 - size / 2
  const layout = canvasLayout(width, height)
  const visualCenterY = (layout.top + layout.contentBottom) / 2
  const y = visualCenterY - size / 2 + Math.sin(time / (busy ? 520 : 1200)) * 7
  if (image) {
    context.save()
    context.shadowColor = "rgba(0,0,0,0.28)"
    context.shadowBlur = 32
    context.shadowOffsetY = 18
    context.drawImage(image, x, y, size, size)
    context.restore()
  }
  paintTriangleDots(context, x + size * 0.86, y + size * 0.08, time, quietBirdColor(birdStatus?.state, busy, canvasTheme))
}

function paintTriangleDots(context, x, y, time, color = "#35e3e5") {
  const points = [[18, 0], [4, 24], [32, 24]]
  points.forEach(([dx, dy], index) => {
    const pulse = 1 + Math.sin(time / 240 + index * 0.8) * 0.22
    context.beginPath()
    context.fillStyle = color
    context.shadowColor = shadowColor(color)
    context.shadowBlur = 14
    context.arc(x + dx, y + dy, 4.3 * pulse, 0, Math.PI * 2)
    context.fill()
  })
  context.shadowBlur = 0
}

function paintBirdStatus(context, width, height, birdStatus, options = {}, canvasTheme = DEFAULT_CANVAS_THEME, overlays = createOverlayStack(canvasLayout(width, height))) {
  if (!birdStatus) return
  const metrics = birdStatus.metrics || {}
  const state = String(birdStatus.state || "ready")
  const label = publicBirdLabel(birdStatus, options.busy)
  const summary = publicBirdSummary(birdStatus)
  const compact = [
    `Очередь ${Number(metrics.queued_tasks || 0)}`,
    `Агенты ${Number(metrics.active_agents || 0)}`,
  ].filter(Boolean).join(" · ")
  const text = summary || compact
  const maxWidth = Math.min(width - 36, 520)
  const x = 18
  const y = overlays.reserve(54)
  const color = stateColor(state, options.busy)
  const scale = readableScale(width, "overlay")

  roundRect(context, x, y, maxWidth, 54, 18)
  context.fillStyle = canvasTheme.panelFill
  context.fill()
  context.strokeStyle = withAlpha(color, 0.42)
  context.stroke()

  context.beginPath()
  context.fillStyle = color
  context.shadowColor = shadowColor(color)
  context.shadowBlur = 12
  context.arc(x + 23, y + 27, 6, 0, Math.PI * 2)
  context.fill()
  context.shadowBlur = 0
  paintText(context, label, x + 40, y + 23, { size: scale.meta, weight: 760, color: canvasTheme.text, maxWidth: maxWidth - 58 })
  paintText(context, text, x + 40, y + 40, { size: scale.caption, weight: 520, color: canvasTheme.textMuted, maxWidth: maxWidth - 58 })
}

function paintManifest(context, state) {
  const { width, manifest, blocks, canvasTheme = DEFAULT_CANVAS_THEME, layout = canvasLayout(width, state.height), manifestScroll = 0 } = state
  const margin = layout.margin
  const maxWidth = Math.min(920, width - margin * 2)
  const scale = readableScale(width, "manifest")
  let y = layout.top - manifestScroll
  context.save()
  context.beginPath()
  context.rect(0, layout.top - 8, width, layout.contentBottom - layout.top + 8)
  context.clip()
  paintText(context, manifest.title || "", margin, y + scale.title, {
    size: scale.title,
    weight: 760,
    color: canvasTheme.text,
    maxWidth,
  })
  y += width < 720 ? scale.title + 22 : scale.title + 28
  const visibleBlocks = blocks
  for (const block of visibleBlocks) {
    const blockHeightValue = blockHeight(block, maxWidth)
    if (y + blockHeightValue < layout.top - 48) {
      y += blockHeightValue + 14
      continue
    }
    if (y > layout.contentBottom - 72) break
    y = paintBlock(context, block, margin, y, maxWidth, canvasTheme)
  }
  context.restore()
  paintScrollIndicator(context, width, layout, manifestScroll, estimateManifestScrollMax(manifest, blocks, width, state.height), canvasTheme)
}

function paintBlock(context, block, x, y, width, canvasTheme = DEFAULT_CANVAS_THEME) {
  const type = String(block.type || "custom_data")
  const content = isPlainObject(block.content) ? block.content : {}
  const rawText = content.text || content.message || content.summary || content.description || ""
  const text = displayBlockText(rawText)
  const title = looksLikeSerializedCanvas(rawText) ? "Ответ требует проверки" : displayBlockTitle(block.title, type)
  const height = blockHeight(block, width)
  const scale = readableScale(width, "block")

  if (type === "heading") {
    paintText(context, title, x, y + 30, { size: scale.heading + 4, weight: 780, color: canvasTheme.text, maxWidth: width })
    if (text) {
      paintWrappedText(context, String(text), x, y + 62, width, {
        size: scale.body,
        color: canvasTheme.textMuted,
        maxLines: 3,
      })
    }
    return y + height + 8
  }

  paintBlockSurface(context, x, y, width, height, type, canvasTheme)
  const hasTitle = Boolean(title)
  if (hasTitle) paintText(context, title, x + 20, y + 28, { size: scale.heading, weight: 760, color: canvasTheme.text, maxWidth: width - 40 })
  let lineY = y + (hasTitle ? 56 : 30)
  const clipBottom = y + height - 18
  if (text && !["table", "text", "custom_data"].includes(type)) {
    lineY = paintWrappedText(context, String(text), x + 20, lineY, width - 40, { size: scale.body, color: canvasTheme.textMuted, maxLines: 4, clipBottom })
  }
  paintBlockContent(context, { type, content, x: x + 20, y: lineY, width: width - 40, clipBottom, canvasTheme, scale })
  return y + height + 14
}

function paintBlockSurface(context, x, y, width, height, type, canvasTheme) {
  const tone = blockTone(type, canvasTheme)
  roundRect(context, x, y, width, height, 18)
  context.fillStyle = canvasTheme.panelFill
  context.fill()
  context.strokeStyle = canvasTheme.panelStroke
  context.lineWidth = 1
  context.stroke()

  roundRect(context, x + 10, y + 10, 4, Math.max(34, height - 20), 3)
  context.fillStyle = tone
  context.fill()
}

function paintBlockContent(context, options) {
  const { type } = options
  if (type === "table") return paintTableBlock(context, options)
  if (type === "form") return paintFormBlock(context, options)
  if (type === "checklist") return paintChecklistBlock(context, options)
  if (type === "source_evidence") return paintSourceBlock(context, options)
  if (type === "artifact_card" || type === "document_preview") return paintArtifactBlock(context, options)
  if (type === "diff") return paintDiffBlock(context, options)
  return paintGenericBlock(context, options)
}

function paintTableBlock(context, { content, x, y, width, clipBottom, canvasTheme, scale }) {
  const rows = contentRows(content).filter(isPlainObject)
  const columns = normalizeColumns(content.columns, rows[0]).slice(0, width < 520 ? 3 : 5)
  let lineY = y
  if (content.summary || content.text) {
    lineY = paintWrappedText(context, displayBlockText(content.summary || content.text), x, lineY, width, {
      size: scale.body,
      color: canvasTheme.textMuted,
      maxLines: 2,
      clipBottom,
    })
  }
  if (!rows.length || !columns.length || lineY > clipBottom) return paintGenericBlock(context, { content, x, y: lineY, width, clipBottom, canvasTheme, scale })

  const rowHeight = 32
  const colWidth = width / columns.length
  roundRect(context, x, lineY - 18, width, rowHeight, 10)
  context.fillStyle = canvasTheme.mode === "dark" ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.5)"
  context.fill()
  columns.forEach((column, index) => {
    paintText(context, column.label, x + index * colWidth + 10, lineY + 3, {
      size: scale.meta,
      weight: 760,
      color: canvasTheme.accent,
      maxWidth: colWidth - 16,
    })
  })
  lineY += rowHeight
  rows.slice(0, 6).forEach(row => {
    if (lineY > clipBottom) return
    columns.forEach((column, index) => {
      paintText(context, readableValue(row[column.key]), x + index * colWidth + 10, lineY, {
        size: scale.caption,
        weight: index === 0 ? 650 : 520,
        color: index === 0 ? canvasTheme.text : canvasTheme.textMuted,
        maxWidth: colWidth - 16,
      })
    })
    context.strokeStyle = canvasTheme.panelStroke
    context.beginPath()
    context.moveTo(x, lineY + 10)
    context.lineTo(x + width, lineY + 10)
    context.stroke()
    lineY += rowHeight
  })
  return lineY
}

function paintFormBlock(context, { content, x, y, width, clipBottom, canvasTheme, scale }) {
  const fields = contentFields(content)
  if (!fields.length) return paintGenericBlock(context, { content, x, y, width, clipBottom, canvasTheme, scale })
  let lineY = y
  fields.slice(0, 7).forEach(field => {
    if (lineY > clipBottom) return
    const label = String(field.label || field.name || field.key || "")
    const value = readableValue(field.value ?? field.placeholder ?? field.default ?? "")
    roundRect(context, x, lineY - 20, width, 34, 12)
    context.fillStyle = canvasTheme.mode === "dark" ? "rgba(255,255,255,0.045)" : "rgba(255,255,255,0.46)"
    context.fill()
    paintText(context, label, x + 12, lineY + 1, {
      size: scale.meta,
      weight: 760,
      color: canvasTheme.accent,
      maxWidth: width * 0.38,
    })
    paintText(context, value, x + Math.min(width * 0.42, 210), lineY + 1, {
      size: scale.caption,
      weight: 560,
      color: canvasTheme.text,
      maxWidth: width * 0.54,
    })
    lineY += 39
  })
  return lineY
}

function paintChecklistBlock(context, { content, x, y, width, clipBottom, canvasTheme, scale }) {
  const items = normalizeItems(contentItems(content))
  let lineY = y
  items.slice(0, 8).forEach(item => {
    if (lineY > clipBottom) return
    const done = Boolean(item.done || item.checked || item.state === "done")
    context.beginPath()
    context.strokeStyle = done ? canvasTheme.accent : canvasTheme.panelStroke
    context.lineWidth = 1.5
    context.arc(x + 8, lineY - 6, 7, 0, Math.PI * 2)
    context.stroke()
    if (done) {
      context.beginPath()
      context.fillStyle = canvasTheme.accent
      context.arc(x + 8, lineY - 6, 3.5, 0, Math.PI * 2)
      context.fill()
    }
    paintText(context, readableValue(item.label || item.text || item.title || item), x + 26, lineY, {
      size: scale.body,
      weight: 560,
      color: canvasTheme.text,
      maxWidth: width - 26,
    })
    lineY += scale.line + 3
  })
  return lineY
}

function paintSourceBlock(context, { content, x, y, width, clipBottom, canvasTheme, scale }) {
  const sources = normalizeItems(contentSources(content))
  if (!sources.length) return paintGenericBlock(context, { content, x, y, width, clipBottom, canvasTheme, scale })
  let lineY = y
  sources.slice(0, 5).forEach(source => {
    if (lineY > clipBottom) return
    const confidence = Number(source.confidence ?? source.score ?? source.trust ?? 0)
    const sourceName = readableValue(source.sourceName || source.name || source.title || source.label || "Источник")
    const meta = [source.region, source.date, source.currency].filter(Boolean).map(readableValue).join(" · ")
    const cardHeight = 42
    roundRect(context, x, lineY - 21, width, cardHeight, 12)
    context.fillStyle = canvasTheme.mode === "dark" ? "rgba(255,255,255,0.045)" : "rgba(255,255,255,0.48)"
    context.fill()
    paintText(context, sourceName, x + 12, lineY, {
      size: scale.caption,
      weight: 720,
      color: canvasTheme.text,
      maxWidth: width - 108,
    })
    paintText(context, meta || "требуется проверка", x + 12, lineY + 17, {
      size: scale.meta,
      weight: 520,
      color: canvasTheme.textMuted,
      maxWidth: width - 108,
    })
    paintConfidence(context, x + width - 82, lineY - 6, 64, confidence, canvasTheme)
    lineY += cardHeight + 8
  })
  return lineY
}

function paintArtifactBlock(context, { content, x, y, width, clipBottom, canvasTheme, scale }) {
  const files = normalizeItems(content.files || content.artifacts || content.items || [content]).slice(0, 4)
  let lineY = y
  files.forEach(file => {
    if (lineY > clipBottom) return
    const label = readableValue(file.label || file.title || file.name || content.title || "Файл")
    const type = readableValue(file.type || file.ext || file.format || content.type || "artifact").toUpperCase()
    roundRect(context, x, lineY - 24, width, 42, 13)
    context.fillStyle = canvasTheme.mode === "dark" ? "rgba(255,255,255,0.05)" : "rgba(255,255,255,0.52)"
    context.fill()
    roundRect(context, x + 11, lineY - 15, 54, 24, 8)
    context.fillStyle = canvasTheme.accentSoft || withAlpha(canvasTheme.accent, 0.22)
    context.fill()
    paintText(context, type, x + 22, lineY + 1, { size: scale.meta, weight: 800, color: canvasTheme.text, maxWidth: 34 })
    paintText(context, label, x + 76, lineY + 1, { size: scale.body, weight: 650, color: canvasTheme.text, maxWidth: width - 86 })
    lineY += 50
  })
  return lineY
}

function paintDiffBlock(context, { content, x, y, width, clipBottom, canvasTheme, scale }) {
  const items = normalizeItems(content.changes || content.items || content.rows)
  let lineY = y
  items.slice(0, 5).forEach(item => {
    if (lineY > clipBottom) return
    const label = readableValue(item.label || item.field || item.title || item)
    const before = readableValue(item.before)
    const after = readableValue(item.after)
    paintText(context, label, x, lineY, { size: scale.body, weight: 700, color: canvasTheme.text, maxWidth: width })
    lineY += scale.line
    if (before !== "—" || after !== "—") {
      paintText(context, `${before} -> ${after}`, x + 12, lineY, { size: scale.caption, weight: 540, color: canvasTheme.textMuted, maxWidth: width - 12 })
      lineY += scale.line
    }
  })
  return lineY
}

function paintGenericBlock(context, { content, x, y, width, clipBottom, canvasTheme, scale }) {
  const text = displayBlockText(content.text || content.message || content.summary || content.description || "")
  const rows = contentRows(content)
  const fields = contentFields(content)
  const items = normalizeItems(contentItems(content))
  const shouldUseStructuredPreview = !text && !rows.length && !fields.length && !items.length
  const preview = shouldUseStructuredPreview ? buildStructuredPreview(content) : null
  let lineY = y
  if (text) {
    lineY = paintWrappedText(context, String(text), x, lineY, width, {
      size: scale.body,
      color: canvasTheme.textMuted,
      maxLines: 5,
      clipBottom,
    })
  }
  if (preview) lineY = paintStructuredPreview(context, preview, x, lineY, width, canvasTheme, clipBottom)
  rows.slice(0, 4).forEach(row => {
    if (lineY > clipBottom) return
    paintText(context, rowSummary(row), x, lineY, {
      size: scale.body,
      color: canvasTheme.textMuted,
      maxWidth: width,
    })
    lineY += scale.line
  })
  fields.slice(0, 4).forEach(field => {
    if (lineY > clipBottom) return
    paintText(context, `${field.label || field.name || ""}: ${readableValue(field.value)}`, x, lineY, {
      size: scale.body,
      color: canvasTheme.textMuted,
      maxWidth: width,
    })
    lineY += scale.line
  })
  items.slice(0, 5).forEach(item => {
    if (lineY > clipBottom) return
    paintText(context, `• ${readableValue(item.label || item.text || item.title || item)}`, x, lineY, {
      size: scale.body,
      color: canvasTheme.textMuted,
      maxWidth: width,
    })
    lineY += scale.line
  })
  return lineY
}

function blockHeight(block, width) {
  const type = String(block.type || "custom_data")
  const content = isPlainObject(block.content) ? block.content : {}
  const text = displayBlockText(content.text || content.message || content.summary || content.description || "")
  const rows = contentRows(content)
  const fields = contentFields(content)
  const items = contentItems(content)
  const sources = contentSources(content)
  if (type === "heading") return clamp(58 + Math.ceil(String(text).length / Math.max(62, width / 9)) * 22, 64, 150)
  if (type === "table") return clamp(108 + Math.min(rows.length, 6) * 32 + textLines(text, width) * 18, 122, 360)
  if (type === "form") return clamp(88 + Math.min(fields.length || rows.length, 7) * 39 + textLines(text, width) * 18, 116, 390)
  if (type === "source_evidence") return clamp(92 + Math.min(sources.length || items.length || rows.length, 5) * 50 + textLines(text, width) * 18, 118, 380)
  if (type === "artifact_card" || type === "document_preview") return clamp(96 + Math.min((content.files || content.artifacts || items || []).length || 1, 4) * 50, 128, 310)
  if (type === "checklist") return clamp(90 + Math.min(items.length || rows.length, 8) * 29 + textLines(text, width) * 18, 118, 340)
  if (type === "diff") return clamp(96 + Math.min((content.changes || items || rows || []).length, 5) * 48, 122, 360)
  const shouldUseStructuredPreview = type === "custom_data" || (!text && !rows.length && !fields.length && !items.length)
  const preview = shouldUseStructuredPreview ? buildStructuredPreview(content) : null
  const previewHeight = preview ? 28 + preview.facts.length * 23 + preview.rows.length * 25 : 0
  return clamp(82 + rows.length * 28 + fields.length * 32 + items.length * 26 + previewHeight + textLines(text, width) * 18, 90, 320)
}

function estimateManifestScrollMax(manifest, blocks, width, height) {
  if (!manifest || manifest.display?.mode === "bird_only") return 0
  const layout = canvasLayout(width, height)
  const maxWidth = Math.min(920, width - layout.margin * 2)
  const titleHeight = width < 720 ? 58 : 70
  const contentHeight = titleHeight + blocks.reduce((total, block) => total + blockHeight(block, maxWidth) + 14, 0)
  const available = layout.contentBottom - layout.top
  return Math.max(0, contentHeight - available + 24)
}

function paintScrollIndicator(context, width, layout, scroll, maxScroll, canvasTheme) {
  if (maxScroll <= 0) return
  const trackHeight = Math.max(96, layout.contentBottom - layout.top - 16)
  const trackX = width - (layout.mobile ? 9 : 14)
  const trackY = layout.top + 6
  const thumbHeight = clamp(trackHeight * (trackHeight / (trackHeight + maxScroll)), 32, trackHeight)
  const thumbY = trackY + (trackHeight - thumbHeight) * (scroll / maxScroll)
  roundRect(context, trackX, trackY, 3, trackHeight, 2)
  context.fillStyle = canvasTheme.mode === "dark" ? "rgba(255,255,255,0.08)" : "rgba(13,43,52,0.08)"
  context.fill()
  roundRect(context, trackX - 1, thumbY, 5, thumbHeight, 3)
  context.fillStyle = canvasTheme.accentSoft || withAlpha(canvasTheme.accent, 0.28)
  context.fill()
}

function paintStructuredPreview(context, preview, x, y, width, canvasTheme, clipBottom = Infinity) {
  let lineY = y
  const scale = readableScale(width, "block")
  preview.facts.slice(0, 4).forEach(fact => {
    if (lineY > clipBottom) return
    paintText(context, `${fact.label}: ${fact.value}`, x, lineY, {
      size: scale.body,
      weight: 560,
      color: canvasTheme.textMuted,
      maxWidth: width,
    })
    lineY += scale.line
  })
  if (preview.rows.length) {
    const columnCount = Math.max(1, preview.columns.length)
    const columnWidth = width / columnCount
    preview.columns.forEach((column, index) => {
      if (lineY > clipBottom) return
      paintText(context, column.label, x + index * columnWidth, lineY, {
        size: scale.meta,
        weight: 760,
        color: canvasTheme.accent,
        maxWidth: columnWidth - 8,
      })
    })
    lineY += scale.line
    preview.rows.slice(0, 4).forEach(row => {
      if (lineY > clipBottom) return
      preview.columns.forEach((column, index) => {
        paintText(context, readableValue(row[column.key]), x + index * columnWidth, lineY, {
          size: scale.caption,
          weight: 520,
          color: canvasTheme.text,
          maxWidth: columnWidth - 8,
        })
      })
      lineY += scale.line
    })
  }
  return lineY + 2
}

function paintConfidence(context, x, y, width, confidence, canvasTheme) {
  const normalized = confidence > 1 ? confidence / 100 : confidence
  const value = clamp(Number.isFinite(normalized) ? normalized : 0, 0, 1)
  roundRect(context, x, y, width, 6, 3)
  context.fillStyle = canvasTheme.mode === "dark" ? "rgba(255,255,255,0.1)" : "rgba(13,43,52,0.08)"
  context.fill()
  roundRect(context, x, y, Math.max(4, width * value), 6, 3)
  context.fillStyle = value >= 0.7 ? canvasTheme.accent : value >= 0.45 ? "#facc15" : "#fb7185"
  context.fill()
  paintText(context, `${Math.round(value * 100)}%`, x + 18, y + 20, {
    size: 11,
    weight: 720,
    color: canvasTheme.textMuted,
    maxWidth: width - 18,
  })
}

function blockTone(type, canvasTheme) {
  return {
    table: canvasTheme.accent,
    form: "#7c8cff",
    checklist: "#46f3c0",
    source_evidence: "#35e3e5",
    document_preview: "#facc15",
    artifact_card: "#facc15",
    diff: "#fb7185",
    confirmation: "#facc15",
    payment_gate: "#facc15",
  }[type] || canvasTheme.accent
}

function displayBlockTitle(title, type) {
  const explicit = String(title || "").trim()
  if (explicit && !isTechnicalBlockTitle(explicit, type)) return explicit
  return {
    table: "Таблица",
    form: "Форма",
    checklist: "Проверка",
    timeline: "Этапы",
    source_evidence: "Источники",
    document_preview: "Документ",
    artifact_card: "Файл",
    diff: "Изменения",
    confirmation: "Подтверждение",
    payment_gate: "Доступ",
  }[type] || ""
}

function isTechnicalBlockTitle(title, type) {
  const value = String(title || "").trim().toLowerCase()
  return !value || value === String(type || "").toLowerCase() || ["text", "custom_data", "block", "canvasblock"].includes(value)
}

function displayBlockText(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim()
  if (!text) return ""
  if (looksLikeSerializedCanvas(text)) {
    return "Модель вернула служебный формат. Холст показывает только валидированные блоки; повторите запрос или уточните задачу."
  }
  return text
}

function looksLikeSerializedCanvas(value) {
  const text = String(value || "")
  return /```json|assistant_text|canvas_manifest|domain_operations|parser_state|guardrails|"\s*blocks\s*"\s*:|"\s*actions\s*"\s*:/i.test(text)
}

function contentRows(content) {
  if (Array.isArray(content.rows)) return content.rows
  if (Array.isArray(content.data)) return content.data
  if (Array.isArray(content.records)) return content.records
  return []
}

function contentFields(content) {
  if (Array.isArray(content.fields)) return content.fields
  if (Array.isArray(content.form)) return content.form
  if (Array.isArray(content.inputs)) return content.inputs
  return []
}

function contentItems(content) {
  if (Array.isArray(content.items)) return content.items
  if (Array.isArray(content.steps)) return content.steps
  if (Array.isArray(content.checks)) return content.checks
  return []
}

function contentSources(content) {
  for (const key of ["sources", "dataSources", "evidence", "references", "rows", "items"]) {
    if (Array.isArray(content[key])) return content[key]
  }
  return []
}

function normalizeItems(items) {
  if (!Array.isArray(items)) return []
  return items.map(item => isPlainObject(item) ? item : { label: item })
}

function normalizeColumns(columns, row) {
  if (Array.isArray(columns) && columns.length) {
    return columns
      .map(column => isPlainObject(column)
        ? { key: String(column.key || column.name || column.id || ""), label: String(column.label || column.title || column.name || column.key || "") }
        : { key: String(column), label: humanizeKey(column) })
      .filter(column => column.key)
  }
  return row && isPlainObject(row) ? chooseColumns(row) : []
}

function rowSummary(row) {
  if (isPlainObject(row)) return Object.values(row).map(readableValue).filter(Boolean).join("  ·  ")
  return readableValue(row)
}

function textLines(text, width) {
  const value = String(text || "")
  if (!value) return 0
  return Math.ceil(value.length / Math.max(48, width / 10))
}

function buildStructuredPreview(content) {
  const record = findRecord(content)
  if (!record) return null
  const facts = collectFacts(record)
  const rows = findTabularRows(record)
  if (!facts.length && !rows.length) return null
  const columns = rows.length ? chooseColumns(rows[0]) : []
  return { facts, rows, columns }
}

function findRecord(value) {
  if (!isPlainObject(value)) return null
  const objectValues = Object.values(value).filter(isPlainObject)
  const arrayValues = Object.values(value).filter(Array.isArray)
  if (arrayValues.length || Object.values(value).some(isPrimitive)) return value
  return objectValues[0] || value
}

function collectFacts(record) {
  const facts = []
  Object.entries(record).forEach(([key, value]) => {
    if (facts.length >= 5) return
    if (isPrimitive(value)) {
      facts.push({ label: humanizeKey(key), value: readableValue(value) })
      return
    }
    if (isPlainObject(value)) {
      Object.entries(value).forEach(([nestedKey, nestedValue]) => {
        if (facts.length < 5 && isPrimitive(nestedValue)) {
          facts.push({ label: humanizeKey(nestedKey), value: readableValue(nestedValue) })
        }
      })
    }
  })
  return facts
}

function findTabularRows(record) {
  const direct = Object.values(record).find(value => Array.isArray(value) && value.some(isPlainObject))
  if (direct) return direct.filter(isPlainObject)
  for (const value of Object.values(record)) {
    if (!isPlainObject(value)) continue
    const nested = Object.values(value).find(item => Array.isArray(item) && item.some(isPlainObject))
    if (nested) return nested.filter(isPlainObject)
  }
  return []
}

function chooseColumns(row) {
  return Object.keys(row)
    .filter(key => key !== "id" && isPrimitive(row[key]))
    .slice(0, 4)
    .map(key => ({ key, label: humanizeKey(key) }))
}

function humanizeKey(key) {
  return String(key || "")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, char => char.toUpperCase())
}

function readableValue(value) {
  if (value === null || value === undefined || value === "") return "—"
  if (typeof value === "number") return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value)
  if (typeof value === "boolean") return value ? "Да" : "Нет"
  if (isPlainObject(value) || Array.isArray(value)) return "…"
  if (looksLikeSerializedCanvas(value)) return "служебный формат скрыт"
  return trimText(String(value), 80)
}

function isPrimitive(value) {
  return value === null || ["string", "number", "boolean"].includes(typeof value)
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function paintActions(context, width, height, actions, hitsRef, canvasTheme = DEFAULT_CANVAS_THEME, layout = canvasLayout(width, height), overlays = createOverlayStack(layout)) {
  const maxWidth = Math.min(width - 32, 920)
  let x = (width - maxWidth) / 2
  const rows = buildActionRows(context, actions.slice(0, 4), maxWidth)
  const totalHeight = rows.length * 38 + Math.max(0, rows.length - 1) * 8
  let y = overlays.reserve(totalHeight)
  rows.forEach(row => {
    x = (width - maxWidth) / 2
    row.forEach(action => {
      const label = String(action.label || "")
      const buttonWidth = clamp(context.measureText(label).width + 42, 74, 220)
      roundRect(context, x, y, buttonWidth, 36, 18)
      context.fillStyle = action.risk === "paid" ? "rgba(250, 204, 21, 0.2)" : canvasTheme.panelFill
      context.fill()
      context.strokeStyle = action.risk === "paid" ? "rgba(250, 204, 21, 0.42)" : canvasTheme.panelStroke
      context.stroke()
      paintText(context, label, x + 18, y + 23, { size: 13, weight: 680, color: canvasTheme.text, maxWidth: buttonWidth - 28 })
      hitsRef.current.push({ x, y, width: buttonWidth, height: 36, action })
      x += buttonWidth + 8
    })
    y += 44
  })
}

function buildActionRows(context, actions, maxWidth) {
  const rows = [[]]
  let rowWidth = 0
  actions.forEach(action => {
    const label = String(action.label || "")
    const buttonWidth = clamp(context.measureText(label).width + 42, 74, 220)
    const nextWidth = rowWidth ? rowWidth + 8 + buttonWidth : buttonWidth
    if (nextWidth > maxWidth && rows[rows.length - 1].length) {
      rows.push([action])
      rowWidth = buttonWidth
      return
    }
    rows[rows.length - 1].push(action)
    rowWidth = nextWidth
  })
  return rows.filter(row => row.length)
}

function paintApprovalPanel(context, width, height, action, hitsRef, canvasTheme = DEFAULT_CANVAS_THEME, layout = canvasLayout(width, height), overlays = createOverlayStack(layout)) {
  const maxWidth = Math.min(width - 36, 560)
  const x = (width - maxWidth) / 2
  const y = overlays.reserve(132)
  const risk = String(action.risk || "review")
  const label = String(action.label || action.intent || "действие")
  const accent = risk === "paid" ? "#facc15" : risk === "destructive" ? "#fb7185" : "#35e3e5"
  const scale = readableScale(width, "overlay")

  roundRect(context, x, y, maxWidth, 132, 20)
  context.fillStyle = canvasTheme.panelFill
  context.fill()
  context.strokeStyle = withAlpha(accent, 0.48)
  context.lineWidth = 1
  context.stroke()

  paintText(context, "Требуется подтверждение", x + 20, y + 31, {
    size: scale.body,
    weight: 760,
    color: canvasTheme.text,
    maxWidth: maxWidth - 40,
  })
  paintWrappedText(context, label, x + 20, y + 59, maxWidth - 40, {
    size: scale.caption,
    color: canvasTheme.textMuted,
    maxLines: 2,
  })

  const cancelWidth = 104
  const approveWidth = 148
  const buttonsY = y + 84
  const approveX = x + maxWidth - approveWidth - 18
  const cancelX = approveX - cancelWidth - 10

  roundRect(context, cancelX, buttonsY, cancelWidth, 34, 17)
  context.fillStyle = canvasTheme.mode === "dark" ? "rgba(255,255,255,0.08)" : "rgba(255,255,255,0.62)"
  context.fill()
  context.strokeStyle = canvasTheme.panelStroke
  context.stroke()
  paintText(context, "Отмена", cancelX + 24, buttonsY + 22, { size: 13, weight: 680, color: canvasTheme.text, maxWidth: cancelWidth - 28 })
  hitsRef.current.push({ x: cancelX, y: buttonsY, width: cancelWidth, height: 34, command: "cancel" })

  roundRect(context, approveX, buttonsY, approveWidth, 34, 17)
  context.fillStyle = withAlpha(accent, 0.22)
  context.fill()
  context.strokeStyle = withAlpha(accent, 0.5)
  context.stroke()
  paintText(context, "Подтвердить", approveX + 20, buttonsY + 22, { size: 13, weight: 760, color: canvasTheme.text, maxWidth: approveWidth - 30 })
  hitsRef.current.push({ x: approveX, y: buttonsY, width: approveWidth, height: 34, command: "approve" })
}

function paintRuntimeErrors(context, width, height, errors, canvasTheme = DEFAULT_CANVAS_THEME, layout = canvasLayout(width, height), overlays = createOverlayStack(layout)) {
  const latest = errors[0] || {}
  const code = String(latest.code || "api_error")
  const message = String(latest.message || "Ошибка API")
  const maxWidth = Math.min(width - 36, 640)
  const x = (width - maxWidth) / 2
  const y = overlays.reserve(94)
  const title = errorTitle(code)
  const scale = readableScale(width, "overlay")

  roundRect(context, x, y, maxWidth, 94, 18)
  context.fillStyle = canvasTheme.panelFill
  context.fill()
  context.strokeStyle = code === "payment_required" ? "rgba(250, 204, 21, 0.42)" : "rgba(248, 113, 113, 0.42)"
  context.lineWidth = 1
  context.stroke()

  paintText(context, title, x + 18, y + 30, {
    size: scale.body,
    weight: 760,
    color: code === "payment_required" ? "#fde68a" : "#fecaca",
    maxWidth: maxWidth - 36,
  })
  paintWrappedText(context, message, x + 18, y + 58, maxWidth - 36, {
    size: scale.caption,
    color: "rgba(238,249,251,0.76)",
    maxLines: 2,
  })
}

function publicBirdLabel(birdStatus, busy = false) {
  if (busy) return "Работаю"
  const state = String(birdStatus?.state || "ready")
  if (state === "attention") return "Под контролем"
  return String(birdStatus?.label || {
    ready: "Готова",
    working: "Работаю",
    syncing: "Синхронизация",
    success: "Готово",
    error: "Ошибка",
    offline: "Офлайн",
  }[state] || "Готова")
}

function publicBirdSummary(birdStatus) {
  const metrics = birdStatus?.metrics || {}
  const state = String(birdStatus?.state || "ready")
  if (state === "attention") {
    return `Очередь ${Number(metrics.queued_tasks || 0)} · агенты ${Number(metrics.active_agents || 0)}`
  }
  const summary = String(birdStatus?.summary || "")
  return summary
    .replace(/\s*·?\s*approval\s*\d*/gi, "")
    .replace(/\s*·?\s*quarantine\s*\d*/gi, "")
    .trim()
}

function shouldPaintBirdStatus({ birdStatus, busy, showActions, pendingApproval, canvas }) {
  if (busy || showActions || pendingApproval || canvas?.errors?.length) return true
  const state = String(birdStatus?.state || "ready")
  return state === "error" || state === "offline"
}

function shouldPaintTurnLog({ manifest, busy, runtimeProgress }) {
  if (!busy && !runtimeProgress) return false
  return !manifest || manifest.display?.mode === "bird_only"
}

function shouldPaintRuntimeProgress(runtimeProgress) {
  const stage = String(runtimeProgress?.stage || "")
  return Boolean(stage) && stage !== "done"
}

function canvasLayout(width, height) {
  const mobile = width < 760
  const composerReserve = mobile ? MOBILE_COMPOSER_RESERVE : DESKTOP_COMPOSER_RESERVE
  const margin = mobile ? 18 : 36
  const top = mobile ? 24 : 32
  const contentBottom = Math.max(top + 220, height - composerReserve)
  return {
    mobile,
    margin,
    top,
    contentBottom,
    actionsY: Math.max(top, contentBottom - (mobile ? 78 : 54)),
    composerReserve,
  }
}

function createOverlayStack(layout) {
  let cursor = layout.contentBottom - 10
  const gap = 10
  return {
    reserve(height) {
      cursor = Math.max(layout.top, cursor - height)
      const y = cursor
      cursor = Math.max(layout.top, cursor - gap)
      return y
    },
  }
}

function readableScale(width, context = "body") {
  const mobile = width < 760
  if (context === "turn") {
    return mobile
      ? { meta: 13, caption: 14, body: 18, line: 25 }
      : { meta: 13, caption: 14, body: 19, line: 27 }
  }
  if (context === "manifest") {
    return mobile
      ? { title: 28, heading: 20, body: 16, caption: 14, meta: 12, line: 24 }
      : { title: 36, heading: 21, body: 16, caption: 14, meta: 12, line: 25 }
  }
  if (context === "block") {
    return mobile
      ? { heading: 20, body: 15, caption: 14, meta: 12, line: 24 }
      : { heading: 20, body: 15, caption: 13, meta: 12, line: 24 }
  }
  return mobile
    ? { body: 16, caption: 14, meta: 12, line: 24 }
    : { body: 15, caption: 13, meta: 12, line: 23 }
}

function errorTitle(code) {
  if (code === "payment_required") return "Нужен доступ"
  if (code === "confirmation_required") return "Нужно подтверждение"
  if (code === "validation_failed") return "Действие не прошло проверку"
  if (code === "model_contract_failed") return "Модель вернула неверный Canvas"
  if (code === "backend_offline") return "Backend недоступен"
  return "Ошибка API"
}

function paintText(context, text, x, y, options = {}) {
  if (!text) return
  context.font = `${options.weight || 500} ${options.size || 14}px Inter, system-ui, sans-serif`
  context.fillStyle = options.color || "#eef9fb"
  context.fillText(String(text), x, y, options.maxWidth)
}

function paintWrappedText(context, text, x, y, width, options = {}) {
  context.font = `${options.weight || 500} ${options.size || 14}px Inter, system-ui, sans-serif`
  context.fillStyle = options.color || "#eef9fb"
  const words = String(text).split(/\s+/)
  const maxLines = Number(options.maxLines || Infinity)
  const clipBottom = Number(options.clipBottom || Infinity)
  let lines = 0
  let line = ""
  let lineY = y
  words.forEach(word => {
    if (lines >= maxLines || lineY > clipBottom) return
    const testLine = line ? `${line} ${word}` : word
    if (context.measureText(testLine).width > width && line) {
      context.fillText(line, x, lineY)
      line = word
      lineY += (options.size || 14) + 7
      lines += 1
    } else {
      line = testLine
    }
  })
  if (line && lines < maxLines && lineY <= clipBottom) {
    context.fillText(line, x, lineY)
    lineY += (options.size || 14) + 7
  }
  return lineY
}

function wrapLines(context, text, width, options = {}) {
  context.font = `${options.weight || 500} ${options.size || 14}px Inter, system-ui, sans-serif`
  const words = String(text).split(/\s+/)
  const maxLines = Number(options.maxLines || 3)
  const lines = []
  let line = ""
  words.forEach(word => {
    if (lines.length >= maxLines) return
    const testLine = line ? `${line} ${word}` : word
    if (context.measureText(testLine).width > width && line) {
      lines.push(line)
      line = word
    } else {
      line = testLine
    }
  })
  if (line && lines.length < maxLines) lines.push(line)
  return lines
}

function roundRect(context, x, y, width, height, radius) {
  context.beginPath()
  context.moveTo(x + radius, y)
  context.arcTo(x + width, y, x + width, y + height, radius)
  context.arcTo(x + width, y + height, x, y + height, radius)
  context.arcTo(x, y + height, x, y, radius)
  context.arcTo(x, y, x + width, y, radius)
  context.closePath()
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function stateColor(state, busy) {
  if (busy) return "#35e3e5"
  return {
    ready: "#35e3e5",
    thinking: "#35e3e5",
    working: "#46f3c0",
    syncing: "#93c5fd",
    success: "#86efac",
    attention: "#facc15",
    error: "#fb7185",
    offline: "#94a3b8",
  }[state] || "#35e3e5"
}

function quietBirdColor(state, busy, canvasTheme = DEFAULT_CANVAS_THEME) {
  const value = String(state || "ready")
  if (!busy && value === "attention") return canvasTheme.accent
  return stateColor(value, busy)
}

function shadowColor(color) {
  if (color === "#facc15") return "rgba(250, 204, 21, 0.65)"
  if (color === "#fb7185") return "rgba(251, 113, 133, 0.62)"
  if (color === "#94a3b8") return "rgba(148, 163, 184, 0.46)"
  return "rgba(53, 227, 229, 0.68)"
}

function withAlpha(color, alpha) {
  const hex = color.replace("#", "")
  if (hex.length !== 6) return `rgba(255,255,255,${alpha})`
  const value = Number.parseInt(hex, 16)
  const red = (value >> 16) & 255
  const green = (value >> 8) & 255
  const blue = value & 255
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}
