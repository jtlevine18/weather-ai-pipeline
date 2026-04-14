import { REGION } from '../regionConfig'

// Shared date/time formatting helpers — pages previously duplicated these.

export function formatTime(dateStr: string | undefined): string {
  if (!dateStr) return '--'
  try {
    return new Date(dateStr).toLocaleString(REGION.locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
    })
  } catch {
    return dateStr
  }
}

export function formatTimeShort(dateStr: string | undefined): string {
  if (!dateStr) return '--'
  try {
    return new Date(dateStr).toLocaleString(REGION.locale, {
      dateStyle: 'short',
      timeStyle: 'short',
    })
  } catch {
    return dateStr
  }
}
