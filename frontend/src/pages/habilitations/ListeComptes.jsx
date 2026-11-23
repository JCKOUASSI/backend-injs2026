/** ListeComptes — recherche instantanée, filtres, colonnes et actions rapides. */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listerComptes, listerRolesCurp, changerStatutCompte, messageErreur } from '@/services/habilitations'
import { libelleCanal, libelleDomaine, libelleStatut, telechargerCsv } from '@/utils/habilitations'
import { useToast } from '@/context/ToastContext'
import { BadgeStatut, BadgeSensible, BadgeCanal, EnChargement, nomCompte } from './partages'
import MotifModal from './MotifModal'
import './habilitations.css'

const STATUTS = ['ACTIF', 'SUSPENDU', 'DESACTIVE', 'VERROUILLE', 'EXPIRE', 'INVITE']
const CANAUX = ['WEB', 'MOBILE', 'LES_DEUX']

export default function ListeComptes() {
  const { showToast } = useToast()
  const [roles, setRoles] = useState([])
  const [filtres, setFiltres] = useState({ search: '', statut: '', role: '', domaine: '', canal: '' })
  const [page, setPage] = useState(1)
  const [donnees, setDonnees] = useState({ results: [], count: 0 })
  const [chargement, setChargement] = useState(true)
  const [erreur, setErreur] = useState('')
  const [action, setAction] = useState(null) // {compte, transition, titre, consequences}

  useEffect(() => {
    listerRolesCurp().then(setRoles).catch(() => setRoles([]))
  }, [])

  const paramsEffectifs = useMemo(
    () => ({
      ...Object.fromEntries(Object.entries(filtres).filter(([, v]) => v)),
      page,
    }),
    [filtres, page],
  )

  useEffect(() => {
    let actif = true
    setChargement(true)
    listerComptes(paramsEffectifs)
      .then((data) => { if (actif) { setDonnees(data); setErreur('') } })
      .catch((e) => actif && setErreur(messageErreur(e)))
      .finally(() => actif && setChargement(false))
    return () => { actif = false }
  }, [paramsEffectifs])

  const majFiltre = (cle, valeur) => {
    setPage(1)
    setFiltres((f) => ({ ...f, [cle]: valeur }))
  }

  const confirmerStatut = async (motif) => {
    const { compte, transition } = action
    try {
      await changerStatutCompte(compte.id, transition, motif)
      showToast(`Statut du compte ${compte.username} mis à jour.`, 'success')
      setAction(null)
      const data = await listerComptes(paramsEffectifs)
      setDonnees(data)
    } catch (e) {
      showToast(messageErreur(e), 'error')
    }
  }

  const totalPages = Math.max(1, Math.ceil(donnees.count / 50))

  const exporterCsv = () => {
    telechargerCsv(
      'comptes_gouvernes.csv',
      ['identifiant', 'nom', 'statut', 'roles', 'canal', 'derniere_connexion'],
      donnees.results.map((c) => [
        c.username, nomCompte(c), c.statut,
        c.roles_actifs.map((r) => r.role).join('|'), c.canal, c.derniere_connexion || '',
      ]),
    )
  }

  return (
    <section>
      <div className="hab-carte">
        <div className="d-flex justify-content-between align-items-center mb-2">
          <h2 className="h5 mb-0">Comptes gouvernés ({donnees.count})</h2>
          <span>
            <button type="button" className="btn btn-outline-secondary btn-sm me-2" data-testid="export-comptes"
                    onClick={exporterCsv} disabled={donnees.results.length === 0}>
              <i className="bi bi-download me-1" />Exporter (CSV)
            </button>
            <Link to="/administration/comptes/nouveau" className="btn btn-success btn-sm">
              <i className="bi bi-person-plus me-1" />Nouveau compte
            </Link>
          </span>
        </div>
        <p className="hab-muted mb-2">
          Les comptes existants non encore rattachés (migration U8) n'apparaissent pas encore ici ;
          la console crée les comptes dans le nouveau dispositif.
        </p>
        <div className="hab-filtres">
          <input className="form-control" placeholder="Rechercher (nom, identifiant, matricule)…"
                 value={filtres.search}
                 onChange={(e) => majFiltre('search', e.target.value)}
                 data-testid="filtre-recherche" />
          <select className="form-select" value={filtres.statut}
                  onChange={(e) => majFiltre('statut', e.target.value)} aria-label="Filtrer par statut">
            <option value="">Tous statuts</option>
            {STATUTS.map((s) => <option key={s} value={s}>{libelleStatut(s)}</option>)}
          </select>
          <select className="form-select" value={filtres.role}
                  onChange={(e) => majFiltre('role', e.target.value)} aria-label="Filtrer par rôle">
            <option value="">Tous rôles</option>
            {roles.map((r) => <option key={r.code} value={r.code}>{r.libelle}</option>)}
          </select>
          <select className="form-select" value={filtres.domaine}
                  onChange={(e) => majFiltre('domaine', e.target.value)} aria-label="Filtrer par domaine">
            <option value="">Tous domaines</option>
            {Array.from(new Set(roles.map((r) => r.domaine))).map((d) => (
              <option key={d} value={d}>{libelleDomaine(d)}</option>
            ))}
          </select>
          <select className="form-select" value={filtres.canal}
                  onChange={(e) => majFiltre('canal', e.target.value)} aria-label="Filtrer par canal">
            <option value="">Tous canaux</option>
            {CANAUX.map((c) => <option key={c} value={c}>{libelleCanal(c)}</option>)}
          </select>
        </div>
      </div>

      <div className="hab-carte">
        {erreur && <p className="text-danger">{erreur}</p>}
        {chargement ? <EnChargement /> : (
          <table className="hab-table" data-testid="table-comptes">
            <thead>
              <tr>
                <th>Compte</th><th>Rôles</th><th>Statut</th><th>Canal</th><th>Dernière connexion</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {donnees.results.map((compte) => (
                <tr key={compte.id}>
                  <td>
                    <Link to={`/administration/comptes/${compte.id}`}>
                      <strong>{nomCompte(compte)}</strong>
                    </Link>
                    <div className="hab-muted">{compte.username}{compte.nb_roles_sensibles > 0 && <BadgeSensible />}</div>
                  </td>
                  <td>
                    {compte.roles_actifs.map((r) => (
                      <span key={r.id || r.role} className="badge bg-light text-dark border me-1 mb-1">
                        {r.role_libelle || r.role}{r.sensible ? ' *' : ''}
                      </span>
                    ))}
                  </td>
                  <td><BadgeStatut statut={compte.statut} /></td>
                  <td><BadgeCanal canal={compte.canal} /></td>
                  <td className="hab-muted">{compte.derniere_connexion || '—'}</td>
                  <td>
                    <Link className="btn btn-sm btn-outline-success me-1"
                          to={`/administration/comptes/${compte.id}/modifier`}>Modifier</Link>
                    <Link className="btn btn-sm btn-outline-primary me-1"
                          title="Arbre des accès effectifs de ce compte"
                          data-testid={`acces-effectifs-${compte.username}`}
                          to={`/administration/comptes/acces-effectifs?user=${compte.user_id}`}>
                      <i className="bi bi-diagram-2" aria-hidden="true" />
                    </Link>
                    {compte.statut === 'ACTIF' ? (
                      <button className="btn btn-sm btn-outline-danger"
                              data-testid={`suspendre-${compte.username}`}
                              onClick={() => setAction({
                                compte, transition: 'suspendre',
                                titre: 'Suspendre le compte',
                                consequences: "L'accès sera immédiatement bloqué (connexion web et mobile).",
                              })}>Suspendre</button>
                    ) : (
                      <button className="btn btn-sm btn-outline-success"
                              onClick={() => setAction({
                                compte, transition: 'activer', titre: 'Réactiver le compte',
                                consequences: "L'accès sera rétabli selon les rôles en place.",
                              })}>Réactiver</button>
                    )}
                  </td>
                </tr>
              ))}
              {donnees.results.length === 0 && (
                <tr><td colSpan="6" className="text-center hab-muted py-3">Aucun compte gouverné ne correspond.</td></tr>
              )}
            </tbody>
          </table>
        )}
        {totalPages > 1 && (
          <div className="d-flex justify-content-between align-items-center mt-2">
            <button className="btn btn-sm btn-secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Précédent</button>
            <span className="hab-muted">Page {page} / {totalPages}</span>
            <button className="btn btn-sm btn-secondary" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Suivant</button>
          </div>
        )}
      </div>

      {action && (
        <MotifModal
          titre={action.titre}
          action={`Compte ${action.compte.username} — ${action.titre.toLowerCase()}`}
          consequences={action.consequences}
          onConfirmer={confirmerStatut}
          onAnnuler={() => setAction(null)}
        />
      )}
    </section>
  )
}
