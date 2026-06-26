const DEFAULT_TIMEOUT_MS = 30000;

export class KolibriApiError extends Error {
  constructor(message, { status, payload } = {}) {
    super(message);
    this.name = 'KolibriApiError';
    this.status = status || 0;
    this.payload = payload || null;
  }
}

export function createKolibriClient({ baseUrl = '', fetchImpl = fetch, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  async function request(path, { method = 'GET', body, headers } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetchImpl(`${baseUrl}${path}`, {
        method,
        headers: {
          Accept: 'application/json',
          ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
          ...(headers || {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      const text = await response.text();
      const payload = text ? JSON.parse(text) : null;
      if (!response.ok) {
        throw new KolibriApiError(`Kolibri API request failed: ${response.status}`, { status: response.status, payload });
      }
      return payload;
    } catch (error) {
      if (error && error.name === 'AbortError') {
        throw new KolibriApiError('Kolibri API request timed out');
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  return {
    health: () => request('/health'),
    models: () => request('/api/models'),
    workspace: () => request('/api/workspace'),
    chat: (message, context = {}) => request('/api/kolibri/chat', { method: 'POST', body: { message, context } }),
    telegramStatus: () => request('/api/telegram/status'),
    telegramTask: (text) => request('/api/telegram/task', { method: 'POST', body: { text } }),
  };
}

export const kolibriClient = createKolibriClient();
