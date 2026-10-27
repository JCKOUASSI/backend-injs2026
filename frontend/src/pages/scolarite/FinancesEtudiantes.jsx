import React, { useCallback, useEffect, useState } from 'react'
import api from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

const BADGE_STATUT_PA = {
  INITIE: 'secondary', EN_ATTENTE: 'info', CONFIRME: 'success',
  ECHOUE: 'warning', ANNULE: 'dark', REMBOSSE: 'dark', RAPPROCHE: 'primary',
}
const BADGE_STATUT_LIGNE = {
  IMPAYE: 'danger', PAYE: 'success', PARTIELLEMENT_PAYE: 'warning', COMPLETE: 'success',
}

export default function FinancesEtudiantes() {
  const { user } = useAuth()
  const toast = useToast()
  // FINANCE / DIRECTION / ADMIN : opérations sensibles (confirmer paiement, remboursement, rapprochement)
  const peutConfirmer = ['FINANCE', 'DIRECTION', 'ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'].includes(user?.role)
  const peutEcrire = peutConfirmer || ['SECRETARIAT', 'CHEF_SECRETARIAT'].includes(user?.role)

  const [echeanciers, setEcheanciers] = useState([])
  const [paiements, setPaiements] = useState([])
  const [chargement, setChargement] = useState(true)
  const [enCours, setEnCours] = useState(false)
  const [onglet, setOnglet] = useState('echeanciers')
  const [formPaiement, setFormPaiement] = useState({
    etudiant_id: '', nature: 'DOSSIER', montant: '', devise: 'XOF', mode: 'CAISSE', transaction_externe: '',
  })

  const charger = useCallback(async () => {
    setChargement(true)
    try {
      const [ec, pa] = await Promise.all([
        api.get('/finances-etudiantes/echeanciers/'),
        api.get('/finances-etudiantes/paiements/'),
      ])
      setEcheanciers(ec.data.results || ec.data)
      setPaiements(pa.data.results || pa.data)
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Chargement des finances étudiantes impossible.', 'error')
    } finally {
      setChargement(false)
    }
  }, [toast])

  useEffect(() => { charger() }, [charger])

  const creerPaiement = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await api.post('/finances-etudiantes/paiements/', formPaiement)
      toast.showToast('Paiement enregistré (idempotent : pivote si la référence existe déjà).')
      setFormPaiement({ etudiant_id: '', nature: 'DOSSIER', montant: '', devise: 'XOF', mode: 'CAISSE', transaction_externe: '' })
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Enregistrement du paiement impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const confirmer = async (p) => {
    if (!window.confirm(`Confirmer le paiement ${p.id} de ${p.montant} ${p.devise} ? Une preuve est exigée.`)) return
    setEnCours(true)
    try {
      await api.post(`/finances-etudiantes/paiements/${p.id}/confirmer/`)
      toast.showToast('Paiement confirmé. Quittance générée.')
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Confirmation impossible (preuve manquante ?).', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const NATURES = ['DOSSIER', 'INSCRIPTION', 'SCOLARITE', 'EXAMEN', 'DOCUMENT']
  const MODES = ['CAISSE', 'VIREMENT', 'ELEPHANT_MONEY', 'MTN_MONEY', 'MOOV_MONEY', 'CARTE_BANCAIRE']

  return (
    <div className="container-fluid py-4">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h1 className="h4 mb-0"><i className="bi bi-cash-coin me-2"></i>Finances étudiantes</h1>
        <button className="btn btn-outline-secondary btn-sm" onClick={charger}>
          <i className="bi bi-arrow-clockwise me-1"></i>Actualiser
        </button>
      </div>

      <ul className="nav nav-tabs mb-3">
        <li className="nav-item">
          <button className={`nav-link ${onglet === 'echeanciers' ? 'active' : ''}`}
                  onClick={() => setOnglet('echeanciers')}>Échéanciers</button>
        </li>
        <li className="nav-item">
          <button className={`nav-link ${onglet === 'paiements' ? 'active' : ''}`}
                  onClick={() => setOnglet('paiements')}>Paiements</button>
        </li>
      </ul>

      {onglet === 'echeanciers' && (
        <div className="card">
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0">
              <thead className="table-light">
                <tr>
                  <th>Étudiant</th><th>Année académique</th><th>Statut global</th><th>Lignes</th>
                </tr>
              </thead>
              <tbody>
                {chargement ? (
                  <tr><td colSpan={4} className="text-center py-4"><div className="spinner-border spinner-border-sm" /></td></tr>
                ) : echeanciers.length === 0 ? (
                  <tr><td colSpan={4} className="text-center text-muted py-4">Aucun échéancier.</td></tr>
                ) : echeanciers.map((e) => (
                  <tr key={e.id}>
                    <td>Étudiant #{e.etudiant_id}</td>
                    <td>{e.annee_academique}</td>
                    <td><span className={`badge text-bg-${BADGE_STATUT_LIGNE[e.statut_global] || 'secondary'}`}>{e.statut_global}</span></td>
                    <td>{e.lignes_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}


      {onglet === 'paiements' && (
        <>
          {peutEcrire && (
            <div className="card mb-3">
              <div className="card-header"><strong>Enregistrer un paiement (idempotent via transaction_externe)</strong></div>
              <div className="card-body">
                <form onSubmit={creerPaiement} className="row g-2">
                  <div className="col-md-2">
                    <label className="form-label small">Étudiant ID</label>
                    <input type="number" className="form-control form-control-sm" required
                           value={formPaiement.etudiant_id}
                           onChange={(e) => setFormPaiement(f => ({ ...f, etudiant_id: e.target.value }))} />
                  </div>
                  <div className="col-md-2">
                    <label className="form-label small">Nature</label>
                    <select className="form-select form-select-sm" value={formPaiement.nature}
                            onChange={(e) => setFormPaiement(f => ({ ...f, nature: e.target.value }))}>
                      {NATURES.map(n => <option key={n} value={n}>{n}</option>)}
                    </select>
                  </div>
                  <div className="col-md-2">
                    <label className="form-label small">Montant</label>
                    <input type="number" step="0.01" className="form-control form-control-sm" required
                           value={formPaiement.montant}
                           onChange={(e) => setFormPaiement(f => ({ ...f, montant: e.target.value }))} />
                  </div>
                  <div className="col-md-1">
                    <label className="form-label small">Devise</label>
                    <input type="text" className="form-control form-control-sm" value={formPaiement.devise}
                           onChange={(e) => setFormPaiement(f => ({ ...f, devise: e.target.value }))} />
                  </div>
                  <div className="col-md-2">
                    <label className="form-label small">Mode</label>
                    <select className="form-select form-select-sm" value={formPaiement.mode}
                            onChange={(e) => setFormPaiement(f => ({ ...f, mode: e.target.value }))}>
                      {MODES.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </div>
                  <div className="col-md-2">
                    <label className="form-label small">Transaction (anti-doublon)</label>
                    <input type="text" className="form-control form-control-sm" required
                           value={formPaiement.transaction_externe}
                           onChange={(e) => setFormPaiement(f => ({ ...f, transaction_externe: e.target.value }))} />
                  </div>
                  <div className="col-md-1 d-flex align-items-end">
                    <button type="submit" className="btn btn-primary btn-sm w-100" disabled={enCours}>OK</button>
                  </div>
                </form>
              </div>
            </div>
          )}

          <div className="card">
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0">
                <thead className="table-light">
                  <tr>
                    <th>ID</th><th>Étudiant</th><th>Nature</th><th>Montant</th><th>Mode</th>
                    <th>Statut</th><th>Date</th><th>Référence</th>
                    {peutConfirmer && <th className="text-end">Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {chargement ? (
                    <tr><td colSpan={9} className="text-center py-4"><div className="spinner-border spinner-border-sm" /></td></tr>
                  ) : paiements.length === 0 ? (
                    <tr><td colSpan={9} className="text-center text-muted py-4">Aucun paiement.</td></tr>
                  ) : paiements.map((p) => (
                    <tr key={p.id}>
                      <td>{p.id}</td>
                      <td>{p.etudiant_id ? `Étudiant #${p.etudiant_id}` : (p.candidat_id ? `Candidat #${p.candidat_id}` : '—')}</td>
                      <td>{p.nature}</td>
                      <td>{p.montant} {p.devise}</td>
                      <td>{p.mode}</td>
                      <td><span className={`badge text-bg-${BADGE_STATUT_PA[p.statut] || 'secondary'}`}>{p.statut}</span></td>
                      <td>{new Date(p.date).toLocaleString()}</td>
                      <td><small className="text-muted">{p.transaction_externe || '—'}</small></td>
                      {peutConfirmer && (
                        <td className="text-end">
                          {(p.statut === 'INITIE' || p.statut === 'EN_ATTENTE') && (
                            <button className="btn btn-outline-success btn-sm" disabled={enCours} onClick={() => confirmer(p)}>Confirmer</button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

