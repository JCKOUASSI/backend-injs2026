/** DemandesAcces — workflow générique de demandes d'accès (Lot C, additif).
 *
 * Liste filtrable, création (justification obligatoire), traitement et
 * décision. L'approbation alimente la file de provisionnement existante :
 * elle n'exécute jamais l'attribution elle-même.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  listerDemandesAcces,
  creerDemandeAcces,
  actionDemandeAcces,
  listerRolesCurp,
  listerComptes,
  messageErreur,
} from '@/services/habilitations'
import { EnChargement } from './partages'
import './habilitations.css'

const STATUTS = ['', 'BROUILLON', 'SOUMISE', 'EN_REVUE', 'APPROUVEE',
  'REFUSEE', 'ANNULEE']

const ACTIONS_PAR_STATUT = {
  BROUILLON: [['soumettre', 'Soumettre'], ['annuler', 'Annuler']],
  SOUMISE: [['revue', 'Placer en revue'], ['approuver', 'Approuver'],
    ['refuser', 'Refuser'], ['annuler', 'Annuler']],
  EN_REVUE: [['approuver', 'Approuver'], ['refuser', 'Refuser'],
    ['annuler', 'Annuler']],
}

export default function DemandesAcces() {
  const [demandes, setDemandes] = useState(null)
  const [roles, setRoles] = useState([])
  const [comptes, setComptes] = useState([])
  const [filtreStatut, setFiltreStatut] = useState('')
  const [erreur, setErreur] = useState('')
  const [message, setMessage] = useState('')
  const [motif, setMotif] = useState('')
  const [formulaire, setFormulaire] = useState({
    type_demande: 'ATTRIBUTION_ROLE', compte_cible: '', role: '',
    justification: '',
  })
  const [ouvrirForm, setOuvrirForm] = useState(false)

  const charger = (statut = filtreStatut) => {
    listerDemandesAcces(statut ? { statut } : {})
      .then((r) => { setDemandes(r.results || r); setErreur('') })
      .catch((e) => setErreur(messageErreur(e, 'Liste indisponible.')))
  }

  useEffect(() => {
    charger()
    listerRolesCurp().then(setRoles).catch(() => {})
    listerComptes({ page: 1 }).then((r) => {
      setComptes(r.results || r || [])
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chargement initial uniquement
  }, [])

  const decider = async (id, action) => {
    if ((action === 'approuver' || action === 'refuser') && !motif.trim()) {
      setMessage('Un motif de décision est obligatoire pour approuver ou refuser.')
      return
    }
    try {
      await actionDemandeAcces(id, action, motif.trim())
      setMessage('Décision enregistrée.')
      setMotif('')
      charger()
    } catch (e) {
      setMessage(messageErreur(e, 'Action impossible.'))
    }
  }

  const creer = async () => {
    if (!formulaire.justification.trim()) {
      setMessage('La justification est obligatoire.')
      return
    }
    try {
      await creerDemandeAcces({
        ...formulaire,
        compte_cible: formulaire.compte_cible || undefined,
        role: formulaire.role || undefined,
      })
      setMessage('Demande créée (brouillon).')
      setOuvrirForm(false)
      setFormulaire({ type_demande: 'ATTRIBUTION_ROLE', compte_cible: '',
        role: '', justification: '' })
      charger()
    } catch (e) {
      setMessage(messageErreur(e, 'Création impossible.'))
    }
  }

  if (erreur && demandes === null) {
    return (
      <section data-testid="ecran-demandes">
        <div className="hab-carte hab-avertissement" data-testid="demandes-erreur">{erreur}</div>
      </section>
    )
  }
  if (demandes === null) {
    return <section data-testid="ecran-demandes"><EnChargement message="Chargement des demandes…" /></section>
  }

  return (
    <section data-testid="ecran-demandes">
      <div className="hab-carte">
        <h2 className="h5">
          <i className="bi bi-clipboard2-check me-2" />Demandes d'accès
        </h2>
        <p className="hab-muted">
          Demande → décision → provisionnement. L'approbation d'une demande
          de rôle alimente la file de provisionnement existante : elle ne
          l'exécute jamais directement.
        </p>
        {message && <div className="hab-muted" data-testid="demandes-message" role="status">{message}</div>}
        <div className="hab-filtres">
          <div>
            <label className="form-label hab-muted mb-1" htmlFor="filtre-statut">Statut</label>
            <select
              id="filtre-statut" className="form-control"
              data-testid="filtre-demandes" value={filtreStatut}
              onChange={(e) => { setFiltreStatut(e.target.value); charger(e.target.value) }}
            >
              {STATUTS.map((s) => (
                <option key={s} value={s}>{s || 'Tous les statuts'}</option>
              ))}
            </select>
          </div>
          <div className="align-self-end">
            <button type="button" className="btn btn-sm btn-dfrc"
                    data-testid="ouvrir-formulaire"
                    onClick={() => setOuvrirForm(!ouvrirForm)}>
              <i className="bi bi-plus-lg me-1" />Nouvelle demande
            </button>
          </div>
        </div>

        {ouvrirForm && (
          <div className="hab-avertissement" data-testid="formulaire-demande">
            <div className="hab-filtres">
              <div>
                <label className="form-label hab-muted mb-1" htmlFor="type-demande">Type</label>
                <select id="type-demande" className="form-control" data-testid="type-demande"
                        value={formulaire.type_demande}
                        onChange={(e) => setFormulaire({ ...formulaire, type_demande: e.target.value })}>
                  <option value="ATTRIBUTION_ROLE">Attribution de rôle</option>
                  <option value="PERMISSION_DIRECTE">Permission directe (dérogation)</option>
                </select>
              </div>
              <div>
                <label className="form-label hab-muted mb-1" htmlFor="compte-cible">Compte bénéficiaire</label>
                <select id="compte-cible" className="form-control" data-testid="compte-cible"
                        value={formulaire.compte_cible}
                        onChange={(e) => setFormulaire({ ...formulaire, compte_cible: e.target.value })}>
                  <option value="">— Sélectionner —</option>
                  {comptes.map((c) => (
                    <option key={c.id ?? c.pk} value={c.id ?? c.pk}>
                      {c.username}{c.nom ? ` (${c.nom})` : ''}
                    </option>
                  ))}
                </select>
              </div>
              {formulaire.type_demande === 'ATTRIBUTION_ROLE' && (
                <div>
                  <label className="form-label hab-muted mb-1" htmlFor="role-demande">Rôle visé</label>
                  <select id="role-demande" className="form-control" data-testid="role-demande"
                          value={formulaire.role}
                          onChange={(e) => setFormulaire({ ...formulaire, role: e.target.value })}>
                    <option value="">— Sélectionner —</option>
                    {roles.map((r) => (
                      <option key={r.id ?? r.code} value={r.id ?? r.code}>{r.code}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
            <label className="form-label hab-muted mb-1" htmlFor="justification-demande">
              Justification (obligatoire)
            </label>
            <textarea id="justification-demande" className="form-control" rows={2}
                      data-testid="justification-demande" value={formulaire.justification}
                      onChange={(e) => setFormulaire({ ...formulaire, justification: e.target.value })} />
            <button type="button" className="btn btn-sm btn-dfrc mt-2"
                    data-testid="creer-demande" onClick={creer}>
              Créer la demande
            </button>
          </div>
        )}

        <div style={{ maxHeight: 560, overflow: 'auto' }} className="mt-2">
          {demandes.length === 0 ? (
            <p className="hab-muted" data-testid="demandes-vide">Aucune demande.</p>
          ) : (
            <table className="hab-table" data-testid="demandes-liste">
              <thead>
                <tr><th>#</th><th>Type</th><th>Bénéficiaire</th><th>Accès</th>
                    <th>Statut</th><th>Demandeur</th><th>Décision</th><th>Traiter</th></tr>
              </thead>
              <tbody>
                {demandes.map((d) => (
                  <tr key={d.id} data-testid={`demande-${d.id}`}>
                    <td>{d.id}</td>
                    <td>{d.type_libelle}</td>
                    <td>{d.username_cible || '—'}</td>
                    <td><code>{d.role || d.permission || '—'}</code></td>
                    <td>{d.statut_libelle}</td>
                    <td>{d.demandeur || '—'}</td>
                    <td>
                      {d.approbateur || '—'}
                      {d.provisionnement && (
                        <><br /><Link
                          className="hab-lien-impact"
                          data-testid={`lien-provisionnement-${d.id}`}
                          to="/administration/comptes/provisionnement"
                        >
                          <small>Provisionnement #{d.provisionnement} en file →</small>
                        </Link></>
                      )}
                    </td>
                    <td>
                      {(ACTIONS_PAR_STATUT[d.statut] || []).map(([action, libelle]) => (
                        <button key={action} type="button"
                                className={`btn btn-sm ${action === 'approuver' ? 'btn-dfrc' : 'btn-outline-secondary'} me-1 mb-1`}
                                data-testid={`action-${action}-${d.id}`}
                                title="Motif requis pour approuver/refuser"
                                onClick={() => decider(d.id, action)}>
                          {libelle}
                        </button>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <label className="form-label hab-muted mb-1 mt-2" htmlFor="motif-decision">
          Motif de décision (obligatoire pour approuver/refuser)
        </label>
        <input id="motif-decision" className="form-control" data-testid="motif-decision"
               value={motif} onChange={(e) => setMotif(e.target.value)} />
      </div>
    </section>
  )
}
