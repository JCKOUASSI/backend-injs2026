import { useState, useEffect, useCallback } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import FinancePeriodFilter from '../components/FinancePeriodFilter'
import { canFilterDashboardBySecretariat, isSecretariatScopedRole } from '../utils/roles'
import { formatDate } from '../utils/dates'
import {
  appendPeriodToSearchParams,
  resolveFinancePeriod,
  saveFinancePeriod,
  isPeriodWhollyFuture,
  financePeriodKey,
} from '../utils/financePeriod'
import {
  buildDashboardSearchParams,
  LIST_STORAGE_KEYS,
  readDashboardFilters,
} from '../utils/listFilters'
import { usePersistedListQuery } from '../hooks/usePersistedListQuery'
import { useListNavigationState } from '../hooks/useListReturn'
import { useVisibilityPolling } from '../hooks/useVisibilityPolling'
import { useSecretariats } from '../hooks/useSecretariats'

const DASHBOARD_POLL_MS = 3 * 60 * 1000

export default function Dashboard() {
  const { user } = useAuth()
  const listNavState = useListNavigationState()
  const [searchParams] = useSearchParams()
  const initialDash = readDashboardFilters(searchParams)
  const isDirection = String(user?.role || '').trim().toUpperCase() === 'DIRECTION'
  const canFilterBySecretariat = canFilterDashboardBySecretariat(user)
  const isSecretariatScoped = isSecretariatScopedRole(user?.role)
  const [stats, setStats] = useState(null)
  const [formationsEnCours, setFormationsEnCours] = useState([])
  const { data: secretariats = [], isLoading: loadingSecretariats } = useSecretariats({ enabled: canFilterBySecretariat })
  const [selectedSecretariatId, setSelectedSecretariatId] = useState(initialDash.secretariat)
  const [presencePeriod, setPresencePeriod] = useState(initialDash.presence_period)
  const [referenceDate, setReferenceDate] = useState(initialDash.reference_date)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [vhPeriod, setVhPeriod] = useState(() => resolveFinancePeriod())
  const [appliedVhPeriod, setAppliedVhPeriod] = useState(() => resolveFinancePeriod())
  const appliedPeriodKey = financePeriodKey(appliedVhPeriod)

  usePersistedListQuery(
    LIST_STORAGE_KEYS.dashboard,
    () => buildDashboardSearchParams({
      secretariat: selectedSecretariatId,
      presence_period: presencePeriod,
      reference_date: referenceDate,
    }, appliedVhPeriod),
    [selectedSecretariatId, presencePeriod, referenceDate, appliedPeriodKey],
  )

  // Le hook useVisibilityPolling invoque cette fonction avec un booléen
  // positionnel (silent), convention identique à
  // ModuleDetail.refreshPresences(silent) — un objet { silent } rendait le
  // rafraîchissement de fond bruyant (§10.16, corrigé au LOT 43).
  const loadDashboardData = useCallback(async (silent = false) => {
    const statsParams = new URLSearchParams()
    if (selectedSecretariatId) statsParams.set('secretariat', selectedSecretariatId)
    if (referenceDate) statsParams.set('reference_date', referenceDate)
    appendPeriodToSearchParams(statsParams, appliedVhPeriod)
    const statsQuery = statsParams.toString()
    const listParams = new URLSearchParams()
    listParams.set('statut', 'EN_COURS')
    listParams.set('page_size', '10')
    if (selectedSecretariatId) listParams.set('secretariat', selectedSecretariatId)
    const todayStr = new Date().toISOString().slice(0, 10)
    if (presencePeriod === 'jour' && referenceDate && referenceDate !== todayStr) {
      listParams.set('date_mode', 'date')
      listParams.set('date', referenceDate)
    } else {
      listParams.set('seance_en_cours', 'true')
    }
    const listQuery = listParams.toString()
    const settled = await Promise.allSettled([
      api.get(`/formations/stats/${statsQuery ? `?${statsQuery}` : ''}`),
      api.get(`/formations/list/?${listQuery}`),
    ])
    const [statsRes, enCoursRes] = settled

    const unwrap = (res, fallback) => {
      if (res.status !== 'fulfilled') return fallback
      const d = res.value.data
      return Array.isArray(d) ? d : (d.results || fallback)
    }

    if (statsRes.status === 'fulfilled') setStats(statsRes.value.data)
    setFormationsEnCours(unwrap(enCoursRes, []))

    // Échec total = toutes les requêtes ont échoué (et non un nombre « 3 »
    // codé en dur, inatteignable avec 2 requêtes — écart §10.6 corrigé).
    const failures = settled.filter(r => r.status === 'rejected')
    if (!silent) {
      if (failures.length === settled.length) {
        setError('Erreur lors du chargement des données')
      } else if (failures.length > 0) {
        setError('Certaines données n\'ont pas pu être chargées')
      } else {
        setError('')
      }
      setLoading(false)
    }
    // presencePeriod doit figurer ici : sa valeur pilote la construction de
    // listQuery (date_mode/date vs seance_en_cours). Sans elle, un changement
    // de période rappelait une closure périmée (bug §10.5, corrigé au LOT 4).
  }, [selectedSecretariatId, referenceDate, presencePeriod, appliedVhPeriod])

  useEffect(() => {
    loadDashboardData()
  }, [selectedSecretariatId, referenceDate, presencePeriod, appliedPeriodKey, loadDashboardData])

  useVisibilityPolling(loadDashboardData, DASHBOARD_POLL_MS, true)

  const handleApplyVhPeriod = useCallback((periodOverride) => {
    const p = periodOverride ?? vhPeriod
    saveFinancePeriod(p)
    // Ne pas appeler setVhPeriod ici car onChange l'a déjà fait si periodOverride vient du filter
    // Mais si on appelle handleApplyVhPeriod sans argument (bouton Appliquer), il faut le faire
    if (!periodOverride) {
      setVhPeriod(p)
    }
    setAppliedVhPeriod({ ...p })
  }, [vhPeriod])

  const selectedSecretariat = secretariats.find((s) => String(s.id) === String(selectedSecretariatId))
  const fmtTime = (ts) => ts ? new Date(ts).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : '—'
  // Étiquette du jour de référence pour le sous-titre : une référence vide ou
  // invalide (champ « Jour spécifique » entièrement vidé) retombe sur la date
  // du jour au lieu d'afficher « Invalid Date » (§10.17, corrigé au LOT 43).
  const referenceDateParsed = new Date(`${referenceDate || ''}T00:00:00`)
  const referenceDateLabel = Number.isNaN(referenceDateParsed.getTime())
    ? new Date().toLocaleDateString('fr-FR')
    : referenceDateParsed.toLocaleDateString('fr-FR')
  const prochainesSeances = stats?.prochaines_seances || []
  const periodLabels = {
    jour: 'Jour',
    semaine: 'Semaine',
    mois: 'Mois',
    annee: 'Année',
  }
  const periodStats = {
    jour: {
      attendus: stats?.total_attendus_jour || 0,
      presents: stats?.presents_aujourd_hui || 0,
      taux: stats?.taux_presence || 0,
      auditeursPresents: stats?.auditeurs_presents_jour || 0,
      auditeursAttendus: stats?.auditeurs_attendus_jour || 0,
      formateursPresents: stats?.formateurs_presents_jour || 0,
      formateursAttendus: stats?.formateurs_attendus_jour || 0,
    },
    semaine: {
      attendus: stats?.total_attendus_semaine || 0,
      presents: stats?.presents_semaine || 0,
      taux: stats?.taux_presence_semaine || 0,
    },
    mois: {
      attendus: stats?.total_attendus_mois || 0,
      presents: stats?.presents_mois || 0,
      taux: stats?.taux_presence_mois || 0,
    },
    annee: {
      attendus: stats?.total_attendus_annee || 0,
      presents: stats?.presents_annee || 0,
      taux: stats?.taux_presence_annee || 0,
    },
  }
  const selectedPeriodStats = periodStats[presencePeriod] || periodStats.jour
  const selectedPeriodAbsence = Math.max(selectedPeriodStats.attendus - selectedPeriodStats.presents, 0)
  const selectedPeriodAbsenceRate = selectedPeriodStats.attendus > 0
    ? Number((100 - (selectedPeriodStats.taux || 0)).toFixed(1))
    : 0

  if (loading) return <div className="loading"><div className="spinner"></div></div>

  return (
    <div>
      {error && <div className="error-message">{error}</div>}
      {canFilterBySecretariat && (
        <div style={{ float: 'right', width: 250, marginLeft: '0.9rem', marginBottom: '0.9rem' }}>
          <div style={{ position: 'sticky', top: '1rem' }}>
            <div
              className="card"
              title="Restreindre les indicateurs du tableau de bord à un secrétariat, ou afficher la synthèse de tous les secrétariats."
            >
              <div className="card-header-bar">
                <span><i className="bi bi-building me-2"></i><strong>Secrétariats</strong></span>
              </div>
              <div className="card-body-flush" style={{ maxHeight: '56vh', overflowY: 'auto' }}>
                {loadingSecretariats ? (
                  <div className="text-center py-3 text-muted" style={{ fontSize: '0.88rem' }}>
                    Chargement...
                  </div>
                ) : (
                  <div style={{ padding: '0.6rem' }}>
                    <button
                      type="button"
                      onClick={() => setSelectedSecretariatId('')}
                      className={`btn btn-sm w-100 mb-2 ${selectedSecretariatId ? 'btn-outline-secondary' : 'btn-dfrc'}`}
                      style={{ textAlign: 'left' }}
                    >
                      <i className="bi bi-grid-3x3-gap me-2"></i>Tous les secrétariats
                    </button>
                    {secretariats.map((sec) => (
                      <button
                        key={sec.id}
                        type="button"
                        onClick={() => setSelectedSecretariatId(String(sec.id))}
                        className={`btn btn-sm w-100 mb-2 ${String(selectedSecretariatId) === String(sec.id) ? 'btn-dfrc' : 'btn-outline-secondary'}`}
                        style={{ textAlign: 'left' }}
                      >
                        <div style={{ fontWeight: 600, fontSize: '0.82rem' }}>{sec.nom}</div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div
              className="card"
              style={{ marginTop: '0.75rem' }}
              title="Choisir le jour de référence et la période (jour, semaine, mois, année) pour les blocs « Capacité » et le graphique de présences ci-dessous."
            >
              <div className="card-header-bar">
                <span><i className="bi bi-funnel-fill me-2"></i><strong>Filtre période</strong></span>
              </div>
              <div className="card-body-flush" style={{ padding: '0.65rem' }}>
                <label htmlFor="dashboard-reference-date" className="form-label" style={{ fontSize: '0.78rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                  Jour spécifique
                </label>
                <input
                  id="dashboard-reference-date"
                  type="date"
                  className="form-control form-control-sm"
                  value={referenceDate}
                  onChange={(e) => setReferenceDate(e.target.value)}
                  style={{ marginBottom: '0.65rem' }}
                />
                <div
                  role="group"
                  aria-label="Filtre de période dashboard"
                  style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}
                >
                  {[
                    { id: 'jour', label: 'Jour spécifique', icon: 'bi-calendar-day' },
                    { id: 'semaine', label: 'Semaine', icon: 'bi-calendar-week' },
                    { id: 'mois', label: 'Mois', icon: 'bi-calendar-month' },
                    { id: 'annee', label: 'Année', icon: 'bi-calendar3' },
                  ].map((opt) => (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setPresencePeriod(opt.id)}
                      className={`btn btn-sm text-start ${presencePeriod === opt.id ? 'btn-dfrc' : 'btn-outline-secondary'}`}
                      style={{ width: '100%' }}
                    >
                      <i className={`bi ${opt.icon} me-2`}></i>{opt.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Bienvenue ── */}
      <div style={{ marginBottom: '1.25rem' }}>
        <h4 style={{ fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.15rem' }}>
          Bonjour, {user?.first_name || user?.username} 👋
        </h4>
        <p style={{ color: '#94a3b8', fontSize: '0.9rem', margin: 0 }}>
          {new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          {canFilterBySecretariat && (
            <span style={{ marginLeft: '0.45rem' }}>
              • {selectedSecretariat ? `Vue: ${selectedSecretariat.nom}` : 'Vue: Tous les secrétariats'}
            </span>
          )}
          {isSecretariatScoped && user?.secretariat_nom && (
            <span style={{ marginLeft: '0.45rem' }}>
              • Secrétariat : {user.secretariat_nom}
            </span>
          )}
          <span style={{ marginLeft: '0.45rem' }}>
            • Référence: {referenceDateLabel}
          </span>
        </p>
      </div>

      <div className="finance-filter-panel" style={{ marginBottom: '1rem' }}>
        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#64748b', marginBottom: '0.5rem', letterSpacing: '0.04em' }}>
          PÉRIODE — VOLUME HORAIRE
        </div>
        <div className="finance-filter-panel-inner">
          <FinancePeriodFilter
            period={vhPeriod}
            onChange={setVhPeriod}
            onApply={handleApplyVhPeriod}
            applying={loading}
            embedded
            autoApplyOnSelect
          />
        </div>
        {isPeriodWhollyFuture(appliedVhPeriod) && (
          <div style={{
            marginTop: '0.65rem', padding: '0.55rem 0.75rem', borderRadius: 8,
            background: '#fffceb', border: '1px solid #fcdf4d', color: '#92660e', fontSize: '0.82rem',
          }}>
            <i className="bi bi-info-circle me-1"/>
            Cette période n&apos;a pas encore commencé — volume horaire réalisé à 0.
            <button
              type="button"
              className="btn btn-link btn-sm p-0 ms-1 align-baseline"
              style={{ fontSize: '0.82rem', verticalAlign: 'baseline' }}
              onClick={() => {
                const now = new Date()
                const next = {
                  ...appliedVhPeriod,
                  preset: 'mois',
                  mois: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`,
                }
                handleApplyVhPeriod(next)
              }}
            >
              Voir ce mois
            </button>
          </div>
        )}
        {stats?.periode?.label && (
          <div className="finance-period-badge">
            <i className="bi bi-calendar-check"></i>
            <div>
              <strong>{stats.periode.label}</strong>
              {stats.periode.periode_label && (
                <span className="ms-1">— {stats.periode.periode_label}</span>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="headline-kpis">
        <div
          className="headline-kpi-card headline-kpi-card-main"
          title="Nombre total de modules dans le périmètre actuel. Plusieurs modules peuvent appartenir à une même formation. Les sous-totaux indiquent combien sont démarrés, planifiés ou terminés."
        >
          <div className="headline-kpi-icon">
            <i className="bi bi-mortarboard-fill"></i>
          </div>
          <div>
            <div className="headline-kpi-topline">
              <span className="headline-kpi-value">{stats?.total_modules || 0}</span>
              <span className="headline-kpi-label">MODULES</span>
            </div>
            <div className="headline-kpi-subline">
              <span><i className="bi bi-play-circle-fill"></i> {stats?.modules_en_cours || 0} démarrés</span>
              <span><i className="bi bi-calendar2-check"></i> {stats?.modules_planifies || 0} planifiés</span>
              <span><i className="bi bi-check-circle-fill"></i> {stats?.modules_termines || 0} terminés</span>
            </div>
          </div>
        </div>
        <div
          className="headline-kpi-card headline-kpi-card-side headline-kpi-card-volume"
          title="Réalisé = somme des séances terminées. Prévu = somme des créneaux horaires planifiés des séances, par module."
        >
          <div className="headline-kpi-icon">
            <i className="bi bi-clock-history"></i>
          </div>
          <div>
            <div className="headline-kpi-value headline-kpi-value-compact">
              {stats?.volume_horaire_effectue_heures || 0}h / {stats?.volume_horaire_total_heures || 0}h
            </div>
            <div className="text-muted" style={{ fontWeight: 600, marginTop: '0.1rem' }}>
              effectué / prévu
            </div>
            <div className="headline-kpi-label headline-kpi-label-compact">VOLUME HORAIRE</div>
            <div className="headline-kpi-subline">
              <span><i className="bi bi-graph-up-arrow"></i> {stats?.volume_horaire_effectue_taux || 0}% effectué</span>
            </div>
          </div>
        </div>
        <div
          className="headline-kpi-card headline-kpi-card-side"
          title="Nombre total d’étudiants (fiches participants) pris en compte dans les statistiques pour le filtre actuel (secrétariat et période le cas échéant)."
        >
          <div className="headline-kpi-icon">
            <i className="bi bi-people-fill"></i>
          </div>
          <div>
            <div className="headline-kpi-value">{stats?.total_participants || 0}</div>
            <div className="headline-kpi-label">AUDITEURS</div>
          </div>
        </div>
      </div>

      {/* ── Capacité du jour ── */}
      <div style={{ marginBottom: '0.35rem', color: '#64748b', fontWeight: 700, fontSize: '0.82rem', letterSpacing: '0.06em' }}>
        CAPACITE - {periodLabels[presencePeriod].toUpperCase()}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem', marginBottom: '0.75rem' }}>
        {(presencePeriod === 'jour'
          ? [
              {
                label: 'Nombre Étudiants Présents/Attendus',
                value: `${selectedPeriodStats.auditeursPresents || 0}/${selectedPeriodStats.auditeursAttendus || 0}`,
                icon: 'bi-people-fill',
                color: '#2b6cb0',
                bg: 'rgba(43,108,178,0.1)',
                tooltip: 'Étudiants déjà pointés présents ce jour (ou jour de référence), par rapport au nombre attendu aux séances concernées.',
              },
              {
                label: 'Nombre Enseignants Présents/Attendus',
                value: `${selectedPeriodStats.formateursPresents || 0}/${selectedPeriodStats.formateursAttendus || 0}`,
                icon: 'bi-person-badge-fill',
                color: '#11407d',
                bg: 'rgba(17,64,125,0.1)',
                tooltip: 'Enseignants pointés présents ce jour par rapport au nombre attendu sur les séances du jour.',
              },
              {
                label: 'Séances planifiées',
                value: stats?.seances_planifiees_aujourd_hui || 0,
                icon: 'bi-calendar-event',
                color: '#c08821',
                bg: 'rgba(245,177,0,0.1)',
                tooltip: 'Nombre de séances prévues à la date affichée dans le filtre « Jour spécifique ».',
              },
            ]
          : [
              {
                label: `Présents / Attendus (${periodLabels[presencePeriod].toLowerCase()})`,
                value: `${selectedPeriodStats.presents || 0}/${selectedPeriodStats.attendus || 0}`,
                icon: 'bi-people-fill',
                color: '#2b6cb0',
                bg: 'rgba(43,108,178,0.1)',
                tooltip: 'Personnes (étudiants et enseignants) pointées présentes sur la période choisie, par rapport au nombre attendu.',
              },
              {
                label: `Taux de présence (${periodLabels[presencePeriod].toLowerCase()})`,
                value: `${(selectedPeriodStats.taux || 0).toFixed(1)}%`,
                icon: 'bi-graph-up-arrow',
                color: '#11407d',
                bg: 'rgba(17,64,125,0.1)',
                tooltip: 'Pourcentage de présence calculé sur la période sélectionnée (présents / attendus).',
              },
              {
                label: `Absents (${periodLabels[presencePeriod].toLowerCase()})`,
                value: `${selectedPeriodAbsence} (${selectedPeriodAbsenceRate.toFixed(1)}%)`,
                icon: 'bi-person-x-fill',
                color: '#c08821',
                bg: 'rgba(245,177,0,0.1)',
                tooltip: 'Nombre de personnes absentes et part d’absents sur la période (attendus − présents).',
              },
            ]).map(({ label, value, icon, color, bg, tooltip }) => (
          <div key={label} className="stat-card" title={tooltip}>
            <div className="stat-body">
              <div className="stat-icon" style={{ background: bg, color }}><i className={`bi ${icon}`}></i></div>
              <div>
                <div className="stat-value" style={{ color }}>{value}</div>
                <div className="stat-label">{label}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Exécution live ── */}
      <div style={{ marginBottom: '0.35rem', color: '#64748b', fontWeight: 700, fontSize: '0.82rem', letterSpacing: '0.06em' }}>
        EXECUTION LIVE
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.6rem', marginBottom: '0.75rem' }}>
        {[
          {
            label: 'Séances actives',
            value: stats?.seances_actives || 0,
            icon: 'bi-broadcast',
            color: '#805ad5',
            bg: 'rgba(128,90,213,0.1)',
            tooltip: 'Séances dont l’horaire est en cours ou qui ont été ouvertes pour badgeage sur la plage considérée.',
          },
          ...(isDirection
            ? []
            : [{
                label: 'Pointages du jour',
                value: stats?.pointages_aujourd_hui || 0,
                icon: 'bi-qr-code-scan',
                color: '#11407d',
                bg: 'rgba(17,64,125,0.1)',
                tooltip: 'Nombre total d’entrées ou sorties enregistrées par badgeage QR ce jour (tous rôles confondus).',
              }]),
          {
            label: 'En salle maintenant',
            value: stats?.en_salle_now || 0,
            icon: 'bi-person-check-fill',
            color: '#2b6cb0',
            bg: 'rgba(43,108,178,0.1)',
            tooltip: 'Personnes actuellement considérées comme présentes en salle (entrée pointée, sortie non encore enregistrée).',
          },
        ].map(({ label, value, icon, color, bg, tooltip }) => (
          <div key={label} className="stat-card" title={tooltip}>
            <div className="stat-body">
              <div className="stat-icon" style={{ background: bg, color }}><i className={`bi ${icon}`}></i></div>
              <div>
                <div className="stat-value" style={{ color }}>{value}</div>
                <div className="stat-label">{label}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Qualité opérationnelle ── */}
      <div style={{ marginBottom: '0.35rem', color: '#64748b', fontWeight: 700, fontSize: '0.82rem', letterSpacing: '0.06em' }}>
        QUALITE OPERATIONNELLE
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '0.9rem', marginBottom: '0.9rem' }}>
        {[
          {
            label: 'Retard moyen (jour)',
            value: `${(stats?.retard_moyen_minutes || 0).toFixed(1)} min`,
            icon: 'bi-alarm',
            color: '#d9a106',
            bg: 'rgba(217,161,6,0.1)',
            tooltip: 'Retard moyen (en minutes) entre l’heure prévue de début de séance et le premier pointage d’entrée, sur la journée de référence.',
          },
        ].map(({ label, value, icon, color, bg, tooltip }) => (
          <div key={label} className="stat-card" title={tooltip}>
            <div className="stat-body">
              <div className="stat-icon" style={{ background: bg, color }}><i className={`bi ${icon}`}></i></div>
              <div>
                <div className="stat-value" style={{ color }}>{value}</div>
                <div className="stat-label">{label}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Taux d'absence du jour ── */}
      {(() => {
        const specificDayLabel = (() => {
          if (!referenceDate) return 'du jour'
          const parsed = new Date(`${referenceDate}T00:00:00`)
          if (Number.isNaN(parsed.getTime())) return 'du jour'
          return `du ${parsed.toLocaleDateString('fr-FR')}`
        })()
        const periodTextLabels = {
          jour: specificDayLabel,
          semaine: "de la semaine",
          mois: "du mois",
          annee: "de l'année",
        }
        const periodFields = {
          jour: {
            attendus: stats?.total_attendus_jour || 0,
            presents: stats?.presents_aujourd_hui || 0,
            taux: stats?.taux_presence || 0,
          },
          semaine: {
            attendus: stats?.total_attendus_semaine || 0,
            presents: stats?.presents_semaine || 0,
            taux: stats?.taux_presence_semaine || 0,
          },
          mois: {
            attendus: stats?.total_attendus_mois || 0,
            presents: stats?.presents_mois || 0,
            taux: stats?.taux_presence_mois || 0,
          },
          annee: {
            attendus: stats?.total_attendus_annee || 0,
            presents: stats?.presents_annee || 0,
            taux: stats?.taux_presence_annee || 0,
          },
        }
        const selected = periodFields[presencePeriod] || periodFields.jour
        const attendus = selected.attendus
        const presents = selected.presents
        const absents = Math.max(attendus - presents, 0)
        const tauxPresence = selected.taux
        const tauxAbsence = attendus > 0 ? Number((100 - tauxPresence).toFixed(1)) : 0
        const absColor = tauxAbsence >= 50 ? '#e53e3e' : tauxAbsence >= 25 ? '#F5B100' : '#11407d'
        return (
          <div
            className="card"
            style={{ marginBottom: '1.25rem', padding: '1rem 1.25rem' }}
            title="Vue d’ensemble des présences et absences (étudiants + enseignants) pour la période sélectionnée. La barre compare présents (vert) et absents (couleur variable)."
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.6rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <span style={{ fontWeight: 700, fontSize: '0.92rem' }}>
                <i className="bi bi-person-x-fill me-2" style={{ color: absColor }}></i>
                Présences {periodTextLabels[presencePeriod]} — personnes (étudiants + enseignants)
              </span>
              {!canFilterBySecretariat && (
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
                  <div className="btn-group btn-group-sm" role="group" aria-label="Période présence">
                    {[
                      { id: 'jour', label: 'Jour' },
                      { id: 'semaine', label: 'Semaine' },
                      { id: 'mois', label: 'Mois' },
                      { id: 'annee', label: 'Année' },
                    ].map((opt) => (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => setPresencePeriod(opt.id)}
                        className={`btn ${presencePeriod === opt.id ? 'btn-dfrc' : 'btn-outline-secondary'}`}
                        style={{ fontSize: '0.78rem' }}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div style={{ display: 'flex', gap: '1.25rem', fontSize: '0.85rem', width: '100%', justifyContent: 'flex-end' }}>
                <span><span style={{ fontWeight: 700, color: '#11407d' }}>{presents}</span> <span className="text-muted">présents</span></span>
                <span><span style={{ fontWeight: 700, color: absColor }}>{absents}</span> <span className="text-muted">absents</span></span>
                <span><span style={{ fontWeight: 700, color: '#718096' }}>{attendus}</span> <span className="text-muted">attendus</span></span>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{ flex: 1, background: '#e2e8f0', borderRadius: 6, height: 10, position: 'relative', overflow: 'hidden' }}>
                <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${tauxPresence}%`, background: 'var(--ci-success)', borderRadius: 6, transition: 'width 0.4s' }}></div>
                <div style={{ position: 'absolute', left: `${tauxPresence}%`, top: 0, height: '100%', width: `${tauxAbsence}%`, background: absColor, opacity: 0.7, borderRadius: '0 6px 6px 0', transition: 'width 0.4s' }}></div>
              </div>
              <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#11407d', whiteSpace: 'nowrap' }}>{tauxPresence.toFixed(1)}% présents</span>
              <span style={{ fontSize: '0.82rem', fontWeight: 700, color: absColor, whiteSpace: 'nowrap' }}>{tauxAbsence.toFixed(1)}% absents</span>
            </div>
            {attendus === 0 && (
              <div style={{ marginTop: '0.55rem', fontSize: '0.8rem', color: '#718096' }}>
                Aucune personne attendue sur cette période pour les modules en cours.
              </div>
            )}
          </div>
        )
      })()}

      {/* ── Modules débutés ── */}
      <div
        className="card"
        title="Modules au statut « en cours » : site, encadrant, effectifs présents / attendus et taux de présence par module. Cliquez sur l’œil pour ouvrir le détail du module."
      >
        <div className="card-header-bar">
          <span><i className="bi bi-play-circle me-2" style={{ color: 'var(--ci-success)' }}></i>
            <strong>{user?.role === 'ENCADRANT' ? 'Mes modules débutés' : 'Modules débutés'}</strong>
          </span>
          <Link to="/modules?statut=EN_COURS" className="btn btn-dfrc btn-sm">Voir tout</Link>
        </div>
        <div className="card-body-flush">
          {formationsEnCours.length > 0 ? (
            <div className="table-container">
              <table className="table">
                <thead><tr>
                  <th>Module</th><th>Site </th><th>Catégorie</th>
                  <th>Encadrant</th><th>Présents / Attendus (étudiants)</th><th>Absents</th><th>Taux présence</th><th></th>
                </tr></thead>
                <tbody>
                  {formationsEnCours.map((f) => {
                    const attendus = f.nb_participants || 0
                    const presents = f.nb_presents || 0
                    const absents = Math.max(attendus - presents, 0)
                    const taux = attendus > 0 ? Math.round(presents / attendus * 100) : 0
                    const tauxAbsence = attendus > 0 ? Math.round(absents / attendus * 100) : 0
                    const tauxColor = taux >= 75 ? 'var(--ci-success)' : taux >= 50 ? 'var(--ci-warning)' : '#e53e3e'
                    const absColor = tauxAbsence >= 50 ? '#e53e3e' : tauxAbsence >= 25 ? '#F5B100' : '#718096'
                    const moduleLabel = f.module || f.intitule || '—'
                    const siteLabel = [f.site, f.batiment, f.salle].filter(Boolean).join(' / ') || '—'
                    return (
                      <tr key={`${f.id}-${f.module_id || ''}`}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{moduleLabel}</div>
                          {f.formation && <small className="text-muted" style={{ display: 'block' }}>{f.formation}</small>}
                          <small className="text-muted">{formatDate(f.date_debut)} — {formatDate(f.date_fin)}</small>
                        </td>
                        <td><span style={{ fontSize: '0.85rem' }}>{siteLabel}</span></td>
                        <td><span style={{ fontSize: '0.82rem', background: '#ebf4ff', color: '#2b6cb0', padding: '2px 7px', borderRadius: 4 }}>{f.categorie || f.grade || '—'}</span></td>
                        <td><span style={{ fontSize: '0.85rem' }}>{f.superviseur_nom || <span className="text-muted">Non assigné</span>}</span></td>
                        <td>
                          <span style={{ fontWeight: 700, color: 'var(--ci-success)' }}>{presents}</span>
                          <span className="text-muted"> / {attendus}</span>
                        </td>
                        <td>
                          <span style={{ fontWeight: 700, color: absColor }}>{absents}</span>
                          {attendus > 0 && <span className="text-muted" style={{ fontSize: '0.78rem' }}> ({tauxAbsence}%)</span>}
                        </td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <div style={{ flex: 1, background: '#e2e8f0', borderRadius: 4, height: 6, minWidth: 50 }}>
                              <div style={{ width: `${taux}%`, background: tauxColor, borderRadius: 4, height: '100%', transition: 'width 0.3s' }}></div>
                            </div>
                            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: tauxColor }}>{taux}%</span>
                          </div>
                        </td>
                        <td>
                          <Link
                            to={`/formations/${f.id}/modules/${f.module_id}`}
                            state={listNavState}
                            className="btn btn-outline-primary btn-sm"
                            title="Voir détail"
                          >
                            <i className="bi bi-eye"></i>
                          </Link>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-4 text-muted">
              <i className="bi bi-inbox" style={{ fontSize: '2rem' }}></i>
              <p className="mt-2">Aucun module en cours</p>
            </div>
          )}
        </div>
      </div>

      {/* ── Ligne du bas : planifiés + derniers pointages ── */}
      <div className="row">
        {/* Prochaines séances */}
        <div className="col-lg-4">
          <div
            className="card"
            title="Liste des prochaines séances planifiées (module, date et heure). Le chevron mène au détail du module."
          >
            <div className="card-header-bar">
              <span><i className="bi bi-calendar-event me-2" style={{ color: 'var(--ci-warning)' }}></i><strong>Prochaines séances</strong></span>
            </div>
            <div className="card-body-flush">
              {prochainesSeances.length > 0 ? (
                <div>
                  {prochainesSeances.map((s) => (
                    <div key={s.session_id} style={{ padding: '0.65rem 1rem', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <div style={{ background: 'rgba(245,177,0,0.1)', color: 'var(--ci-warning)', borderRadius: 8, padding: '0.45rem 0.5rem' }}>
                        <i className="bi bi-calendar3"></i>
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600, fontSize: '0.88rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {s.module || s.formation}
                        </div>
                        <small className="text-muted">
                          {formatDate(s.date_journee)} {s.heure_debut_prevue ? `• ${String(s.heure_debut_prevue).slice(0, 5)}` : ''}
                        </small>
                      </div>
                      <Link
                        to={`/formations/${s.formation_id}/modules/${s.module_id}`}
                        state={listNavState}
                        style={{ color: '#94a3b8', fontSize: '0.85rem' }}
                      >
                        <i className="bi bi-chevron-right"></i>
                      </Link>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-4 text-muted" style={{ fontSize: '0.9rem' }}>
                  <i className="bi bi-calendar-x" style={{ fontSize: '1.5rem' }}></i>
                  <p className="mt-1">Aucune séance à venir</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Derniers pointages */}
        <div className="col-lg-8">
          <div
            className="card"
            title="Derniers badgeages enregistrés : nom, matricule, rôle, module concerné, horaires d’entrée et de sortie."
          >
            <div className="card-header-bar">
              <span><i className="bi bi-clock-history me-2" style={{ color: '#805ad5' }}></i><strong>Derniers pointages</strong></span>
            </div>
            <div className="card-body-flush">
              {stats?.derniers_pointages?.length > 0 ? (
                <div className="table-container">
                  <table className="table">
                    <thead><tr>
                      <th>Nom</th><th>Matricule</th><th>Rôle</th><th>Module</th><th>Date</th><th>Entrée</th><th>Sortie</th>
                    </tr></thead>
                    <tbody>
                      {stats.derniers_pointages.map((pt, i) => (
                        <tr key={i}>
                          <td style={{ fontWeight: 600, fontSize: '0.88rem' }}>{pt.nom || '—'}</td>
                          <td><code style={{ fontSize: '0.78rem' }}>{pt.matricule || '—'}</code></td>
                          <td>
                            <span style={{
                              background: pt.type === 'formateur' ? '#ebf4ff' : pt.type === 'encadrant' ? '#fffcf0' : '#f0f4ff',
                              color: pt.type === 'formateur' ? '#2b6cb0' : pt.type === 'encadrant' ? '#9c4221' : '#4a5568',
                              borderRadius: 4, padding: '2px 6px', fontSize: '0.72rem'
                            }}>
                              {pt.type === 'formateur' ? 'Enseignant' : pt.type === 'encadrant' ? 'Encadrant' : 'Étudiant'}
                            </span>
                          </td>
                          <td style={{ fontSize: '0.82rem', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{pt.module || '—'}</td>
                          <td style={{ fontSize: '0.82rem', whiteSpace: 'nowrap' }}>{formatDate(pt.date)}</td>
                          <td style={{ fontFamily: 'monospace', fontSize: '0.82rem' }}>{fmtTime(pt.heure_entree)}</td>
                          <td style={{ fontFamily: 'monospace', fontSize: '0.82rem', color: pt.heure_sortie ? '#11407d' : '#94a3b8' }}>
                            {fmtTime(pt.heure_sortie)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-4 text-muted" style={{ fontSize: '0.9rem' }}>
                  <i className="bi bi-qr-code" style={{ fontSize: '1.5rem' }}></i>
                  <p className="mt-1">Aucun pointage récent</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      <div style={{ clear: 'both' }}></div>
    </div>
  )
}
