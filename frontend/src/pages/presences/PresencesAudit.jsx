import React, { useCallback, useEffect, useState } from 'react'
import api from '../../services/api'
import { messageErreur } from './commun'
import '../../styles/presences.css'

/**
 * Journal d'audit des présences — lecture du `presences.AuditLog` via
 * `GET /api/audit-logs/` (filtres serveur : action, cible,
 * période). Aucune écriture depuis cet écran.
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
  if (extra.motif) morceaux.push(`motif ${extra.motif}`)
  if (extra.type_sortie) morceaux.push(extra.type_sortie)
  if (extra.source_position) morceaux.push(extra.source_position)
  if (extra.evaluation) morceaux.push(extra.evaluation)
  if (extra.canal) morceaux.push(extra.canal)
  return morceaux.length ? morceaux.join(' · ') : null
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
          <span className="pqr-hero-badge"><i className="bi bi-clock-history me-1"></i>AUDIT</span>
          <h1 className="pqr-hero-title">Journal d’audit</h1>
          <p className="pqr-hero-intro">
            Tous les événements de badgeage et les interventions humaines, tracés côté serveur :
            acteur, cible, horodatage, appareil et contexte (motif, mode, position).
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
        <div className="table-container">
          <table className="table edt-table mb-0">
            <thead>
              <tr><th>Horodatage</th><th>Action</th><th>Acteur</th><th>Cible</th><th>Contexte</th><th>Appareil</th></tr>
            </thead>
            <tbody>
              {lignes.map((l) => (
                <tr key={l.id}>
                  <td><code>{new Date(l.timestamp).toLocaleString('fr-FR')}</code></td>
                  <td>
                    <span className={`badge ${(l.action || '').includes('MANUEL') || (l.action || '').startsWith('FORCE')
                      ? 'text-bg-warning' : 'text-bg-primary'}`}>
                      {l.action_label || l.action}
                    </span>
                  </td>
                  <td>{l.acteur_label}{l.acteur_role ? <small className="text-muted"> ({l.acteur_role})</small> : null}</td>
                  <td>{l.cible_nom} <small className="text-muted">{l.cible_numero}</small></td>
                  <td><small>{resumeExtra(l.extra) || l.formation_titre || '—'}</small></td>
                  <td><small className="text-muted">{l.device_id || '—'}</small></td>
                </tr>
              ))}
              {!charge && lignes.length === 0 && (
                <tr><td colSpan={6} className="text-center text-muted py-4">
                  Aucun événement ne correspond aux filtres (le journal est conservé côté serveur, jamais purgé par cet écran).
                </td></tr>
              )}
              {charge && (
                <tr><td colSpan={6} className="text-center py-4"><div className="loading"><div className="spinner"></div></div></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
