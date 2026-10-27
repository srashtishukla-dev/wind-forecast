export function formatTime(value, options = {}) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, {
    timeZone: 'UTC',
    month: options.month || 'short',
    day: '2-digit',
    year: 'numeric',
    hour: options.hour || '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}
