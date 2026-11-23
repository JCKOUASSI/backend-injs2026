/** Normalise une réponse API paginée (objet ou tableau legacy). */
export function parsePaginatedResponse(data, pageSize = 50) {
  if (Array.isArray(data)) {
    const results = data
    return {
      results,
      count: results.length,
      totalPages: 1,
    }
  }
  const results = data?.results ?? []
  const count = data?.count ?? results.length
  const totalPages = data?.total_pages ?? Math.max(1, Math.ceil(count / pageSize) || 1)
  return { results, count, totalPages }
}
