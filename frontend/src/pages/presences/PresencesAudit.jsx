import React, { useCallback, useEffect, useState } from 'react'
import api from '../../services/api'
import { messageErreur } from './commun'
import '../../styles/presences.css'

/**
 * Journal d'audit des présences — traçabilité non destructive.
 *
 * Lecture du `presences.AuditLog` via `GET /api/audit-logs/` (filtres
 * serveur : action, cible, période). Toute présence manuelle, toute
 * correction, toute clôture de séance et toute modification de
 * configuration géographique y sont inscrites avec leur auteur, leur
 * date et leur motif. Une correction conserve l'ancienne valeur à côté
 * de la nouvelle (`extra.avant` / `extra.apres`, ou
 * `extra.ancienne_valeur` / `extra.nouvelle_valeur`) : rien n'est écrasé
 * silencieusement. Aucune écriture depuis cet écran.
 */

const ACTIONS = [
  ['', 'Toutes les actions'],
  ['SCAN_SECURE_ENTREE', 'Entrées (scan sécurisé)'],
  ['SCAN_SECURE_SORTIE', 'Sorties (scan sécurisé)'],
  ['SCAN_HEARTBEAT', 'Heartbeats'],
  ['OUT_OF_GEOFENCE', 'Sorties de périmètre'],
  ['AUTO_EXIT', 'Sorties automatiques'],
  ['FORCE_ENTREE', 'Entrées forcées / émargements'],
  ['FORCE_SORTIE', 'Sorties forcées'],
  ['CLOSE_SESSION', 'Clôtures de séance'],
  ['AUTO_ABSENT', 'Absents automatiques'],
  ['FORMATION_QR_GENERATE', 'Générations de QR'],
  ['POINTAGE_MODIFIE', 'Modifications après clôture'],
]

function resumeExtra(extra) {
  if (!extra || typeof extra !== 'object') return null
  const morceaux = []
  if (extra.mode) morceaux.push(`mode ${extra.mode}`)
  if (extra.type_sortie) morceaux.push(extra.type_sortie)
  if (extra.source_position) morceaux.push(extra.source_position)
  if (extra.evaluation) morceaux.push(extra.evaluation)
  if (extra.canal) morceaux.push(extra.canal)
  return morceaux.length ? morceaux.join(' · ') : null
}

/** Ancienne valeur tracée par le serveur (correction), sinon null. */
function ancienneValeur(extra) {
  if (!extra || typeof extra !== 'object') return null
  if (extra.avant !== undefined) return extra.avant
  if (extra.ancienne_valeur !== undefined) return extra.ancienne_valeur
  return null
}

/** Nouvelle valeur tracée par le serveur (correction), sinon null. */
function nouvelleValeur(extra) {
  if (!extra || typeof extra !== 'object') return null
  if (extra.apres !== undefined) return extra.apres
  if (extra.nouvelle_valeur !== undefined) return extra.nouvelle_valeur
  return null
}

/** Ton de la puce d'action : alerte pour les interventions humaines. */
function tonAction(ligne) {
  const action = ligne.action || ''
  if (action.includes('MODIFIE') || action.includes('CORRECTION') || action.startsWith('FORCE')) {
    return 'alerte'
  }
  if (ligne.extra && ligne.extra.mode === 'MANUEL') return 'alerte'
  return 'conforme'
}

function Valeur({ titre, contenu }) {
  if (contenu === null || contenu === undefined) return null
  return (
    <div>
      <div className="pqr-audit-valeur-titre">{titre}</div>
      <pre className="pqr-audit-valeur">{JSON.stringify(contenu, null, 2)}</pre>
    </div>
  )
}

export default function PresencesAudit() {
  const [action, setAction] = useState('')
  const [cible, setCible] = useState('')
  const [dateDebut, setDateDebut] = useState('')
  const [dateFin, setDateFin] = useState('')
  const [lignes, setLignes] = useState([])
  const [total, setTotal] = useState(0)
  const [charge, setCharge] = useState(false)
  const [erreur, setErreur] = useState('')

  const charger = useCallback(async () => {
    setCharge(true)
    setErreur('')
    try {
      const params = new URLSearchParams()
      if (action) params.set('action', action)
      if (cible.trim()) params.set('cible_numero', cible.trim())
      if (dateDebut) params.set('date_debut', dateDebut)
      if (dateFin) params.set('date_fin', dateFin)
      const res = await api.get(`/audit-logs/?${params.toString()}`)
      setLignes(res.data.results || [])
      setTotal(res.data.count || 0)
    } catch (err) {
      setErreur(messageErreur(err, 'Journal d’audit indisponible.'))
      setLignes([])
      setTotal(0)
    } finally {
      setCharge(false)
    }
  }, [action, cible, dateDebut, dateFin])

  useEffect(() => { charger() }, [charger])

  return (
    <div>
      <div className="pqr-hero">
        <div>
          <span className="pqr-hero-badge"><i className="bi bi-clock-history me-1"></i>TRAÇABILITÉ NON DESTRUCTIVE</span>
          <h1 className="pqr-hero-title">Journal d’audit</h1>
          <p className="pqr-hero-intro">
            Toute présence manuelle, toute correction, toute clôture de séance et toute
            modification de configuration géographique y sont inscrites avec leur auteur,
            leur date et leur motif. Une correction conserve l’ancienne valeur à côté de
            la nouvelle : rien n’est écrasé silencieusement.
          </p>
        </div>
        <div className="pqr-hero-actions">
          <span className="badge text-bg-light">{total} événement(s)</span>
        </div>
      </div>

      {erreur && <div className="error-message">{erreur}</div>}

      <div className="pqr-panel">
        <div className="pqr-panel-corps">
          <div className="pqr-filtres">
            <div>
              <label className="label" htmlFor="pqr-audit-action">Action</label>
              <select id="pqr-audit-action" className="input" value={action}
                      onChange={(e) => setAction(e.target.value)}>
                {ACTIONS.map(([valeur, libelle]) => (
                  <option key={valeur} value={valeur}>{libelle}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="pqr-audit-cible">Cible (matricule / numéro)</label>
              <input id="pqr-audit-cible" className="input" value={cible}
                     onChange={(e) => setCible(e.target.value)} placeholder="ex. MAT011" />
            </div>
            <div>
              <label className="label" htmlFor="pqr-audit-debut">Du</label>
              <input id="pqr-audit-debut" type="date" className="input" value={dateDebut}
                     onChange={(e) => setDateDebut(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="pqr-audit-fin">Au</label>
              <input id="pqr-audit-fin" type="date" className="input" value={dateFin}
                     onChange={(e) => setDateFin(e.target.value)} />
            </div>
            <button className="btn btn-dfrc" onClick={charger} disabled={charge}>
              <i className="bi bi-search me-1"></i>Filtrer
            </button>
          </div>
        </div>
      </div>

      <div className="pqr-panel">
        <div className="pqr-audit-liste">
          {lignes.map((l, i) => {
            const extra = l.extra || {}
            const contexte = resumeExtra(extra)
            return (
              <article
                key={l.id}
                className={`pqr-audit-ligne pqr-audit-animee${(i + 1) % 5 === 0 ? ' pqr-audit-ligne-epaisse' : ''}`}
                style={{ animationDelay: `${Math.min(i, 20) * 18}ms` }}
              >
                <div>
                  <div className="pqr-audit-horodatage">
                    {new Date(l.timestamp).toLocaleString('fr-FR')}
                  </div>
                  <div className="pqr-audit-auteur">{l.acteur_label}</div>
                  {l.acteur_role && <div className="pqr-audit-role">{l.acteur_role}</div>}
                  <div className="pqr-audit-entite">
                    {(l.cible_type || 'cible')}{l.cible_numero ? ` #${l.cible_numero}` : ''}
                  </div>
                  {l.cible_nom && <div className="pqr-audit-cible-nom">{l.cible_nom}</div>}
                </div>

                <div>
                  <div className="pqr-audit-entete">
                    <span className={`pqr-puce pqr-puce-${tonAction(l)}`}>
                      {l.action_label || l.action}
                    </span>
                    {extra.motif
                      ? <span className="pqr-audit-motif">motif : {extra.motif}</span>
                      : null}
                  </div>
                  {(contexte || l.formation_titre || extra.commentaire || l.device_id) && (
                    <div className="pqr-audit-contexte">
                      {[contexte, l.formation_titre || null,
                        extra.commentaire ? `« ${extra.commentaire} »` : null,
                        l.device_id ? `appareil ${l.device_id}` : null,
                        l.pointage_id ? `pointage #${l.pointage_id}` : null]
                        .filter(Boolean).join(' · ')}
                    </div>
                  )}

                  <div className="pqr-audit-valeurs">
                    <Valeur titre="Ancienne valeur" contenu={ancienneValeur(extra)} />
                    <Valeur titre="Nouvelle valeur" contenu={nouvelleValeur(extra)} />
                  </div>
                </div>
              </article>
            )
          })}
          {charge && (
            <div className="text-center py-4"><div className="loading"><div className="spinner"></div></div></div>
          )}
          {!charge && lignes.length === 0 && (
            <p className="pqr-audit-vide">
              Aucun événement d’audit.
              <small>Le journal est conservé côté serveur, jamais purgé par cet écran.</small>
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
