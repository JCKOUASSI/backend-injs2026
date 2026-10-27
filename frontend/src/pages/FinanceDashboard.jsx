import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { fmtDuration, fmtHeures, formatMoney } from '../components/FinanceStatsGrid'
import FinancePageShell, { FinanceNavActions } from '../components/finance/FinancePageShell'
import {
  buildFinanceListSearchParams,
  buildFinanceQuery,
  FINANCE_QUERY_STORAGE_KEY,
  resolveFinancePeriod,
  saveFinancePeriod,
} from '../utils/financePeriod'
import { usePersistedListQuery } from '../hooks/usePersistedListQuery'
import Pagination from '../components/Pagination'
import FinanceModuleBreakdownModal from '../components/finance/FinanceModuleBreakdownModal'
import FinanceToleranceBadge from '../components/finance/FinanceToleranceBadge'

const maxActivite = (items) => Math.max(...items.map((i) => Number(i.minutes_realisees || 0)), 1)

const SYNTHESE_PAGE_SIZE = 25

const HERO_KPIS = [
  {
    id: 'planifie',
    label: 'Volume horaire total planifié',
    icon: 'bi-clock',
    variant: 'plan',
    kpiKey: 'total_duree_minutes',
    format: 'duration',
    evolutionKey: 'total_duree_minutes',
    sub: (kpis) => `${kpis.total_sessions ?? 0} séance(s)`,
  },
  {
    id: 'cout_prevu',
    label: 'Coût prévisionnel du volume horaire',
    icon: 'bi-calculator',
    variant: 'forecast',
    kpiKey: 'total_montant_prevu',
    format: 'money',
    evolutionKey: 'total_montant_prevu',
    sub: (kpis) => {
      const h = fmtHeures(kpis.total_duree_heures)
      return `Basé sur ${h} h planifiées · tarif par cycle de formation`
    },
  },
  {
    id: 'realise',
    label: 'Volume horaire total réalisé',
    icon: 'bi-clock-history',
    variant: 'time',
    kpiKey: 'total_duree_realisee_minutes',
    format: 'duration',
    evolutionKey: 'total_duree_realisee_minutes',
    sub: (kpis) => `${kpis.formateurs_actifs ?? 0} enseignant(s) actif(s)`,
  },
  {
    id: 'taux',
    label: 'Taux de réalisation global',
    icon: 'bi-percent',
    variant: 'rate',
    kpiKey: 'taux_realisation_global_pct',
    format: 'pct',
    evolutionKey: 'taux_realisation_global_pct',
    sub: (kpis, comparaison) => {
      const prev = comparaison?.kpis?.taux_realisation_global_pct
      return prev != null ? `Période précédente : ${prev} %` : 'Hors séances sans horaire planifié'
    },
  },
  {
    id: 'cout',
    label: 'Coût global du volume horaire réalisé',
    icon: 'bi-cash-stack',
    variant: 'money',
    kpiKey: 'total_montant_realise',
    format: 'money',
    evolutionKey: 'total_montant_realise',
    sub: (kpis) => {
      const n = Array.isArray(kpis.tarifs_appliques) ? kpis.tarifs_appliques.length : 0
      return n > 1
        ? `Facturation selon le tarif de chaque formation (${n} tarifs appliqués)`
        : 'Facturation selon le tarif de chaque formation'
    },
  },
]

const KPI_GROUPS = [
  {
    title: 'Effectifs',
    iconClass: 'finance-kpi-card-icon--people',
    items: [
      { key: 'total_formateurs', label: 'Enseignants', icon: 'bi-person-video3' },
      { key: 'formateurs_actifs', label: 'Actifs', icon: 'bi-person-check' },
      { key: 'formateurs_inactifs', label: 'Inactifs', icon: 'bi-person-dash' },
    ],
  },
  {
    title: 'Séances',
    iconClass: 'finance-kpi-card-icon--sessions',
    items: [
      { key: 'total_sessions', label: 'Séances', icon: 'bi-calendar3' },
      { key: 'sessions_avec_pointage', label: 'Pointées', icon: 'bi-check2-square' },
    ],
  },
  {
    title: 'Moyenne',
    iconClass: 'finance-kpi-card-icon--time',
    items: [
      { key: 'moyenne_heures_realisees_par_enseignant', label: 'Moy. h / actif', format: 'hours', icon: 'bi-graph-up' },
    ],
  },
]

function formatKpiValue(kpis, item) {
  const v = kpis[item.key]
  if (item.format === 'duration') return fmtDuration(v)
  if (item.format === 'money') return `${formatMoney(v)} FCFA`
  if (item.format === 'hours') return `${fmtHeures(v)} h`
  return v ?? 0
}

function formatHeroKpiValue(kpis, item) {
  const v = kpis[item.kpiKey]
  if (item.format === 'duration') return fmtDuration(v)
  if (item.format === 'money') return `${formatMoney(v)} FCFA`
  if (item.format === 'pct') return `${v ?? 0} %`
  return v ?? 0
}

function RankMedal({ idx }) {
  if (idx >= 3) return <span className="text-muted">{idx + 1}</span>
  return <span className={`finance-rank-medal finance-rank-medal--${idx + 1}`}>{idx + 1}</span>
}

function EvolutionBadge({ evolution, kpiKey, format }) {
  const ev = evolution?.[kpiKey]
  if (!ev) return null
  const delta = Number(ev.delta || 0)
  const pct = Number(ev.pourcent || 0)
  const up = delta > 0
  const down = delta < 0
  const cls = up ? 'finance-evolution--up' : down ? 'finance-evolution--down' : 'finance-evolution--flat'
  const sign = up ? '+' : ''
  const display = format === 'money'
    ? `${sign}${formatMoney(delta)} F`
    : format === 'duration'
      ? `${sign}${fmtDuration(Math.abs(delta))}`
      : `${sign}${delta}${format === 'pct' ? ' pts' : ''}`
  return (
    <span className={`finance-evolution ${cls}`} title={`vs période précédente (${pct >= 0 ? '+' : ''}${pct} %)`}>
      <i className={`bi bi-arrow-${up ? 'up' : down ? 'down' : 'right'}-short`}></i>
      {display}
    </span>
  )
}

export default function FinanceDashboard() {
  const [searchParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [period, setPeriod] = useState(() => resolveFinancePeriod())
  const [appliedPeriod, setAppliedPeriod] = useState(() => resolveFinancePeriod())
  const [rankTab, setRankTab] = useState(() => searchParams.get('rank_tab') || 'realise')
  const [synthesePage, setSynthesePage] = useState(1)
  const [moduleDrill, setModuleDrill] = useState(null)
  const [specialiteDrill, setSpecialiteDrill] = useState(null)

  usePersistedListQuery(
    FINANCE_QUERY_STORAGE_KEY,
    () => buildFinanceListSearchParams(appliedPeriod, {}, { rankTab }),
    [appliedPeriod, rankTab],
  )

  const load = useCallback(async (p) => {
    setLoading(true)
    try {
      const qs = buildFinanceQuery(p).toString()
      const res = await api.get(`/formations/finance/dashboard/${qs ? `?${qs}` : ''}`)
      setData(res.data || null)
      setError('')
    } catch (err) {
      setError(err.response?.data?.detail || 'Impossible de charger le dashboard finance.')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(appliedPeriod)
  }, [appliedPeriod, load])

  useEffect(() => {
    setSynthesePage(1)
  }, [appliedPeriod])

  const handleApply = () => {
    saveFinancePeriod(period)
    setAppliedPeriod({ ...period })
    setSynthesePage(1)
  }

  // Mémoïsé : sans cela, le fallback `[]` est un tableau neuf à chaque rendu
  // et le useMemo des KPI ci-dessous perdait toute mémoïsation (warning
  // exhaustive-deps LOT 6). Référence stable tant que `data` ne change pas.
  const volumesParModule = useMemo(
    () => (Array.isArray(data?.volumes_par_module) ? data.volumes_par_module : []),
    [data?.volumes_par_module],
  )
  const kpis = useMemo(() => {
    const raw = data?.kpis || {}
    if (raw.total_montant_prevu != null && raw.total_montant_prevu !== '') {
      return raw
    }
    const sumPrevu = volumesParModule.reduce(
      (s, m) => s + Number(m.montant_prevu || 0),
      0,
    )
    return { ...raw, total_montant_prevu: sumPrevu }
  }, [data?.kpis, volumesParModule])
  const comparaison = data?.comparaison || null
  const evolution = comparaison?.evolution || null
  const periode = data?.periode || {}
  const activite = Array.isArray(data?.activite_par_mois) ? data.activite_par_mois : []
  const topPlanifie = Array.isArray(data?.top_formateurs) ? data.top_formateurs : []
  const topRealise = Array.isArray(data?.top_temps_realise) ? data.top_temps_realise : []
  const topMontants = Array.isArray(data?.top_montants) ? data.top_montants : []
  const specialites = Array.isArray(data?.repartition_specialites) ? data.repartition_specialites : []
  // Idem ci-dessus : le fallback `[]` recyclé à chaque rendu rendait le
  // useMemo de la page de synthèse inopérant (warning LOT 6).
  const synthese = useMemo(
    () => (Array.isArray(data?.synthese_formateurs) ? data.synthese_formateurs : []),
    [data?.synthese_formateurs],
  )
  const syntheseTotalPages = Math.max(1, Math.ceil(synthese.length / SYNTHESE_PAGE_SIZE))
  const synthesePageSafe = Math.min(synthesePage, syntheseTotalPages)
  const synthesePageRows = useMemo(() => {
    const start = (synthesePageSafe - 1) * SYNTHESE_PAGE_SIZE
    return synthese.slice(start, start + SYNTHESE_PAGE_SIZE)
  }, [synthese, synthesePageSafe])
  const activiteMax = maxActivite(activite)

  const rankConfig = {
    planifie: { rows: topPlanifie, label: 'Temps planifié', fmt: (f) => fmtDuration(f.total_duree_minutes) },
    realise: { rows: topRealise, label: 'Temps réalisé', fmt: (f) => fmtDuration(f.total_duree_realisee_minutes) },
    montants: { rows: topMontants, label: 'Montant', fmt: (f) => `${formatMoney(f.montant_total_realise)} FCFA` },
  }
  const activeRank = rankConfig[rankTab] || rankConfig.realise

  return (
    <FinancePageShell
      title="Tableau de Bord Finance"
      subtitle="Suivi des temps de cours et rémunération des enseignants"
      icon="bi-speedometer2"
      actions={<FinanceNavActions active="dashboard" />}
      period={period}
      onPeriodChange={setPeriod}
      onPeriodApply={handleApply}
      periodApplying={loading}
      periodeInfo={periode}
    >
      {error && <div className="error-message">{error}</div>}

      {!loading && kpis.tolerance?.tolerance_active && (
        <div className="alert alert-warning py-2 small mb-3">
          <i className="bi bi-shield-check me-1"></i>
          Tolérance active : {kpis.tolerance.tolerance_minutes} min ou {kpis.tolerance.tolerance_pct} % —
          {' '}
          <strong>{kpis.tolerance.formateurs_anomalie ?? 0}</strong> hors tolérance,
          {' '}
          <strong>{kpis.tolerance.formateurs_alerte ?? 0}</strong> dans la tolérance,
          {' '}
          <strong>{kpis.tolerance.formateurs_conformes ?? 0}</strong> conforme(s).
        </div>
      )}

      {!loading && (
        <div className="alert alert-info py-2 small mb-3">
          <i className="bi bi-info-circle me-1"></i>
          Les montants sont calculés avec le <strong>tarif horaire propre à chaque type de formation</strong>
          {Array.isArray(kpis.tarifs_appliques) && kpis.tarifs_appliques.length > 0 && (
            <> ({kpis.tarifs_appliques.map((t) => `${formatMoney(t)} F/h`).join(', ')})</>
          )}.
        </div>
      )}

      {loading ? (
        <div className="loading py-5"><div className="spinner"></div></div>
      ) : (
        <>
          <div className="finance-hero-kpis finance-hero-kpis--5">
            {HERO_KPIS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`finance-hero-kpi finance-hero-kpi--${item.variant} finance-hero-kpi--clickable`}
                onClick={() => setModuleDrill(item.id)}
                title="Cliquer pour le détail par module"
              >
                <div className="finance-hero-kpi-label">
                  <i className={`bi ${item.icon} me-1`}></i>
                  {item.label}
                </div>
                <div className="finance-hero-kpi-value">
                  {formatHeroKpiValue(kpis, item)}
                  <EvolutionBadge evolution={evolution} kpiKey={item.evolutionKey} format={item.format} />
                </div>
                <div className="finance-hero-kpi-sub">
                  {item.sub(kpis, comparaison)}
                </div>
                <div className="finance-hero-kpi-hint">
                  <i className="bi bi-box-arrow-up-right"></i> Détail par module
                </div>
              </button>
            ))}
          </div>

          <div className="finance-kpi-grid">
            {KPI_GROUPS.flatMap((g) =>
              g.items.map((item) => (
                <div className="finance-kpi-card" key={item.key}>
                  <div className={`finance-kpi-card-icon ${g.iconClass}`}>
                    <i className={`bi ${item.icon}`}></i>
                  </div>
                  <div>
                    <div className="finance-kpi-card-value">{formatKpiValue(kpis, item)}</div>
                    <div className="finance-kpi-card-label">{item.label}</div>
                  </div>
                </div>
              ))
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem' }}>
            {activite.length > 0 && (
              <section className="finance-section">
                <div className="finance-section-header">
                  <h2><i className="bi bi-bar-chart-line"></i>Activité mensuelle</h2>
                </div>
                <div className="finance-section-body">
                  {activite.map((m) => (
                    <div className="finance-chart-row" key={m.mois}>
                      <span className="finance-chart-label">{m.label}</span>
                      <div className="finance-chart-bar-wrap">
                        <div
                          className="finance-chart-bar"
                          style={{ width: `${Math.min(100, (m.minutes_realisees / activiteMax) * 100)}%` }}
                        />
                      </div>
                      <span className="finance-chart-meta">
                        {fmtDuration(m.minutes_realisees)} · {formatMoney(m.montant)} F
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {specialites.length > 0 && (
              <section className="finance-section">
                <div className="finance-section-header">
                  <h2><i className="bi bi-pie-chart"></i>Spécialités</h2>
                </div>
                <div className="finance-section-body" style={{ padding: 0 }}>
                  <div className="finance-table-wrap">
                    <table className="finance-table">
                      <thead>
                        <tr><th>Spécialité</th><th style={{ textAlign: 'right' }}>Enseignants</th></tr>
                      </thead>
                      <tbody>
                        {specialites.map((s) => (
                          <tr key={s.specialite}>
                            <td>{s.specialite}</td>
                            <td style={{ textAlign: 'right' }}>
                              <span
                                className="badge-bg-info"
                                style={{ cursor: 'pointer' }}
                                title="Voir les enseignants"
                                onClick={() => setSpecialiteDrill(s)}
                              >{s.count}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </section>
            )}
          </div>

          <section className="finance-section">
            <div className="finance-section-header">
              <h2><i className="bi bi-trophy"></i>Classement enseignants</h2>
            </div>
            <div className="finance-rank-tabs">
              {[
                { id: 'realise', label: 'Temps réalisé', icon: 'bi-clock-history' },
                { id: 'planifie', label: 'Temps planifié', icon: 'bi-clock' },
                { id: 'montants', label: 'Montants', icon: 'bi-cash-stack' },
              ].map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`finance-rank-tab${rankTab === t.id ? ' active' : ''}`}
                  onClick={() => setRankTab(t.id)}
                >
                  <i className={`bi ${t.icon} me-1`}></i>{t.label}
                </button>
              ))}
            </div>
            <div className="finance-table-wrap">
              <table className="finance-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Enseignant</th>
                    <th>Spécialité</th>
                    <th>Séances</th>
                    <th>{activeRank.label}</th>
                  </tr>
                </thead>
                <tbody>
                  {activeRank.rows.length > 0 ? activeRank.rows.map((f, idx) => (
                    <tr key={f.id}>
                      <td><RankMedal idx={idx} /></td>
                      <td>
                        <strong>{f.prenom} {f.nom}</strong>
                        <div className="text-muted small">{f.numerobadge || '—'}</div>
                      </td>
                      <td className="text-muted small">{f.specialite || '—'}</td>
                      <td><span className="badge-bg-secondary">{f.sessions_count || 0}</span></td>
                      <td><span className="badge-bg-success">{activeRank.fmt(f)}</span></td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan="5">
                        <div className="finance-empty">
                          <i className="bi bi-inbox"></i>
                          Aucune donnée sur cette période
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="finance-section">
            <div className="finance-section-header">
              <h2><i className="bi bi-table"></i>Fiche de paie globale — synthèse enseignants</h2>
              <span className="badge-bg-secondary">
                {synthese.length} formateur(s)
                {syntheseTotalPages > 1 && (
                  <> — page {synthesePageSafe} / {syntheseTotalPages}</>
                )}
              </span>
            </div>
            <div className="finance-table-wrap">
              <table className="finance-table">
                <thead>
                  <tr>
                    <th>N°</th>
                    <th>Nom</th>
                    <th>Prénom</th>
                    <th>Modules dispensés</th>
                    <th>Grade(s)</th>
                    <th>Groupe(s)</th>
                    <th>Mod.</th>
                    <th>Séances</th>
                    <th>Taux</th>
                    <th>Statut</th>
                    <th>Planifié</th>
                    <th>Réalisé</th>
                    <th>Montant</th>
                  </tr>
                </thead>
                <tbody>
                  {synthesePageRows.length > 0 ? synthesePageRows.map((f) => {
                    const st = f.statistiques || {}
                    const taux = st.taux_realisation_pct ?? 0
                    return (
                      <tr key={f.id}>
                        <td><span className="badge-bg-info">{f.numerobadge || '-'}</span></td>
                        <td><strong>{f.nom}</strong></td>
                        <td>{f.prenom}</td>
                        <td className="small text-muted">{f.modules_dispenses || '—'}</td>
                        <td className="small">{f.grades || '—'}</td>
                        <td className="small">{f.groupes || '—'}</td>
                        <td>{f.nb_formations ?? 0}</td>
                        <td>{f.sessions_count ?? 0}</td>
                        <td>
                          <div>{taux}%</div>
                          <div className="finance-taux-bar">
                            <div className="finance-taux-bar-fill" style={{ width: `${Math.min(100, taux)}%` }} />
                          </div>
                        </td>
                        <td>
                          <FinanceToleranceBadge tolerance={f.tolerance} showInactive />
                        </td>
                        <td style={{ whiteSpace: 'nowrap' }}>{fmtDuration(f.total_duree_minutes)}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{fmtDuration(f.total_duree_realisee_minutes)}</td>
                        <td style={{ whiteSpace: 'nowrap', fontWeight: 700, color: 'var(--fin-accent)' }}>
                          {formatMoney(f.montant_total_realise)} F
                        </td>
                      </tr>
                    )
                  }) : (
                    <tr>
                      <td colSpan="13">
                        <div className="finance-empty"><i className="bi bi-inbox"></i>Aucun enseignant</div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="finance-section-footer">
              <Pagination
                page={synthesePageSafe}
                totalPages={syntheseTotalPages}
                onPageChange={setSynthesePage}
                totalItems={synthese.length}
                pageSize={SYNTHESE_PAGE_SIZE}
                activeClassName="pagination-num--active pagination-num--finance"
              />
            </div>
          </section>

          {data?.generated_at && (
            <p className="text-muted small text-end">
              Actualisé le {new Date(data.generated_at).toLocaleString('fr-FR')}
            </p>
          )}

          {moduleDrill && (
            <FinanceModuleBreakdownModal
              drillType={moduleDrill}
              modules={volumesParModule}
              onClose={() => setModuleDrill(null)}
            />
          )}

          {specialiteDrill && (
            <div className="modal-overlay" onClick={() => setSpecialiteDrill(null)}>
              <div className="modal-content" style={{ maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                  <h5 style={{ margin: 0 }}>
                    <i className="bi bi-people me-2"></i>
                    {specialiteDrill.specialite}
                    <span className="badge-bg-secondary ms-2" style={{ fontSize: '0.8rem' }}>{specialiteDrill.count}</span>
                  </h5>
                  <button className="btn-close" onClick={() => setSpecialiteDrill(null)}>&times;</button>
                </div>
                <div className="modal-body" style={{ maxHeight: '60vh', overflowY: 'auto' }}>
                  {(specialiteDrill.formateurs || []).length === 0 ? (
                    <p className="text-muted">Aucun enseignant.</p>
                  ) : (
                    <table className="finance-table">
                      <thead>
                        <tr><th>N°</th><th>Nom</th><th>Prénom</th></tr>
                      </thead>
                      <tbody>
                        {(specialiteDrill.formateurs || []).map((f) => (
                          <tr key={f.id}>
                            <td><span className="badge-bg-info">{f.numerobadge || '—'}</span></td>
                            <td><strong>{f.nom}</strong></td>
                            <td>{f.prenom}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
                <div className="modal-footer">
                  <button className="btn btn-secondary" onClick={() => setSpecialiteDrill(null)}>Fermer</button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </FinancePageShell>
  )
}
