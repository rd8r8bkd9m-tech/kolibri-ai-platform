import { NextRequest, NextResponse } from 'next/server';
import { createHash } from 'crypto';
import { chatWithGigaChat, chatWithGigaChatStream, checkGigaChatHealth } from '@/lib/gigachat';
import {
  ESTIMATE_TERMS,
  buildAttachmentBlock,
  buildDomainFallback,
  finalizeContent,
  buildToolInstructions,
} from '@/lib/chatPipeline';
import { aiLogger, dbLogger } from '@/lib/logger';
import { requireAuthOrRespond } from '@/lib/auth/middleware';
import { getCachedChatResponse, setCachedChatResponse } from '@/lib/cache';
import { modelHub, type Message as ModelHubMessage } from '@/lib/model-hub';
import { chatRequestSchema, validateBody } from '@/lib/security/validation';
import { sanitizePlainText, mightContainXss } from '@/lib/security/sanitize';
import { sanitizeMessage } from '@/lib/promptValidation';

const GATEWAY_URL = process.env.CORE_GATEWAY_URL || 'http://127.0.0.1:8001/api/v1/ai/chat';

const SYSTEM_PROMPT = `Ты — Коли, помощник по подготовке черновиков строительных смет, актов, договоров и деловых документов.

## Правила достоверности
- Не выдумывай объёмы, цены, региональные коэффициенты, нормативные коды/редакции, характеристики материалов, реквизиты, даты, ставки налогов или юридические требования.
- Отделяй исходные данные пользователя от вычисленных значений и явно показывай формулы и единицы измерения.
- Сумму считай только из явно предоставленных количества и цены. Если одного из значений нет, оставь поле «не задано», не выводи итог и запроси недостающие данные.
- Не считай площадь стен чистой без фактических размеров/суммарной площади проёмов. Не считай объём заказа с запасом без заданного пользователем процента и обоснования.
- Найденный фрагмент или демонстрационный пример не является подтверждением действующей ФЕР/ГЭСН/ТЕР. Называй норматив только при наличии проверяемого источника, региона и редакции; иначе запроси их.
- Не применяй фиксированные проценты накладных расходов, прибыли и НДС. Учитывай их только по предоставленной методике/договору и с явным указанием базы расчёта.
- Если исходных данных недостаточно, сначала задай короткий список уточняющих вопросов. Не оформляй догадки как готовую смету.
- Помечай сгенерированные договоры, акты и формы как черновики для проверки специалистом; не утверждай, что они автоматически соответствуют действующим требованиям или являются официальными формами.

## Подготовка документа
- Для ведомости объёмов используй таблицу: №, наименование, единица, количество, источник/формула, цена, сумма.
- Показывай итоги только по полностью рассчитанным строкам; если есть незаполненные цены или объёмы, пометь общий итог как «не рассчитан».
- Добавляй дату составления, перечень допущений и список не предоставленных данных. Не превращай дату генерации в дату выполнения работ.
- Сохраняй исходные наименования и числа; округляй только отображение, не меняя исходные значения.
- Перед финальным ответом проверь размерности, арифметику строк и совпадение итогов.
- Если нужен точный расчёт объёма/площади, вызови доступный детерминированный инструмент; не имитируй его вывод.
- Не показывай внутренний формат вызова пользователю; дождись результата инструмента.`;

interface ChatMessage {
  role: string;
  content: string;
}

/** Обычная (непотоковая) генерация: GigaChat → gateway → доменный фолбэк. */
async function generateOnce(params: {
  chatMessages: ChatMessage[];
  lastUserMessage: string;
  userMessage: string;
  isEstimateRequest: boolean;
  conversationId?: string;
  clientId?: string;
}): Promise<{ content: string; provider: string }> {
  const { chatMessages, lastUserMessage, userMessage, isEstimateRequest, conversationId, clientId } = params;

  let content = '';
  let provider = '';

  // Autonomous-first: an explicit AI_DEFAULT_MODEL wins over the legacy
  // direct GigaChat branch, so production does not spend cloud quota unless
  // the operator intentionally selects a cloud model.
  const configuredModel = process.env.AI_DEFAULT_MODEL || process.env.AI_BLOG_MODEL;
  if (configuredModel) {
    try {
      const response = await modelHub.chat(
        chatMessages as ModelHubMessage[],
        { model: configuredModel, temperature: isEstimateRequest ? 0.3 : 0.7, maxTokens: 2048 },
      );
      content = response.content;
      provider = response.model || configuredModel;
    } catch (localError) {
      console.warn('Configured AI model failed, continuing legacy fallbacks:', localError);
    }
  }

  const gigachatReady = process.env.GIGA_CHAT_AUTH_KEY
    || (process.env.GIGA_CHAT_API_KEY && process.env.GIGA_CHAT_API_SECRET);

  if (gigachatReady) {
    try {
      content = await chatWithGigaChat(chatMessages, {
        temperature: isEstimateRequest ? 0.3 : 0.7,
        maxTokens: 4096,
      });
      provider = 'gigachat';
    } catch (gigaError) {
      console.warn('GigaChat failed, falling back to gateway:', gigaError);
    }
  }

  if (!content) {
    try {
      const response = await fetch(GATEWAY_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: lastUserMessage.slice(-4096),
          conversation_id: conversationId,
          client_id: clientId,
          profile: isEstimateRequest ? 'deep' : 'balanced',
          time_budget_ms: isEstimateRequest ? 30000 : 12000,
          persona: 'assistant',
          memory_enabled: true,
        }),
        signal: AbortSignal.timeout(30000),
      });

      if (response.ok) {
        const data = await response.json();
        content = typeof data.response === 'string' ? data.response.trim() : '';
        provider = 'gateway';
      }
    } catch (gatewayError) {
      console.warn('Gateway failed:', gatewayError);
    }
  }

  return { content: finalizeContent(content, lastUserMessage, userMessage, isEstimateRequest), provider };
}

/** SSE-поток: дельты GigaChat; при сбое — единый блок через обычную генерацию. */
function buildStreamResponse(params: {
  chatMessages: ChatMessage[];
  lastUserMessage: string;
  userMessage: string;
  isEstimateRequest: boolean;
  conversationId?: string;
  clientId?: string;
  signal: AbortSignal;
}): Response {
  const { chatMessages, lastUserMessage, userMessage, isEstimateRequest, conversationId, clientId, signal } = params;
  const encoder = new TextEncoder();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (payload: Record<string, unknown>) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(payload)}\n\n`));
      };

      try {
        const gigachatReady = process.env.GIGA_CHAT_AUTH_KEY
          || (process.env.GIGA_CHAT_API_KEY && process.env.GIGA_CHAT_API_SECRET);

        let accumulated = '';
        let provider = '';
        let streamed = false;

        if (gigachatReady) {
          try {
            for await (const delta of chatWithGigaChatStream(
              chatMessages,
              { temperature: isEstimateRequest ? 0.3 : 0.7, maxTokens: 4096 },
              signal
            )) {
              accumulated += delta;
              streamed = true;
              send({ type: 'delta', text: delta });
            }
            provider = 'gigachat';
          } catch (streamError) {
            console.warn('GigaChat stream failed, falling back:', streamError);
          }
        }

        const finalized = finalizeContent(accumulated, lastUserMessage, userMessage, isEstimateRequest);

        if (!streamed) {
          const result = await generateOnce({
            chatMessages, lastUserMessage, userMessage, isEstimateRequest, conversationId, clientId,
          });
          if (result.content) send({ type: 'delta', text: result.content });
          provider = result.provider;
        } else if (finalized !== accumulated) {
          send({ type: 'replace', text: finalized });
        }

        send({ type: 'done', provider: provider || 'fallback' });
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        send({ type: 'error', message });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}

export async function POST(request: NextRequest) {
  let userMessage = '';
  let startTime = Date.now();

  // Проверка авторизации
  const authCheck = await requireAuthOrRespond(request, { requireAuth: true });
  if (authCheck.response) {
    return authCheck.response;
  }

  try {
    const body = await request.json();

    // Validate and sanitize request body using Zod schema
    const validation = validateBody(body, chatRequestSchema);
    if ('error' in validation) {
      aiLogger.warn('Chat API: validation failed', { error: validation.error });
      return NextResponse.json({ error: validation.error }, { status: 400 });
    }

    const { messages, conversationId, clientId, attachments, stream } = validation.data;

    // Sanitize each message to prevent XSS / prompt injection
    const sanitizedMessages = messages.map((msg) => {
      const sanitized = sanitizePlainText(msg.content, 50000);
      // Log potential XSS attempts for monitoring
      if (mightContainXss(msg.content) && !mightContainXss(sanitized)) {
        aiLogger.warn('Chat API: XSS pattern detected and sanitized', {
          contentLength: msg.content.length,
        });
      }
      return { ...msg, content: sanitized };
    });

    const lastUserMessage = [...sanitizedMessages]
      .reverse()
      .find((m): m is { role: 'user'; content: string } => {
        if (!m || typeof m !== 'object') return false;
        return m.role === 'user' && typeof m.content === 'string';
      })?.content || '';

    if (!lastUserMessage.trim()) {
      return NextResponse.json({ error: 'A user message is required' }, { status: 400 });
    }
    userMessage = lastUserMessage.trim();

    // История для GigaChat: системный промпт + контекст файлов + последние 20 сообщений.
    const chatMessages: ChatMessage[] = [
      { role: 'system', content: SYSTEM_PROMPT + buildToolInstructions() + buildAttachmentBlock(attachments) },
      ...sanitizedMessages.slice(-20),
    ];

    const isEstimateRequest = ESTIMATE_TERMS.test(lastUserMessage);
    
    // Проверяем кэш для одинаковых запросов.
    // Важно: btoa() бросает «Invalid character» на кириллице, поэтому хэшируем через sha256.
    const promptHash = createHash('sha256')
      .update(lastUserMessage.trim().toLowerCase().slice(0, 200))
      .digest('hex')
      .slice(0, 32);
    const cachedResponse = getCachedChatResponse(promptHash);
    if (cachedResponse) {
      aiLogger.info('Chat cache hit', { promptHash, latency: Date.now() - startTime });
      return NextResponse.json({
        content: cachedResponse.content,
        provider: cachedResponse.provider,
        cached: true,
      });
    }

    aiLogger.info('Chat request', {
      messageLength: userMessage.length,
      isEstimateRequest,
      hasAttachments: !!attachments?.length,
      conversationId,
    });

    if (stream === true) {
      return buildStreamResponse({
        chatMessages,
        lastUserMessage,
        userMessage,
        isEstimateRequest,
        conversationId: typeof conversationId === 'string' ? conversationId : undefined,
        clientId: typeof clientId === 'string' ? clientId : undefined,
        signal: request.signal,
      });
    }

    const result = await generateOnce({
      chatMessages,
      lastUserMessage,
      userMessage,
      isEstimateRequest,
      conversationId: typeof conversationId === 'string' ? conversationId : undefined,
      clientId: typeof clientId === 'string' ? clientId : undefined,
    });

    const latency = Date.now() - startTime;
    aiLogger.info('Chat response', {
      provider: result.provider,
      contentLength: result.content.length,
      latency,
    });

    // Сохраняем в кэш
    setCachedChatResponse(promptHash, result.content, result.provider);

    // Отправляем push-уведомление если пользователь подписан
    if (conversationId && result.content.length > 100) {
      sendPushNotificationQueued(conversationId, result.content).catch(() => {
        // Не блокируем ответ отправкой уведомления
      });
    }

    return NextResponse.json(result);
  } catch (error) {
    const latency = Date.now() - startTime;
    const message = error instanceof Error ? error.message : 'Unknown error';
    
    aiLogger.error('Chat API error', {
      error: message,
      latency,
      userMessageLength: userMessage.length,
    });
    
    const fallback = userMessage ? buildDomainFallback(userMessage) : null;
    if (fallback) {
      aiLogger.info('Chat fallback used', { latency });
      return NextResponse.json({ content: fallback, provider: 'fallback' });
    }
    
    return NextResponse.json(
      { error: 'Failed to process request', details: message },
      { status: 500 }
    );
  }
}

/**
 * Отправить push-уведомление пользователю (асинхронно, не блокирует ответ)
 */
async function sendPushNotificationQueued(sessionId: string, content: string) {
  try {
    // Get session to find user
    const { db } = await import('@/lib/db');
    const session = await db.session.findUnique({
      where: { id: sessionId },
      select: { userId: true },
    });

    if (!session?.userId) return;

    // Get push subscription
    const setting = await db.systemSetting.findFirst({
      where: { key: `push_subscription_${session.userId}` },
    });

    if (!setting) return;

    const subscription = JSON.parse(setting.value);
    
    // Send notification
    const webpush = await import('web-push');
    const vapidKeys = {
      publicKey: process.env.VAPID_PUBLIC_KEY || 'BEl62iUY4tWj7R2eB09FeJKFqR1gE7JhXkq3MWnT4Q6vN8pL2sK7jF9dR3hG5tY8wP1mX4cV6bN0aS7eR2uI5o',
      privateKey: process.env.VAPID_PRIVATE_KEY || 'your-private-key-here',
    };

    webpush.setVapidDetails(
      'mailto:admin@koli.app',
      vapidKeys.publicKey,
      vapidKeys.privateKey
    );

    const preview = content.length > 100 ? content.slice(0, 100) + '...' : content;

    await webpush.sendNotification(
      subscription.endpoint,
      JSON.stringify({
        title: 'Коли — Ответ готов',
        body: preview,
        url: '/chat',
        sessionId,
      }),
      {
        vapidDetails: {
          subject: 'mailto:admin@koli.app',
          publicKey: vapidKeys.publicKey,
          privateKey: vapidKeys.privateKey,
        },
      }
    );

    aiLogger.info('Push notification sent', { sessionId, userId: session.userId });
  } catch (error) {
    // Silently fail - don't block the response
    aiLogger.warn('Failed to send push notification', { error: error instanceof Error ? error.message : 'Unknown' });
  }
}
