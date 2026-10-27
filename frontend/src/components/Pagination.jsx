import { buildPaginationItems } from '../utils/paginationPages'

/**
 * @param {number} page — page courante (1-based)
 * @param {number} totalPages
 * @param {(page: number) => void} onPageChange
 * @param {number} [totalItems]
 * @param {number} [pageSize]
 * @param {string} [className]
 * @param {string} [activeClassName]
 */
export default function Pagination({
  page,
  totalPages: totalPagesProp,
  onPageChange,
  totalItems,
  pageSize,
  className = '',
  activeClassName = '',
}) {
  const computedFromCount =
    totalItems != null && pageSize != null && pageSize > 0
      ? Math.max(1, Math.ceil(totalItems / pageSize))
      : null

  const totalPages = Math.max(
    totalPagesProp || 1,
    computedFromCount || 1,
  )

  if (totalPages <= 1) return null

  const currentPage = Math.min(Math.max(1, page), totalPages)
  const items = buildPaginationItems(currentPage, totalPages)
  const activeNumClass = activeClassName || 'pagination-num--active'

  let rangeLabel = null
  if (totalItems != null && pageSize != null && totalItems > 0) {
    const from = (currentPage - 1) * pageSize + 1
    const to = Math.min(currentPage * pageSize, totalItems)
    rangeLabel = `${from}–${to} sur ${totalItems}`
  }

  const goTo = (next) => {
    const n = typeof next === 'number' ? next : parseInt(next, 10)
    if (!Number.isFinite(n)) return
    onPageChange(Math.min(totalPages, Math.max(1, n)))
  }

  return (
    <nav className={`pagination ${className}`.trim()} aria-label="Pagination">
      <button
        type="button"
        className="pagination-btn"
        onClick={() => goTo(currentPage - 1)}
        disabled={currentPage === 1}
        aria-label="Page précédente"
      >
        <i className="bi bi-chevron-left" aria-hidden /> Précédent
      </button>

      <div className="pagination-pages" role="group" aria-label="Numéros de page">
        {items.map((item, idx) =>
          item === '…' ? (
            <span key={`ellipsis-${idx}`} className="pagination-ellipsis" aria-hidden>
              …
            </span>
          ) : (
            <button
              key={item}
              type="button"
              className={`pagination-btn pagination-num ${item === currentPage ? activeNumClass : ''}`}
              onClick={() => goTo(item)}
              aria-label={`Page ${item}`}
              aria-current={item === currentPage ? 'page' : undefined}
            >
              {item}
            </button>
          ),
        )}
      </div>

      {rangeLabel && <span className="pagination-summary">{rangeLabel}</span>}

      <button
        type="button"
        className="pagination-btn"
        onClick={() => goTo(currentPage + 1)}
        disabled={currentPage === totalPages}
        aria-label="Page suivante"
      >
        Suivant <i className="bi bi-chevron-right" aria-hidden />
      </button>
    </nav>
  )
}
