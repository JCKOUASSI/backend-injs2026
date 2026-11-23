/**
 * Formate une date en JJ/MM/AAAA
 * Accepte : string ISO (2025-09-01 ou 2025-09-01T08:00:00Z), Date object
 */
export function formatDate(d) {
  if (!d) return '-'
  const s = String(d)
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
    const [y, m, day] = s.slice(0, 10).split('-')
    return `${day}/${m}/${y}`
  }
  const dt = new Date(d)
  if (isNaN(dt)) return String(d)
  const day = String(dt.getDate()).padStart(2, '0')
  const month = String(dt.getMonth() + 1).padStart(2, '0')
  const year = dt.getFullYear()
  return `${day}/${month}/${year}`
}

/**
 * Formate une datetime en JJ/MM/AAAA HH:MM
 */
export function formatDateTime(d) {
  if (!d) return '-'
  const dt = new Date(d)
  if (isNaN(dt)) return String(d)
  const day = String(dt.getDate()).padStart(2, '0')
  const month = String(dt.getMonth() + 1).padStart(2, '0')
  const year = dt.getFullYear()
  const h = String(dt.getHours()).padStart(2, '0')
  const m = String(dt.getMinutes()).padStart(2, '0')
  return `${day}/${month}/${year} ${h}:${m}`
}
