import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { appendPeriodToSearchParams, financePeriodKey } from '../utils/financePeriod'

export const STATS_META_QUERY_KEY = 'stats-meta'

const META_SECTIONS = 'formations_liste,secretariats_liste,filtre_actif'

async function fetchStatsMeta({ formationId, secretariatId, period }) {
  const params = new URLSearchParams()
  params.set('sections', META_SECTIONS)
  if (formationId) params.set('formation_id', formationId)
  if (secretariatId) params.set('secretariat_id', secretariatId)
  appendPeriodToSearchParams(params, period)
  const res = await api.get(`/statistiques/?${params}`)
  const d = res.data || {}
  return {
    formations_liste: d.formations_liste,
    secretariats_liste: d.secretariats_liste,
    filtre_actif: d.filtre_actif,
  }
}

/** Méta listes Statistiques (formations, secrétariats, filtre) — une fetch partagée. */
export function useStatsMeta({ formationId, secretariatId, period, enabled = true }) {
  const periodKey = financePeriodKey(period)
  return useQuery({
    queryKey: [STATS_META_QUERY_KEY, formationId || '', secretariatId || '', periodKey],
    queryFn: () => fetchStatsMeta({ formationId, secretariatId, period }),
    staleTime: 10 * 60 * 1000,
    enabled,
  })
}
