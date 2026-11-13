/**
 * Unified AI Model Interface — абстракция над всеми моделями
 * 
 * Поддерживаемые провайдеры:
 * - GigaChat (Sber API)
 * - Ollama (local models)
 * - LM Studio (local desktop)
 * - OpenAI Compatible API
 * 
 * Использование:
 * const result = await modelHub.chat(messages, { model: 'ollama:llama3.2' });
 * const stream = await modelHub.chatStream(messages, { model: 'gigachat:GigaChat-3-Ultra' });
 */

import { aiLogger } from './logger';
import { chatWithGigaChat, chatWithGigaChatStream } from './gigachat';
import { chatWithOllama, chatWithOllamaStream } from './ollama';
import { chatWithLMStudio, chatWithLMStudioStream } from './lm-studio';
import { chatWithOpenAICompatible, chatWithOpenAICompatibleStream } from './openai-compatible';

export interface Message {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_call_id?: string;
}

function toProviderMessages(messages: Message[]): { role: 'system' | 'user' | 'assistant'; content: string }[] {
  return messages.map((m) => ({
    role: m.role === 'tool' ? 'user' : m.role,
    content: m.content,
  }));
}

export interface ModelOptions {
  model?: string;
  temperature?: number;
  maxTokens?: number;
  topP?: number;
  frequencyPenalty?: number;
  presencePenalty?: number;
  signal?: AbortSignal;
  /** Disable cross-provider fallback for bounded internal jobs. */
  fallback?: boolean;
}

export interface ChatResponse {
  content: string;
  model: string;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  finishReason?: string;
}

export type ModelProvider = 'gigachat' | 'ollama' | 'lm-studio' | 'openai-compatible';

/** Определяет провайдера из имени модели */
function detectProvider(model: string): ModelProvider {
  if (model.startsWith('ollama:')) return 'ollama';
  if (model.startsWith('lm-studio:')) return 'lm-studio';
  if (model.startsWith('openai:')) return 'openai-compatible';
  return 'gigachat'; // default
}

/** Извлекает имя модели без префикса провайдера */
function extractModelName(model: string): string {
  const parts = model.split(':');
  return parts.length > 1 ? parts.slice(1).join(':') : model;
}

/** Доступные локальные модели */
export const LOCAL_MODELS = {
  ollama: [
    { id: 'ollama:llama3.2', name: 'Llama 3.2 3B', size: '2.0 GB', description: 'Быстрая, лёгкая' },
    { id: 'ollama:llama3.2:8b', name: 'Llama 3.2 8B', size: '4.9 GB', description: 'Баланс качества и скорости' },
    { id: 'ollama:mistral-small3.1', name: 'Mistral Small 3.1', size: '~15 GB', description: 'Высокое качество' },
    { id: 'ollama:qwen2.5-coder:7b', name: 'Qwen 2.5 Coder 7B', size: '4.4 GB', description: 'Генерация кода' },
    { id: 'ollama:phi3.5', name: 'Phi-3.5 Mini', size: '2.3 GB', description: 'Microsoft, лёгкая' },
  ],
  'lm-studio': [
    { id: 'lm-studio:local', name: 'LM Studio Default', size: 'varies', description: 'Загруженная модель' },
  ],
} as const;

/** Доступные облачные модели */
export const CLOUD_MODELS = [
  { id: 'gigachat:GigaChat-3-Ultra', name: 'GigaChat 3 Ultra', size: 'N/A', description: 'Максимальное качество' },
  { id: 'gigachat:GigaChat-3-Plus', name: 'GigaChat 3 Plus', size: 'N/A', description: 'Баланс качества и скорости' },
  { id: 'gigachat:GigaChat-3-Lite', name: 'GigaChat 3 Lite', size: 'N/A', description: 'Быстрые ответы' },
] as const;

/** Все доступные модели */
export const ALL_MODELS = [
  ...CLOUD_MODELS,
  ...LOCAL_MODELS.ollama,
  ...LOCAL_MODELS['lm-studio'],
] as const;

/** Проверка доступности модели */
export async function checkModelAvailability(provider: ModelProvider): Promise<boolean> {
  try {
    switch (provider) {
      case 'ollama':
        const ollamaRes = await fetch('http://localhost:11434/api/tags', { signal: AbortSignal.timeout(3000) });
        return ollamaRes.ok;
      
      case 'lm-studio':
        const lmRes = await fetch('http://localhost:1234/v1/models', { signal: AbortSignal.timeout(3000) });
        return lmRes.ok;
      
      case 'openai-compatible':
        const openaiRes = await fetch(`${process.env.OPENAI_COMPATIBLE_URL || 'http://localhost:8000'}/v1/models`, {
          signal: AbortSignal.timeout(3000),
        });
        return openaiRes.ok;
      
      case 'gigachat':
        // GigaChat всегда доступен (API)
        return true;
    }
  } catch (error) {
    aiLogger.debug(`Model availability check failed for ${provider}:`, error);
    return false;
  }
  return false;
}

/**
 * Основной метод чата — неблокирующий, с fallback
 */
export async function chat(
  messages: Message[],
  options: ModelOptions = {}
): Promise<ChatResponse> {
  const { model = getDefaultModel(), temperature, maxTokens, signal } = options;
  const provider = detectProvider(model);
  const modelName = extractModelName(model);

  aiLogger.info(`Chat with ${provider}:${modelName}`, {
    messageCount: messages.length,
    temperature,
    maxTokens,
  });

  try {
    let content: string;

    switch (provider) {
      case 'gigachat':
        content = await chatWithGigaChat(
          toProviderMessages(messages),
          { model: modelName, temperature, maxTokens }
        );
        break;

      case 'ollama':
        content = await chatWithOllama(
          toProviderMessages(messages),
          { model: modelName, temperature, maxTokens, signal }
        );
        break;

      case 'lm-studio':
        content = await chatWithLMStudio(
          toProviderMessages(messages),
          { model: modelName, temperature, maxTokens, signal }
        );
        break;

      case 'openai-compatible':
        content = await chatWithOpenAICompatible(
          toProviderMessages(messages),
          { model: modelName, temperature, maxTokens, signal }
        );
        break;

      default:
        throw new Error(`Unknown provider: ${provider}`);
    }

    return {
      content,
      model: `${provider}:${modelName}`,
      finishReason: 'stop',
    };
  } catch (error) {
    aiLogger.error(`Chat failed with ${provider}:${modelName}:`, error);
    
    // Fallback на другую модель
    if (signal?.aborted || options.fallback === false) throw error;
    const fallbackModel = getFallbackModel(provider);
    if (fallbackModel && fallbackModel !== model) {
      aiLogger.info(`Falling back to ${fallbackModel}`);
      return chat(messages, { ...options, model: fallbackModel });
    }

    throw error;
  }
}

/**
 * Потоковый чат — для real-time ответов
 */
export async function* chatStream(
  messages: Message[],
  options: ModelOptions = {}
): AsyncGenerator<string, void, unknown> {
  const { model = getDefaultModel(), temperature, maxTokens, signal } = options;
  const provider = detectProvider(model);
  const modelName = extractModelName(model);

  aiLogger.info(`Chat stream with ${provider}:${modelName}`);

  try {
    switch (provider) {
      case 'gigachat':
        for await (const chunk of chatWithGigaChatStream(
          toProviderMessages(messages),
          { model: modelName, temperature, maxTokens },
          signal
        )) {
          yield chunk;
        }
        break;

      case 'ollama':
        for await (const chunk of chatWithOllamaStream(
          toProviderMessages(messages),
          { model: modelName, temperature, maxTokens, signal }
        )) {
          yield chunk;
        }
        break;

      case 'lm-studio':
        for await (const chunk of chatWithLMStudioStream(
          toProviderMessages(messages),
          { model: modelName, temperature, maxTokens, signal }
        )) {
          yield chunk;
        }
        break;

      case 'openai-compatible':
        for await (const chunk of chatWithOpenAICompatibleStream(
          toProviderMessages(messages),
          { model: modelName, temperature, maxTokens, signal }
        )) {
          yield chunk;
        }
        break;

      default:
        throw new Error(`Unknown provider: ${provider}`);
    }
  } catch (error) {
    aiLogger.error(`Chat stream failed with ${provider}:${modelName}:`, error);
    throw error;
  }
}

/** Получить модель по умолчанию */
export function getDefaultModel(): string {
  // Приоритет: локальные модели > GigaChat
  if (process.env.AI_DEFAULT_MODEL) {
    return process.env.AI_DEFAULT_MODEL;
  }
  
  // Проверяем доступность Ollama
  if (process.env.AI_USE_LOCAL === 'true') {
    return 'ollama:qwen2.5:1.5b';
  }
  
  return 'gigachat:GigaChat-3-Ultra';
}

/** Получить fallback модель */
function getFallbackModel(currentProvider: ModelProvider): string | null {
  switch (currentProvider) {
    case 'gigachat':
      return 'ollama:qwen2.5:1.5b'; // fallback на стабильную локальную модель
    case 'ollama':
    case 'lm-studio':
      return 'gigachat:GigaChat-3-Lite'; // fallback на облако
    case 'openai-compatible':
      return 'gigachat:GigaChat-3-Lite';
    default:
      return null;
  }
}

/** Получить статус всех моделей */
export async function getModelsStatus(): Promise<Record<ModelProvider, boolean>> {
  return {
    gigachat: await checkModelAvailability('gigachat'),
    ollama: await checkModelAvailability('ollama'),
    'lm-studio': await checkModelAvailability('lm-studio'),
    'openai-compatible': await checkModelAvailability('openai-compatible'),
  };
}

/** Export для использования в других модулях */
export const modelHub = {
  chat,
  chatStream,
  checkModelAvailability,
  getModelsStatus,
  getDefaultModel,
  detectProvider,
  LOCAL_MODELS,
  CLOUD_MODELS,
  ALL_MODELS,
};
