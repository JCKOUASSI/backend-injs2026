/**
 * ModificationCompte — l'écran central de la règle S2 : le DIFFÉRENTIEL de
 * droits (gagnés en vert / perdus en rouge) est calculé au fil de l'édition,
 * affiché et doit être explicitement acquitté avant toute validation.
 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import {
  listerRolesCurp, recupererCompte, simulerModification, modifierCompte, messageErreur,
} from '@/services/habilitations'
import { useSecretariats } from '@/hooks/useSecretariats'
import { useToast } from '@/context/ToastContext'
import DifferentialPanel from './DifferentialPanel'
import { BadgeSensible, EnChargement } from './partages'
import PerimetresOrganisation from './PerimetresOrganisation'
import { peutValiderModification, resumerDifferential } from '@/utils/habilitations'
import './habilitations.css'

export default function ModifierCompte() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const { data: secretariats = [] } = useSecretariats()
  const [roles, setRoles] = useState([])
  const [compte, setCompte] = useState(null)
  const [selection, setSelection] = useState([])
  const [secretariatsChoisis, setSecretariatsChoisis] = useState([])
  const [bornes, setBornes] = useState([])
  const [motif, setMotif] = useState('')
  const [acquitte, setAcquitte] = useState(false)
  const [differentiel, setDifferentiel] = useState(null)
  const [enCours, setEnCours] = useState(false)
  const [erreur, setErreur] = useState('')

  useEffect(() => {
    listerRolesCurp().then(setRoles)
    recupererCompte(id).then((c) => {
      setCompte(c)
      setSelection(c.roles_actifs.map((r) => ({ code: r.role, niveau: r.niveau, sensible_valide: r.validee })))
    })
  }, [id])

  const rolesChoisis = selection.map((s) => roles.find((r) => r.code === s.code)).filter(Boolean)
  const besoinPerimetre = rolesChoisis.some((r) => r.perimetre_defaut === 'SECRETARIAT')

  const payloadRoles = useMemo(() => ({
    roles: selection.map((s) => ({
      role: s.code, niveau: s.niveau, sensible_valide: s.sensible_valide,
      perimetres_secretariats: besoinPerimetre ? secretariatsChoisis : [],
      // LOT 5 (L4-02) : bornages Direction/Département, additifs et optionnels.
      perimetres: bornes,
      motif: motif || 'Modification via la console CURP.',
    })),
  }), [selection, secretariatsChoisis, besoinPerimetre, motif, bornes])

  const calculer = async () => {
    setAcquitte(false)
    try {
      setDifferentiel(await simulerModification(id, payloadRoles))
    } catch (e) {
      setErreur(messageErreur(e))
    }
  }

  const resume = differentiel ? resumerDifferential(differentiel) : null
  const valide = peutValiderModification(resume, acquitte) && motif.trim().length >= 8

  const basculerRole = (role) => {
    setAcquitte(false)
    setSelection((sel) => sel.some((s) => s.code === role.code)
      ? sel.filter((s) => s.code !== role.code)
      : [...sel, { code: role.code, niveau: role.niveau_defaut, sensible_valide: false }])
  }

  const valider = async () => {
    setEnCours(true)
    setErreur('')
    try {
      await modifierCompte(id, {
        ...payloadRoles, motif: motif.trim(), differential_accepte: true,
      })
      showToast('Compte modifié.', 'success')
      navigate(`/administration/comptes/${id}`)
    } catch (e) {
      setErreur(messageErreur(e))
    } finally {
      setEnCours(false)
    }
  }

  if (!compte) return <EnChargement />
  return (
    <section data-testid="ecran-modification">
      <div className="hab-carte">
        <h2 className="h5">
          Modifier les droits de {compte.personne?.prenoms} {compte.personne?.nom || compte.username}
        </h2>
        <Link to={`/administration/comptes/${id}`} className="hab-muted">← Retour à la fiche</Link>
        <div className="row mt-3">
          <div className="col-md-6">
            <h3 className="h6">Rôles métier</h3>
            <div style={{ maxHeight: 360, overflow: 'auto' }} data-testid="liste-roles">
              {roles.map((r) => (
                <div key={r.code} className="form-check">
                  <input type="checkbox" className="form-check-input" id={`m-${r.code}`}
                         checked={selection.some((s) => s.code === r.code)}
                         data-testid={`role-${r.code}`}
                         onChange={() => basculerRole(r)} />
                  <label className="form-check-label" htmlFor={`m-${r.code}`}>
                    {r.libelle}{r.sensible && <BadgeSensible />}
                  </label>
                  {selection.some((s) => s.code === r.code) && (
                    <select className="form-select form-select-sm d-inline w-auto ms-2"
                            value={selection.find((s) => s.code === r.code)?.niveau}
                            onChange={(e) => setSelection((sel) => sel.map((s) => s.code === r.code ? { ...s, niveau: e.target.value } : s))}>
                      {['N0', 'N1', 'N2', 'N3', 'N4'].map((n) => <option key={n}>{n}</option>)}
                    </select>
                  )}
                </div>
              ))}
            </div>
            {besoinPerimetre && (
              <div className="mt-2">
                <label className="form-label">Périmètres secrétariat</label>
                <select multiple className="form-select" style={{ minHeight: 90 }}
                        onChange={(e) => setSecretariatsChoisis(Array.from(e.target.selectedOptions, (o) => Number(o.value)))}>
                  {secretariats.map((s) => <option key={s.id || s.numero} value={s.id}>{s.nom}</option>)}
                </select>
              </div>
            )}
            <PerimetresOrganisation perimetres={bornes} onChange={setBornes} />
          </div>
          <div className="col-md-6">
            <button className="btn btn-outline-success btn-sm mb-2" data-testid="bouton-calculer"
                    onClick={calculer}>
              <i className="bi bi-calculator me-1" />Calculer le différentiel
            </button>
            {differentiel && (
              <DifferentialPanel differentiel={differentiel} acquitte={acquitte} onAcquitte={setAcquitte} />
            )}
            <label className="form-label mt-2">Motif de la modification (obligatoire)</label>
            <textarea className="form-control" rows="2" value={motif} data-testid="input-motif-modif"
                      onChange={(e) => setMotif(e.target.value)} />
            {erreur && <p className="text-danger mt-2" data-testid="modif-erreur">{erreur}</p>}
            <button className="btn btn-success mt-3" disabled={!valide || enCours} data-testid="bouton-valider"
                    onClick={valider}
                    title={!valide ? 'Affichez et acceptez le différentiel, puis saisissez un motif.' : ''}>
              {enCours ? 'Enregistrement…' : 'Valider la modification'}
            </button>
            {!resume && <p className="hab-muted small mt-2">Le bouton reste désactivé tant que le différentiel n'a pas été calculé et accepté.</p>}
          </div>
        </div>
      </div>
    </section>
  )
}
