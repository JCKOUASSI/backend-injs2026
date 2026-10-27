/** Minutes entre deux horaires « HH:MM[:SS] ». */
export function minutesEntreHeures(debut, fin) {
  if (!debut || !fin) return 0
  const [dh, dm, ds = 0] = debut.split(':').map(Number)
  const [fh, fm, fs = 0] = fin.split(':').map(Number)
  const start = dh * 60 + dm + ds / 60
  const end = fh * 60 + fm + fs / 60
  return Math.max(0, end - start)
}

/** Somme des créneaux planifiés de toutes les séances (heures). */
export function sommeSeancesHeures(sessions) {
  if (!sessions?.length) return null
  const totalMin = sessions.reduce((sum, s) => {
    const debut = s.heure_debut ?? s.heure_debut_prevue
    const fin = s.heure_fin ?? s.heure_fin_prevue
    return sum + minutesEntreHeures(debut, fin)
  }, 0)
  if (totalMin <= 0) return null
  return Math.round((totalMin / 60) * 100) / 100
}

/** Libellé court du numéro de séance dans la journée (ex. « n°1 »). */
export function sessionNumeroLabel(session) {
  const n = session?.numero
  if (n == null || n === '') return '—'
  return `n°${n}`
}

/** Libellé complet séance : numéro + intitulé. */
export function sessionDisplayLabel(session) {
  const num = sessionNumeroLabel(session)
  const title = (session?.intitule || '').trim()
  if (title && num !== '—') return `${num} — ${title}`
  if (title) return title
  return num !== '—' ? `Séance ${num}` : 'Séance'
}

/** Prochain numéro disponible pour une date (séances du même module). */
export function nextSessionNumeroForDate(sessions, dateJournee) {
  if (!dateJournee) return 1
  const sameDay = (sessions || []).filter(s => s.date === dateJournee)
  if (!sameDay.length) return 1
  return Math.max(...sameDay.map(s => Number(s.numero) || 0)) + 1
}

/** Libellé « 28h » ou « 28.5h » pour affichage. */
export function fmtHeuresLabel(heures) {
  if (heures == null || heures <= 0) return null
  const n = Number(heures)
  if (Number.isNaN(n)) return null
  return Number.isInteger(n) || Math.abs(n - Math.round(n)) < 0.01
    ? `${Math.round(n)}h`
    : `${parseFloat(n.toFixed(1))}h`
}

/** Durée planifiée d'une séance (heures). */
export function sessionDureeHeures(session) {
  const debut = session?.heure_debut ?? session?.heure_debut_prevue
  const fin = session?.heure_fin ?? session?.heure_fin_prevue
  const min = minutesEntreHeures(debut, fin)
  if (min <= 0) return null
  return Math.round((min / 60) * 100) / 100
}

/** Écart objectif contractuel − total EDT planifié (positif = heures manquantes). */
export function ecartEdtHeures(objectif, planifie) {
  if (objectif == null || planifie == null) return null
  const ecart = Number(objectif) - Number(planifie)
  if (Number.isNaN(ecart)) return null
  return Math.round(ecart * 100) / 100
}

/** Message « EDT planifié : 28h / 30h — il manque 2h » (durées variables par séance). */
export function fmtEdtVsObjectif(objectif, planifie) {
  if (!objectif || planifie == null) return null
  const plan = fmtHeuresLabel(planifie)
  const obj = fmtHeuresLabel(objectif)
  const ecart = ecartEdtHeures(objectif, planifie)
  if (ecart == null) return null
  if (Math.abs(ecart) < 0.01) {
    return `EDT planifié : ${plan} / ${obj} — objectif atteint`
  }
  if (ecart > 0) {
    return `EDT planifié : ${plan} / ${obj} — il manque ${fmtHeuresLabel(ecart)}`
  }
  return `EDT planifié : ${plan} / ${obj} — excédent de ${fmtHeuresLabel(Math.abs(ecart))}`
}
