import { useEffect } from 'react'
import { useLocation } from 'react-router'
import { resolvePortalRouteMeta } from './portalRoutes'

function ensureMeta(name: string): HTMLMetaElement {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[name="${name}"]`)
  if (!element) {
    element = document.createElement('meta')
    element.name = name
    document.head.append(element)
  }
  return element
}

function ensureProperty(property: string): HTMLMetaElement {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[property="${property}"]`)
  if (!element) {
    element = document.createElement('meta')
    element.setAttribute('property', property)
    document.head.append(element)
  }
  return element
}

export default function PortalMetadata() {
  const { pathname } = useLocation()

  useEffect(() => {
    const meta = resolvePortalRouteMeta(pathname)
    document.documentElement.lang = 'ru'
    document.title = meta.title
    ensureMeta('description').content = meta.description
    ensureMeta('robots').content = meta.robots
    ensureProperty('og:title').content = meta.title
    ensureProperty('og:description').content = meta.description
    ensureProperty('og:type').content = 'website'

    let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
    if (meta.canonical) {
      if (!canonical) {
        canonical = document.createElement('link')
        canonical.rel = 'canonical'
        document.head.append(canonical)
      }
      canonical.href = meta.canonical
      ensureProperty('og:url').content = meta.canonical
    } else {
      canonical?.remove()
      document.head.querySelector<HTMLMetaElement>('meta[property="og:url"]')?.remove()
    }
  }, [pathname])

  return null
}
