/** Contenu des étapes de l'assistant de création (U4, §3.5). */
import { BadgeSensible, BadgeCanal } from './partages'
import PerimetresOrganisation from './PerimetresOrganisation'
import { libelleDomaine } from '@/utils/habilitations'

const input = 'form-control'
const select = 'form-select'

export function EtapePersonne({ personne, setPersonne, resultats, recherche, setRecherche }) {
  const selectionner = (p) => setPersonne({ ...personne, resultatSelectionne: p, matricule: p.matricule })
  return (
    <div data-testid="etape-personne">
      <h3 className="h6">1 · Identité de la personne</h3>
      <p className="hab-muted">On recherche d'abord une personne déjà connue pour ne pas créer de doublon.</p>
      <input className={input} placeholder="Matricule, nom ou email…" value={recherche}
             onChange={(e) => setRecherche(e.target.value)} data-testid="recherche-personne" />
      {resultats.length > 0 && (
        <div className="hab-carte mt-2" data-testid="resultats-personne">
          {resultats.map((p) => (
            <button type="button" key={p.id} className="list-group-item list-group-item-action"
                    onClick={() => selectionner(p)}>
              {p.prenoms} {p.nom} — <span className="hab-muted">{p.matricule}</span>
            </button>
          ))}
        </div>
      )}
      {personne.resultatSelectionne ? (
        <div className="hab-avertissement mt-2" data-testid="personne-trouvee">
          Personne existante retenue : {personne.resultatSelectionne.prenoms}{' '}
          {personne.resultatSelectionne.nom} ({personne.resultatSelectionne.matricule})
        </div>
      ) : (
        <div className="row g-2 mt-1">
          <div className="col-md-6"><label className="form-label">Nom *</label>
            <input className={input} value={personne.nom} data-testid="input-nom"
                   onChange={(e) => setPersonne({ ...personne, nom: e.target.value })} /></div>
          <div className="col-md-6"><label className="form-label">Prénoms</label>
            <input className={input} value={personne.prenoms}
                   onChange={(e) => setPersonne({ ...personne, prenoms: e.target.value })} /></div>
          <div className="col-md-6"><label className="form-label">Email institutionnel</label>
            <input className={input} type="email" value={personne.email}
                   onChange={(e) => setPersonne({ ...personne, email: e.target.value })} /></div>
          <div className="col-md-6"><label className="form-label">Téléphone</label>
            <input className={input} value={personne.telephone}
                   onChange={(e) => setPersonne({ ...personne, telephone: e.target.value })} /></div>
          <div className="col-12"><label className="form-label">Service / direction</label>
            <input className={input} value={personne.service}
                   onChange={(e) => setPersonne({ ...personne, service: e.target.value })} /></div>
        </div>
      )}
    </div>
  )
}

export function EtapeCompte({ compte, setCompte, legacyOptions }) {
  const maj = (k, v) => setCompte({ ...compte, [k]: v })
  return (
    <div data-testid="etape-compte">
      <h3 className="h6">2 · Compte de connexion</h3>
      <p className="hab-muted">
        Le « rôle d'accès actuel » est provisoire : il assure la connexion pendant la période
        d'observation, puis sera remplacé par les rôles métier à la bascule (U8).
      </p>
      <div className="row g-2">
        <div className="col-md-6"><label className="form-label">Identifiant *</label>
          <input className={input} value={compte.username} data-testid="input-username"
                 onChange={(e) => maj('username', e.target.value)} /></div>
        <div className="col-md-6"><label className="form-label">Email</label>
          <input className={input} type="email" value={compte.email}
                 onChange={(e) => maj('email', e.target.value)} /></div>
        <div className="col-md-6"><label className="form-label">Mot de passe initial * (6 caractères min.)</label>
          <input className={input} type="password" value={compte.mot_de_passe} data-testid="input-mdp"
                 onChange={(e) => maj('mot_de_passe', e.target.value)} /></div>
        <div className="col-md-6"><label className="form-label">Rôle d'accès actuel (provisoire) *</label>
          <select className={select} value={compte.role_legacy} data-testid="select-role-legacy"
                  onChange={(e) => maj('role_legacy', e.target.value)}>
            <option value="">— Choisir —</option>
            {legacyOptions.map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
          </select></div>
        <div className="col-md-6"><label className="form-label">Canal d'accès</label>
          <select className={select} value={compte.canal}
                  onChange={(e) => maj('canal', e.target.value)}>
            <option value="WEB">Web</option>
            <option value="MOBILE">Mobile</option>
            <option value="LES_DEUX">Web et mobile</option>
          </select></div>
      </div>
    </div>
  )
}

export function EtapeRoles({ roles, selection, basculerRole, changerNiveau, changerSignature }) {
  const codes = selection.map((s) => s.code)
  const incompatibles = new Set()
  selection.forEach((s) => {
    const role = roles.find((r) => r.code === s.code)
    role?.incompatible_avec?.forEach((c) => codes.includes(c) && incompatibles.add(c) && incompatibles.add(s.code))
  })
  const parDomaine = roles.reduce((acc, r) => {
    (acc[r.domaine] = acc[r.domaine] || []).push(r)
    return acc
  }, {})
  return (
    <div data-testid="etape-roles">
      <h3 className="h6">3 · Rôles métier</h3>
      {[...incompatibles].length > 0 && (
        <div className="hab-avertissement bloquant" data-testid="incompatibilite">
          <i className="bi bi-exclamation-triangle me-1" />
          Cumul de rôles incompatibles (séparation des tâches) : {[...incompatibles].join(', ')}.
        </div>
      )}
      <div style={{ maxHeight: 320, overflow: 'auto' }}>
        {Object.entries(parDomaine).map(([domaine, liste]) => (
          <div key={domaine} className="mb-2">
            <div className="fw-semibold small text-muted">{libelleDomaine(domaine)}</div>
            {liste.map((r) => {
              const sel = selection.find((s) => s.code === r.code)
              return (
                <div key={r.code} className="form-check ms-2">
                  <input type="checkbox" className="form-check-input" id={`role-${r.code}`}
                         checked={!!sel} data-testid={`role-${r.code}`}
                         onChange={() => basculerRole(r)} />
                  <label className="form-check-label" htmlFor={`role-${r.code}`}>
                    {r.libelle} <code className="small">{r.code}</code>
                    {r.sensible && <BadgeSensible />} <BadgeCanal canal={r.canal_impose} />
                  </label>
                  {sel && (
                    <span className="ms-2">
                      <select className="form-select form-select-sm d-inline w-auto"
                              value={sel.niveau} data-testid={`niveau-${r.code}`}
                              onChange={(e) => changerNiveau(r.code, e.target.value)}>
                        {['N0', 'N1', 'N2', 'N3', 'N4'].map((n) => <option key={n}>{n}</option>)}
                      </select>
                      {r.sensible && (
                        <label className="ms-2 small">
                          <input type="checkbox" className="me-1" data-testid={`signature-${r.code}`}
                                 checked={!!sel.sensible_valide}
                                 onChange={(e) => changerSignature(r.code, e.target.checked)} />
                          seconde signature
                        </label>
                      )}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

export function EtapePerimetres({ secretariats, basculerSecretariat, motif, setMotif, besoinPerimetre,
                               perimetres, setPerimetres, directions, departements }) {
  return (
    <div data-testid="etape-perimetres">
      <h3 className="h6">4 · Périmètres et motif</h3>
      {besoinPerimetre && (
        <>
          <p className="hab-muted">Un ou plusieurs rôles relèvent d'un périmètre secrétariat.</p>
          <select className="form-select" multiple style={{ minHeight: 120 }}
                  data-testid="select-secretariats"
                  onChange={(e) => {
                    const ids = Array.from(e.target.selectedOptions).map((o) => Number(o.value))
                    basculerSecretariat(ids)
                  }}>
            {secretariats.map((s) => (
              <option key={s.id || s.numero} value={s.id}>{s.nom} ({s.numero})</option>
            ))}
          </select>
        </>
      )}
      {setPerimetres && (
        <PerimetresOrganisation perimetres={perimetres || []}
                                onChange={setPerimetres}
                                directions={directions} departements={departements} />
      )}
      <label className="form-label mt-2">Motif de la création (obligatoire, tracé au journal)</label>
      <textarea className="form-control" rows="3" value={motif} data-testid="input-motif"
                onChange={(e) => setMotif(e.target.value)} placeholder="Ex. : recrutement / affectation / stage…" />
    </div>
  )
}
