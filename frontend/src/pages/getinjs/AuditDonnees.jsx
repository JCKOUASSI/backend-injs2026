import { useCallback, useEffect, useState } from 'react'
import api from '../../services/api'
import { formatApiErrors } from '../../utils/apiErrors'
import '../../styles/ecransGeneriques.css'

/**
 * GET INJS APP — « Audit des données ».
 *
 * Répond à la question « puis-je générer ? » **avant** de lancer une campagne.
 * La réponse vient de `/api/edts/lmd/audit/` : chaque contrôle est classé
 * `OK`, `WARNING` ou `BLOCKING`, avec son code, son explication et l'action
 * recommandée. Aucun contrôle n'est reformulé ni adouci côté écran : une
 * donnée absente reste un avertissement ou un blocage, jamais un succès.
 *
 * Le tableau des contraintes (`/api/edts/lmd/constraints/`) rappelle les
 * règles dures (C1 → C10) et sépare explicitement les préférences.
 */

/** Libellés des origines de la politique de contraintes souples. */
const ORIGINES = {
  defaut: 'valeurs par défaut du code',
  reglage_django: 'réglage de déploiement',
  base: 'réglage enregistré dans l’administration',
  parametre: 'paramètre de cette génération',
}

/** « 4 » → « 4 h », « 4,5 » → « 4 h 30 ». */
function heures(valeur) {
  if (valeur === null || valeur === undefined) return '—'
  const total = Math.round(Number(valeur) * 60)
  const h = Math.floor(total / 60)
  const m = total % 60
  return m ? `${h} h ${String(m).padStart(2, '0')}` : `${h} h`
}

function dateLisible(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
}

/**
 * Bloc « contraintes souples ».
 *
 * Affiche la politique **effective** et surtout son origine : un utilisateur
 * doit pouvoir savoir si le moteur suit les défauts du code, un réglage de
 * déploiement ou la décision enregistrée dans l'administration. Aucune règle
 * n'est présentée comme active si la politique ne l'est pas.
 */
function PolitiqueSouples({ souples }) {
  const politique = souples.politique || {}
  const reglage = souples.reglage
  const active = Boolean(politique.actives)
  return (
    <div className="card mt-3" data-testid="politique-souples">
      <div className="card-body">
        <h5 className="card-title">
          Contraintes souples{' '}
          <span className={`badge ${active ? 'badge-warning' : 'badge-neutral'}`}>
            {active ? 'actives' : 'désactivées'}
          </span>
        </h5>
        <p className="small text-muted mb-2">
          Origine : {ORIGINES[souples.origine] || souples.origine || 'inconnue'}.
          {' '}Ces règles ne bloquent jamais un placement : elles produisent des
          pénalités visibles.
        </p>
        <ul className="list-unstyled small mb-2">
          <li>Série consécutive maximale : {heures(politique.max_heures_consecutives)}</li>
          <li>Total maximum par jour : {heures(politique.max_heures_par_jour)}</li>
          <li>Interruption tolérée : {politique.tolerance_minutes ?? '—'} min</li>
          <li>
            Pause institutionnelle :{' '}
            {politique.pause_dejeuner
              ? `${politique.pause_dejeuner[0]} – ${politique.pause_dejeuner[1]}`
              : 'aucune déclarée (une coupure méridienne compte alors comme un trou)'}
          </li>
          <li>
            Poids : trou {politique.poids_trou ?? '—'} · série {politique.poids_consecutif ?? '—'} · surcharge {politique.poids_surcharge ?? '—'}
          </li>
        </ul>
        {reglage?.motif && (
          <p className="small mb-1">
            <strong>Motif enregistré :</strong> {reglage.motif}
          </p>
        )}
        {reglage && (
          <p className="small text-muted mb-2">
            Dernière modification par {reglage.modifie_par || 'un compte supprimé'}
            {dateLisible(reglage.modifie_le) ? ` le ${dateLisible(reglage.modifie_le)}` : ''}.
          </p>
        )}
        <p className="small text-muted mb-0">{souples.activation}</p>
      </div>
    </div>
  )
}

const NIVEAUX = {
  OK: { libelle: 'OK', classe: 'badge-success', icone: 'bi-check-circle' },
  WARNING: { libelle: 'Avertissement', classe: 'badge-warning', icone: 'bi-exclamation-triangle' },
  BLOCKING: { libelle: 'Bloquant', classe: 'badge-danger', icone: 'bi-x-octagon' },
}

function Pastille({ niveau }) {
  const info = NIVEAUX[niveau] || { libelle: niveau || '—', classe: 'badge-neutral', icone: 'bi-question' }
  return (
    <span className={`badge ${info.classe}`}>
      <i className={`bi ${info.icone} me-1`}></i>
      {info.libelle}
    </span>
  )
}

export default function AuditDonnees() {
  const [rapport, setRapport] = useState(null)
  const [contraintes, setContraintes] = useState(null)
  const [annees, setAnnees] = useState([])
  const [anneeId, setAnneeId] = useState('')
  const [chargement, setChargement] = useState(true)
  const [erreur, setErreur] = useState('')

  /**
   * Charge l'audit et le tableau des contraintes pour une année donnée.
   *
   * La fonction prend l'année en paramètre explicite : le premier chargement
   * part de l'année courante résolue juste avant, ce qui évite une double
   * requête (une sans année, puis une avec) et donc un affichage qui bascule
   * deux fois.
   */
  const charger = useCallback(async (annee) => {
    setChargement(true)
    setErreur('')
    try {
      const params = annee ? { annee_academique_id: annee } : {}
      const [audit, ref] = await Promise.all([
        api.get('/edts/lmd/audit/', { params }),
        api.get('/edts/lmd/constraints/'),
      ])
      setRapport(audit.data)
      setContraintes(ref.data)
    } catch (e) {
      setErreur(formatApiErrors(e?.response?.data, {
        fallback: 'Impossible de charger l’audit des données.',
      }))
      setRapport(null)
    } finally {
      setChargement(false)
    }
  }, [])

  // Années d'abord, audit ensuite : un seul aller-retour, état stable.
  useEffect(() => {
    let annule = false
    api.get('/scolarite/ref/annees/')
      .then(({ data }) => {
        if (annule) return
        const liste = data?.results || data || []
        setAnnees(liste)
        const courante = liste.find((a) => a.courante)
        const id = courante ? String(courante.id) : ''
        setAnneeId(id)
        return charger(id)
      })
      .catch(() => { if (!annule) setChargement(false) })
    return () => { annule = true }
  }, [charger])

  const changerAnnee = (valeur) => {
    setAnneeId(valeur)
    charger(valeur)
  }

  const controles = rapport?.controles || []
  const resume = rapport?.resume || {}
  const generable = rapport?.generable

  return (
    <div className="getinjs-page">
      <div className="getinjs-entete">
        <div>
          <h4 className="mb-1">Audit des données</h4>
          <p className="text-muted mb-0">
            « Puis-je générer ? » — contrôles réels sur les données de l’année,
            avant lancement d’une campagne.
          </p>
        </div>
        <div className="d-flex gap-2">
          <select
            className="form-select form-select-sm"
            aria-label="Année académique"
            value={anneeId}
            onChange={(e) => changerAnnee(e.target.value)}
          >
            <option value="">Année courante</option>
            {annees.map((a) => (
              <option key={a.id} value={a.id}>{a.libelle}</option>
            ))}
          </select>
          <button className="btn btn-outline-secondary btn-sm" onClick={() => charger(anneeId)} disabled={chargement}>
            <i className="bi bi-arrow-clockwise me-1"></i>Relancer l’audit
          </button>
        </div>
      </div>

      {erreur && <div className="alert alert-danger" role="alert">{erreur}</div>}

      {chargement ? (
        <p className="text-muted">Audit en cours…</p>
      ) : (
        <>
          <div className="d-flex flex-wrap gap-3 mb-3">
            <div className={`alert mb-0 ${generable ? 'alert-success' : 'alert-danger'}`}>
              {generable
                ? 'Génération possible : aucun contrôle bloquant.'
                : 'Génération impossible en l’état : au moins un contrôle bloquant.'}
            </div>
            <div className="d-flex gap-2 align-items-center">
              <span className="badge badge-success">{resume.ok ?? 0} OK</span>
              <span className="badge badge-warning">{resume.warning ?? 0} avertissement(s)</span>
              <span className="badge badge-danger">{resume.blocking ?? 0} bloquant(s)</span>
            </div>
          </div>

          <div className="table-responsive mb-4">
            <table className="table table-sm align-middle">
              <caption className="visually-hidden">Contrôles d’aptitude à la génération</caption>
              <thead>
                <tr>
                  <th scope="col">Niveau</th>
                  <th scope="col">Code</th>
                  <th scope="col">Constat</th>
                  <th scope="col">Action recommandée</th>
                </tr>
              </thead>
              <tbody>
                {controles.map((c, i) => (
                  <tr key={`${c.code}-${i}`}>
                    <td><Pastille niveau={c.niveau} /></td>
                    <td><code>{c.code}</code></td>
                    <td>{c.message}</td>
                    <td className="text-muted small">{c.action_recommandee || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {contraintes && (
            <div className="card">
              <div className="card-body">
                <h5 className="card-title">Contraintes appliquées par le moteur</h5>
                <ul className="list-unstyled small mb-2">
                  {(contraintes.dures || []).map((c) => (
                    <li key={c.code} className="mb-1">
                      <span className="badge badge-danger me-2">{c.code}</span>
                      {c.libelle}
                    </li>
                  ))}
                </ul>
                <p className="small text-muted mb-1">
                  Préférences (non bloquantes) : {(contraintes.avertissements || []).join(' · ')}
                </p>
                <p className="small text-muted mb-0">{contraintes.capacite_inconnue}</p>
              </div>
            </div>
          )}

          {contraintes?.souples && <PolitiqueSouples souples={contraintes.souples} />}
        </>
      )}
    </div>
  )
}
