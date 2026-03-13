/**
 * Вспомогательные функции форматирования.
 */

/**
 * Форматировать дату в читаемый вид (DD.MM.YYYY HH:MM).
 */
export function formatDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  if (isNaN(d)) return dateStr
  return d.toLocaleString('ru-RU', {
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
