/**
 * Вспомогательные функции форматирования.
 */

/**
 * Форматировать дату в читаемый вид (DD.MM.YYYY HH:MM).
 */
export function formatDate(dateStr) {
  if (!dateStr) return '—'
  // Парсим формат CRM: "DD.MM.YYYY HH:MM:SS" или "DD.MM.YYYY"
  const dmyMatch = dateStr.match(/^(\d{2})\.(\d{2})\.(\d{4})(?:\s(\d{2}):(\d{2}))?/)
  if (dmyMatch) {
    const [, d, m, y, hh, mm] = dmyMatch
    const label = `${d}.${m}.${y}`
    return hh ? `${label} ${hh}:${mm}` : label
  }
  // ISO или другие форматы — стандартный парсинг
  const dt = new Date(dateStr)
  if (isNaN(dt)) return dateStr
  return dt.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

/**
 * Форматировать сумму в рублях.
 */
export function formatMoney(amount) {
  if (amount === null || amount === undefined) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0
  }).format(amount)
}
