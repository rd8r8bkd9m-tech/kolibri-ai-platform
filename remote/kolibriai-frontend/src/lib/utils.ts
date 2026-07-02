import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  const fmt = localStorage.getItem('kolibri-date-format') || 'DD.MM.YYYY'
  const day = String(d.getDate()).padStart(2, '0')
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const year = d.getFullYear()
  switch (fmt) {
    case 'MM/DD/YYYY': return `${month}/${day}/${year}`
    case 'YYYY-MM-DD': return `${year}-${month}-${day}`
    default: return `${day}.${month}.${year}`
  }
}

export function formatRelativeDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const days = Math.floor(diff / 86400000)
  if (days === 0) return 'Сегодня'
  if (days === 1) return 'Вчера'
  if (days < 7) return `${days} дн. назад`
  return formatDate(d)
}

export function formatCurrency(amount: number | string): string {
  const n = typeof amount === 'string' ? parseFloat(amount) : amount
  if (isNaN(n)) return String(amount)
  const currency = localStorage.getItem('kolibri-currency') || 'RUB'
  const symbols: Record<string, string> = { RUB: '₽', USD: '$', EUR: '€' }
  return `${n.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 })} ${symbols[currency] || '₽'}`
}

export function formatNum(s: string | number): string {
  const n = typeof s === 'string' ? parseFloat(s) : s
  return isNaN(n) ? String(s) : n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
