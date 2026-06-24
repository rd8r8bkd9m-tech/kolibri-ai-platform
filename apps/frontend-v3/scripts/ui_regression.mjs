import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")

function read(file) {
  return fs.readFileSync(path.join(root, file), "utf8")
}

function assert(condition, message) {
  if (!condition) {
    console.error(`ui regression failed: ${message}`)
    process.exit(1)
  }
}

const app = read("src/App.jsx")
const stage = read("src/CanvasStage.jsx")
const css = read("src/styles.css")
const html = read("index.html")

assert(html.includes("<section id=\"root\""), "root mount must not be a div")
assert(app.includes("screen-canvas"), "screen must be the canvas")
assert(app.includes("CanvasStage"), "real canvas stage must be mounted")
assert(stage.includes("<canvas"), "stage must render an actual canvas")
assert(stage.includes("className=\"kolibri-canvas\""), "canvas must have stable class")
assert(!app.includes("<div"), "shell must not include div wrappers")
assert(!app.includes("<aside"), "shell must not include DOM side panels")
assert(!app.includes("<nav"), "shell must not include DOM action menus")
assert(!app.includes("canvas-viewport"), "shell must not use a DOM viewport")
assert(!app.includes("messages.map"), "shell must not render a separate chat timeline")
assert(!css.includes(".bubble"), "shell CSS must not include hardcoded chat bubbles")
assert(stage.includes("paintBird"), "bird must be painted on canvas")
assert(stage.includes("paintTriangleDots"), "thinking dots must be painted on canvas")
assert(app.includes("composer"), "single composer must exist")
assert(stage.includes("aria-label={qaState.ariaLabel}"), "canvas must expose dynamic accessible name")
assert(stage.includes("data-testid=\"kolibri-canvas\""), "canvas must expose stable QA selector")
assert(stage.includes("data-bird-state"), "canvas must expose bird state for QA without DOM UI")
assert(stage.includes("data-approval-mode"), "canvas must expose approval mode for QA without DOM UI")
assert(stage.includes("data-turns-count"), "canvas must expose user question count for QA without DOM UI")
assert(stage.includes("data-progress-stage"), "canvas must expose progress state for QA without DOM UI")
assert(stage.includes("data-manifest-scroll"), "canvas must expose internal manifest scroll state for QA")
assert(stage.includes("data-manifest-scroll-max"), "canvas must expose internal manifest scroll range for QA")
assert(stage.includes("onWheel={handleWheel}"), "canvas must support wheel scroll for long generated manifests")
assert(stage.includes("onKeyDown={handleKeyDown}"), "canvas must support keyboard scroll for long generated manifests")
assert(stage.includes("sr-only-action"), "canvas actions must have accessible non-visual controls")
assert(stage.includes("paintApprovalPanel"), "approval must be painted inside the canvas")
assert(stage.includes("paintTurnLog"), "user questions must be painted inside the canvas")
assert(stage.includes("paintRuntimeProgress"), "public progress must be painted inside the canvas")
assert(stage.includes("paintPremiumAurora"), "canvas must not degrade to a flat black surface")
assert(stage.includes("paintMaterialGrid"), "canvas must render premium material depth")
assert(stage.includes("shouldPaintBirdStatus"), "idle canvas must stay free of control-plane status panels")
assert(!stage.includes("paintGlassHorizon"), "canvas must not render a visible horizon stripe artifact")
assert(!stage.includes("paintGlow"), "background must not rely on radial placeholder glows")
assert(stage.includes("data-runtime-status"), "canvas must expose runtime status for QA without DOM UI")
assert(css.includes("@media (max-width: 760px)"), "mobile responsive rules must exist")
assert(css.includes("100dvh"), "mobile layout must use dynamic viewport height")
assert(css.includes("env(safe-area-inset-bottom)"), "mobile composer must respect safe area")
assert(css.includes("focus-within"), "composer must include a polished focus state")
assert(css.includes(".sr-only-action"), "accessible canvas actions must be visually hidden by default")
assert(css.includes("prefers-reduced-motion"), "reduced motion support must exist")
assert(!/width:\s*100vw/.test(css), "avoid page-level 100vw overflow risk")
assert(!/border-radius:\s*[3-9]\dpx/.test(css), "avoid oversized pill/card radii except circular buttons")

console.log("frontend-v3 UI regression guards passed")
