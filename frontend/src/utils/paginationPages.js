/** Numéros de page + ellipses pour une barre de pagination compacte. */
export function buildPaginationItems(currentPage, totalPages) {
  if (totalPages <= 1) return [1]
  if (totalPages <= 9) {
    return Array.from({ length: totalPages }, (_, i) => i + 1)
  }

  const pages = new Set([1, totalPages, currentPage])
  for (const delta of [-2, -1, 1, 2]) {
    const n = currentPage + delta
    if (n >= 1 && n <= totalPages) pages.add(n)
  }

  const sorted = [...pages].sort((a, b) => a - b)
  const items = []
  for (let i = 0; i < sorted.length; i++) {
    if (i > 0 && sorted[i] - sorted[i - 1] > 1) items.push('…')
    items.push(sorted[i])
  }
  return items
}
