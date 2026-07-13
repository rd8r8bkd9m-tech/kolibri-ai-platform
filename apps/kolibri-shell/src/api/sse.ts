export interface SseMessage {
  event: string;
  data: unknown;
  id?: string;
}

function decodePayload(raw: string): unknown {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

export async function* parseSseStream(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<SseMessage> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n');

    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseSseFrame(frame);
      if (parsed) yield parsed;
      boundary = buffer.indexOf('\n\n');
    }

    if (done) break;
  }

  const finalFrame = parseSseFrame(buffer.trim());
  if (finalFrame) yield finalFrame;
}

export function parseSseFrame(frame: string): SseMessage | null {
  if (!frame || frame.startsWith(':')) return null;
  let event = 'message';
  let id: string | undefined;
  const data: string[] = [];

  for (const line of frame.split('\n')) {
    if (!line || line.startsWith(':')) continue;
    const separator = line.indexOf(':');
    const field = separator >= 0 ? line.slice(0, separator) : line;
    const value = separator >= 0 ? line.slice(separator + 1).replace(/^ /, '') : '';
    if (field === 'event') event = value;
    if (field === 'id') id = value;
    if (field === 'data') data.push(value);
  }

  if (!data.length) return null;
  return { event, id, data: decodePayload(data.join('\n')) };
}
