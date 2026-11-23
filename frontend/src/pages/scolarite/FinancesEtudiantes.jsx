import React, { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import '../../styles/financesEtudiantes.css'

const BADGE_STATUT_PA = {
  INITIE: 'secondary', EN_ATTENTE: 'info', CONFIRME: 'success',
  ECHOUE: 'warning', ANNULE: 'dark', REMBOSSE: 'dark', RAPPROCHE: 'primary',
}
const BADGE_STATUT_LIGNE = {
  IMPAYE: 'danger', PAYE: 'success', PARTIELLEMENT_PAYE: 'warning', COMPLETE: 'success',
}

const formaterNombre = (n) => Number(n || 0).toLocaleString('fr-FR')

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

  // Synthèse calculée sur les données chargées (aucun chiffre inventé).
  const synthese = useMemo(() => ({
    echeanciers: echeanciers.length,
    lignes: echeanciers.reduce((total, e) => total + Number(e.lignes_count || 0), 0),
    paiements: paiements.length,
    aConfirmer: paiements.filter((p) => p.statut === 'INITIE' || p.statut === 'EN_ATTENTE').length,
    confirmes: paiements.filter((p) => p.statut === 'CONFIRME').length,
  }), [echeanciers, paiements])

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
    <div className="fin-page">
      <header className="fin-hero">
        <div className="fin-hero-identite">
          <span className="fin-hero-icone" aria-hidden="true">
            <i className="bi bi-cash-coin"></i>
          </span>
          <div>
            <span className="fin-hero-eyebrow">Scolarité</span>
            <h1 className="fin-hero-titre">Finances étudiantes</h1>
            <p className="fin-hero-intro">
              Échéanciers et encaissements des étudiants : {formaterNombre(synthese.echeanciers)} échéanciers suivis,
              {' '}{formaterNombre(synthese.paiements)} paiements enregistrés
              {synthese.aConfirmer > 0
                ? `, ${formaterNombre(synthese.aConfirmer)} en attente de confirmation.`
                : '.'}
            </p>
          </div>
        </div>
        <button type="button" className="fin-btn-hero" onClick={charger}>
          <i className="bi bi-arrow-clockwise" aria-hidden="true"></i>Actualiser
        </button>
      </header>

      <div className="fin-kpis">
        <div className="fin-kpi">
          <span className="fin-kpi-icone is-blue" aria-hidden="true"><i className="bi bi-calendar-range"></i></span>
          <span className="fin-kpi-corps">
            <span className="fin-kpi-valeur">{formaterNombre(synthese.echeanciers)}</span>
            <span className="fin-kpi-libelle">Échéanciers suivis</span>
          </span>
        </div>
        <div className="fin-kpi">
          <span className="fin-kpi-icone is-indigo" aria-hidden="true"><i className="bi bi-list-ol"></i></span>
          <span className="fin-kpi-corps">
            <span className="fin-kpi-valeur">{formaterNombre(synthese.lignes)}</span>
            <span className="fin-kpi-libelle">Lignes d’échéance</span>
          </span>
        </div>
        <div className="fin-kpi">
          <span className="fin-kpi-icone is-cyan" aria-hidden="true"><i className="bi bi-wallet2"></i></span>
          <span className="fin-kpi-corps">
            <span className="fin-kpi-valeur">{formaterNombre(synthese.paiements)}</span>
            <span className="fin-kpi-libelle">Paiements enregistrés</span>
          </span>
        </div>
        <div className="fin-kpi">
          <span className="fin-kpi-icone is-amber" aria-hidden="true"><i className="bi bi-hourglass-split"></i></span>
          <span className="fin-kpi-corps">
            <span className="fin-kpi-valeur">{formaterNombre(synthese.aConfirmer)}</span>
            <span className="fin-kpi-libelle">À confirmer</span>
            <span className="fin-kpi-sub">{formaterNombre(synthese.confirmes)} confirmé{synthese.confirmes > 1 ? 's' : ''}</span>
          </span>
        </div>
      </div>

      <div className="fin-tabs" aria-label="Finances étudiantes">
        <button
          type="button" aria-pressed={onglet === 'echeanciers'}
          className={`fin-tab${onglet === 'echeanciers' ? ' is-active' : ''}`}
          onClick={() => setOnglet('echeanciers')}>
          <i className="bi bi-calendar-range" aria-hidden="true"></i>Échéanciers
        </button>
        <button
          type="button" aria-pressed={onglet === 'paiements'}
          className={`fin-tab${onglet === 'paiements' ? ' is-active' : ''}`}
          onClick={() => setOnglet('paiements')}>
          <i className="bi bi-wallet2" aria-hidden="true"></i>Paiements
        </button>
      </div>

      {onglet === 'echeanciers' && (
        <section className="fin-panel">
          <header className="fin-panel-head">
            <h2 className="fin-panel-titre">
              <i className="bi bi-calendar-range" aria-hidden="true"></i>Échéanciers
            </h2>
            <span className="fin-count-pill">{formaterNombre(echeanciers.length)} élément{echeanciers.length > 1 ? 's' : ''}</span>
          </header>
          <div className="fin-table-wrap">
            <table className="fin-table">
              <thead>
                <tr>
                  <th scope="col">Étudiant</th><th scope="col">Année académique</th><th scope="col">Statut global</th><th scope="col">Lignes</th>
                </tr>
              </thead>
              <tbody>
                {chargement ? (
                  <tr><td colSpan={4} className="fin-centre"><div className="spinner-border spinner-border-sm" /></td></tr>
                ) : echeanciers.length === 0 ? (
                  <tr>
                    <td colSpan={4}>
                      <div className="fin-vide">
                        <span className="fin-vide-icone" aria-hidden="true"><i className="bi bi-calendar-x"></i></span>
                        <p className="fin-vide-titre">Aucun échéancier.</p>
                        <p className="fin-vide-texte">Les échéanciers générés à partir du barème actif apparaîtront ici.</p>
                      </div>
                    </td>
                  </tr>
                ) : echeanciers.map((e) => (
                  <tr key={e.id}>
                    <td><span className="fin-etudiant">Étudiant #{e.etudiant_id}</span></td>
                    <td>{e.annee_academique}</td>
                    <td><span className={`badge text-bg-${BADGE_STATUT_LIGNE[e.statut_global] || 'secondary'}`}>{e.statut_global}</span></td>
                    <td><span className="fin-nombre-chip">{e.lignes_count}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {onglet === 'paiements' && (
        <>
          {peutEcrire && (
            <div className="card fin-form-card mb-3">
              <div className="fin-panel-head">
                <h2 className="fin-panel-titre">
                  <i className="bi bi-plus-circle" aria-hidden="true"></i>
                  Enregistrer un paiement (idempotent via transaction_externe)
                </h2>
              </div>
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
                    <button type="submit" className="btn btn-primary btn-sm w-100 fin-btn-ok" disabled={enCours}>OK</button>
                  </div>
                </form>
              </div>
            </div>
          )}

          <section className="fin-panel">
            <header className="fin-panel-head">
              <h2 className="fin-panel-titre">
                <i className="bi bi-wallet2" aria-hidden="true"></i>Paiements
              </h2>
              <span className="fin-count-pill">{formaterNombre(paiements.length)} élément{paiements.length > 1 ? 's' : ''}</span>
            </header>
            <div className="fin-table-wrap">
              <table className="fin-table">
                <thead>
                  <tr>
                    <th scope="col">ID</th><th scope="col">Étudiant</th><th scope="col">Nature</th><th scope="col">Montant</th><th scope="col">Mode</th>
                    <th scope="col">Statut</th><th scope="col">Date</th><th scope="col">Référence</th>
                    {peutConfirmer && <th scope="col" className="text-end">Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {chargement ? (
                    <tr><td colSpan={9} className="fin-centre"><div className="spinner-border spinner-border-sm" /></td></tr>
                  ) : paiements.length === 0 ? (
                    <tr>
                      <td colSpan={9}>
                        <div className="fin-vide">
                          <span className="fin-vide-icone" aria-hidden="true"><i className="bi bi-wallet2"></i></span>
                          <p className="fin-vide-titre">Aucun paiement.</p>
                          <p className="fin-vide-texte">Les paiements enregistrés à la caisse ou par mobile money apparaîtront ici.</p>
                        </div>
                      </td>
                    </tr>
                  ) : paiements.map((p) => (
                    <tr key={p.id}>
                      <td><span className="fin-id-chip">{p.id}</span></td>
                      <td><span className="fin-etudiant">{p.etudiant_id ? `Étudiant #${p.etudiant_id}` : (p.candidat_id ? `Candidat #${p.candidat_id}` : '—')}</span></td>
                      <td>{p.nature}</td>
                      <td><span className="fin-montant">{p.montant} {p.devise}</span></td>
                      <td>{p.mode}</td>
                      <td><span className={`badge text-bg-${BADGE_STATUT_PA[p.statut] || 'secondary'}`}>{p.statut}</span></td>
                      <td><span className="fin-date">{new Date(p.date).toLocaleString()}</span></td>
                      <td>{p.transaction_externe
                        ? <span className="fin-ref-chip">{p.transaction_externe}</span>
                        : <small className="text-muted">—</small>}</td>
                      {peutConfirmer && (
                        <td className="text-end">
                          {(p.statut === 'INITIE' || p.statut === 'EN_ATTENTE') && (
                            <button type="button" className="fin-btn-confirmer" disabled={enCours} onClick={() => confirmer(p)}>Confirmer</button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
