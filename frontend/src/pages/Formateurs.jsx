import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import ConfirmModal from '../components/ConfirmModal'
import { useToast } from '../context/ToastContext'
import { useDebounce } from '../hooks/useDebounce'
import { formatMoney, fmtDuration } from '../components/FinanceStatsGrid'
import FinancePageShell, { FinanceNavActions } from '../components/finance/FinancePageShell'
import FinanceDetailModal from '../components/finance/FinanceDetailModal'
import FormateurFicheModal from '../components/formateurs/FormateurFicheModal'
import {
  buildFinanceListSearchParams,
  buildFinanceExportQuery,
  buildFinanceQuery,
  FINANCE_EXPORT_MONTANTS_KEY,
  FINANCE_QUERY_STORAGE_KEY,
  loadFinanceExportMontants,
  resolveFinancePeriod,
  saveFinanceExportMontants,
  saveFinancePeriod,
} from '../utils/financePeriod'
import {
  buildFormateursListSearchParams,
  LIST_STORAGE_KEYS,
  parseListPage,
  readFormateursListExtras,
} from '../utils/listFilters'
import { usePersistedListQuery } from '../hooks/usePersistedListQuery'
import Pagination from '../components/Pagination'
import { parsePaginatedResponse } from '../utils/paginatedResponse'
import { canMutateFormations, FINANCE_MODULE_ROLES } from '../utils/roles'
import { safeLocalStorage } from '../utils/safeStorage'
import '../styles/premiumCommun.css'
import '../styles/formateurs.css'

const emptyForm = { numerobadge: '', nom: '', prenom: '', email: '', telephone: '', specialite: '', organisation: '', observations: '', secretariats: [] }

const financeStatsForGrid = (detail) => ({
  ...(detail?.statistiques || {}),
  sessions_count: detail?.sessions_count,
  total_duree_minutes: detail?.total_duree_minutes,
  total_duree_realisee_minutes: detail?.total_duree_realisee_minutes,
})

export default function Formateurs() {
  const { user } = useAuth()
  const isArchiveRole = user?.role === 'ARCHIVE'
  const canViewFinanceData = FINANCE_MODULE_ROLES.includes(user?.role) && !isArchiveRole
  const canEditFormateurSensitive = user?.role === 'FINANCE'
  // Données sensibles (pièce d'identité, RIB) visibles en lecture pour FINANCE et ARCHIVE
  const canViewSensitive = user?.role === 'FINANCE' || isArchiveRole
  const [searchParams] = useSearchParams()
  const listExtras = readFormateursListExtras(searchParams)
  const [formateurs, setFormateurs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [page, setPage] = useState(() => parseListPage(searchParams))
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [search, setSearch] = useState(listExtras.search)
  const [showModal, setShowModal] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState({ ...emptyForm })
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [detailFormateur, setDetailFormateur] = useState(null)
  const [exportingFiche, setExportingFiche] = useState('')
  const { showToast } = useToast()

  const [refModules, setRefModules] = useState([])
  const [financeDetail, setFinanceDetail] = useState(null)
  const [financeDetailLoading, setFinanceDetailLoading] = useState(false)
  const [financeDetailTab, setFinanceDetailTab] = useState('statistiques')
  const [exportAfficherMontants, setExportAfficherMontants] = useState(() => loadFinanceExportMontants(true))
  const [exportingSynthese, setExportingSynthese] = useState(false)
  const [financePeriod, setFinancePeriod] = useState(() => resolveFinancePeriod())
  const [financePeriodeInfo, setFinancePeriodeInfo] = useState(null)

  const debouncedSearch = useDebounce(search)
  const [appliedFinancePeriod, setAppliedFinancePeriod] = useState(() => resolveFinancePeriod())
  const syncFormateursQuery = () => buildFormateursListSearchParams(
    page,
    debouncedSearch,
    appliedFinancePeriod,
    {},
    canViewFinanceData,
    buildFinanceListSearchParams,
  )

  usePersistedListQuery(
    canViewFinanceData ? FINANCE_QUERY_STORAGE_KEY : LIST_STORAGE_KEYS.formateurs,
    syncFormateursQuery,
    [page, debouncedSearch, appliedFinancePeriod, canViewFinanceData],
  )

  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  useEffect(() => { loadFormateurs() }, [page, debouncedSearch, appliedFinancePeriod])

  useEffect(() => {
    api.get('/formations/ref/modules/')
      .then(res => setRefModules(Array.isArray(res.data) ? res.data.filter(m => m.actif !== false) : []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!canViewFinanceData) return
    api.get('/formations/finance/settings/')
      .then((res) => {
        if (safeLocalStorage.getItem(FINANCE_EXPORT_MONTANTS_KEY) === null) {
          setExportAfficherMontants(res.data?.afficher_montants_exports !== false)
        }
      })
      .catch(() => {})
  }, [canViewFinanceData])

  const handleExportMontantsChange = (checked) => {
    setExportAfficherMontants(checked)
    saveFinanceExportMontants(checked)
  }

  const loadFormateurs = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page })
      if (debouncedSearch) params.set('search', debouncedSearch)
      const endpoint = canViewFinanceData
        ? '/formations/formateurs/finance-report/'
        : '/formations/formateurs/list/'
      if (canViewFinanceData) {
        params.set('include_sessions', '0')
        buildFinanceQuery(appliedFinancePeriod).forEach((v, k) => params.set(k, v))
      }
      const response = await api.get(`${endpoint}?${params}`)
      const { results, count, totalPages: pages } = parsePaginatedResponse(response.data, 50)
      setFormateurs(results)
      setTotalCount(count)
      setTotalPages(pages)
      if (canViewFinanceData && response.data?.periode) {
        setFinancePeriodeInfo(response.data.periode)
      }
    } catch (err) {
      setError('Erreur lors du chargement des enseignants')
      console.error(err)
    } finally { setLoading(false) }
  }

  const openCreate = () => { setEditingId(null); setForm({ ...emptyForm }); setFormError(''); setShowModal(true) }
  const openEdit = (f) => {
    setEditingId(f.id)
    setForm({
      numerobadge: f.numerobadge || '',
      nom: f.nom || '',
      prenom: f.prenom || '',
      email: f.email || '',
      telephone: f.telephone || '',
      specialite: f.specialite || '',
      organisation: f.organisation || '',
      observations: f.observations || '',
      secretariats: f.secretariats || [],
    })
    setFormError('')
    setShowModal(true)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setFormError('')
    setSaving(true)
    try {
      if (editingId) {
        await api.patch(`/formations/formateurs/${editingId}/`, form)
      } else {
        await api.post('/formations/formateurs/', form)
      }
      setShowModal(false)
      loadFormateurs()
      showToast(editingId ? 'Enseignant modifié' : 'Enseignant créé')
    } catch (err) {
      const data = err.response?.data
      if (data && typeof data === 'object') {
        const msgs = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
        setFormError(msgs.join('\n'))
      } else {
        setFormError('Erreur lors de la sauvegarde')
      }
    } finally { setSaving(false) }
  }

  const handleDelete = (id) => {
    setConfirmDialog({
      message: 'Supprimer cet enseignant ?',
      detail: 'Cette action est définitive.',
      onConfirm: async () => {
        try { await api.delete(`/formations/formateurs/${id}/`); loadFormateurs(); showToast('Enseignant supprimé') }
        catch { showToast('Erreur lors de la suppression', 'error') }
      }
    })
  }

  const canEdit = !canViewFinanceData && canMutateFormations(user)
  const canDelete = !canViewFinanceData && canMutateFormations(user)

  const formatDate = (value) => {
    if (!value) return '-'
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return '-'
    return d.toLocaleDateString('fr-FR')
  }

  const downloadBlob = (blob, filename) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  const exportFinanceSummary = async (f, format, afficherMontants = exportAfficherMontants) => {
    const ext = format === 'pdf' ? 'pdf' : 'xlsx'
    const qs = buildFinanceExportQuery(appliedFinancePeriod, afficherMontants).toString()
    const base = format === 'pdf'
      ? `/exports/formateur/${f.id}/pdf/`
      : `/exports/formateur/${f.id}/excel/`
    const path = qs ? `${base}?${qs}` : base
    try {
      const { blob, fileName } = await api.getBlob(path)
      const safeName = `${f.nom || 'formateur'}_${f.prenom || ''}`.trim().replace(/\s+/g, '_')
      downloadBlob(blob, fileName || `fiche_resume_${safeName || f.id}.${ext}`)
      showToast(`Fiche résumé exportée (${ext.toUpperCase()})`)
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur export état financier', 'error')
    }
  }

  const exportFicheFormateur = async (f, format) => {
    if (!f?.id) return
    setExportingFiche(format)
    const ext = format === 'pdf' ? 'pdf' : 'xlsx'
    // preset 'tout' = toutes les données ; montants masqués hors finance
    const q = buildFinanceExportQuery({ preset: 'tout' }, canViewFinanceData)
    const base = format === 'pdf'
      ? `/exports/formateur/${f.id}/pdf/`
      : `/exports/formateur/${f.id}/excel/`
    try {
      const { blob, fileName } = await api.getBlob(`${base}?${q.toString()}`)
      const safeName = `${f.nom || 'formateur'}_${f.prenom || ''}`.trim().replace(/\s+/g, '_')
      downloadBlob(blob, fileName || `fiche_formateur_${safeName || f.id}.${ext}`)
      showToast(`Fiche enseignant exportée (${ext.toUpperCase()})`)
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur lors de l\'export de la fiche', 'error')
    } finally {
      setExportingFiche('')
    }
  }

  const exportFinanceSynthese = async (format) => {
    const ext = format === 'pdf' ? 'pdf' : 'xlsx'
    const params = buildFinanceExportQuery(appliedFinancePeriod, exportAfficherMontants)
    if (debouncedSearch) params.set('search', debouncedSearch)
    const qs = params.toString()
    const base = format === 'pdf'
      ? '/exports/finance/synthese/pdf/'
      : '/exports/finance/synthese/excel/'
    const path = qs ? `${base}?${qs}` : base
    setExportingSynthese(true)
    try {
      const { blob, fileName } = await api.getBlob(path)
      downloadBlob(blob, fileName || `fiche_paie_globale.${ext}`)
      showToast(`Fiche de paie globale (${ext.toUpperCase()})`)
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur export consolidé', 'error')
    } finally {
      setExportingSynthese(false)
    }
  }

  const reloadFinanceDetail = async (formateurId = financeDetail?.id) => {
    if (!formateurId) return
    setFinanceDetailLoading(true)
    try {
      const periodQs = buildFinanceQuery(appliedFinancePeriod).toString()
      const res = await api.get(
        `/formations/formateurs/finance-report/?formateur_id=${formateurId}${periodQs ? `&${periodQs}` : ''}`
      )
      const rows = Array.isArray(res.data) ? res.data : (res.data.results || [])
      const row = rows[0]
      if (row) setFinanceDetail(row)
      if (res.data?.periode) setFinancePeriodeInfo(res.data.periode)
    } catch {
      showToast('Impossible de recharger le détail', 'error')
    } finally {
      setFinanceDetailLoading(false)
    }
  }

  const openFinanceDetail = async (f) => {
    setFinanceDetailTab('statistiques')
    setFinanceDetail({
      id: f.id,
      nom: f.nom,
      prenom: f.prenom,
      numerobadge: f.numerobadge,
      email: f.email,
      telephone: f.telephone,
      specialite: f.specialite,
      organisation: f.organisation,
      secretariats_noms: f.secretariats_noms,
      nb_formations: f.nb_formations,
      sessions: [],
      total_duree_minutes: f.total_duree_minutes,
    })
    setFinanceDetailLoading(true)
    try {
      const periodQs = buildFinanceQuery(appliedFinancePeriod).toString()
      const res = await api.get(
        `/formations/formateurs/finance-report/?formateur_id=${f.id}${periodQs ? `&${periodQs}` : ''}`
      )
      const rows = Array.isArray(res.data) ? res.data : (res.data.results || [])
      const row = rows[0]
      if (row) setFinanceDetail(row)
      if (res.data?.periode) setFinancePeriodeInfo(res.data.periode)
    } catch {
      showToast('Impossible de charger le détail', 'error')
      setFinanceDetail(null)
    } finally {
      setFinanceDetailLoading(false)
    }
  }

  const financeListContent = (
    <>
      <div className="finance-section" style={{ marginBottom: '0.75rem' }}>
        <div className="finance-section-body">
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ flex: '1 1 280px' }}>
              <div className="input-group">
                <span className="input-group-text"><i className="bi bi-search"></i></span>
                <input
                  type="text"
                  className="form-control"
                  placeholder="Rechercher par nom, prénom ou spécialité…"
                  value={search}
                  onChange={(e) => { setSearch(e.target.value); setPage(1) }}
                />
              </div>
            </div>
            <label className="form-check mb-0 small text-nowrap" style={{ cursor: 'pointer' }}>
              <input
                type="checkbox"
                className="form-check-input me-1"
                checked={exportAfficherMontants}
                onChange={(e) => handleExportMontantsChange(e.target.checked)}
              />
              Montants sur les exports
            </label>
            <div className="d-flex gap-1 flex-wrap">
              <button
                type="button"
                className="btn btn-outline-success btn-sm"
                disabled={exportingSynthese || loading}
                onClick={() => exportFinanceSynthese('excel')}
                title="Fiche de paie globale Excel (tous les enseignants)"
              >
                <i className="bi bi-file-earmark-spreadsheet me-1"></i>
                {exportingSynthese ? 'Export…' : 'Paie globale Excel'}
              </button>
              <button
                type="button"
                className="btn btn-outline-danger btn-sm"
                disabled={exportingSynthese || loading}
                onClick={() => exportFinanceSynthese('pdf')}
                title="Fiche de paie globale PDF (tous les enseignants)"
              >
                <i className="bi bi-file-earmark-pdf me-1"></i>
                {exportingSynthese ? 'Export…' : 'Paie globale PDF'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <section className="finance-section">
        <div className="finance-section-header">
          <h2><i className="bi bi-people"></i>Suivi des enseignants</h2>
          <span className="badge-bg-secondary">{formateurs.length} résultat(s)</span>
        </div>
        <div className="finance-table-wrap">
          {loading ? (
            <div className="loading py-5"><div className="spinner"></div></div>
          ) : (
            <>
              <table className="finance-table">
                <thead>
                  <tr>
                    <th>N°</th>
                    <th>Nom</th>
                    <th>Prénom</th>
                    <th>Spécialité</th>
                    <th>Grade(s)</th>
                    <th>Groupe(s)</th>
                    <th>Séances</th>
                    <th>Planifié</th>
                    <th>Réalisé</th>
                    <th>Taux</th>
                    <th>Montant</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {formateurs.length > 0 ? formateurs.map((f) => {
                    const taux = f.statistiques?.taux_realisation_pct ?? 0
                    return (
                      <tr key={f.id}>
                        <td><span className="badge-bg-info">{f.numerobadge || '-'}</span></td>
                        <td><strong>{f.nom}</strong></td>
                        <td>{f.prenom}</td>
                        <td className="small text-muted">{f.specialite || '—'}</td>
                        <td className="small">{f.grades || '—'}</td>
                        <td className="small">{f.groupes || '—'}</td>
                        <td><span className="badge-bg-secondary">{f.sessions_count ?? 0}</span></td>
                        <td style={{ whiteSpace: 'nowrap' }}>{fmtDuration(f.total_duree_minutes)}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{fmtDuration(f.total_duree_realisee_minutes)}</td>
                        <td>
                          <div>{taux}%</div>
                          <div className="finance-taux-bar">
                            <div className="finance-taux-bar-fill" style={{ width: `${Math.min(100, taux)}%` }} />
                          </div>
                        </td>
                        <td style={{ whiteSpace: 'nowrap', fontWeight: 700, color: 'var(--fin-accent)' }}>
                          {formatMoney(f.montant_total_realise)} F
                        </td>
                        <td style={{ whiteSpace: 'nowrap' }}>
                          <button
                            type="button"
                            onClick={() => openFinanceDetail(f)}
                            className="btn btn-dfrc btn-sm"
                          >
                            <i className="bi bi-eye me-1"></i>Fiche
                          </button>
                        </td>
                      </tr>
                    )
                  }) : (
                    <tr>
                      <td colSpan="12">
                        <div className="finance-empty"><i className="bi bi-inbox"></i>Aucun enseignant</div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <Pagination
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                totalItems={totalCount}
                pageSize={50}
                className="p-3"
              />
            </>
          )}
        </div>
      </section>
    </>
  )

  if (canViewFinanceData) {
    return (
      <FinancePageShell
        title="Suivi Finance"
        subtitle="Temps de cours et rémunération par enseignant"
        icon="bi-cash-stack"
        actions={<FinanceNavActions active="formateurs" />}
        period={financePeriod}
        onPeriodChange={setFinancePeriod}
        onPeriodApply={() => {
          saveFinancePeriod(financePeriod)
          setAppliedFinancePeriod({ ...financePeriod })
          setPage(1)
        }}
        periodApplying={loading}
        periodeInfo={financePeriodeInfo}
      >
        {financeListContent}
        {financeDetail && (
          <FinanceDetailModal
            financeDetail={financeDetail}
            financeDetailLoading={financeDetailLoading}
            financeDetailTab={financeDetailTab}
            setFinanceDetailTab={setFinanceDetailTab}
            onClose={() => !financeDetailLoading && setFinanceDetail(null)}
            formatDuration={fmtDuration}
            formatDate={formatDate}
            exportFinanceSummary={exportFinanceSummary}
            exportAfficherMontants={exportAfficherMontants}
            onExportMontantsChange={handleExportMontantsChange}
            canViewSensitive={canEditFormateurSensitive}
            canEditSensitive={canEditFormateurSensitive}
            onSensitiveSaved={(data) => {
              setFinanceDetail((prev) => prev ? { ...prev, ...data } : prev)
            }}
            financeStatsForGrid={financeStatsForGrid}
            canProposeAjustement
            onRefreshDetail={() => reloadFinanceDetail()}
          />
        )}
      </FinancePageShell>
    )
  }

  return (
    <div className="ens-page">
      {/* Hero — Variante A « Clair raffiné » */}
      <header className="px-hero">
        <span className="px-hero-icon"><i className="bi bi-person-video3"></i></span>
        <div className="px-hero-text">
          <span className="px-hero-eyebrow">Corps enseignant · INJS</span>
          <h1 className="px-hero-title">Enseignants</h1>
          <p className="px-hero-intro">Profils, spécialités et rattachement des modules enseignés dans les formations LMD.</p>
        </div>
        <div className="px-hero-side">
          <span className="px-plaquette">{formateurs.length} enseignant(s)</span>
          <span className="px-plaquette px-plaquette--soft">{canDelete ? 'Gestion' : 'Consultation'}</span>
        </div>
      </header>

      {/* Barre de recherche — panneau premium */}
      <div className="card px-panel ens-toolbar">
        <div className="px-toolbar-body">
          <label className="px-field px-field--recherche">
            <span className="px-field-label">Rechercher</span>
            <span className="px-search">
              <i className="bi bi-search"></i>
              <input type="text" className="px-input" placeholder={canViewFinanceData ? 'Rechercher un enseignant...' : 'Rechercher par nom, prénom ou spécialité...'}
                value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
            </span>
          </label>
          {canDelete && (
            <div className="px-toolbar-actions">
              <button onClick={openCreate} className="btn btn-dfrc">
                <i className="bi bi-plus-lg me-1"></i>Nouvel enseignant
              </button>
            </div>
          )}
        </div>
      </div>

      {error && <div className="error-message px-error">{error}</div>}

      {/* Résultats */}
      <div className="card px-panel ens-panel">
        <div className="px-panel-head">
          <div className="px-panel-headtext">
            <h2 className="px-panel-title">
              <i className={`bi ${canViewFinanceData ? 'bi-calculator' : 'bi-person-video3'}`}></i>
              {canViewFinanceData ? 'Suivi des temps de cours enseignants' : 'Liste des enseignants'}
            </h2>
            <p className="px-panel-sub">Ouvrez la fiche complète d'un enseignant avec « Détail ».</p>
          </div>
          <div className="px-panel-tools">
            <span className="px-count-pill">{formateurs.length} résultat(s)</span>
          </div>
        </div>
        <div className="card-body-flush">
          {loading ? <div className="loading px-loading"><div className="spinner"></div></div> : (
            <>
              <div className="table-container">
                <table className="table px-table ens-table">
                  <thead>
                    <tr>
                      <th>Numéro</th>
                      <th>Nom</th>
                      <th>Prénom</th>
                      <th>Spécialité</th>
                      {!canViewFinanceData && <th>Adresse e-mail</th>}
                      {!canViewFinanceData && <th>Téléphone</th>}
                      {!canViewFinanceData && <th>Modules</th>}
                      {!canViewFinanceData && canViewSensitive && <th>N° pièce d'identité</th>}
                      {!canViewFinanceData && canViewSensitive && <th>N° compte bancaire (RIB)</th>}
                      {canViewFinanceData && <th>Séances</th>}
                      {canViewFinanceData && <th>Temps planifié</th>}
                      {canViewFinanceData && <th>Temps réalisé</th>}
                      {canViewFinanceData && <th>Taux réal.</th>}
                      {canViewFinanceData && <th>Montant</th>}
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {formateurs.length > 0 ? formateurs.map((f) => (
                      <tr key={f.id}>
                        <td>{f.numerobadge
                          ? <span className="badge-bg-info ens-num">{f.numerobadge}</span>
                          : <span className="px-dash">—</span>}</td>
                        <td><strong>{f.nom}</strong></td>
                        <td>{f.prenom}</td>
                        <td>{f.specialite || <span className="px-dash">—</span>}</td>
                        {!canViewFinanceData && <td>{f.email || <span className="px-dash">—</span>}</td>}
                        {!canViewFinanceData && <td>{f.telephone || <span className="px-dash">—</span>}</td>}
                        {!canViewFinanceData && (
                          <td><span className={`ens-count${f.nb_formations ? ' ens-count--on' : ''}`}>{f.nb_formations || 0}</span></td>
                        )}
                        {!canViewFinanceData && canViewSensitive && <td className="small">{f.numero_piece_identite || '-'}</td>}
                        {!canViewFinanceData && canViewSensitive && <td className="small">{f.numero_compte_bancaire || '-'}</td>}
                        {canViewFinanceData && (
                          <td><span className="badge-bg-secondary">{f.sessions_count ?? 0}</span></td>
                        )}
                        {canViewFinanceData && (
                          <td><span className="badge-bg-info">{fmtDuration(f.total_duree_minutes)}</span></td>
                        )}
                        {canViewFinanceData && (
                          <td><span className="badge-bg-success">{fmtDuration(f.total_duree_realisee_minutes)}</span></td>
                        )}
                        {canViewFinanceData && (
                          <td>{(f.statistiques?.taux_realisation_pct ?? 0)}%</td>
                        )}
                        {canViewFinanceData && (
                          <td style={{ whiteSpace: 'nowrap', fontWeight: 600 }}>{formatMoney(f.montant_total_realise)} FCFA</td>
                        )}
                        {canViewFinanceData && (
                          <td>
                            <div className="btn-group" role="group">
                              <button type="button" onClick={() => openFinanceDetail(f)} className="btn btn-outline-primary btn-sm" title="Voir le détail par séance">
                                <i className="bi bi-eye me-1"></i>Détail
                              </button>
                              <button type="button" onClick={() => exportFinanceSummary(f, 'excel')} className="btn btn-outline-success btn-sm" title="Exporter en Excel">
                                <i className="bi bi-file-earmark-spreadsheet me-1"></i>Excel
                              </button>
                              <button type="button" onClick={() => exportFinanceSummary(f, 'pdf')} className="btn btn-outline-danger btn-sm" title="Exporter en PDF">
                                <i className="bi bi-file-earmark-pdf me-1"></i>PDF
                              </button>
                            </div>
                          </td>
                        )}
                        <td>
                          <div className="btn-group">
                            <button onClick={() => setDetailFormateur(f)} className="btn btn-outline-primary btn-sm" title="Voir la fiche détaillée">
                              <i className="bi bi-eye me-1"></i>Détail
                            </button>
                            {canEdit && (
                              <button onClick={() => openEdit(f)} className="btn btn-outline-secondary btn-sm" title="Modifier">
                                <i className="bi bi-pencil"></i>
                              </button>
                            )}
                            {canDelete && (
                              <button onClick={() => handleDelete(f.id)} className="btn btn-outline-danger btn-sm" title="Supprimer">
                                <i className="bi bi-trash"></i>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )) : (
                      <tr><td colSpan={canViewFinanceData ? 10 : (8 + (canViewSensitive ? 2 : 0))} className="text-center py-4 text-muted">
                        <span className="px-empty">
                          <span className="px-empty-badge"><i className="bi bi-person-x"></i></span>
                          Aucun enseignant trouvé
                        </span>
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                totalItems={totalCount}
                pageSize={50}
              />
            </>
          )}
        </div>
      </div>

      {confirmDialog && (
        <ConfirmModal
          message={confirmDialog.message}
          detail={confirmDialog.detail}
          onConfirm={() => { setConfirmDialog(null); confirmDialog.onConfirm() }}
          onCancel={() => setConfirmDialog(null)}
        />
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5>{editingId ? "Modifier l'enseignant" : 'Nouvel enseignant'}</h5>
              <button className="btn-close" onClick={() => setShowModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                {formError && <div className="alert alert-danger">{formError}</div>}
                <div className="form-group">
                  <label className="form-label">N° Badge <small className="text-muted">(auto-généré si vide)</small></label>
                  <input type="text" className="form-control" placeholder="Ex : F0042" value={form.numerobadge} onChange={e => setForm({...form, numerobadge: e.target.value})} />
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Nom *</label>
                    <input type="text" className="form-control" required value={form.nom} onChange={e => setForm({...form, nom: e.target.value})} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Prénom *</label>
                    <input type="text" className="form-control" required value={form.prenom} onChange={e => setForm({...form, prenom: e.target.value})} />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Spécialité</label>
                  <select className="form-control" value={form.specialite} onChange={e => setForm({...form, specialite: e.target.value})}>
                    <option value="">— Sélectionner une spécialité —</option>
                    {refModules.map(m => (
                      <option key={m.id} value={m.intitule}>{m.intitule}</option>
                    ))}
                  </select>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Adresse e-mail</label>
                    <input type="email" className="form-control" value={form.email} onChange={e => setForm({...form, email: e.target.value})} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Téléphone</label>
                    <input type="text" className="form-control" value={form.telephone} onChange={e => setForm({...form, telephone: e.target.value})} />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Organisation</label>
                  <input type="text" className="form-control" value={form.organisation} onChange={e => setForm({...form, organisation: e.target.value})} />
                </div>
                <div className="form-group">
                  <label className="form-label">Observations <small className="text-muted">(notes internes)</small></label>
                  <textarea className="form-control" rows={4} value={form.observations} onChange={e => setForm({...form, observations: e.target.value})} placeholder="Notes / observations sur l'enseignant…" />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Annuler</button>
                <button type="submit" className="btn btn-dfrc" disabled={saving}>{saving ? 'Enregistrement...' : (editingId ? 'Enregistrer' : 'Créer')}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Fiche formateur à onglets (lecture seule) */}
      {detailFormateur && (
        <FormateurFicheModal
          formateur={detailFormateur}
          onClose={() => setDetailFormateur(null)}
          canViewSensitive={canViewSensitive}
          onExport={exportFicheFormateur}
          exporting={exportingFiche}
        />
      )}
    </div>
  )
}
