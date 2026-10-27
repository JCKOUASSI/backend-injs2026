import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import FinancePageShell, { FinanceNavActions } from '../components/finance/FinancePageShell'
import { formatMoney } from '../components/FinanceStatsGrid'
import {
  buildFinanceListSearchParams,
  FINANCE_QUERY_STORAGE_KEY,
  resolveFinancePeriod,
} from '../utils/financePeriod'
import { usePersistedListQuery } from '../hooks/usePersistedListQuery'

const formatDateTime = (value) => {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '-'
  return d.toLocaleString('fr-FR')
}

export default function FinanceParametrage() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const canEdit = user?.role === 'FINANCE'
  const [searchParams] = useSearchParams()

  usePersistedListQuery(
    FINANCE_QUERY_STORAGE_KEY,
    () => {
      return buildFinanceListSearchParams(resolveFinancePeriod(), {})
    },
    [searchParams],
  )

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [tarifs, setTarifs] = useState([])
  const [toleranceSettings, setToleranceSettings] = useState({
    tolerance_active: false,
    tolerance_minutes: 30,
    tolerance_pct: 5,
  })
  const [exportSettings, setExportSettings] = useState({
    afficher_montants_exports: true,
    export_titre_document: 'FICHE DE PAIE DÉTAILLÉE',
    export_entete_ligne1: '',
    export_entete_ligne2: '',
    export_organisme: '',
    export_adresse: '',
    export_reference_prefix: 'EFI',
    export_mention_legale: '',
    export_signataire_nom: '',
    export_signataire_fonction: '',
    export_contacts: '',
    export_pied_page_titre: '',
    export_pied_page_texte: '',
  })
  const [meta, setMeta] = useState({ updated_at: null, updated_by: null })

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const res = await api.get('/formations/finance/settings/')
        setTarifs(
          (res.data?.tarifs_formations ?? []).map((t) => ({
            ...t,
            prix_heure_realisee: t.prix_heure_realisee != null ? String(t.prix_heure_realisee) : '',
          })),
        )
        setToleranceSettings({
          tolerance_active: res.data?.tolerance_active === true,
          tolerance_minutes: res.data?.tolerance_minutes ?? 30,
          tolerance_pct: res.data?.tolerance_pct ?? 5,
        })
        setExportSettings({
          afficher_montants_exports: res.data?.afficher_montants_exports !== false,
          export_titre_document: res.data?.export_titre_document || 'FICHE DE PAIE DÉTAILLÉE',
          export_entete_ligne1: res.data?.export_entete_ligne1 || '',
          export_entete_ligne2: res.data?.export_entete_ligne2 || '',
          export_organisme: res.data?.export_organisme || '',
          export_adresse: res.data?.export_adresse || '',
          export_reference_prefix: res.data?.export_reference_prefix || 'EFI',
          export_mention_legale: res.data?.export_mention_legale || '',
          export_signataire_nom: res.data?.export_signataire_nom || '',
          export_signataire_fonction: res.data?.export_signataire_fonction || '',
          export_contacts: res.data?.export_contacts || '',
          export_pied_page_titre: res.data?.export_pied_page_titre || '',
          export_pied_page_texte: res.data?.export_pied_page_texte || '',
        })
        setMeta({
          updated_at: res.data?.updated_at || null,
          updated_by: res.data?.updated_by || null,
        })
      } catch {
        showToast('Impossible de charger les paramètres finance.', 'error')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [showToast])

  const handleTarifChange = (id, value) => {
    setTarifs((prev) =>
      prev.map((t) => (t.id === id ? { ...t, prix_heure_realisee: value } : t)),
    )
  }

  const parsePrix = (raw) => {
    if (raw === '' || raw == null) return null
    const value = Number(String(raw).replace(',', '.'))
    if (Number.isNaN(value) || value < 0) return NaN
    return value
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!canEdit) return

    const tarifsPayload = []
    for (const t of tarifs) {
      const value = parsePrix(t.prix_heure_realisee)
      if (Number.isNaN(value)) {
        showToast(`Tarif invalide pour « ${t.intitule} ».`, 'error')
        return
      }
      tarifsPayload.push({ id: t.id, prix_heure_realisee: value })
    }

    setSaving(true)
    try {
      const res = await api.patch('/formations/finance/settings/', {
        tarifs_formations: tarifsPayload,
        ...toleranceSettings,
        tolerance_minutes: Number(toleranceSettings.tolerance_minutes) || 0,
        tolerance_pct: Number(toleranceSettings.tolerance_pct) || 0,
        ...exportSettings,
      })
      setTarifs(
        (res.data?.tarifs_formations ?? []).map((t) => ({
          ...t,
          prix_heure_realisee: t.prix_heure_realisee != null ? String(t.prix_heure_realisee) : '',
        })),
      )
      setMeta({
        updated_at: res.data?.updated_at || null,
        updated_by: res.data?.updated_by || null,
      })
      setToleranceSettings({
        tolerance_active: res.data?.tolerance_active === true,
        tolerance_minutes: res.data?.tolerance_minutes ?? 30,
        tolerance_pct: res.data?.tolerance_pct ?? 5,
      })
      setExportSettings({
        afficher_montants_exports: res.data?.afficher_montants_exports !== false,
        export_titre_document: res.data?.export_titre_document || 'FICHE DE PAIE DÉTAILLÉE',
        export_entete_ligne1: res.data?.export_entete_ligne1 || '',
        export_entete_ligne2: res.data?.export_entete_ligne2 || '',
        export_organisme: res.data?.export_organisme || '',
        export_adresse: res.data?.export_adresse || '',
        export_reference_prefix: res.data?.export_reference_prefix || 'EFI',
        export_mention_legale: res.data?.export_mention_legale || '',
        export_signataire_nom: res.data?.export_signataire_nom || '',
        export_signataire_fonction: res.data?.export_signataire_fonction || '',
        export_contacts: res.data?.export_contacts || '',
        export_pied_page_titre: res.data?.export_pied_page_titre || '',
        export_pied_page_texte: res.data?.export_pied_page_texte || '',
      })
      showToast('Paramètres enregistrés')
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur lors de la sauvegarde', 'error')
    } finally {
      setSaving(false)
    }
  }

  const setExportField = (key, value) => {
    setExportSettings((prev) => ({ ...prev, [key]: value }))
  }

  const setToleranceField = (key, value) => {
    setToleranceSettings((prev) => ({ ...prev, [key]: value }))
  }

  const tarifsActifs = tarifs.filter((t) => t.actif !== false)
  const tarifsInactifs = tarifs.filter((t) => t.actif === false)

  const renderTarifRow = (t) => {
    const hasTarif = t.prix_heure_realisee !== '' && t.prix_heure_realisee != null
    return (
      <tr key={t.id} className={t.actif === false ? 'text-muted' : ''}>
        <td>
          {t.intitule}
          {t.actif === false && (
            <span className="badge bg-secondary ms-2" style={{ fontSize: '0.65rem' }}>Inactif</span>
          )}
        </td>
        <td>
          <div className="input-group input-group-sm">
            <input
              type="number"
              className="form-control"
              min="0"
              step="0.01"
              placeholder="—"
              value={t.prix_heure_realisee}
              onChange={(e) => handleTarifChange(t.id, e.target.value)}
              disabled={!canEdit || saving}
            />
            <span className="input-group-text">FCFA / h</span>
          </div>
        </td>
        <td className="text-muted small">
          {hasTarif
            ? `${formatMoney(Number(t.prix_heure_realisee))} FCFA / h`
            : <span className="text-warning">Non défini</span>}
        </td>
      </tr>
    )
  }

  return (
    <FinancePageShell
      title="Paramétrage Finance"
      subtitle="Tarifs horaires et exports"
      icon="bi-sliders"
      actions={<FinanceNavActions active="parametrage" />}
      showPeriodFilter={false}
    >
      {loading ? (
        <div className="loading py-5"><div className="spinner"></div></div>
      ) : (
        <div className="finance-settings-card finance-settings-card-wide">
          {!canEdit && (
            <div className="alert alert-secondary py-2 small mb-3">
              <i className="bi bi-eye me-1"></i>
              Consultation seule.
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <h6 className="fw-semibold mb-3">
              <i className="bi bi-journal-bookmark me-2"></i>
              Tarifs par formation
            </h6>

            {tarifs.length === 0 ? (
              <p className="text-muted small">Aucune formation dans le référentiel.</p>
            ) : (
              <div className="finance-table-wrap mb-4">
                <table className="finance-table finance-settings-table">
                  <thead>
                    <tr>
                      <th>Formation (cycle)</th>
                      <th style={{ width: 240 }}>Tarif horaire</th>
                      <th style={{ width: 180 }}>Tarif appliqué</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tarifsActifs.map(renderTarifRow)}
                    {tarifsInactifs.map(renderTarifRow)}
                  </tbody>
                </table>
              </div>
            )}

            <hr className="my-4" />

            <h6 className="fw-semibold mb-3">
              <i className="bi bi-shield-check me-2"></i>
              Tolérance horaire
            </h6>

            <div className="form-check form-switch mb-3">
              <input
                type="checkbox"
                className="form-check-input"
                id="tolerance_active"
                checked={toleranceSettings.tolerance_active}
                onChange={(e) => setToleranceField('tolerance_active', e.target.checked)}
                disabled={!canEdit || saving}
              />
              <label className="form-check-label" htmlFor="tolerance_active">
                Activer la marge de tolérance sur les volumes réalisés inférieurs au planifié
              </label>
            </div>

            {toleranceSettings.tolerance_active && (
              <div className="row g-3 mb-3">
                <div className="col-md-4">
                  <label className="form-label">Tolérance fixe (minutes)</label>
                  <input
                    type="number"
                    className="form-control"
                    min="0"
                    step="1"
                    value={toleranceSettings.tolerance_minutes}
                    onChange={(e) => setToleranceField('tolerance_minutes', e.target.value)}
                    disabled={!canEdit || saving}
                  />
                </div>
                <div className="col-md-4">
                  <label className="form-label">Tolérance relative (%)</label>
                  <div className="input-group">
                    <input
                      type="number"
                      className="form-control"
                      min="0"
                      max="100"
                      step="0.1"
                      value={toleranceSettings.tolerance_pct}
                      onChange={(e) => setToleranceField('tolerance_pct', e.target.value)}
                      disabled={!canEdit || saving}
                    />
                    <span className="input-group-text">%</span>
                  </div>
                </div>
                <div className="col-12">
                  <p className="text-muted small mb-0">
                    Le seuil appliqué est le plus favorable entre la marge en minutes et le pourcentage du volume planifié.
                    Les formateurs dans la tolérance sont signalés en orange ; hors tolérance en rouge.
                  </p>
                </div>
              </div>
            )}

            <hr className="my-4" />

            <h6 className="fw-semibold mb-3">
              <i className="bi bi-file-earmark-text me-2"></i>
              Exports PDF / Excel
            </h6>

            <div className="form-check form-switch mb-3">
              <input
                type="checkbox"
                className="form-check-input"
                id="afficher_montants_exports"
                checked={exportSettings.afficher_montants_exports}
                onChange={(e) => setExportField('afficher_montants_exports', e.target.checked)}
                disabled={!canEdit || saving}
              />
              <label className="form-check-label" htmlFor="afficher_montants_exports">
                Afficher les montants par défaut sur les exports
              </label>
            </div>

            <div className="row g-3 mb-3">
              <div className="col-md-6">
                <label className="form-label">Titre du document</label>
                <input
                  type="text"
                  className="form-control"
                  value={exportSettings.export_titre_document}
                  onChange={(e) => setExportField('export_titre_document', e.target.value)}
                  disabled={!canEdit || saving}
                />
              </div>
              <div className="col-md-6">
                <label className="form-label">Préfixe référence</label>
                <input
                  type="text"
                  className="form-control"
                  value={exportSettings.export_reference_prefix}
                  onChange={(e) => setExportField('export_reference_prefix', e.target.value)}
                  disabled={!canEdit || saving}
                  placeholder="EFI"
                />
              </div>
              <div className="col-md-6">
                <label className="form-label">En-tête ligne 1</label>
                <input
                  type="text"
                  className="form-control"
                  value={exportSettings.export_entete_ligne1}
                  onChange={(e) => setExportField('export_entete_ligne1', e.target.value)}
                  disabled={!canEdit || saving}
                  placeholder="République de Côte d'Ivoire"
                />
              </div>
              <div className="col-md-6">
                <label className="form-label">En-tête ligne 2</label>
                <input
                  type="text"
                  className="form-control"
                  value={exportSettings.export_entete_ligne2}
                  onChange={(e) => setExportField('export_entete_ligne2', e.target.value)}
                  disabled={!canEdit || saving}
                  placeholder="Ministère / Direction"
                />
              </div>
              <div className="col-md-6">
                <label className="form-label">Organisme</label>
                <input
                  type="text"
                  className="form-control"
                  value={exportSettings.export_organisme}
                  onChange={(e) => setExportField('export_organisme', e.target.value)}
                  disabled={!canEdit || saving}
                  placeholder="INJS"
                />
              </div>
              <div className="col-md-6">
                <label className="form-label">Signataire — nom</label>
                <input
                  type="text"
                  className="form-control"
                  value={exportSettings.export_signataire_nom}
                  onChange={(e) => setExportField('export_signataire_nom', e.target.value)}
                  disabled={!canEdit || saving}
                />
              </div>
              <div className="col-12">
                <label className="form-label">Coordonnées en-tête (synthèse globale)</label>
                <textarea
                  className="form-control"
                  rows={2}
                  value={exportSettings.export_adresse}
                  onChange={(e) => setExportField('export_adresse', e.target.value)}
                  disabled={!canEdit || saving}
                  placeholder="Optionnel — affiché en haut des exports synthèse / paie globale"
                />
              </div>
              <div className="col-md-6">
                <label className="form-label">Signataire — fonction</label>
                <input
                  type="text"
                  className="form-control"
                  value={exportSettings.export_signataire_fonction}
                  onChange={(e) => setExportField('export_signataire_fonction', e.target.value)}
                  disabled={!canEdit || saving}
                />
              </div>
              <div className="col-md-6">
                <label className="form-label">Note NB (sous le tableau modules)</label>
                <textarea
                  className="form-control"
                  rows={2}
                  value={exportSettings.export_mention_legale}
                  onChange={(e) => setExportField('export_mention_legale', e.target.value)}
                  disabled={!canEdit || saving}
                  placeholder="NB : Le volume horaire indiqué ne tient pas compte des heures…"
                />
              </div>
              <div className="col-12">
                <label className="form-label">Contacts (fiche récap formateur)</label>
                <textarea
                  className="form-control"
                  rows={4}
                  value={exportSettings.export_contacts}
                  onChange={(e) => setExportField('export_contacts', e.target.value)}
                  disabled={!canEdit || saving}
                  placeholder={'Pour toute information complémentaire, veuillez contacter :\nNom et téléphone du contact 1\nNom et téléphone du contact 2'}
                />
                <p className="text-muted small mb-0 mt-1">
                  Une ligne par phrase ou contact. Laissez vide pour conserver les contacts par défaut de l'INJS.
                </p>
              </div>
            </div>

            <h6 className="fw-semibold mb-3 mt-2">
              <i className="bi bi-layout-text-window-reverse me-2"></i>
              Pied de page (fiche récap formateur)
            </h6>
            <div className="row g-3 mb-3">
              <div className="col-md-6">
                <label className="form-label">Titre</label>
                <input
                  type="text"
                  className="form-control"
                  value={exportSettings.export_pied_page_titre}
                  onChange={(e) => setExportField('export_pied_page_titre', e.target.value)}
                  disabled={!canEdit || saving}
                  placeholder="DOCUMENT CONFIDENTIEL"
                />
              </div>
              <div className="col-12">
                <label className="form-label">Texte institutionnel</label>
                <textarea
                  className="form-control"
                  rows={5}
                  value={exportSettings.export_pied_page_texte}
                  onChange={(e) => setExportField('export_pied_page_texte', e.target.value)}
                  disabled={!canEdit || saving}
                  placeholder="MINISTERE D'ETAT, MINISTERE DE LA FONCTION PUBLIQUE… Bouaké / Abidjan : coordonnées"
                />
                <p className="text-muted small mb-0 mt-1">
                  Affiché en bas de la fiche PDF/Excel formateur (sous les contacts). Laissez vide pour le texte INJS par défaut.
                </p>
              </div>
            </div>

            {(meta.updated_at || meta.updated_by) && (
              <p className="text-muted small mt-3 mb-3">
                <i className="bi bi-clock-history me-1"></i>
                Dernière mise à jour : {formatDateTime(meta.updated_at)}
                {meta.updated_by ? ` par ${meta.updated_by}` : ''}
              </p>
            )}

            {canEdit && (
              <button type="submit" className="btn btn-dfrc mt-2" disabled={saving}>
                {saving ? 'Enregistrement…' : (
                  <><i className="bi bi-check-lg me-1"></i>Enregistrer</>
                )}
              </button>
            )}
          </form>
        </div>
      )}
    </FinancePageShell>
  )
}
