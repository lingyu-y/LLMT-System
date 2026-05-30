const BEIJING_TIME_ZONE = 'Asia/Shanghai'
const ISO_WITHOUT_TIMEZONE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/
const HAS_TIMEZONE = /(?:Z|[+-]\d{2}:?\d{2})$/i

const normalizeBackendTime = (value: string) => {
  const trimmed = value.trim()

  // Some backend code uses datetime.utcnow().isoformat(), which produces an ISO
  // string without timezone. Treat that shape as UTC so Beijing time is correct.
  if (ISO_WITHOUT_TIMEZONE.test(trimmed) && !HAS_TIMEZONE.test(trimmed)) return `${trimmed}Z`

  return trimmed
}

export const parseBackendTime = (value?: string | null) => {
  if (!value) return undefined
  const date = new Date(normalizeBackendTime(value))
  return Number.isNaN(date.getTime()) ? undefined : date
}

export const formatBeijingDate = (value?: string | null, fallback = '-') => {
  const date = parseBackendTime(value)
  if (!date) return value?.slice(0, 10) || fallback

  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: BEIJING_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date).replace(/\//g, '-')
}

export const formatBeijingDateTime = (value?: string | null, fallback = '-') => {
  const date = parseBackendTime(value)
  if (!date) return value || fallback

  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: BEIJING_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date).replace(/\//g, '-')
}

export const formatBeijingTime = (value?: string | null, fallback = '') => {
  const date = parseBackendTime(value)
  if (!date) return fallback

  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: BEIJING_TIME_ZONE,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

export const formatBeijingMonthDayTime = (value?: string | null, fallback = '') => {
  const date = parseBackendTime(value)
  if (!date) return fallback

  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: BEIJING_TIME_ZONE,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date).replace(/\//g, '-')
}

export const relativeFromBeijingNow = (value?: string | null) => {
  const date = parseBackendTime(value)
  if (!date) return ''

  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000))
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  return `${Math.floor(minutes / 60)}小时前`
}
