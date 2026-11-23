import { safeLocalStorage } from './safeStorage'
const STORAGE_KEY = 'finance_period'
const STORAGE_FILTERS_KEY = 'finance_filters'

export const FINANCE_PERIOD_PRESETS = [
  { id: 'mois', label: 'Ce mois' },
  { id: 'trimestre', label: 'Trimestre' },
  { id: 'annee', label: 'Cette année' },
  { id: 'tout', label: 'Tout' },
  { id: 'custom', label: 'Personnalisé' },
]

export const TRIMESTRE_OPTIONS = [
  { q: 1, label: 'T1' },
  { q: 2, label: 'T2' },
  { q: 3, label: 'T3' },
  { q: 4, label: 'T4' },
]

export const defaultFinancePeriod = () => {
  const now = new Date()
  const mois = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  return {
    preset: 'mois',
    mois,
    annee: String(now.getFullYear()),
    trimestreAnnee: String(now.getFullYear()),
    trimestreQ: Math.floor(now.getMonth() / 3) + 1,
    trimestre: currentTrimestreKey(now),
    dateDebut: '',
    dateFin: '',
  }
}

export const currentTrimestreKey = (d = new Date()) => {
  const q = Math.floor(d.getMonth() / 3) + 1
  return `${d.getFullYear()}-Q${q}`
}

export const trimestreKeyFromParts = (year, q) => `${year}-Q${q}`

export const parseTrimestreKey = (key) => {
  if (!key || !key.includes('-Q')) return null
  const [y, q] = key.toUpperCase().split('-Q')
  return { year: String(y), q: Number(q) }
}

export const defaultFinanceFilters = () => ({})

export const loadFinanceFilters = () => {
  try {
    const raw = sessionStorage.getItem(STORAGE_FILTERS_KEY)
    if (raw) return { ...defaultFinanceFilters(), ...JSON.parse(raw) }
  } catch {
    /* ignore */
  }
  return defaultFinanceFilters()
}

export const saveFinanceFilters = (filters) => {
  try {
    sessionStorage.setItem(STORAGE_FILTERS_KEY, JSON.stringify(filters))
  } catch {
    /* ignore */
  }
}

/** Période partagée (dashboard, finance, stats) — sessionStorage, pas l’URL (évite un ?preset= obsolète). */
export const resolveFinancePeriod = () => loadFinancePeriod()

export const loadFinancePeriod = () => {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      const merged = { ...defaultFinancePeriod(), ...parsed }
      if (merged.preset === 'trimestre' && merged.trimestre && !merged.trimestreAnnee) {
        const parts = parseTrimestreKey(merged.trimestre)
        if (parts) {
          merged.trimestreAnnee = parts.year
          merged.trimestreQ = parts.q
        }
      }
      if (merged.trimestreAnnee && merged.trimestreQ) {
        merged.trimestre = trimestreKeyFromParts(merged.trimestreAnnee, merged.trimestreQ)
      }
      return merged
    }
  } catch {
    /* ignore */
  }
  return defaultFinancePeriod()
}

export const saveFinancePeriod = (period) => {
  try {
    const toSave = { ...period }
    if (toSave.trimestreAnnee && toSave.trimestreQ) {
      toSave.trimestre = trimestreKeyFromParts(toSave.trimestreAnnee, toSave.trimestreQ)
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
  } catch {
    /* ignore */
  }
}

export const buildFinancePeriodQuery = (period) => {
  const p = new URLSearchParams()
  if (!period?.preset) return p
  p.set('preset', period.preset)
  if (period.preset === 'mois' && period.mois) p.set('mois', period.mois)
  if (period.preset === 'annee' && period.annee) p.set('annee', period.annee)
  if (period.preset === 'trimestre') {
    const tk = period.trimestre
      || (period.trimestreAnnee && period.trimestreQ
        ? trimestreKeyFromParts(period.trimestreAnnee, period.trimestreQ)
        : '')
    if (tk) p.set('trimestre', tk)
  }
  if (period.preset === 'custom') {
    if (period.dateDebut && period.dateFin) {
      p.set('date_debut', period.dateDebut)
      p.set('date_fin', period.dateFin)
    } else {
      // Si dates manquantes, ne pas envoyer preset=custom, utiliser tout
      p.delete('preset')
      p.set('preset', 'tout')
    }
  }
  return p
}

/** Clé stable pour détecter un changement de période (query string API). */
export const financePeriodKey = (period) => buildFinancePeriodQuery(period).toString()

export const appendPeriodToSearchParams = (params, period) => {
  const q = buildFinancePeriodQuery(period)
  q.forEach((value, key) => params.set(key, value))
}

/** Bornes inclusives de la période sélectionnée (null si « Tout »). */
export const getPeriodBounds = (period) => {
  if (!period?.preset || period.preset === 'tout') return null
  const today = new Date()
  const yNow = today.getFullYear()
  const pad = (n) => String(n).padStart(2, '0')

  if (period.preset === 'mois' && period.mois) {
    const [y, m] = period.mois.split('-').map(Number)
    if (!y || !m) return null
    const last = new Date(y, m, 0).getDate()
    return {
      dateDebut: `${y}-${pad(m)}-01`,
      dateFin: `${y}-${pad(m)}-${pad(last)}`,
    }
  }
  if (period.preset === 'annee' && period.annee) {
    const y = Number(period.annee)
    if (!y) return null
    return { dateDebut: `${y}-01-01`, dateFin: `${y}-12-31` }
  }
  if (period.preset === 'trimestre') {
    const y = Number(period.trimestreAnnee || yNow)
    const q = Number(period.trimestreQ || Math.floor(today.getMonth() / 3) + 1)
    if (!y || q < 1 || q > 4) return null
    const m0 = (q - 1) * 3 + 1
    const m1 = m0 + 2
    const last = new Date(y, m1, 0).getDate()
    return {
      dateDebut: `${y}-${pad(m0)}-01`,
      dateFin: `${y}-${pad(m1)}-${pad(last)}`,
    }
  }
  if (period.preset === 'custom' && period.dateDebut && period.dateFin) {
    return { dateDebut: period.dateDebut, dateFin: period.dateFin }
  }
  return null
}

/** Vrai si le début de période est strictement après aujourd'hui. */
export const isPeriodWhollyFuture = (period) => {
  const bounds = getPeriodBounds(period)
  if (!bounds?.dateDebut) return false
  const start = bounds.dateDebut.slice(0, 10)
  const today = new Date().toISOString().slice(0, 10)
  return start > today
}

export const currentTrimestreParts = (d = new Date()) => ({
  annee: String(d.getFullYear()),
  q: Math.floor(d.getMonth() / 3) + 1,
})

export const buildFinanceQuery = (period) => buildFinancePeriodQuery(period)

export const financePeriodQueryString = (period) => {
  const q = buildFinanceQuery(period)
  const s = q.toString()
  return s ? `?${s}` : ''
}

export const FINANCE_QUERY_STORAGE_KEY = 'finance_list_query'
export const FINANCE_EXPORT_MONTANTS_KEY = 'finance_export_afficher_montants'

export const loadFinanceExportMontants = (defaultValue = true) => {
  try {
    const v = safeLocalStorage.getItem(FINANCE_EXPORT_MONTANTS_KEY)
    if (v === null) return defaultValue
    return v === '1' || v === 'true'
  } catch {
    return defaultValue
  }
}

export const saveFinanceExportMontants = (value) => {
  try {
    safeLocalStorage.setItem(FINANCE_EXPORT_MONTANTS_KEY, value ? '1' : '0')
  } catch {
    /* ignore */
  }
}

export const buildFinanceExportQuery = (period, afficherMontants = true) => {
  const q = buildFinanceQuery(period)
  q.set('afficher_montants', afficherMontants ? '1' : '0')
  return q
}

/** Lit période + filtres finance depuis l’URL (?preset=…). */
export const readFinanceStateFromSearchParams = (searchParams) => {
  const preset = searchParams.get('preset')
  if (!preset) return null

  const period = { ...defaultFinancePeriod(), preset }
  if (preset === 'mois' && searchParams.get('mois')) period.mois = searchParams.get('mois')
  if (preset === 'annee' && searchParams.get('annee')) period.annee = searchParams.get('annee')
  if (preset === 'trimestre') {
    const tk = searchParams.get('trimestre')
    if (tk) {
      period.trimestre = tk
      const parts = parseTrimestreKey(tk)
      if (parts) {
        period.trimestreAnnee = parts.year
        period.trimestreQ = parts.q
      }
    }
  }
  if (preset === 'custom') {
    period.dateDebut = searchParams.get('date_debut') || ''
    period.dateFin = searchParams.get('date_fin') || ''
  }

  return { period, filters: defaultFinanceFilters() }
}

/** Paramètres URL liste finance (période + filtres + pagination / onglets optionnels). */
export const buildFinanceListSearchParams = (period, _filters, extras = {}) => {
  const p = buildFinanceQuery(period)
  if (extras.page > 1) p.set('page', String(extras.page))
  if (extras.search) p.set('search', extras.search)
  if (extras.rankTab && extras.rankTab !== 'realise') p.set('rank_tab', extras.rankTab)
  return p
}

/** Navigation entre pages finance en gardant la même période / filtres. */
export const financeNavHref = (pathname) => {
  let qs = ''
  try {
    qs = sessionStorage.getItem(FINANCE_QUERY_STORAGE_KEY) || ''
  } catch {
    /* ignore */
  }
  return qs ? `${pathname}?${qs}` : pathname
}
