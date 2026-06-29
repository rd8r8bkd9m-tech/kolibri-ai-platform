export const IS_LOCAL = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
export const API_BASE = IS_LOCAL ? `http://${window.location.hostname}:8000` : ""
export const WS_HOST = IS_LOCAL ? `${window.location.hostname}:8000` : window.location.host
