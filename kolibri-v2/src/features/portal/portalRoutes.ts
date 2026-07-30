export const PRODUCTION_ORIGIN = 'https://kolibriai.ru'

export interface PortalRouteMeta {
  title: string
  description: string
  robots: 'index, follow' | 'noindex, nofollow'
  canonical: string | null
}

const publicRoutes = {
  '/': {
    title: 'Kolibri AI OS — от задачи к готовому результату',
    description: 'Kolibri ведёт задачу от диалога до проверяемого результата в одном проекте.',
  },
  '/pricing': {
    title: 'Тарифы — Kolibri AI',
    description: 'Условия бета-доступа и тарифы Kolibri AI без скрытых списаний.',
  },
  '/security': {
    title: 'Безопасность — Kolibri AI',
    description: 'Как Kolibri защищает сессии, проекты, артефакты и доступ к инструментам.',
  },
  '/privacy': {
    title: 'Конфиденциальность — Kolibri AI',
    description: 'Какие данные обрабатывает Kolibri AI и как пользователь управляет ими.',
  },
  '/terms': {
    title: 'Условия использования — Kolibri AI',
    description: 'Условия использования бета-версии Kolibri AI.',
  },
  '/developers': {
    title: 'Разработчикам — Kolibri AI',
    description: 'Документация и подтверждённые API-маршруты Kolibri AI.',
  },
  '/docs': {
    title: 'Документация — Kolibri AI',
    description: 'Контракты и примеры для подтверждённых возможностей Kolibri AI.',
  },
} as const

export const PUBLIC_PORTAL_PATHS = Object.freeze(Object.keys(publicRoutes))

const privatePrefixes = Object.freeze([
  '/app',
  '/chat',
  '/library',
  '/apps',
  '/estimates',
  '/documents',
  '/contracts',
  '/agents',
  '/control',
  '/servers',
  '/settings',
  '/login',
  '/playground',
  '/share',
])

function normalizePathname(pathname: string): string {
  const normalized = pathname.startsWith('/') ? pathname : `/${pathname}`
  return normalized.length > 1 ? normalized.replace(/\/+$/, '') : normalized
}

export function isPrivatePortalPath(pathname: string): boolean {
  const normalized = normalizePathname(pathname)
  return privatePrefixes.some(prefix => normalized === prefix || normalized.startsWith(`${prefix}/`))
}

export function resolvePortalRouteMeta(pathname: string): PortalRouteMeta {
  const normalized = normalizePathname(pathname)
  const route = publicRoutes[normalized as keyof typeof publicRoutes]

  if (route) {
    return {
      ...route,
      robots: 'index, follow',
      canonical: `${PRODUCTION_ORIGIN}${normalized === '/' ? '/' : normalized}`,
    }
  }

  return {
    title: isPrivatePortalPath(normalized) ? 'Kolibri — рабочее пространство' : 'Страница не найдена — Kolibri AI',
    description: 'Защищённое рабочее пространство Kolibri AI.',
    robots: 'noindex, nofollow',
    canonical: null,
  }
}
