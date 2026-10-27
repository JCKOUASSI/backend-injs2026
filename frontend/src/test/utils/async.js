/** Attend que les promesses en file (micro+tâches) soient purgées. */
export function flushPromises(ticks = 1) {
  return Array.from({ length: ticks }).reduce(
    (p) => p.then(() => new Promise((resolve) => setTimeout(resolve, 0))),
    Promise.resolve(),
  )
}

/** Attend un nombre de ms (utile pour les timeouts, à défaut de fake timers). */
export function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** Construit une réponse fetch minimaliste pour les tests de services/api. */
export function fetchResponse(body, { status = 200, headers = {} } = {}) {
  const text = typeof body === 'string' ? body : JSON.stringify(body)
  const headersMap = new Headers(headers)
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : `HTTP ${status}`,
    headers: headersMap,
    async text() {
      return text
    },
    async json() {
      return JSON.parse(text)
    },
    clone() {
      return fetchResponse(body, { status, headers })
    },
    async blob() {
      return new Blob([text], { type: headersMap.get('Content-Type') || 'application/octet-stream' })
    },
  }
}
