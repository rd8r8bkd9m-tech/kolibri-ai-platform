import { uiInvocableCapabilities } from './normalize'
import type { CapabilityCatalog, DiscoveredCapability, UiCapability, UiCapabilityKey } from './types'

interface UiCapabilityDefinition {
  key: UiCapabilityKey
  aliases: readonly string[]
  renderers: readonly string[]
  title: string
  description: string
}

const DEFINITIONS: readonly UiCapabilityDefinition[] = [
  {
    key: 'web.search',
    aliases: ['web.search', 'web_search', 'search.web'],
    renderers: ['sources', 'research', 'web'],
    title: 'Интернет',
    description: 'Найти актуальные источники',
  },
  {
    key: 'file.search',
    aliases: ['file.search', 'file_search', 'files.search', 'files'],
    renderers: ['file', 'files', 'document'],
    title: 'Файлы',
    description: 'Добавить и проанализировать файлы',
  },
  {
    key: 'code.execute',
    aliases: ['code.execute', 'code.run', 'code', 'shell.execute'],
    renderers: ['code', 'monaco', 'terminal'],
    title: 'Код',
    description: 'Создать, выполнить и проверить код',
  },
  {
    key: 'image.generate',
    aliases: ['image.generate', 'images.generate', 'image_generation'],
    renderers: ['image'],
    title: 'Изображение',
    description: 'Создать и показать проверенный файл',
  },
  {
    key: 'browser.use',
    aliases: ['browser.use', 'browser', 'computer.use'],
    renderers: ['browser', 'preview'],
    title: 'Браузер',
    description: 'Открыть изолированную веб-сессию',
  },
  {
    key: 'mcp.invoke',
    aliases: ['mcp.invoke', 'mcp', 'integration.invoke'],
    renderers: ['mcp', 'tool', 'integration'],
    title: 'Интеграции',
    description: 'Использовать подключённые MCP-инструменты',
  },
] as const

function normalized(value: string | undefined): string {
  return value?.trim().toLowerCase() ?? ''
}

function matchesDefinition(capability: DiscoveredCapability, definition: UiCapabilityDefinition): boolean {
  const id = normalized(capability.id)
  const renderer = normalized(capability.renderer.id)
  return definition.aliases.includes(id) && definition.renderers.includes(renderer)
}

/**
 * Converts server truth into the only capability controls the current Shell
 * can actually render. Unknown capabilities and renderer mismatches stay
 * hidden even when the server advertises them as live.
 */
export function uiCapabilityMenu(catalog: CapabilityCatalog): UiCapability[] {
  const live = uiInvocableCapabilities(catalog)
  return DEFINITIONS.flatMap(definition => {
    const capability = live.find(candidate => matchesDefinition(candidate, definition))
    return capability ? [{
      key: definition.key,
      capability,
      title: definition.title,
      description: definition.description,
    }] : []
  })
}

export function findUiCapability(
  catalog: CapabilityCatalog,
  key: UiCapabilityKey,
): UiCapability | undefined {
  return uiCapabilityMenu(catalog).find(item => item.key === key)
}

export function capabilityPrompt(key: UiCapabilityKey): string {
  const prompts: Record<UiCapabilityKey, string> = {
    'web.search': 'Найди в интернете актуальную информацию и укажи источники: ',
    'file.search': 'Проанализируй прикреплённые файлы: ',
    'code.execute': 'Создай, выполни и проверь код: ',
    'image.generate': 'Создай изображение: ',
    'browser.use': 'Открой браузер и выполни задачу: ',
    'mcp.invoke': 'Используй подходящие подключённые инструменты: ',
  }
  return prompts[key]
}
