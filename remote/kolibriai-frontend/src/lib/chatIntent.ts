export type IntentKind = 'estimate' | 'document' | 'analysis' | 'build' | 'search' | 'general'

export interface IntentDirection {
  label: string
  detail: string
}

export interface ChatIntent {
  kind: IntentKind
  title: string
  subtitle: string
  directions: IntentDirection[]
}

const INTENTS: Record<IntentKind, ChatIntent> = {
  estimate: {
    kind: 'estimate',
    title: 'Похоже, нужна смета',
    subtitle: 'Колибри уточнит объект, объемы и сразу соберет рабочий черновик.',
    directions: [
      { label: 'Структура работ', detail: 'разделы, позиции, единицы' },
      { label: 'Материалы', detail: 'цены, количество, запас' },
      { label: 'Документ', detail: 'КП, акт или договор' },
    ],
  },
  document: {
    kind: 'document',
    title: 'Похоже, нужен документ',
    subtitle: 'Колибри выдержит деловой тон и сохранит факты из диалога.',
    directions: [
      { label: 'Черновик', detail: 'структура и формулировки' },
      { label: 'Проверка', detail: 'риски, пробелы, даты' },
      { label: 'Финальная версия', detail: 'готовый текст' },
    ],
  },
  analysis: {
    kind: 'analysis',
    title: 'Похоже, нужен разбор',
    subtitle: 'Колибри разложит данные по шагам и покажет выводы без лишнего шума.',
    directions: [
      { label: 'Факты', detail: 'что известно сейчас' },
      { label: 'Выводы', detail: 'что это значит' },
      { label: 'Следующий шаг', detail: 'что сделать дальше' },
    ],
  },
  build: {
    kind: 'build',
    title: 'Похоже, нужно собрать задачу',
    subtitle: 'Колибри уточнит результат, ограничения и подготовит план выполнения.',
    directions: [
      { label: 'Цель', detail: 'что должно измениться' },
      { label: 'Ограничения', detail: 'что нельзя трогать' },
      { label: 'Проверка', detail: 'как понять, что готово' },
    ],
  },
  search: {
    kind: 'search',
    title: 'Похоже, нужно найти информацию',
    subtitle: 'Колибри спросит контекст и вернет короткую выжимку с источниками в проекте.',
    directions: [
      { label: 'Где искать', detail: 'сметы, документы, база' },
      { label: 'Критерии', detail: 'дата, клиент, объект' },
      { label: 'Результат', detail: 'список или ответ' },
    ],
  },
  general: {
    kind: 'general',
    title: 'Можно начать с одной фразы',
    subtitle: 'Колибри сам выберет маршрут и задаст уточняющий вопрос, если данных мало.',
    directions: [
      { label: 'Объяснить', detail: 'коротко и понятно' },
      { label: 'Собрать', detail: 'из фактов в результат' },
      { label: 'Продолжить', detail: 'следующим действием' },
    ],
  },
}

export function detectChatIntent(input: string): ChatIntent {
  const text = input.toLowerCase()
  if (/(смет|расцен|калькуляц|стоимост|прайс|материал|электромонтаж|монтаж|объем|объём)/.test(text)) {
    return INTENTS.estimate
  }
  if (/(договор|акт|документ|коммерчес|кп|письмо|тз|заявлен|отчет|отчёт)/.test(text)) {
    return INTENTS.document
  }
  if (/(анализ|разбор|сравн|продаж|данн|метрик|почему|вывод|причин)/.test(text)) {
    return INTENTS.analysis
  }
  if (/(сделай|создай|собери|построй|реализ|почини|исправ|задач|план|запусти)/.test(text)) {
    return INTENTS.build
  }
  if (/(найди|поиск|где|покажи|посмотри|истори|библиотек)/.test(text)) {
    return INTENTS.search
  }
  return INTENTS.general
}

export function shouldShowIntent(input: string) {
  return input.trim().length >= 3
}
