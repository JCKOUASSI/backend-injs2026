/**
 * Organisation — directions, départements, services et rattachements des
 * comptes (LOT 3). Les données sont servies par l'API
 * /api/habilitations/organisation/* (garde drapeau + trio admin) ; chaque
 * geste est journalisé côté backend. L'interface ne confère aucun droit.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  listerDirections, creerDirection, modifierDirection,
  listerDepartements, creerDepartement, modifierDepartement, recupererDepartement,
  listerServicesOrganisation, creerServiceOrganisation, modifierServiceOrganisation,
  recupererServiceOrganisation,
  listerComptes,
  rattacherCompteDepartement, detacherCompteDepartement,
  rattacherCompteService, detacherCompteService,
  messageErreur,
} from '@/services/habilitations'
import { useToast } from '@/context/ToastContext'
import { EnChargement } from './partages'
import './habilitations.css'

const ONGLETS = [
  { id: 'directions', icone: 'bi-building', libelle: 'Directions' },
  { id: 'departements', icone: 'bi-diagram-3', libelle: 'Départements' },
  { id: 'services', icone: 'bi-briefcase', libelle: 'Services' },
]

function BadgeActif({ actif }) {
  return (
    <span className={`badge ${actif ? 'text-bg-success' : 'text-bg-secondary'}`}>
      {actif ? 'Actif' : 'Inactif'}
    </span>
  )
}

function CarteForm({ titre, testid, children }) {
  return (
    <div className="hab-carte" data-testid={testid}>
      <h3 className="h6">{titre}</h3>
      {children}
    </div>
  )
}

/** Panneau de rattachement compte ↔ entité (département ou service). */
function RattachementsPanel({
  entiteId, entiteLibelle, comptesRattaches, rattacher, detacher, toast,
}) {
  const [tous, setTous] = useState([])
  const [recherche, setRecherche] = useState('')
  const [selection, setSelection] = useState('')
  const [chargement, setChargement] = useState(true)

  const charger = useCallback(() => {
    listerComptes({ page_size: 300 })
      .then((page) => setTous(page.results || []))
      .catch((e) => toast(messageErreur(e), 'error'))
      .finally(() => setChargement(false))
  }, [toast])

  useEffect(() => { charger() }, [charger])

  const rattaches = new Set(comptesRattaches.map((c) => c.id))
  const filtre = (recherche || '').toLowerCase()
  const candidats = tous.filter(
    (c) => !rattaches.has(c.id)
      && (!filtre || `${c.username} ${c.email || ''}`.toLowerCase().includes(filtre))
  )

  const faire = async (action, compteId) => {
    try {
      const reponse = await action(entiteId, compteId)
      const comptes = reponse.comptes || []
      toast(
        comptes.length > comptesRattaches.length
          ? 'Compte rattaché.'
          : 'Compte détaché.',
        'success'
      )
    } catch (e) {
      toast(messageErreur(e), 'error')
    }
  }

  return (
    <div className="hab-carte mt-3" data-testid="rattachements-panel">
      <h3 className="h6">Comptes rattachés — {entiteLibelle}</h3>
      {comptesRattaches.length === 0
        ? <p className="hab-muted mb-2">Aucun compte rattaché.</p>
        : (
          <ul className="mb-2">
            {comptesRattaches.map((c) => (
              <li key={c.id} className="d-flex justify-content-between align-items-center">
                <span>
                  {c.personne || c.username} <code className="small">{c.username}</code>
                  <span className="hab-muted"> — {c.statut}</span>
                </span>
                <button
                  type="button"
                  className="btn btn-sm btn-outline-danger"
                  data-testid={`detacher-${c.id}`}
                  onClick={() => faire(detacher, c.id)}
                >
                  <i className="bi bi-person-dash me-1" />Détacher
                </button>
              </li>
            ))}
          </ul>
        )}
      <div className="d-flex gap-2 align-items-center">
        <input
          className="form-control form-control-sm"
          placeholder="Rechercher un compte (identifiant, courriel)…"
          value={recherche}
          onChange={(e) => setRecherche(e.target.value)}
          style={{ maxWidth: '320px' }}
        />
        <select
          className="form-select form-select-sm"
          style={{ maxWidth: '260px' }}
          value={selection}
          data-testid="rattachement-select"
          onChange={(e) => setSelection(e.target.value)}
          disabled={chargement}
        >
          <option value="">
            {chargement ? 'Chargement…' : (candidats.length ? 'Sélectionner un compte…' : 'Aucun compte candidat')}
          </option>
          {candidats.map((c) => (
            <option key={c.id} value={c.id}>{c.username} — {c.email || ''}</option>
          ))}
        </select>
        <button
          type="button"
          className="btn btn-sm btn-primary"
          data-testid="rattachement-ajouter"
          disabled={!selection}
          onClick={() => { faire(rattacher, Number(selection)); setSelection('') }}
        >
          <i className="bi bi-person-plus me-1" />Rattacher
        </button>
      </div>
    </div>
  )
}

export default function Organisation() {
  const { showToast } = useToast()
  const [onglet, setOnglet] = useState('directions')
  const [directions, setDirections] = useState(null)
  const [departements, setDepartements] = useState(null)
  const [services, setServices] = useState(null)

  const [formDir, setFormDir] = useState({ code: '', libelle: '', description: '', ordre: 0 })
  const [formDep, setFormDep] = useState({ code: '', libelle: '', description: '', direction: '', ordre: 0 })
  const [formSvc, setFormSvc] = useState({ nom: '', description: '', departement: '' })

  // Ligne en cours d'édition : { type, id, form }
  const [edition, setEdition] = useState(null)
  const [detailDep, setDetailDep] = useState(null)
  const [detailSvc, setDetailSvc] = useState(null)
  const [occupes, setOccupes] = useState(false)

  const charger = useCallback(() => {
    listerDirections().then(setDirections).catch((e) => showToast(messageErreur(e), 'error'))
    listerDepartements().then(setDepartements).catch((e) => showToast(messageErreur(e), 'error'))
    listerServicesOrganisation().then(setServices).catch((e) => showToast(messageErreur(e), 'error'))
  }, [showToast])

  useEffect(() => { charger() }, [charger])
  useEffect(() => {
    if (directions || departements || services) setOccupes(true)
  }, [directions, departements, services])

  const creer = async (action, form, champs, testid) => {
    if (!form[champs[0]] || !form[champs[1]]) {
      showToast('Renseignez au moins les champs obligatoires (en gras).', 'error')
      return
    }
    try {
      const payload = Object.fromEntries(
        Object.entries(form).filter(([cle]) => cle !== 'actif')
      )
      Object.entries(payload).forEach(([cle, valeur]) => {
        if (valeur === '' && (cle === 'direction' || cle === 'departement')) delete payload[cle]
        if (typeof valeur === 'number') payload[cle] = valeur
      })
      await action(payload)
      showToast('Créé avec succès.', 'success')
      charger()
      if (testid === 'form-direction') setFormDir({ code: '', libelle: '', description: '', ordre: 0 })
      if (testid === 'form-departement') setFormDep({ code: '', libelle: '', description: '', direction: '', ordre: 0 })
      if (testid === 'form-service') setFormSvc({ nom: '', description: '', departement: '' })
    } catch (e) {
      showToast(messageErreur(e), 'error')
    }
  }

  const validerEdition = async () => {
    const { type, id, form } = edition
    try {
      const payload = {}
      Object.entries(form).forEach(([cle, valeur]) => {
        if (type === 'direction') {
          if (cle === 'ordre') payload.ordre = Number(valeur) || 0
          else if (cle === 'actif') payload.actif = Boolean(valeur)
          else payload[cle] = valeur
        }
        if (type === 'departement') {
          if (cle === 'ordre') payload.ordre = Number(valeur) || 0
          else if (cle === 'actif') payload.actif = Boolean(valeur)
          else if (cle === 'direction') payload.direction = valeur === '' ? null : Number(valeur)
          else payload[cle] = valeur
        }
        if (type === 'service') {
          if (cle === 'actif') payload.actif = Boolean(valeur)
          else if (cle === 'departement') payload.departement = valeur === '' ? null : Number(valeur)
          else payload[cle] = valeur
        }
      })
      const action = { direction: modifierDirection, departement: modifierDepartement, service: modifierServiceOrganisation }[type]
      await action(id, payload)
      showToast('Modification enregistrée.', 'success')
      setEdition(null)
      charger()
    } catch (e) {
      showToast(messageErreur(e), 'error')
    }
  }

  const basculerActif = async (type, id, actif) => {
    const action = { direction: modifierDirection, departement: modifierDepartement, service: modifierServiceOrganisation }[type]
    try {
      await action(id, { actif: !actif })
      showToast(actif ? 'Désactivé.' : 'Activé.', 'success')
      charger()
    } catch (e) {
      showToast(messageErreur(e), 'error')
    }
  }

  const ouvrirDetailDep = async (dep) => {
    setDetailDep(null)
    setDetailSvc(null)
    try {
      setDetailDep(await recupererDepartement(dep.id))
    } catch (e) {
      showToast(messageErreur(e), 'error')
    }
  }

  const ouvrirDetailSvc = async (svc) => {
    setDetailDep(null)
    setDetailSvc(null)
    try {
      setDetailSvc(await recupererServiceOrganisation(svc.id))
    } catch (e) {
      showToast(messageErreur(e), 'error')
    }
  }

  if (!occupes) return <EnChargement message="Chargement de l'organisation…" />

  return (
    <section data-testid="ecran-organisation">
      <div className="btn-group btn-group-sm mb-3" role="tablist" aria-label="Niveaux d'organisation">
        {ONGLETS.map((o) => (
          <button
            key={o.id}
            type="button"
            role="tab"
            aria-selected={onglet === o.id}
            className={`btn ${onglet === o.id ? 'btn-primary' : 'btn-outline-primary'}`}
            data-testid={`onglet-${o.id}`}
            onClick={() => setOnglet(o.id)}
          >
            <i className={`bi ${o.icone} me-1`} />{o.libelle}
          </button>
        ))}
      </div>

      {onglet === 'directions' && (
        <>
          <CarteForm titre="Nouvelle direction" testid="form-direction">
            <div className="row g-2">
              <div className="col-md-2">
                <label className="form-label small fw-bold">Code *</label>
                <input className="form-control form-control-sm" value={formDir.code}
                       onChange={(e) => setFormDir({ ...formDir, code: e.target.value })} placeholder="DG" />
              </div>
              <div className="col-md-4">
                <label className="form-label small fw-bold">Libellé *</label>
                <input className="form-control form-control-sm" value={formDir.libelle}
                       onChange={(e) => setFormDir({ ...formDir, libelle: e.target.value })} placeholder="Direction Générale" />
              </div>
              <div className="col-md-4">
                <label className="form-label small">Description</label>
                <input className="form-control form-control-sm" value={formDir.description}
                       onChange={(e) => setFormDir({ ...formDir, description: e.target.value })} />
              </div>
              <div className="col-md-1">
                <label className="form-label small">Ordre</label>
                <input type="number" min="0" className="form-control form-control-sm" value={formDir.ordre}
                       onChange={(e) => setFormDir({ ...formDir, ordre: Number(e.target.value) })} />
              </div>
              <div className="col-md-1 d-flex align-items-end">
                <button type="button" className="btn btn-sm btn-success w-100" data-testid="creer-direction"
                        onClick={() => creer(creerDirection, formDir, ['code', 'libelle'], 'form-direction')}>
                  Créer
                </button>
              </div>
            </div>
          </CarteForm>

          <table className="hab-table mt-3">
            <thead>
              <tr><th>Libellé</th><th>Code</th><th>Ordre</th><th>Départements</th><th>Statut</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {(directions || []).map((d) => (
                <tr key={d.id}>
                  <td>
                    {edition?.type === 'direction' && edition.id === d.id ? (
                      <input className="form-control form-control-sm" value={edition.form.libelle}
                             onChange={(e) => setEdition({ ...edition, form: { ...edition.form, libelle: e.target.value } })} />
                    ) : d.libelle}
                  </td>
                  <td><code>{d.code}</code></td>
                  <td>
                    {edition?.type === 'direction' && edition.id === d.id ? (
                      <input type="number" min="0" className="form-control form-control-sm" value={edition.form.ordre}
                             onChange={(e) => setEdition({ ...edition, form: { ...edition.form, ordre: e.target.value } })} />
                    ) : d.ordre}
                  </td>
                  <td>{d.nb_departements}</td>
                  <td>
                    {edition?.type === 'direction' && edition.id === d.id ? (
                      <select className="form-select form-select-sm" value={edition.form.actif ? '1' : '0'}
                              onChange={(e) => setEdition({ ...edition, form: { ...edition.form, actif: e.target.value === '1' } })}>
                        <option value="1">Actif</option><option value="0">Inactif</option>
                      </select>
                    ) : <BadgeActif actif={d.actif} />}
                  </td>
                  <td className="text-nowrap">
                    {edition?.type === 'direction' && edition.id === d.id ? (
                      <>
                        <button type="button" className="btn btn-sm btn-success me-1" data-testid={`valider-${d.id}`} onClick={validerEdition}>OK</button>
                        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setEdition(null)}>Annuler</button>
                      </>
                    ) : (
                      <>
                        <button type="button" className="btn btn-sm btn-outline-primary me-1" data-testid={`modifier-${d.id}`}
                                onClick={() => setEdition({ type: 'direction', id: d.id, form: { libelle: d.libelle, ordre: d.ordre, actif: d.actif, description: d.description } })}>
                          Modifier
                        </button>
                        <button type="button" className={`btn btn-sm ${d.actif ? 'btn-outline-warning' : 'btn-outline-success'}`}
                                onClick={() => basculerActif('direction', d.id, d.actif)}>
                          {d.actif ? 'Désactiver' : 'Activer'}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {(directions || []).length === 0 && <tr><td colSpan="6" className="hab-muted">Aucune direction.</td></tr>}
            </tbody>
          </table>
        </>
      )}

      {onglet === 'departements' && (
        <>
          <CarteForm titre="Nouveau département" testid="form-departement">
            <div className="row g-2">
              <div className="col-md-2">
                <label className="form-label small fw-bold">Code *</label>
                <input className="form-control form-control-sm" value={formDep.code}
                       onChange={(e) => setFormDep({ ...formDep, code: e.target.value })} placeholder="DAF" />
              </div>
              <div className="col-md-3">
                <label className="form-label small fw-bold">Libellé *</label>
                <input className="form-control form-control-sm" value={formDep.libelle}
                       onChange={(e) => setFormDep({ ...formDep, libelle: e.target.value })} placeholder="Affaires Financières" />
              </div>
              <div className="col-md-3">
                <label className="form-label small">Direction</label>
                <select className="form-select form-select-sm" value={formDep.direction}
                        onChange={(e) => setFormDep({ ...formDep, direction: e.target.value })}>
                  <option value="">— autonome —</option>
                  {(directions || []).map((d) => <option key={d.id} value={d.id}>{d.libelle}</option>)}
                </select>
              </div>
              <div className="col-md-4">
                <label className="form-label small">Description</label>
                <input className="form-control form-control-sm" value={formDep.description}
                       onChange={(e) => setFormDep({ ...formDep, description: e.target.value })} />
              </div>
            </div>
            <button type="button" className="btn btn-sm btn-success mt-2" data-testid="creer-departement"
                    onClick={() => creer(creerDepartement, formDep, ['code', 'libelle'], 'form-departement')}>
              Créer
            </button>
          </CarteForm>

          <table className="hab-table mt-3">
            <thead>
              <tr><th>Libellé</th><th>Code</th><th>Direction</th><th>Services</th><th>Comptes</th><th>Statut</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {(departements || []).map((d) => (
                <tr key={d.id}>
                  <td>
                    {edition?.type === 'departement' && edition.id === d.id ? (
                      <input className="form-control form-control-sm" value={edition.form.libelle}
                             onChange={(e) => setEdition({ ...edition, form: { ...edition.form, libelle: e.target.value } })} />
                    ) : d.libelle}
                  </td>
                  <td><code>{d.code}</code></td>
                  <td>
                    {edition?.type === 'departement' && edition.id === d.id ? (
                      <select className="form-select form-select-sm" value={edition.form.direction}
                              onChange={(e) => setEdition({ ...edition, form: { ...edition.form, direction: e.target.value } })}>
                        <option value="">— autonome —</option>
                        {(directions || []).map((x) => <option key={x.id} value={x.id}>{x.libelle}</option>)}
                      </select>
                    ) : d.direction ? d.direction.libelle : <span className="hab-muted">autonome</span>}
                  </td>
                  <td>{d.nb_services}</td>
                  <td>{d.nb_comptes}</td>
                  <td>
                    {edition?.type === 'departement' && edition.id === d.id ? (
                      <select className="form-select form-select-sm" value={edition.form.actif ? '1' : '0'}
                              onChange={(e) => setEdition({ ...edition, form: { ...edition.form, actif: e.target.value === '1' } })}>
                        <option value="1">Actif</option><option value="0">Inactif</option>
                      </select>
                    ) : <BadgeActif actif={d.actif} />}
                  </td>
                  <td className="text-nowrap">
                    {edition?.type === 'departement' && edition.id === d.id ? (
                      <>
                        <button type="button" className="btn btn-sm btn-success me-1" onClick={validerEdition}>OK</button>
                        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setEdition(null)}>Annuler</button>
                      </>
                    ) : (
                      <>
                        <button type="button" className="btn btn-sm btn-outline-primary me-1"
                                data-testid={`detail-departement-${d.id}`}
                                onClick={() => ouvrirDetailDep(d)}>
                          <i className="bi bi-list-ul me-1" />Détail
                        </button>
                        <button type="button" className="btn btn-sm btn-outline-secondary me-1" data-testid={`modifier-${d.id}`}
                                onClick={() => setEdition({
                                  type: 'departement', id: d.id,
                                  form: {
                                    libelle: d.libelle, ordre: d.ordre, actif: d.actif,
                                    description: d.description, direction: d.direction_id || '',
                                  },
                                })}>
                          Modifier
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {(departements || []).length === 0 && <tr><td colSpan="7" className="hab-muted">Aucun département.</td></tr>}
            </tbody>
          </table>

          {detailDep && (
            <div className="hab-carte mt-3" data-testid="detail-departement">
              <div className="d-flex justify-content-between align-items-center">
                <h3 className="h6 mb-0">Département : {detailDep.libelle}</h3>
                <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setDetailDep(null)}>Fermer</button>
              </div>
              <h4 className="h6 mt-3">Services ({(detailDep.services || []).length})</h4>
              {detailDep.services?.length ? (
                <ul className="mb-0 small">
                  {detailDep.services.map((s) => <li key={s.id}>{s.nom}</li>)}
                </ul>
              ) : <p className="hab-muted small mb-2">Aucun service rattaché.</p>}
              <RattachementsPanel
                entiteId={detailDep.id}
                entiteLibelle={detailDep.libelle}
                comptesRattaches={detailDep.comptes || []}
                rattacher={rattacherCompteDepartement}
                detacher={detacherCompteDepartement}
                toast={showToast}
              />
            </div>
          )}
        </>
      )}

      {onglet === 'services' && (
        <>
          <CarteForm titre="Nouveau service" testid="form-service">
            <div className="row g-2 align-items-end">
              <div className="col-md-4">
                <label className="form-label small fw-bold">Nom *</label>
                <input className="form-control form-control-sm" value={formSvc.nom}
                       onChange={(e) => setFormSvc({ ...formSvc, nom: e.target.value })} placeholder="Comptabilité" />
              </div>
              <div className="col-md-4">
                <label className="form-label small">Département</label>
                <select className="form-select form-select-sm" value={formSvc.departement}
                        onChange={(e) => setFormSvc({ ...formSvc, departement: e.target.value })}>
                  <option value="">— non rattaché —</option>
                  {(departements || []).map((d) => <option key={d.id} value={d.id}>{d.libelle}</option>)}
                </select>
              </div>
              <div className="col-md-2">
                <label className="form-label small">Description</label>
                <input className="form-control form-control-sm" value={formSvc.description}
                       onChange={(e) => setFormSvc({ ...formSvc, description: e.target.value })} />
              </div>
              <div className="col-md-2">
                <button type="button" className="btn btn-sm btn-success w-100" data-testid="creer-service"
                        onClick={() => creer(creerServiceOrganisation, formSvc, ['nom'], 'form-service')}>
                  Créer
                </button>
              </div>
            </div>
          </CarteForm>

          <table className="hab-table mt-3">
            <thead>
              <tr><th>Nom</th><th>Département</th><th>Comptes</th><th>Statut</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {(services || []).map((s) => (
                <tr key={s.id}>
                  <td>
                    {edition?.type === 'service' && edition.id === s.id ? (
                      <input className="form-control form-control-sm" value={edition.form.nom}
                             onChange={(e) => setEdition({ ...edition, form: { ...edition.form, nom: e.target.value } })} />
                    ) : s.nom}
                  </td>
                  <td>
                    {edition?.type === 'service' && edition.id === s.id ? (
                      <select className="form-select form-select-sm" value={edition.form.departement}
                              onChange={(e) => setEdition({ ...edition, form: { ...edition.form, departement: e.target.value } })}>
                        <option value="">— non rattaché —</option>
                        {(departements || []).map((d) => <option key={d.id} value={d.id}>{d.libelle}</option>)}
                      </select>
                    ) : s.departement ? s.departement.libelle : <span className="hab-muted">non rattaché</span>}
                  </td>
                  <td>{s.nb_comptes}</td>
                  <td>
                    {edition?.type === 'service' && edition.id === s.id ? (
                      <select className="form-select form-select-sm" value={edition.form.actif ? '1' : '0'}
                              onChange={(e) => setEdition({ ...edition, form: { ...edition.form, actif: e.target.value === '1' } })}>
                        <option value="1">Actif</option><option value="0">Inactif</option>
                      </select>
                    ) : <BadgeActif actif={s.actif} />}
                  </td>
                  <td className="text-nowrap">
                    {edition?.type === 'service' && edition.id === s.id ? (
                      <>
                        <button type="button" className="btn btn-sm btn-success me-1" onClick={validerEdition}>OK</button>
                        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setEdition(null)}>Annuler</button>
                      </>
                    ) : (
                      <>
                        <button type="button" className="btn btn-sm btn-outline-primary me-1"
                                data-testid={`detail-service-${s.id}`}
                                onClick={() => ouvrirDetailSvc(s)}>
                          <i className="bi bi-list-ul me-1" />Détail
                        </button>
                        <button type="button" className="btn btn-sm btn-outline-secondary me-1" data-testid={`modifier-${s.id}`}
                                onClick={() => setEdition({
                                  type: 'service', id: s.id,
                                  form: { nom: s.nom, description: s.description, actif: s.actif, departement: s.departement_id || '' },
                                })}>
                          Modifier
                        </button>
                        <button type="button" className={`btn btn-sm ${s.actif ? 'btn-outline-warning' : 'btn-outline-success'}`}
                                onClick={() => basculerActif('service', s.id, s.actif)}>
                          {s.actif ? 'Désactiver' : 'Activer'}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {(services || []).length === 0 && <tr><td colSpan="5" className="hab-muted">Aucun service.</td></tr>}
            </tbody>
          </table>

          {detailSvc && (
            <div className="hab-carte mt-3" data-testid="detail-service">
              <div className="d-flex justify-content-between align-items-center">
                <h3 className="h6 mb-0">Service : {detailSvc.nom}</h3>
                <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setDetailSvc(null)}>Fermer</button>
              </div>
              <RattachementsPanel
                entiteId={detailSvc.id}
                entiteLibelle={detailSvc.nom}
                comptesRattaches={detailSvc.comptes || []}
                rattacher={rattacherCompteService}
                detacher={detacherCompteService}
                toast={showToast}
              />
            </div>
          )}
        </>
      )}
    </section>
  )
}
