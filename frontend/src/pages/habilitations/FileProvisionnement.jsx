/**
 * FileProvisionnement (U5, C3) — file de VALIDATION HUMAINE OBLIGATOIRE.
 *
 * Les sondes ne créent jamais rien : elles déposent des propositions qu'un
 * administrateur instruit ici (approbation ou rejet motivé). L'écran permet
 * aussi de lancer manuellement le scan des déclencheurs activés et de
 * compléter, pour les recrutements, le rôle d'accès et le rôle CURP que la
 * sonde ne peut pas déduire. Aucun bouton n'applique une proposition sans
 * motif saisi.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  listerPropositions,
  approuverProposition,
  rejeterProposition,
  scannerProvisions,
  listerRolesCurp,
  messageErreur,
} from '@/services/habilitations'
import { useToast } from '@/context/ToastContext'
import { EnChargement } from './partages'
import './habilitations.css'

const STATUTS = [
  ['EN_ATTENTE', 'En attente'],
  ['APPLIQUEE', 'Appliquées'],
  ['REJETEE', 'Rejetées'],
  ['ANNULEE', 'Annulées'],
]
const ROLES_LEGACY = ['', 'SECRETARIAT', 'PERSONNEL', 'FORMATEUR', 'AUDITEUR']

function DecisionModal({ proposition, roles, mode, onClose, onResult }) {
  const [motif, setMotif] = useState('')
  const [roleLegacy, setRoleLegacy] = useState('')
  const [roleCurp, setRoleCurp] = useState('')
  const [enCours, setEnCours] = useState(false)
  const [erreur, setErreur] = useState('')
  const aCompleter = !!proposition.proposition?.role_a_completer
  const motifOk = motif.trim().length >= 8

  const valider = async () => {
    setEnCours(true)
    setErreur('')
    try {
      if (mode === 'approuver') {
        const ajustements = aCompleter
          ? {
              identifiants: { role_legacy: roleLegacy },
              roles: roleCurp ? [{ role: roleCurp, niveau: 'N2' }] : [],
            }
          : {}
        await approuverProposition(proposition.id, motif.trim(), ajustements)
      } else {
        await rejeterProposition(proposition.id, motif.trim())
      }
      onResult()
      onClose()
    } catch (e) {
      setErreur(messageErreur(e))
    } finally {
      setEnCours(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h5>
            <i className={`bi ${mode === 'approuver' ? 'bi-check2-circle' : 'bi-x-circle'} me-2`} />
            {mode === 'approuver' ? 'Approuver la proposition' : 'Rejeter la proposition'}
          </h5>
          <button className="btn-close" onClick={onClose} aria-label="Fermer">&times;</button>
        </div>
        <div className="modal-body">
          <p className="fw-semibold mb-1">{proposition.source_libelle}</p>
          <p className="text-muted small mb-3">
            {proposition.declencheur_libelle} · {proposition.action_libelle} · {proposition.source}
          </p>
          {aCompleter && mode === 'approuver' && (
            <div className="row g-2 mb-2" data-testid="zone-role-completer">
              <div className="col-6">
                <label className="form-label">Rôle d'accès actuel</label>
                <select className="form-select" data-testid="role-legacy"
                        value={roleLegacy} onChange={(e) => setRoleLegacy(e.target.value)}>
                  {ROLES_LEGACY.map((r) => <option key={r} value={r}>{r || 'À choisir…'}</option>)}
                </select>
              </div>
              <div className="col-6">
                <label className="form-label">Rôle CURP</label>
                <select className="form-select" data-testid="role-curp"
                        value={roleCurp} onChange={(e) => setRoleCurp(e.target.value)}>
                  <option value="">Aucun (à traiter plus tard)</option>
                  {roles.map((r) => <option key={r.code} value={r.code}>{r.libelle}</option>)}
                </select>
              </div>
            </div>
          )}
          <label className="form-label">Motif (obligatoire, conservé au journal)</label>
          <textarea className="form-control" rows="3" data-testid="motif-decision"
                    value={motif} onChange={(e) => setMotif(e.target.value)} />
          {motif.length > 0 && !motifOk && (
            <div className="form-text text-danger">Le motif doit comporter au moins 8 caractères.</div>
          )}
          {erreur && <p className="text-danger mt-2 mb-0">{erreur}</p>}
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={enCours}>Annuler</button>
          <button
            data-testid="confirmer-decision"
            className={`btn ${mode === 'approuver' ? 'btn-success' : 'btn-outline-danger'}`}
            disabled={!motifOk || enCours || (aCompleter && mode === 'approuver' && !roleLegacy)}
            onClick={valider}
          >
            {enCours ? 'Traitement…' : mode === 'approuver' ? 'Approuver et appliquer' : 'Rejeter'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function FileProvisionnement() {
  const { showToast } = useToast()
  const [donnees, setDonnees] = useState(null)
  const [roles, setRoles] = useState([])
  const [statut, setStatut] = useState('EN_ATTENTE')
  const [bilanScan, setBilanScan] = useState(null)
  const [enCours, setEnCours] = useState(false)
  const [decision, setDecision] = useState(null)

  const charger = useCallback(() => {
    listerPropositions({ statut, page_size: 100 }).then(setDonnees)
  }, [statut])
  useEffect(() => {
    charger()
    listerRolesCurp().then(setRoles)
  }, [charger])

  const lancerScan = async () => {
    setEnCours(true)
    try {
      const resultat = await scannerProvisions()
      setBilanScan(resultat)
      if (!resultat.maitre_actif) {
        showToast("Le drapeau maître de provisionnement est fermé : aucun scan (no-op).", 'info')
      } else {
        showToast(`Scan terminé : ${resultat.total} nouvelle(s) proposition(s).`, 'success')
      }
      charger()
    } catch (e) {
      showToast(messageErreur(e), 'error')
    } finally {
      setEnCours(false)
    }
  }

  if (!donnees) return <EnChargement />
  return (
    <section data-testid="ecran-file-provisionnement">
      <div className="hab-carte">
        <div className="d-flex justify-content-between align-items-center flex-wrap gap-2">
          <h2 className="h5 mb-0">File de provisionnement — validation humaine</h2>
          <button className="btn btn-sm btn-outline-primary" data-testid="bouton-scan"
                  disabled={enCours} onClick={lancerScan}>
            <i className="bi bi-radar me-1" />{enCours ? 'Analyse…' : 'Lancer un scan'}
          </button>
        </div>
        <p className="hab-muted mt-2 mb-2">
          Aucun compte n'est créé, suspendu ou modifié automatiquement : chaque proposition
          attend une décision motivée d'un administrateur.
        </p>
        {bilanScan && (
          <p className="small mb-0" data-testid="bilan-scan">
            Dernier scan : {bilanScan.total} nouvelle(s) proposition(s) —{' '}
            {Object.entries(bilanScan.bilan).map(([k, v]) => `${k} : ${v}`).join(' · ') || 'aucun déclencheur actif'}
          </p>
        )}
        <div className="d-flex gap-2 flex-wrap mt-2" role="tablist">
          {STATUTS.map(([code, libelle]) => (
            <button key={code} role="tab" aria-selected={statut === code}
                    data-testid={`onglet-${code}`}
                    className={`btn btn-sm ${statut === code ? 'btn-primary' : 'btn-outline-secondary'}`}
                    onClick={() => setStatut(code)}>
              {libelle} ({donnees.compteurs?.[code] ?? 0})
            </button>
          ))}
        </div>
      </div>

      <div className="hab-carte">
        <table className="hab-table">
          <thead>
            <tr><th>Origine</th><th>Action proposée</th><th>Référence</th><th>Motif</th><th>État</th><th></th></tr>
          </thead>
          <tbody>
            {donnees.results.map((p) => (
              <tr key={p.id} data-testid={`proposition-${p.id}`}>
                <td>{p.declencheur_libelle}<br /><span className="hab-muted small">{p.source_libelle}</span></td>
                <td>{p.action_libelle}</td>
                <td className="small">{p.source}</td>
                <td className="small">{p.motif}</td>
                <td>{p.statut_libelle || p.statut}</td>
                <td>
                  {p.statut === 'EN_ATTENTE' && (
                    <div className="d-flex gap-1">
                      <button className="btn btn-sm btn-success" data-testid={`approuver-${p.id}`}
                              onClick={() => setDecision({ p, mode: 'approuver' })}>
                        Approuver
                      </button>
                      <button className="btn btn-sm btn-outline-danger" data-testid={`rejeter-${p.id}`}
                              onClick={() => setDecision({ p, mode: 'rejeter' })}>
                        Rejeter
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {donnees.results.length === 0 && (
              <tr><td colSpan="6" className="hab-muted text-center py-3">Aucune proposition dans cet état.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {decision && (
        <DecisionModal
          proposition={decision.p}
          roles={roles}
          mode={decision.mode}
          onClose={() => setDecision(null)}
          onResult={charger}
        />
      )}
    </section>
  )
}
