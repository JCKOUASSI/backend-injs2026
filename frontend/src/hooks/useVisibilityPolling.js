import { useEffect, useRef } from 'react'

/**
 * Exécute callback à intervalle régulier uniquement quand l'onglet est visible.
 * Rafraîchit aussi au retour sur l'onglet (visibilitychange).
 */
export function useVisibilityPolling(callback, intervalMs, enabled = true) {
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  useEffect(() => {
    if (!enabled || !intervalMs) return

    const tick = () => {
      if (document.visibilityState === 'visible') {
        callbackRef.current(true)
      }
    }

    const timer = setInterval(tick, intervalMs)
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        callbackRef.current(true)
      }
    }
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [intervalMs, enabled])
}
