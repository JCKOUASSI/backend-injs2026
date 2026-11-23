import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { FinanceStatsGrid, FinanceModulesList, formatMoney } from '../FinanceStatsGrid'
import FinanceModulesRecap from './FinanceModulesRecap'
import { FinanceSessionsByGroupeTable } from './FinanceSessionsByGroupe'
import FinanceToleranceBadge from './FinanceToleranceBadge'
import FinanceProposeAjustementModal from './FinanceProposeAjustementModal'
import FinancePaieModulesTable from './FinancePaieModulesTable'

const FINANCE_DETAIL_TABS = [
  { id: 'statistiques', label: 'Statistiques', icon: 'bi-graph-up' },
  { id: 'identite', label: 'Identité', icon: 'bi-person-badge' },
  { id: 'recap_modules', label: 'Récap modules', icon: 'bi-list-check' },
  { id: 'modules', label: 'Modules', icon: 'bi-journal-bookmark' },
  { id: 'seances', label: 'Séances', icon: 'bi-clock-history' },
  { id: 'paie', label: 'Fiche de paie', icon: 'bi-cash-coin' },
]

export default function FinanceDetailModal({
  financeDetail,
  financeDetailLoading,
  financeDetailTab,
  setFinanceDetailTab,
  onClose,
  formatDuration,
  formatDate,
  exportFinanceSummary,
  exportAfficherMontants = true,
  onExportMontantsChange,
  financeStatsForGrid,
  canEditSensitive = false,
  canViewSensitive = false,
  onSensitiveSaved,
  canProposeAjustement = false,
  onRefreshDetail,
}) {
  const { showToast } = useToast()
  const [sensitive, setSensitive] = useState({ numero_piece_identite: '', numero_compte_bancaire: '' })
  const [savingSensitive, setSavingSensitive] = useState(false)
  const [ajustementSession, setAjustementSession] = useState(null)

  useEffect(() => {
    if (financeDetail) {
      setSensitive({
        numero_piece_identite: financeDetail.numero_piece_identite || '',
        numero_compte_bancaire: financeDetail.numero_compte_bancaire || '',
      })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [
    financeDetail?.id,
    financeDetail?.numero_piece_identite,
    financeDetail?.numero_compte_bancaire,
  ])

  const saveSensitive = async () => {
    if (!financeDetail?.id || !canEditSensitive) return
    setSavingSensitive(true)
    try {
      const res = await api.patch(`/formations/formateurs/${financeDetail.id}/donnees-sensibles/`, sensitive)
      showToast('Coordonnées bancaires enregistrées')
      onSensitiveSaved?.(res.data)
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur lors de la sauvegarde', 'error')
    } finally {
      setSavingSensitive(false)
    }
  }
  const sessionsByGroupe = financeDetail?.sessions_by_groupe ?? []

  if (!financeDetail) return null

  return (
    <div className="modal-overlay finance-modal" onClick={onClose}>
      <div
        className="modal-content"
        style={{ width: 'min(96vw, 1100px)', maxWidth: '1100px', maxHeight: '92vh', display: 'flex', flexDirection: 'column' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h5>
            <i className="bi bi-person-video3 me-2"></i>
            {financeDetail.prenom} {financeDetail.nom}
            {financeDetail.numerobadge && (
              <small className="ms-2 opacity-75">({financeDetail.numerobadge})</small>
            )}
          </h5>
          <button type="button" className="btn-close" disabled={financeDetailLoading} onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body" style={{ overflowY: 'auto', flex: 1, padding: '1rem 1.25rem' }}>
          {financeDetailLoading ? (
            <div className="loading py-5"><div className="spinner"></div></div>
          ) : (
            <>
              <ul className="finance-detail-tabs" role="tablist">
                {FINANCE_DETAIL_TABS.map((tab) => (
                  <li key={tab.id} role="presentation">
                    <button
                      type="button"
                      className={`finance-detail-tab${financeDetailTab === tab.id ? ' active' : ''}`}
                      onClick={() => setFinanceDetailTab(tab.id)}
                    >
                      <i className={`bi ${tab.icon}`}></i>
                      <span>{tab.label}</span>
                    </button>
                  </li>
                ))}
              </ul>

              <div className="finance-modal-summary">
                <span><i className="bi bi-clock"></i>Planifié <strong>{formatDuration(financeDetail.total_duree_minutes)}</strong></span>
                <span><i className="bi bi-clock-history"></i>Réalisé <strong>{formatDuration(financeDetail.total_duree_realisee_minutes)}</strong></span>
                <span><i className="bi bi-percent"></i>Taux <strong>{financeDetail.statistiques?.taux_realisation_pct ?? 0}%</strong></span>
                {financeDetail.tolerance && (
                  <span>
                    <i className="bi bi-shield-check"></i>
                    Statut <FinanceToleranceBadge tolerance={financeDetail.tolerance} showInactive />
                  </span>
                )}
                <span><i className="bi bi-cash-stack"></i>À verser <strong>{formatMoney(financeDetail.montant_total_realise)} FCFA</strong></span>
              </div>

              {financeDetailTab === 'statistiques' && (
                <FinanceStatsGrid
                  stats={financeStatsForGrid(financeDetail)}
                  montant={financeDetail.montant_total_realise}
                />
              )}

              {financeDetailTab === 'identite' && (
                <div className="grid-2">
                  <div><small className="text-muted">N° Badge</small><div><span className="badge-bg-info">{financeDetail.numerobadge || '-'}</span></div></div>
                  <div><small className="text-muted">Nom</small><div><strong>{financeDetail.nom || '-'}</strong></div></div>
                  <div><small className="text-muted">Prénom</small><div><strong>{financeDetail.prenom || '-'}</strong></div></div>
                  <div><small className="text-muted">Spécialité</small><div>{financeDetail.specialite || '-'}</div></div>
                  <div><small className="text-muted">Grade(s)</small><div>{financeDetail.grades || '-'}</div></div>
                  <div><small className="text-muted">Groupe(s)</small><div>{financeDetail.groupes || '-'}</div></div>
                  <div><small className="text-muted">E-mail</small><div>{financeDetail.email || '-'}</div></div>
                  <div><small className="text-muted">Téléphone</small><div>{financeDetail.telephone || '-'}</div></div>
                  <div><small className="text-muted">Organisation</small><div>{financeDetail.organisation || '-'}</div></div>
                  <div><small className="text-muted">Modules (période)</small><div><span className="badge-bg-success">{financeDetail.nb_formations ?? 0}</span></div></div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <small className="text-muted">Secrétariat(s)</small>
                    <div>
                      {Array.isArray(financeDetail.secretariats_noms) && financeDetail.secretariats_noms.length > 0
                        ? financeDetail.secretariats_noms.join(', ')
                        : '-'}
                    </div>
                  </div>
                  {financeDetail.created_at && (
                    <div><small className="text-muted">Enregistré le</small><div>{formatDate(financeDetail.created_at)}</div></div>
                  )}
                  {canViewSensitive && (
                    <>
                      <div style={{ gridColumn: '1 / -1' }}>
                        <hr className="my-2" />
                        <small className="text-muted fw-semibold">Données confidentielles (finance)</small>
                      </div>
                      <div>
                        <small className="text-muted">N° pièce d&apos;identité</small>
                        {canEditSensitive ? (
                          <input
                            type="text"
                            className="form-control form-control-sm mt-1"
                            value={sensitive.numero_piece_identite}
                            onChange={(e) => setSensitive((s) => ({ ...s, numero_piece_identite: e.target.value }))}
                            disabled={savingSensitive}
                          />
                        ) : (
                          <div>{financeDetail.numero_piece_identite || '-'}</div>
                        )}
                      </div>
                      <div>
                        <small className="text-muted">N° compte bancaire</small>
                        {canEditSensitive ? (
                          <input
                            type="text"
                            className="form-control form-control-sm mt-1"
                            value={sensitive.numero_compte_bancaire}
                            onChange={(e) => setSensitive((s) => ({ ...s, numero_compte_bancaire: e.target.value }))}
                            disabled={savingSensitive}
                          />
                        ) : (
                          <div>{financeDetail.numero_compte_bancaire || '-'}</div>
                        )}
                      </div>
                      {canEditSensitive && (
                        <div style={{ gridColumn: '1 / -1' }}>
                          <button
                            type="button"
                            className="btn btn-dfrc btn-sm"
                            disabled={savingSensitive}
                            onClick={saveSensitive}
                          >
                            {savingSensitive ? 'Enregistrement…' : 'Enregistrer les données bancaires'}
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {financeDetailTab === 'recap_modules' && (
                <FinanceModulesRecap
                  modules={financeDetail.recap_modules ?? financeDetail.modules}
                  formatDuration={formatDuration}
                />
              )}

              {financeDetailTab === 'modules' && (
                <FinanceModulesList modules={financeDetail.modules} formatDuration={formatDuration} />
              )}

              {financeDetailTab === 'seances' && (
                <>
                  {canProposeAjustement && (
                    <p className="small text-muted mb-2">
                      <i className="bi bi-arrow-left-right me-1"></i>
                      Cliquez sur <i className="bi bi-arrow-left-right"></i> pour proposer un ajustement sur une séance terminée.
                    </p>
                  )}
                  <FinanceSessionsByGroupeTable
                    groups={sessionsByGroupe}
                    formatDuration={formatDuration}
                    formatMoney={formatMoney}
                    showPointage
                    showAjustement={canProposeAjustement}
                    onProposeAjustement={setAjustementSession}
                  />
                </>
              )}

              {financeDetailTab === 'paie' && (
                <>
                  <div className="finance-paie-hero">
                    <div className="grid-2">
                      <div>
                        <small className="text-muted">Tarif horaire</small>
                        <div style={{ fontWeight: 600 }}>
                          Selon la formation
                        </div>
                      </div>
                      <div>
                        <small className="text-muted">Temps réalisé</small>
                        <div style={{ fontWeight: 600 }}>
                          {formatDuration(financeDetail.total_duree_realisee_minutes)}
                        </div>
                      </div>
                      <div style={{ gridColumn: '1 / -1' }}>
                        <small className="text-muted">Montant total à verser</small>
                        <div className="finance-paie-total">{formatMoney(financeDetail.montant_total_realise ?? 0)} FCFA</div>
                      </div>
                    </div>
                  </div>

                  {(financeDetail.modules ?? []).some((m) => !(Number(m.prix_heure_realisee) > 0)) && (
                    <div className="alert alert-warning py-2 small">
                      <i className="bi bi-exclamation-triangle me-1"></i>
                      Tarif non défini pour une ou plusieurs formations — <Link to="/finance-parametrage">Paramétrage Finance</Link>
                    </div>
                  )}

                  {(financeDetail.recap_modules ?? financeDetail.modules ?? []).length > 0 && (
                    <FinancePaieModulesTable modules={financeDetail.recap_modules ?? financeDetail.modules} />
                  )}

                  {sessionsByGroupe.length > 0 ? (
                    <>
                      {canProposeAjustement && (
                        <p className="small text-muted mb-2">
                          <i className="bi bi-arrow-left-right me-1"></i>
                          Ajustement horaire disponible sur chaque ligne (validation Direction/Finance).
                        </p>
                      )}
                      <FinanceSessionsByGroupeTable
                        groups={sessionsByGroupe}
                        formatDuration={formatDuration}
                        formatMoney={formatMoney}
                        showMontant
                        showAjustement={canProposeAjustement}
                        onProposeAjustement={setAjustementSession}
                      />
                      <div className="finance-paie-total mt-3" style={{ textAlign: 'right' }}>
                        Total à verser : {formatMoney(financeDetail.montant_total_realise ?? 0)} FCFA
                      </div>
                    </>
                  ) : (
                    <div className="finance-empty"><i className="bi bi-cash"></i>Aucune donnée de paie</div>
                  )}
                </>
              )}
            </>
          )}
        </div>

        <div className="modal-footer">
          {!financeDetailLoading && (
            <div className="d-flex flex-wrap align-items-center gap-3 me-auto">
              <label className="form-check mb-0 small" style={{ cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  className="form-check-input me-1"
                  checked={exportAfficherMontants}
                  onChange={(e) => onExportMontantsChange?.(e.target.checked)}
                />
                Afficher les montants sur l&apos;export
              </label>
              <div className="btn-group">
                <button
                  type="button"
                  className="btn btn-outline-success btn-sm"
                  onClick={() => exportFinanceSummary(financeDetail, 'excel', exportAfficherMontants)}
                >
                  <i className="bi bi-file-earmark-spreadsheet me-1"></i>Excel
                </button>
                <button
                  type="button"
                  className="btn btn-outline-danger btn-sm"
                  onClick={() => exportFinanceSummary(financeDetail, 'pdf', exportAfficherMontants)}
                >
                  <i className="bi bi-file-earmark-pdf me-1"></i>PDF
                </button>
              </div>
            </div>
          )}
          {canProposeAjustement && (
            <Link to="/finance-ajustements" className="btn btn-outline-warning btn-sm">
              <i className="bi bi-inbox me-1"></i>File d&apos;attente
            </Link>
          )}
          <button type="button" className="btn btn-secondary" disabled={financeDetailLoading} onClick={onClose}>Fermer</button>
        </div>
      </div>

      <FinanceProposeAjustementModal
        open={!!ajustementSession}
        session={ajustementSession}
        formateurId={financeDetail.id}
        formateurLabel={`${financeDetail.prenom} ${financeDetail.nom}`.trim()}
        onClose={() => setAjustementSession(null)}
        onSuccess={onRefreshDetail}
      />
    </div>
  )
}
