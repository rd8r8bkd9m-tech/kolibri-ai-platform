import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest, NextResponse } from 'next/server';

const mocks = vi.hoisted(() => ({
  requireAuthOrRespond: vi.fn(),
  chatWithGigaChat: vi.fn(),
  modelChat: vi.fn(),
  rateLimit: vi.fn(),
  clientIp: vi.fn(),
}));

vi.mock('@/lib/auth/middleware', () => ({
  requireAuthOrRespond: mocks.requireAuthOrRespond,
}));

vi.mock('@/lib/gigachat', () => ({
  chatWithGigaChat: mocks.chatWithGigaChat,
}));

vi.mock('@/lib/model-hub', () => ({
  modelHub: { chat: mocks.modelChat },
}));

vi.mock('@/lib/rateLimit', () => ({
  rateLimit: mocks.rateLimit,
  clientIp: mocks.clientIp,
}));

import { POST } from '@/app/api/admin/blog/generate/route';

const article = {
  title: 'Как подготовить строительный проект',
  excerpt: 'Практические советы по организации исходных данных для проекта.',
  content: `# Подготовка проекта

Подготовка начинается со сбора исходных данных и согласования целей. Зафиксируйте требования участников, сроки и доступные документы.

## Организация материалов

Соберите планы, спецификации и переписку в одном месте. Отмечайте версии и источники каждого документа, чтобы участники могли проверить актуальность.

## Проверка результата

Перед использованием проекта сверьте исходные данные с ответственными специалистами. Уточните все значения, которые требуют внешнего подтверждения.

## Итог

Понятный процесс подготовки помогает команде видеть пробелы и вовремя задавать вопросы.`,
  tags: ['проекты', 'строительство'],
  seoTitle: 'Подготовка строительного проекта: советы',
  seoDescription: 'Практические шаги по подготовке исходных данных и организации строительного проекта.',
};

function request(body: unknown) {
  return new NextRequest('http://localhost/api/admin/blog/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

describe('POST /api/admin/blog/generate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv('GIGA_CHAT_AUTH_KEY', 'test-key');
    vi.stubEnv('GIGA_CHAT_API_KEY', '');
    vi.stubEnv('GIGA_CHAT_API_SECRET', '');
    mocks.requireAuthOrRespond.mockResolvedValue({
      context: { userId: 'admin-1' },
      response: null,
    });
    mocks.rateLimit.mockReturnValue({ allowed: true, retryAfterSec: 0 });
    mocks.clientIp.mockReturnValue('127.0.0.1');
    mocks.modelChat.mockResolvedValue(JSON.stringify(article));
    mocks.modelChat.mockResolvedValue({ content: JSON.stringify(article), model: 'gigachat:GigaChat-3-Ultra' });
  });

  it('requires an authenticated administrator before generation', async () => {
    mocks.requireAuthOrRespond.mockResolvedValue({
      context: { userId: null },
      response: NextResponse.json({ error: 'Необходима авторизация' }, { status: 401 }),
    });

    const req = request({ topic: 'Строительный проект' });
    const response = await POST(req);

    expect(response.status).toBe(401);
    expect(mocks.requireAuthOrRespond).toHaveBeenCalledWith(req, {
      requireAuth: true,
      minRole: 'admin',
    });
    expect(mocks.modelChat).not.toHaveBeenCalled();
  });

  it('rejects a non-admin user', async () => {
    mocks.requireAuthOrRespond.mockResolvedValue({
      context: { userId: 'user-1' },
      response: NextResponse.json({ error: 'Доступ запрещён' }, { status: 403 }),
    });

    const response = await POST(request({ topic: 'Строительный проект' }));

    expect(response.status).toBe(403);
    expect(mocks.modelChat).not.toHaveBeenCalled();
  });

  it('validates input before making an AI request', async () => {
    const response = await POST(request({ topic: 'x' }));

    expect(response.status).toBe(400);
    expect(mocks.modelChat).not.toHaveBeenCalled();
  });

  it('returns a validated article draft without persisting it', async () => {
    const response = await POST(request({
      topic: 'Подготовка строительного проекта',
      audience: 'Подрядчики',
      instructions: 'Добавь практический чек-лист',
    }));
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.draft).toEqual(article);
    expect(mocks.modelChat).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({ role: 'system' }),
        expect.objectContaining({
          role: 'user',
          content: JSON.stringify({
            topic: 'Подготовка строительного проекта',
            audience: 'Подрядчики',
            instructions: 'Добавь практический чек-лист',
          }),
        }),
      ]),
      { model: undefined, temperature: 0.65, maxTokens: 3000 }
    );
  });

  it('limits generation requests and rejects when the limit is exceeded', async () => {
    mocks.rateLimit.mockReturnValue({ allowed: false, retryAfterSec: 60 });

    const response = await POST(request({ topic: 'Строительный проект' }));

    expect(response.status).toBe(429);
    expect(response.headers.get('Retry-After')).toBe('60');
    expect(mocks.modelChat).not.toHaveBeenCalled();
  });

  it('reports an unavailable AI provider explicitly', async () => {
    vi.stubEnv('GIGA_CHAT_AUTH_KEY', '');

    const response = await POST(request({ topic: 'Строительный проект' }));

    expect(response.status).toBe(503);
    expect(mocks.modelChat).not.toHaveBeenCalled();
  });

  it('rejects malformed or out-of-contract AI output', async () => {
    mocks.modelChat.mockResolvedValue('not JSON');

    const response = await POST(request({ topic: 'Строительный проект' }));

    expect(response.status).toBe(502);
  });
});
