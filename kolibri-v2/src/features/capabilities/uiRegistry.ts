import { isUiInvocableCapability } from './normalize'
import type { CapabilityCatalog, DiscoveredCapability, UiCapability, UiCapabilityKey } from './types'

interface UiCapabilityDefinition {
  key: UiCapabilityKey
  aliases: readonly string[]
  renderers: readonly string[]
  title: string
  description: string
}

const DEFINITIONS: readonly UiCapabilityDefinition[] = [
  // estimate.create — disabled: heavy estimate composer removed from kolibriai.ru
  {
    key: 'document.editor',
    aliases: ['document.editor'],
    renderers: ['document_editor'],
    title: 'Документ',
    description: 'Создать редактируемый документ',
  },
  {
    key: 'web.search',
    aliases: ['web.search', 'web_search', 'search.web'],
    renderers: ['sources', 'research', 'web'],
    title: 'Интернет',
    description: 'Найти актуальные источники',
  },
  {
    key: 'file.search',
    aliases: ['file.search', 'file.upload', 'file_search', 'files.search', 'files'],
    renderers: ['file', 'files', 'document', 'file_search'],
    title: 'Файлы',
    description: 'Добавить и проанализировать файлы',
  },
  {
    key: 'document.pdf',
    aliases: ['document.pdf'],
    renderers: ['pdf'],
    title: 'PDF',
    description: 'Создать проверенный PDF-документ',
  },
  {
    key: 'document.docx',
    aliases: ['document.docx'],
    renderers: ['document'],
    title: 'Документ',
    description: 'Создать редактируемый DOCX',
  },
  {
    key: 'document.xlsx',
    aliases: ['document.xlsx'],
    renderers: ['spreadsheet'],
    title: 'Таблица',
    description: 'Создать и скачать XLSX',
  },
  {
    key: 'document.pptx',
    aliases: ['document.pptx'],
    renderers: ['presentation'],
    title: 'Презентация',
    description: 'Создать и скачать PPTX',
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
    key: 'image.edit',
    aliases: ['image.edit', 'images.edit'],
    renderers: ['image'],
    title: 'Редактировать изображение',
    description: 'Изменить сохранённое изображение',
  },
  {
    key: 'site.create',
    aliases: ['site.create', 'website.create'],
    renderers: ['project_preview'],
    title: 'Сайт',
    description: 'Создать файлы, preview и ZIP',
  },
  {
    key: 'app.create',
    aliases: ['app.create', 'application.create'],
    renderers: ['project_preview'],
    title: 'Приложение',
    description: 'Создать приложение, preview и ZIP',
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
  if (catalog.availability === 'unavailable') return []
  const visible = catalog.capabilities.filter(isUiInvocableCapability)
  return DEFINITIONS.flatMap(definition => {
    const capability = visible.find(candidate => matchesDefinition(candidate, definition))
    return capability ? [{
      key: definition.key,
      capability,
      title: definition.title,
      description: definition.description,
      enabled: true,
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
    'document.editor': 'Создай редактируемый документ: ',
    'web.search': 'Найди в интернете актуальную информацию и укажи источники: ',
    'file.search': 'Проанализируй прикреплённые файлы: ',
    'document.pdf': 'Создай PDF-документ: ',
    'document.docx': 'Создай редактируемый документ: ',
    'document.xlsx': 'Создай таблицу XLSX: ',
    'document.pptx': 'Создай презентацию PPTX: ',
    'code.execute': 'Создай, выполни и проверь код: ',
    'image.generate': 'Создай изображение: ',
    'image.edit': 'Отредактируй прикреплённое изображение: ',
    'site.create': 'Создай готовый сайт с preview и файлами: ',
    'app.create': 'Создай готовое приложение с preview и файлами: ',
    'browser.use': 'Открой браузер и выполни задачу: ',
    'mcp.invoke': 'Используй подходящие подключённые инструменты: ',
  }
  return prompts[key]
}
