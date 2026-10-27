import React, { cloneElement, useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'
import ConfirmModal from '../components/ConfirmModal'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { isAdminLevelRole } from '../utils/roles'
import '../styles/organigramme.css'

/**
 * Organigramme de l'établissement — Directions / Départements / Services,
 * plus les secrétariats rattachés à la structure (modèle fonctionnel 13 et §15 :
 * « un secrétariat est rattaché à une structure »). Remplace l'écran dédié
 * « Secrétariats » ; le chemin /secretariats redirige vers l'onglet adapté.
 */

const BASE = '/administrations/organigramme'

const ONGLETS = [
  { cle: 'directions', libelle: 'Directions', icone: 'bi-diagram-3', endpoint: 'directions' },
  { cle: 'departements', libelle: 'Départements', icone: 'bi-collection', endpoint: 'departements' },
  { cle: 'services', libelle: 'Services', icone: 'bi-briefcase', endpoint: 'services' },
  { cle: 'secretariats', libelle: 'Secrétariats', icone: 'bi-inboxes', endpoint: 'secretariats' },
]

const FORM_INITIAL = {
  directions: () => ({
    code: '', libelle: '', ordre: 0, description: '', responsable_id: '', adjoint_id: '',
    telephone: '', email: '', localisation: '', actif: true, motif: '',
  }),
  departements: () => ({
    code: '', libelle: '', ordre: 0, direction: '', description: '', responsable_id: '', adjoint_id: '',
    telephone: '', email: '', localisation: '', actif: true, motif: '',
  }),
  services: () => ({
    code: '', nom: '', type_unite: 'SERVICE', parent: '', departement: '', description: '',
    responsable_id: '', adjoint_id: '',
    telephone: '', email: '', localisation: '', actif: true, motif: '',
  }),
  secretariats: () => ({
    nom: '', type: '', direction: '', departement: '', description: '',
    responsable_id: '', adjoint_id: '', telephone: '', email: '', localisation: '',
    actif: true, motif: '',
  }),
}

// Modèle 13.4 : sous-unités (bureau / unité / cellule) greffées sous leur
// service parent — la hiérarchie n'a pas de profondeur codée en dur.
function SousServices({ items }) {
  if (!items || items.length === 0) return []
  return items.map((u) => (
    <NoeudArbre
      key={`su-${u.id}`}
      code={u.code}
      libelle={`${u.type_unite && u.type_unite !== 'SERVICE' ? `${u.type_unite} — ` : ''}${u.nom || u.libelle}`}
      effectif={u.effectif}
      sousNoeuds={SousServices({ items: u.sous_unites })}
    />
  ))
}

/** Initiales du responsable (rendu « pilule » du tableau, comme la référence). */
function initiales(nom) {
  return String(nom || '?')
    .split(/\s+/).filter(Boolean).slice(0, 2).map((m) => m[0].toUpperCase()).join('')
}

function ResponsableBadge({ valeur }) {
  if (!valeur) return <span className="orga-sous-texte">— non pourvu —</span>
  return (
    <span className="orga-avec-avatar" title={`Responsable : ${valeur.nom}`}>
      <span className="orga-avatar">{initiales(valeur.nom)}</span>
      <span>{valeur.nom}</span>
    </span>
  )
}

function NoeudArbre({ libelle, code, effectif, sousNoeuds }) {
  return (
    <li className="orga-noeud">
      <span className="orga-noeud-ligne">
        {code && <code>{code}</code>}
        {libelle}
        {typeof effectif === 'number' && (
          <span className="orga-effectif" title="Comptes rattachés">{effectif}</span>
        )}
      </span>
      {sousNoeuds && sousNoeuds.length > 0 && <ul className="orga-noeud-enfants">{sousNoeuds}</ul>}
    </li>
  )
}

export default function Organisation() {
  const { user: currentUser } = useAuth()
  const isDFRC = isAdminLevelRole(currentUser?.role)
  const { showToast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const ongletParam = searchParams.get('onglet')
  const onglet = ONGLETS.some((o) => o.cle === ongletParam) ? ongletParam : 'directions'

  const [lignes, setLignes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')
  const [voirInactifs, setVoirInactifs] = useState(false)

  const [arbres, setArbres] = useState(null)
  const [montreArbre, setMontreArbre] = useState(false)

  const [reps, setReps] = useState([])
  const [types, setTypes] = useState([])
  const [parents, setParents] = useState({ directions: [], departements: [], services: [] })

  const [modal, setModal] = useState(null) // {editingId, form}
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirmDialog, setConfirmDialog] = useState(null)

  const cfg = ONGLETS.find((o) => o.cle === onglet)

  const charger = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      if (voirInactifs) params.set('actif', '')
      if (q.trim()) params.set('q', q.trim())
      const res = await api.get(`${BASE}/${cfg.endpoint}/?${params.toString()}`)
      const data = Array.isArray(res.data) ? res.data : (res.data.results || [])
      setLignes(voirInactifs ? data : data.filter((x) => x.actif !== false))
      if (montreArbre) {
        const arb = await api.get(`${BASE}/arbre/${voirInactifs ? '?inactifs=1' : ''}`)
        setArbres(arb.data)
      }
    } catch {
      setError('Erreur lors du chargement de l’organigramme')
    } finally {
      setLoading(false)
    }
  }, [cfg.endpoint, montreArbre, voirInactifs, q])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    Promise.all([
      api.get(`${BASE}/responsables/`),
      api.get(`${BASE}/types-secretariat/`),
      api.get(`${BASE}/directions/`),
      api.get(`${BASE}/departements/`),
      api.get(`${BASE}/services/`),
    ]).then(([rUsers, rTypes, rDirs, rDeps, rSvc]) => {
      setReps(Array.isArray(rUsers.data) ? rUsers.data : [])
      setTypes(Array.isArray(rTypes.data) ? rTypes.data : [])
      setParents({
        directions: Array.isArray(rDirs.data) ? rDirs.data : [],
        departements: Array.isArray(rDeps.data) ? rDeps.data : [],
        services: Array.isArray(rSvc.data) ? rSvc.data : [],
      })
    }).catch(() => { /* référentiels optionnels : les sélecteurs restent vides */ })
  }, [])

  const changerOnglet = (cle) => {
    const sp = new URLSearchParams(searchParams)
    sp.set('onglet', cle)
    setSearchParams(sp, { replace: true })
  }

  const openCreate = () => {
    setModal({ editingId: null, form: FORM_INITIAL[onglet]() })
    setFormError('')
  }
  const openEdit = (ligne) => {
    const form = FORM_INITIAL[onglet]()
    Object.keys(form).forEach((champ) => {
      if (champ === 'motif') return
      const brut = ligne[champ]
      form[champ] = brut === null || brut === undefined ? (champ === 'actif' ? true : '') : brut
      if (['responsable_id', 'adjoint_id'].includes(champ) && brut && typeof brut === 'object') {
        form[champ] = brut.id
      }
    })
    setModal({ editingId: ligne.id, form })
    setFormError('')
  }

  const soumettre = async (e) => {
    e.preventDefault()
    setFormError('')
    setSaving(true)
    const payload = { ...modal.form }
    Object.keys(payload).forEach((k) => {
      if (payload[k] === '' && ['responsable_id', 'adjoint_id', 'type', 'direction', 'departement'].includes(k)) {
        payload[k] = null
      }
    })
    try {
      const url = modal.editingId ? `${BASE}/${cfg.endpoint}/${modal.editingId}/` : `${BASE}/${cfg.endpoint}/`
      if (modal.editingId) await api.patch(url, payload)
      else await api.post(url, payload)
      setModal(null)
      showToast(modal.editingId ? 'Unité modifiée' : 'Unité créée')
      charger()
    } catch (err) {
      const data = err.response?.data
      if (data && typeof data === 'object') {
        const msgs = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
        setFormError(msgs.join('\n'))
      } else {
        setFormError('Erreur lors de la sauvegarde')
      }
    } finally {
      setSaving(false)
    }
  }

  const desactiver = (ligne) => {
    setConfirmDialog({
      message: `Désactiver « ${ligne.libelle || ligne.nom} » ?`,
      detail: 'L’unité restera dans l’historique et les rattachements existants sont conservés ; elle disparaîtra simplement des listes.',
      onConfirm: async () => {
        try {
          await api.delete(`${BASE}/${cfg.endpoint}/${ligne.id}/`)
          showToast('Unité désactivée')
          charger()
        } catch {
          showToast('Erreur lors de la désactivation', 'error')
        }
      },
    })
  }

  const reactiver = async (ligne) => {
    try {
      await api.patch(`${BASE}/${cfg.endpoint}/${ligne.id}/`, { actif: true, motif: 'Réactivation depuis l’organigramme.' })
      showToast('Unité réactivée')
      charger()
    } catch {
      showToast('Erreur lors de la réactivation', 'error')
    }
  }

  const selectResponsable = (valeur, onChange) => (
    <select className="input" value={valeur || ''} onChange={(e) => onChange(e.target.value)}>
      <option value="">— aucun —</option>
      {reps.map((u) => <option key={u.id} value={u.id}>{u.nom} ({u.role})</option>)}
    </select>
  )

  const colonnes = {
    directions: ['Code', 'Libellé', 'Responsable', 'Contact', 'Localisation', 'Départements', 'Comptes'],
    departements: ['Code', 'Libellé', 'Direction', 'Responsable', 'Contact', 'Services', 'Comptes'],
    services: ['Code', 'Nom', 'Type', 'Unité parente', 'Département', 'Responsable', 'Contact', 'Comptes'],
    secretariats: ['Numéro', 'Nom', 'Type', 'Rattachement', 'Responsable', 'Participants', 'Modules'],
  }[onglet]

  const rendreLigne = (ligne) => {
    const base = (
      <>
        {onglet === 'secretariats' ? (
          <>
            <td><code>{ligne.numero}</code></td>
            <td>
              <div className="orga-cellule">
                <strong>{ligne.nom}</strong>
                {!ligne.actif && <span className="badge-bg-warning">inactif</span>}
              </div>
            </td>
            <td>{ligne.type_libelle || <span className="text-muted">—</span>}</td>
            <td>{ligne.direction_libelle || ligne.departement_libelle || <span className="text-muted">non rattaché</span>}</td>
            <td><ResponsableBadge valeur={ligne.responsable} /></td>
            <td><span className="orga-pastille">{ligne.nb_participants ?? 0}</span></td>
            <td><span className="orga-pastille">{ligne.nb_modules ?? 0}</span></td>
          </>
        ) : (
          <>
            <td><code>{ligne.code}</code></td>
            <td>
              <div className="orga-cellule">
                <strong>{onglet === 'services' ? ligne.nom : ligne.libelle}</strong>
                {!ligne.actif && <span className="badge-bg-warning">inactif</span>}
                {ligne.description && <span className="orga-sous-texte">{ligne.description}</span>}
              </div>
            </td>
            {onglet === 'services' && (
              <td>
                {ligne.type_unite && ligne.type_unite !== 'SERVICE'
                  ? <span className="badge-bg-secondary">{ligne.type_unite}</span>
                  : <span className="text-muted">service</span>}
                {ligne.nb_sous_unites > 0 && <small className="ms-1 text-muted">({ligne.nb_sous_unites})</small>}
              </td>
            )}
            {onglet === 'services' && <td>{ligne.parent_libelle || <span className="text-muted">—</span>}</td>}
            {onglet === 'departements' && <td>{ligne.direction_libelle || <span className="text-muted">autonome</span>}</td>}
            <td><ResponsableBadge valeur={ligne.responsable} /></td>
            <td>
              <div className="orga-cellule">
                {ligne.telephone && <span><i className="bi bi-telephone me-1"></i>{ligne.telephone}</span>}
                {ligne.email && <span className="orga-sous-texte"><i className="bi bi-envelope me-1"></i>{ligne.email}</span>}
                {!ligne.telephone && !ligne.email && <span className="orga-sous-texte">—</span>}
              </div>
            </td>
            {onglet !== 'secretariats' && <td>{ligne.localisation || <span className="text-muted">—</span>}</td>}
            {onglet === 'directions' && <td><span className="orga-pastille">{ligne.nb_departements ?? 0}</span></td>}
            {onglet === 'departements' && <td><span className="orga-pastille">{ligne.nb_services ?? 0}</span></td>}
            <td><span className="orga-pastille orga-pastille--neutre">{ligne.effectif ?? 0}</span></td>
          </>
        )}
      </>
    )
    return (
      <tr key={ligne.id}>
        {base}
        <td className="orga-actions-cell">
          <div className="orga-ligne-actions">
            {isDFRC && (
              <>
                <button className="btn btn-outline-secondary btn-sm" onClick={() => openEdit(ligne)} title="Modifier">
                  <i className="bi bi-pencil"></i>
                </button>
                {ligne.actif === false ? (
                  <button className="btn btn-outline-success btn-sm" onClick={() => reactiver(ligne)} title="Réactiver">
                    <i className="bi bi-arrow-counterclockwise"></i>
                  </button>
                ) : (
                  <button className="btn btn-outline-danger btn-sm" onClick={() => desactiver(ligne)} title="Désactiver">
                    <i className="bi bi-slash-circle"></i>
                  </button>
                )}
              </>
            )}
          </div>
        </td>
      </tr>
    )
  }

  const champ = (cle, libelle, composant) => (
    <div className="mb-2">
      <label className="orga-label" htmlFor={`orga-champ-${cle}`}>{libelle}</label>
      {cloneElement(composant, { id: `orga-champ-${cle}` })}
    </div>
  )

  const rendreFormulaire = () => {
    const { form } = modal
    const set = (cle) => (e) => setModal((m) => ({ ...m, form: { ...m.form, [cle]: e.target.value } }))
    const setBool = (cle) => (e) => setModal((m) => ({ ...m, form: { ...m.form, [cle]: e.target.checked } }))
    const texte = (cle, attrs = {}) => (
      <input className="input" value={form[cle] ?? ''} onChange={set(cle)} {...attrs} />
    )
    return (
      <div className="modal-overlay" onClick={() => setModal(null)}>
        <div className="modal-card" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h6 className="mb-0">{modal.editingId ? 'Modifier l’unité' : `Nouvelle unité — ${cfg.libelle.toLowerCase()}`}</h6>
            <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setModal(null)}>×</button>
          </div>
          <form onSubmit={soumettre}>
            <div className="modal-body">
              {formError && <div className="error-message" style={{ whiteSpace: 'pre-line' }}>{formError}</div>}
              <div className="orga-grille">
                <div className="orga-col">
                  {(onglet === 'directions' || onglet === 'departements')
                    && champ('code', 'Code *', texte('code', { placeholder: onglet === 'directions' ? 'ex. DAF' : 'ex. DEP-PED' }))}
                  {(onglet === 'directions' || onglet === 'departements')
                    && champ('libelle', 'Libellé *', texte('libelle'))}
                  {onglet === 'services'
                    && champ('nom', 'Nom *', texte('nom', { placeholder: 'ex. Service du courrier' }))}
                  {onglet === 'services'
                    && champ('code', 'Code court', texte('code', { placeholder: 'ex. SCOL01' }))}
                  {onglet === 'secretariats'
                    && champ('nom', 'Nom *', texte('nom', { placeholder: 'ex. Scolarité CAA' }))}
                  {onglet === 'departements' && champ('direction', 'Direction', (
                    <select className="input" value={form.direction || ''} onChange={set('direction')}>
                      <option value="">— autonome —</option>
                      {parents.directions.map((d) => <option key={d.id} value={d.id}>{d.libelle}</option>)}
                    </select>
                  ))}
                  {onglet === 'services' && champ('type_unite', 'Type d’unité', (
                    <select className="input" value={form.type_unite || 'SERVICE'} onChange={set('type_unite')}>
                      {['SERVICE', 'BUREAU', 'UNITE', 'CELLULE', 'AUTRE'].map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  ))}
                  {onglet === 'services' && champ('parent', 'Unité rattachante', (
                    <select className="input" value={form.parent || ''} onChange={set('parent')}>
                      <option value="">— aucune —</option>
                      {lignes
                        .filter((x) => x.id !== modal.editingId && !x.parent)
                        .map((x) => <option key={x.id} value={x.id}>{x.nom}</option>)}
                    </select>
                  ))}
                  {onglet === 'services' && champ('departement', 'Département', (
                    <select className="input" value={form.departement || ''} onChange={set('departement')}>
                      <option value="">— non rattaché —</option>
                      {parents.departements.map((d) => <option key={d.id} value={d.id}>{d.libelle}</option>)}
                    </select>
                  ))}
                  {onglet === 'secretariats' && (
                    <>
                      {champ('type', 'Type', (
                        <select className="input" value={form.type || ''} onChange={set('type')}>
                          <option value="">—</option>
                          {types.map((t) => <option key={t.id} value={t.id}>{t.libelle}</option>)}
                        </select>
                      ))}
                      {champ('direction', 'Direction (ou département)', (
                        <select className="input" value={form.direction || ''} onChange={set('direction')}>
                          <option value="">—</option>
                          {parents.directions.map((d) => <option key={d.id} value={d.id}>{d.libelle}</option>)}
                        </select>
                      ))}
                      {champ('departement', 'Département (ou direction)', (
                        <select className="input" value={form.departement || ''} onChange={set('departement')}>
                          <option value="">—</option>
                          {parents.departements.map((d) => <option key={d.id} value={d.id}>{d.libelle}</option>)}
                        </select>
                      ))}
                    </>
                  )}
                  {(onglet === 'directions' || onglet === 'departements')
                    && champ('ordre', 'Ordre d’affichage', texte('ordre', { type: 'number' }))}
                </div>
                <div className="orga-col">
                  {champ('responsable_id', 'Responsable', selectResponsable(form.responsable_id, set('responsable_id')))}
                  {champ('adjoint_id', 'Adjoint(e)', selectResponsable(form.adjoint_id, set('adjoint_id')))}
                  {champ('telephone', 'Téléphone', texte('telephone', { placeholder: '+225 …' }))}
                  {champ('email', 'E-mail', texte('email', { type: 'email' }))}
                  {champ('localisation', 'Localisation', texte('localisation', { placeholder: 'bâtiment, étage, porte' }))}
                  {champ('description', 'Description', (
                    <textarea className="input" rows={2} value={form.description ?? ''} onChange={set('description')} />
                  ))}
                  {champ('motif', 'Motif du changement', texte('motif', { placeholder: 'journalisé avec la modification' }))}
                  <div className="orga-check">
                    <input id="orga-actif" type="checkbox" className="orga-check-input" checked={form.actif !== false} onChange={setBool('actif')} />
                    <label htmlFor="orga-actif" className="orga-check-label">Unité active</label>
                  </div>
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-outline-secondary me-2" onClick={() => setModal(null)}>Annuler</button>
              <button type="submit" className="btn btn-dfrc" disabled={saving}>
                {saving ? 'Enregistrement…' : 'Enregistrer'}
              </button>
            </div>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="orga-page">
      <div className="card orga-hero">
        <div className="card-body">
          <div className="orga-hero-row">
            <div>
              <span className="orga-ensemble">Organisation</span>
              <h6 className="orga-titre">
                <i className="bi bi-diagram-3"></i>Directions / Départements / Services
              </h6>
              <small className="orga-sous-titre">
                Structure hiérarchique de l’établissement (modèle 13) ; les secrétariats s’y rattachent.
              </small>
            </div>
            <div className="orga-actions">
              <label className="orga-switch">
                <input type="checkbox" checked={voirInactifs} onChange={(e) => setVoirInactifs(e.target.checked)} />
                <small>Inactifs</small>
              </label>
              <button className="btn btn-outline-secondary btn-sm" onClick={() => setMontreArbre((v) => !v)}>
                <i className={`bi bi-${montreArbre ? 'list-ul' : 'share'} me-1`}></i>{montreArbre ? 'Liste' : 'Arbre'}
              </button>
              {isDFRC && !montreArbre && (
                <button className="btn btn-dfrc" onClick={openCreate}>
                  <i className="bi bi-plus-lg me-1"></i>Nouvelle unité
                </button>
              )}
            </div>
          </div>
          <ul className="orga-onglets">
            {ONGLETS.map((o) => (
              <li key={o.cle}>
                <button
                  type="button"
                  className={`orga-onglet ${onglet === o.cle ? 'is-active' : ''}`}
                  onClick={() => changerOnglet(o.cle)}
                >
                  <i className={`bi ${o.icone} me-1`}></i>{o.libelle}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {montreArbre ? (
        <div className="card orga-panel">
          <div className="card-header-bar orga-panel-head">
            <span><i className="bi bi-share"></i>Arbre de l’organisation</span>
            {loading && <span className="spinner"></span>}
          </div>
          <div className="card-body">
            {!arbres ? <div className="loading"><div className="spinner"></div></div> : (
              <ul className="orga-arbre">
                {(arbres.directions || []).map((d) => (
                  <NoeudArbre
                    key={`d-${d.id}`}
                    code={d.code}
                    libelle={d.libelle}
                    effectif={d.effectif}
                    sousNoeuds={[
                      ...(d.departements || []).map((dep) => (
                        <NoeudArbre
                          key={`p-${dep.id}`}
                          code={dep.code}
                          libelle={dep.libelle}
                          effectif={dep.effectif}
                          sousNoeuds={[
                            ...(dep.services || []).map((s) => (
                              <NoeudArbre
                          key={`s-${s.id}`}
                          code={s.code}
                          libelle={s.libelle}
                          effectif={s.effectif}
                          sousNoeuds={[<SousServices key={`ssv-${s.id}`} items={s.sous_unites} />]}
                        />
                            )),
                            ...(dep.secretariats || []).map((s) => (
                              <NoeudArbre key={`ss-${s.id}`} code={s.numero} libelle={`Secrétariat — ${s.nom}`} effectif={s.nb_participants} />
                            )),
                          ].filter(Boolean)}
                        />
                      )),
                      ...(d.secretariats || []).map((s) => (
                        <NoeudArbre key={`sd-${s.id}`} code={s.numero} libelle={`Secrétariat — ${s.nom}`} effectif={s.nb_participants} />
                      )),
                    ].filter(Boolean)}
                  />
                ))}
                {(arbres.non_rattaches?.departements || []).length + (arbres.non_rattaches?.services || []).length
                  + (arbres.non_rattaches?.secretariats || []).length > 0 && (
                  <NoeudArbre
                    libelle='Unités sans rattachement'
                    sousNoeuds={[
                      ...(arbres.non_rattaches.departements || []).map((d) => (
                        <NoeudArbre key={`nd-${d.id}`} code={d.code} libelle={d.libelle} effectif={d.effectif} />
                      )),
                      ...(arbres.non_rattaches.services || []).map((s) => (
                        <NoeudArbre
                          key={`ns-${s.id}`}
                          code={s.code}
                          libelle={s.nom}
                          effectif={s.effectif}
                          sousNoeuds={[<SousServices key={`ssv-${s.id}`} items={s.sous_unites} />]}
                        />
                      )),
                      ...(arbres.non_rattaches.secretariats || []).map((s) => (
                        <NoeudArbre key={`nse-${s.id}`} code={s.numero} libelle={`Secrétariat — ${s.nom}`} effectif={s.nb_participants} />
                      )),
                    ]}
                  />
                )}
              </ul>
            )}
          </div>
        </div>
      ) : (
        <div className="card orga-panel">
          <div className="card-header-bar orga-panel-head">
            <span><i className={`bi ${cfg.icone}`}></i>{cfg.libelle}</span>
            <div className="orga-panel-actions">
              <div className="orga-recherche">
                <i className="bi bi-search"></i>
                <input
                  type="search"
                  placeholder="Rechercher…"
                  aria-label="Rechercher une unité"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>
              <span className="orga-compteur">{lignes.length} unité(s)</span>
            </div>
          </div>
          <div className="card-body-flush">
            {loading ? (
              <div className="loading"><div className="spinner"></div></div>
            ) : lignes.length === 0 ? (
              <div className="orga-vide">
                <i className={`bi ${cfg.icone}`}></i>
                <span className="orga-vide-titre">Aucune unité dans cet onglet</span>
                <span className="orga-vide-aide">
                  Créez une première unité
                  {onglet === 'secretariats' ? ' et rattachez-la à une direction ou à un département.' : '.'}
                </span>
                {isDFRC && (
                  <button className="btn btn-dfrc btn-sm" onClick={openCreate}>
                    <i className="bi bi-plus-lg me-1"></i>Créer une unité
                  </button>
                )}
              </div>
            ) : (
              <div className="table-container">
                <table className="table orga-table">
                  <thead>
                    <tr>{colonnes.map((c) => <th key={c}>{c}</th>)}<th className="text-end">Actions</th></tr>
                  </thead>
                  <tbody>{lignes.map(rendreLigne)}</tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {modal && rendreFormulaire()}
      {confirmDialog && (
        <ConfirmModal
          message={confirmDialog.message}
          detail={confirmDialog.detail}
          onConfirm={() => { const f = confirmDialog.onConfirm; setConfirmDialog(null); f() }}
          onCancel={() => setConfirmDialog(null)}
        />
      )}
    </div>
  )
}
