const FULL_SURFACE_KINDS = new Set([
  "workspace",
  "canvas",
  "estimate",
  "pdf",
  "response",
  "document",
  "site",
  "app",
]);

export function isMobileFullSurface(kind) {
  return FULL_SURFACE_KINDS.has(kind);
}
