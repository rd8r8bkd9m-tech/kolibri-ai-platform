const configured = import.meta.env.VITE_API_URL?.replace(/\/$/, '');
const API_BASE = configured || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '');
const TOKEN_KEY = 'vista.session.token';
const SESSION_KEY = 'vista.session.data';

function url(path) { return `${API_BASE}${path}`; }
function storedToken() { return sessionStorage.getItem(TOKEN_KEY) || ''; }

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = options.token ?? storedToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  let body = options.body;
  if (body !== undefined && !(body instanceof FormData) && typeof body !== 'string') {
    headers.set('Content-Type', 'application/json');
    body = JSON.stringify(body);
  }
  const response = await fetch(url(path), { ...options, headers, body });
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof payload === 'object' ? payload.detail || JSON.stringify(payload) : payload;
    throw new Error(message || `HTTP ${response.status}`);
  }
  return payload;
}

export const api = {
  base: API_BASE,
  token: storedToken,
  session: () => { try { return JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null'); } catch { return null; } },
  hasSession: () => Boolean(storedToken() && sessionStorage.getItem(SESSION_KEY)),
  clearSession: () => { sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(SESSION_KEY); },
  async createSession({ role = 'client_pro', device = 'auto', plan, adminToken } = {}) {
    const headers = adminToken ? { 'X-Vista-Admin-Token': adminToken } : {};
    const result = await request('/api/os/session', { method: 'POST', headers, body: { role, device, plan }, token: '' });
    sessionStorage.setItem(TOKEN_KEY, result.token);
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(result.session));
    return result;
  },
  health: () => request('/api/health', { token: '' }),
  manifest: () => request('/api/os/manifest', { token: '' }),
  resolve: (body) => request('/api/os/resolve', { method: 'POST', body }),
  getSession: (id) => request(`/api/os/session/${id}`),
  patchSession: (id, body) => request(`/api/os/session/${id}`, { method: 'PATCH', body }),
  listEstimates: () => request('/api/estimates'),
  createEstimate: (body) => request('/api/estimates', { method: 'POST', body }),
  getEstimate: (id) => request(`/api/estimates/${id}`),
  updateEstimate: (id, body) => request(`/api/estimates/${id}`, { method: 'PATCH', body }),
  addEstimateItem: (id, body) => request(`/api/estimates/${id}/items`, { method: 'POST', body }),
  updateEstimateItem: (id, itemId, body) => request(`/api/estimates/${id}/items/${itemId}`, { method: 'PATCH', body }),
  deleteEstimateItem: (id, itemId) => request(`/api/estimates/${id}/items/${itemId}`, { method: 'DELETE' }),
  saveEstimateVersion: (id, note = '') => request(`/api/estimates/${id}/versions`, { method: 'POST', body: { note } }),
  estimateVersions: (id) => request(`/api/estimates/${id}/versions`),
  proposal: (id) => request(`/api/estimates/${id}/proposal`),
  generateDocuments: (id) => request(`/api/estimates/${id}/documents`, { method: 'POST' }),
  artifacts: (id) => request(`/api/estimates/${id}/artifacts`),
  createShare: (id, ttl_hours = 168) => request(`/api/estimates/${id}/share`, { method: 'POST', body: { ttl_hours } }),
  listShares: (id) => request(`/api/estimates/${id}/shares`),
  revokeShare: (id, token) => request(`/api/estimates/${id}/shares/${encodeURIComponent(token)}`, { method: 'DELETE' }),
  publicShare: (token) => request(`/api/public/share/${token}`, { token: '' }),

  async publicDownloadArtifact(token, artifact) {
    const response = await fetch(url(`/api/public/share/${encodeURIComponent(token)}/artifacts/${artifact.id}/download`));
    if (!response.ok) {
      let message = 'Download failed';
      try { message = (await response.json()).detail || message; } catch {}
      throw new Error(message);
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = artifact.name || 'vista-document';
    document.body.append(anchor); anchor.click(); anchor.remove();
    URL.revokeObjectURL(objectUrl);
  },
  async downloadArtifact(artifact) {
    const response = await fetch(url(`/api/artifacts/${artifact.id}/download`), { headers: { Authorization: `Bearer ${storedToken()}` } });
    if (!response.ok) throw new Error((await response.json()).detail || 'Download failed');
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = artifact.name || 'vista-document';
    document.body.append(anchor); anchor.click(); anchor.remove();
    URL.revokeObjectURL(objectUrl);
  },
  factoryStats: () => request('/api/factory/stats'),
  factoryTasks: () => request('/api/factory/tasks'),
  createFactoryTask: (body) => request('/api/factory/tasks', { method: 'POST', body }),
  nodes: () => request('/api/nodes'),
  fleetHealth: () => request('/api/fleet/health'),
  serverMetrics: () => request('/api/server/metrics'),
  serverLogs: () => request('/api/server/logs'),
  developerCompatibility: () => request('/api/developer/openai-compatibility'),
  developerKeys: () => request('/api/developer/keys'),
  createDeveloperKey: (body) => request('/api/developer/keys', { method: 'POST', body }),
};
