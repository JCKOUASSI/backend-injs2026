/** Delegations — création bornée U4, contrôles U5 (détention, re-délégation,
 * activation par un administrateur, action déléguée tracée, fin anticipée). */
import { useEffect, useState } from 'react'
import {
  listerComptes, listerRolesCurp, listerDelegations, creerDelegation,
  terminerDelegation, activerDelegation, actionParDelegation, messageErreur,
} from '@/services/habilitations'
import { useToast } from '@/context/ToastContext'
import { EnChargement } from './partages'
import MotifModal from './MotifModal'
import './habilitations.css'

const formVide = { delegant: '', delegataire: '', roles: [], date_fin: '', motif: '' }

/** Petite fenêtre de saisie d'une action faite par délégation. */
function ActionDelegueeModal({ delegation, onClose, onFait }) {
  const { showToast } = useToast()
  const [action, setAction] = useState('')
  const enregistrer = async () => {
    try {
      const r = await actionParDelegation(delegation.id, action.trim())
      showToast(`Action tracée (n° ${r.numero}) « Agit par délégation de ${r.delegant} ».`, 'success')
      onFait()
      onClose()
    } catch (e) {
      showToast(messageErreur(e), 'error')
    }
  }
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h5><i className="bi bi-person-check me-2" />Action exercée par délégation</h5>
          <button className="btn-close" onClick={onClose} aria-label="Fermer">&times;</button>
        </div>
        <div className="modal-body">
          <p className="small text-muted">
            Délégation {delegation.delegant} → {delegation.delegataire}. L'action est journalisée
            avec la mention du délégant ; seul le délégataire peut l'enregistrer.
          </p>
          <label className="form-label">Description de l'action</label>
          <textarea className="form-control" rows="2" data-testid="action-deleguee-input"
                    value={action} onChange={(e) => setAction(e.target.value)} />
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>Annuler</button>
          <button className="btn btn-success" data-testid="action-deleguee-valider"
                  disabled={action.trim().length < 3} onClick={enregistrer}>Journaliser</button>
        </div>
      </div>
    </div>
  )
}

export default function Delegations() {
  const { showToast } = useToast()
  const [comptes, setComptes] = useState([])
  const [roles, setRoles] = useState([])
  const [donnees, setDonnees] = useState(null)
  const [chargement, setChargement] = useState(true)
  const [erreurChargement, setErreurChargement] = useState('')
  const [form, setForm] = useState(formVide)
  const [aTerminer, setATerminer] = useState(null)
  const [aActiver, setAActiver] = useState(null)
  const [aTracer, setATracer] = useState(null)

  const charger = async () => {
    setChargement(true)
    setErreurChargement('')
    try {
      const [listeComptes, listeRoles, listeDelegations] = await Promise.all([
        listerComptes({ page_size: 500 }), listerRolesCurp(),
        listerDelegations({ page_size: 200 }),
      ])
      setComptes(listeComptes.results || [])
      setRoles(listeRoles)
      setDonnees(listeDelegations)
    } catch (e) {
      setErreurChargement(messageErreur(e, 'Chargement des délégations impossible.'))
    } finally {
      setChargement(false)
    }
  }
  useEffect(() => { charger() }, [])

  const maj = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const creer = async (e) => {
    e.preventDefault()
    if (form.delegant === form.delegataire) {
      showToast('Le délégant et le délégataire doivent être distincts.', 'error')
      return
    }
    try {
      await creerDelegation({
        delegant: Number(form.delegant), delegataire: Number(form.delegataire),
        roles: form.roles, date_fin: form.date_fin, motif: form.motif,
      })
      showToast('Délégation proposée.', 'success')
      setForm(formVide)
      charger()
    } catch (erreur) {
      showToast(messageErreur(erreur), 'error')
    }
  }
  const confirmerFin = async (motif) => {
    await terminerDelegation(aTerminer.id, motif)
    showToast('Délégation terminée.', 'success')
    setATerminer(null)
    charger()
  }
  const confirmerActivation = async (motif) => {
    try {
      await activerDelegation(aActiver.id, motif)
      showToast('Délégation activée après contrôle des droits détenus.', 'success')
      setAActiver(null)
      charger()
    } catch (e) {
      showToast(messageErreur(e), 'error')
      setAActiver(null)
    }
  }

  if (chargement) return <EnChargement message="Chargement des délégations…" />
  if (erreurChargement) return (
    <section data-testid="ecran-delegations">
      <div className="hab-carte hab-avertissement" role="alert" data-testid="delegations-erreur">
        <p>{erreurChargement}</p>
        <button type="button" className="btn btn-sm btn-outline-primary" onClick={charger}>Réessayer</button>
      </div>
    </section>
  )
  return (
    <section data-testid="ecran-delegations">
      <div className="hab-carte">
        <h2 className="h5">Délégations temporaires</h2>
        <p className="hab-muted">
          Toute délégation est bornée dans le temps. Le serveur vérifie que le délégant détient
          réellement et directement chaque droit jusqu'à la date de fin (la re-délégation est
          interdite), puis un administrateur active la délégation. Chaque action exercée par le
          délégataire est journalisée avec la mention du délégant.
        </p>
        <form className="row g-2" onSubmit={creer} data-testid="form-delegation">
          <div className="col-md-3">
            <label className="form-label">Délégant</label>
            <select className="form-select" required value={form.delegant} onChange={(e) => maj('delegant', e.target.value)}>
              <option value="">Compte…</option>
              {comptes.map((c) => <option key={c.id} value={c.id}>{c.username}</option>)}
            </select>
          </div>
          <div className="col-md-3">
            <label className="form-label">Délégataire</label>
            <select className="form-select" required value={form.delegataire} onChange={(e) => maj('delegataire', e.target.value)}>
              <option value="">Compte…</option>
              {comptes.map((c) => <option key={c.id} value={c.id}>{c.username}</option>)}
            </select>
          </div>
          <div className="col-md-3">
            <label className="form-label">Date de fin</label>
            <input type="date" className="form-control" required value={form.date_fin}
                   onChange={(e) => maj('date_fin', e.target.value)} />
          </div>
          <div className="col-md-3">
            <label className="form-label">Motif</label>
            <input className="form-control" required value={form.motif}
                   onChange={(e) => maj('motif', e.target.value)} />
          </div>
          <div className="col-12">
            <label className="form-label">Rôles délégués</label>
            <select multiple className="form-select" style={{ minHeight: 90 }}
                    onChange={(e) => maj('roles', Array.from(e.target.selectedOptions, (o) => o.value))}>
              {roles.map((r) => <option key={r.code} value={r.code}>{r.libelle}</option>)}
            </select>
          </div>
          <div className="col-12"><button className="btn btn-success btn-sm" data-testid="bouton-creer-delegation">Proposer la délégation</button></div>
        </form>
      </div>
      <div className="hab-carte">
        <table className="hab-table">
          <thead><tr><th>Délégant</th><th>Délégataire</th><th>Rôles</th><th>Fin</th><th>Statut</th><th>Actions</th></tr></thead>
          <tbody>
            {donnees.results.map((d) => (
              <tr key={d.id} data-testid={`delegation-${d.id}`}>
                <td>{d.delegant}</td>
                <td>{d.delegataire}</td>
                <td>{(d.roles || []).join(', ') || '—'}</td>
                <td>{d.date_fin}</td>
                <td>{d.statut}</td>
                <td>
                  <div className="d-flex gap-1 flex-wrap">
                    {d.statut === 'PROPOSEE' && (
                      <button className="btn btn-sm btn-success" data-testid={`activer-${d.id}`}
                              onClick={() => setAActiver(d)}>Activer</button>
                    )}
                    {d.statut === 'ACTIVE' && (
                      <button className="btn btn-sm btn-outline-primary" data-testid={`action-${d.id}`}
                              onClick={() => setATracer(d)}>Action déléguée</button>
                    )}
                    {['PROPOSEE', 'ACTIVE'].includes(d.statut) && (
                      <button className="btn btn-sm btn-outline-danger" onClick={() => setATerminer(d)}>Terminer</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {donnees.results.length === 0 && <tr><td colSpan="6" className="hab-muted text-center py-3">Aucune délégation.</td></tr>}
          </tbody>
        </table>
      </div>
      {aTerminer && (
        <MotifModal titre="Terminer la délégation" action={`Mettre fin à la délégation ${aTerminer.delegant} → ${aTerminer.delegataire}`}
                    consequences="Le délégataire perd dès l'enregistrement les droits correspondants."
                    onConfirmer={confirmerFin} onAnnuler={() => setATerminer(null)} />
      )}
      {aActiver && (
        <MotifModal titre="Activer la délégation" variant="success"
                    confirmationLabel="Activer"
                    action={`Activer la délégation ${aActiver.delegant} → ${aActiver.delegataire}`}
                    consequences="Le serveur recontrôle que les droits sont détenus directement et couverts jusqu'à la date de fin."
                    onConfirmer={confirmerActivation} onAnnuler={() => setAActiver(null)} />
      )}
      {aTracer && (
        <ActionDelegueeModal delegation={aTracer} onClose={() => setATracer(null)} onFait={charger} />
      )}
    </section>
  )
}
