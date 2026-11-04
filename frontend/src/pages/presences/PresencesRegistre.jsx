import React, { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { badgeCanal as badgeCanalBase, formatHeure, messageErreur } from './commun'
import { ModalBadgeageManuel } from '../EdtPresences'
import '../../styles/presences.css'

/**
 * Module « Présences » du hub — Registre des présences (historique).
 *
 * Refonte alignée sur le registre de référence : historique transversal
 * des pointages LMD (étudiants, enseignants, encadrants), filtres
 * **côté serveur** synchronisés dans l'URL (période, nom, groupe, type,
 * mode, séance), et section « Émargement manuel et corrections »
 * (séance → participant → motif obligatoire, acteur = compte connecté
 * tracé par le serveur). Source : `GET /presences/seances-edt/historique/`.
 * Les coordonnées GPS brutes ne sont jamais affichées : seuls le
 * verdict, la précision annoncée et les anomalies sont restitués.
 */

const TYPES = [
  { valeur: '', libelle: 'Tous les types' },
  { valeur: 'ETUDIANT', libelle: 'Étudiants' },
  { valeur: 'ENSEIGNANT', libelle: 'Enseignants' },
  { valeur: 'ENCADRANT', libelle: 'Encadrants' },
]
const MODES = [
  { valeur: '', libelle: 'Tous les modes' },
  { valeur: 'QR_AUTOMATIQUE', libelle: 'QR automatique' },
  { valeur: 'MANUEL', libelle: 'Manuel' },
]

const TON_TYPE = { ETUDIANT: 'text-bg-primary', ENSEIGNANT: 'text-bg-dark', ENCADRANT: 'text-bg-warning' }
const TON_VERDICT = {
  DANS_PERIMETRE: 'text-bg-success', HORS_PERIMETRE: 'text-bg-danger', SIGNAL_PERDU: 'text-bg-warning',
}
const LIBELLE_VERDICT = {
  DANS_PERIMETRE: 'Dans le périmètre', HORS_PERIMETRE: 'Hors périmètre', SIGNAL_PERDU: 'Signal perdu',
}

function badgeStatutLigne(l) {
  const statut = l.statut_assiduite || l.statut
  const tons = {
    PRESENT: 'text-bg-success', RETARD: 'text-bg-warning', ABSENT: 'text-bg-danger',
    ABSENCE_JUSTIFIEE: 'text-bg-info', EXCUSE: 'text-bg-info',
  }
  return <span className={`badge ${tons[statut] || 'text-bg-secondary'}`}>{statut || '—'}</span>
}

export default function PresencesRegistre() {
  const { showToast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const aujourdhui = new Date().toLocaleDateString('en-CA')
  const [dateDebut, setDateDebut] = useState(() => searchParams.get('date') || aujourdhui)
  const [dateFin, setDateFin] = useState(() => searchParams.get('date') || aujourdhui)
  const [nom, setNom] = useState(() => searchParams.get('nom') || '')
  const [groupe, setGroupe] = useState(() => searchParams.get('groupe') || '')
  const [type, setType] = useState(() => searchParams.get('type') || '')
  const [mode, setMode] = useState(() => searchParams.get('mode') || '')
  const [seanceFiltre, setSeanceFiltre] = useState(() => searchParams.get('seance') || '')
  const [donnees, setDonnees] = useState(null)
  const [charge, setCharge] = useState(true)
  const [erreur, setErreur] = useState('')

  // Section exceptions : émargement manuel par séance.
  const [seancesJour, setSeancesJour] = useState([])
  const [seanceExc, setSeanceExc] = useState(null)
  const [lignesExc, setLignesExc] = useState([])
  const [badgeageManuel, setBadgeageManuel] = useState(null)

  const charger = useCallback(async () => {
    setCharge(true)
    setErreur('')
    try {
      const params = new URLSearchParams({ date_debut: dateDebut, date_fin: dateFin })
      if (nom.trim()) params.set('nom', nom.trim())
      if (groupe.trim()) params.set('groupe', groupe.trim())
      if (type) params.set('type', type)
      if (mode) params.set('mode', mode)
      if (seanceFiltre) params.set('seance_id', seanceFiltre)
      const res = await api.get(`/presences/seances-edt/historique/?${params.toString()}`)
      setDonnees(res.data)
    } catch (err) {
      setErreur(messageErreur(err, 'Registre des présences indisponible.'))
    } finally {
      setCharge(false)
    }
  }, [dateDebut, dateFin, nom, groupe, type, mode, seanceFiltre])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    const sp = new URLSearchParams()
    sp.set('date', dateDebut)
    if (nom.trim()) sp.set('nom', nom.trim())
    if (groupe.trim()) sp.set('groupe', groupe.trim())
    if (type) sp.set('type', type)
    if (mode) sp.set('mode', mode)
    if (seanceFiltre) sp.set('seance', seanceFiltre)
    setSearchParams(sp, { replace: true })
  }, [dateDebut, dateFin, nom, groupe, type, mode, seanceFiltre, setSearchParams])

  const chargerSeancesExc = useCallback(async () => {
    try {
      const res = await api.get(`/presences/seances-edt/du-jour/?date=${dateFin}`)
      const liste = Array.isArray(res.data) ? res.data : (res.data.results || [])
      setSeancesJour(liste)
    } catch {
      setSeancesJour([])
    }
  }, [dateFin])

  useEffect(() => { chargerSeancesExc() }, [chargerSeancesExc])

  const chargerLignesExc = useCallback(async () => {
    if (!seanceExc) { setLignesExc([]); return }
    try {
      const res = await api.get(`/presences/seances-edt/${seanceExc.id}/presences/?date=${dateFin}`)
      setLignesExc(res.data.lignes || [])
    } catch (err) {
      showToast(messageErreur(err, 'Participants de la séance indisponibles.'), 'error')
      setLignesExc([])
    }
  }, [seanceExc, dateFin, showToast])

  useEffect(() => { chargerLignesExc() }, [chargerLignesExc])

  const lignes = donnees?.resultats || []
  const nbManuels = lignes.filter((l) => l.mode === 'MANUEL').length

  return (
    <div>
      <div className="pqr-hero">
        <div>
          <span className="pqr-hero-badge"><i className="bi bi-journal-check me-1"></i>HISTORIQUE · ÉTUDIANTS, ENSEIGNANTS, ENCADRANTS</span>
          <h1 className="pqr-hero-title">Registre des présences</h1>
          <p className="pqr-hero-intro">
            Tous les pointages rattachés aux séances LMD publiées : entrée, sortie, durée,
            canal de badgeage, verdict de périmètre et assiduité — tels que calculés
            et conservés par le serveur.
          </p>
          <div className="d-flex flex-wrap gap-2 mt-3">
            <span className="badge text-bg-light">{donnees?.total ?? 0} présence(s)</span>
            <span className="badge text-bg-light">{nbManuels} manuelle(s) sur la sélection</span>
            {seanceFiltre && (
              <button className="badge text-bg-warning border-0" onClick={() => setSeanceFiltre('')}>
                Séance filtrée : #{seanceFiltre} × retirer
              </button>
            )}
          </div>
        </div>
      </div>

      {erreur && <div className="error-message">{erreur}</div>}

      <div className="pqr-panel mt-3">
        <div className="pqr-panel-corps">
          <div className="pqr-filtres">
            <div>
              <label className="label" htmlFor="pqr-hist-debut">Du</label>
              <input id="pqr-hist-debut" type="date" className="input" value={dateDebut}
                     onChange={(e) => setDateDebut(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="pqr-hist-fin">Au</label>
              <input id="pqr-hist-fin" type="date" className="input" value={dateFin}
                     onChange={(e) => setDateFin(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="pqr-hist-nom">Nom du participant</label>
              <input id="pqr-hist-nom" className="input" value={nom}
                     onChange={(e) => setNom(e.target.value)} placeholder="Nom ou matricule" />
            </div>
            <div>
              <label className="label" htmlFor="pqr-hist-groupe">Groupe</label>
              <input id="pqr-hist-groupe" className="input" value={groupe}
                     onChange={(e) => setGroupe(e.target.value)} placeholder="ex. L1-G1" />
            </div>
            <div>
              <label className="label" htmlFor="pqr-hist-type">Type</label>
              <select id="pqr-hist-type" className="input" value={type}
                      onChange={(e) => setType(e.target.value)}>
                {TYPES.map((t) => <option key={t.valeur} value={t.valeur}>{t.libelle}</option>)}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="pqr-hist-mode">Mode</label>
              <select id="pqr-hist-mode" className="input" value={mode}
                      onChange={(e) => setMode(e.target.value)}>
                {MODES.map((m) => <option key={m.valeur} value={m.valeur}>{m.libelle}</option>)}
              </select>
            </div>
            <button className="btn btn-dfrc" onClick={charger} disabled={charge}>
              <i className="bi bi-funnel me-1"></i>Filtrer
            </button>
          </div>
        </div>
      </div>

      <div className="pqr-panel">
        <div className="table-container">
          <table className="table edt-table mb-0">
            <thead>
              <tr>
                <th>Participant</th><th>Type</th><th>Séance</th><th>Date</th><th>Entrée</th>
                <th>Sortie</th><th className="text-end">Durée</th><th>Mode</th>
                <th>Position</th><th>Assiduité</th><th>Anomalies</th>
              </tr>
            </thead>
            <tbody>
              {lignes.map((l) => (
                <tr key={l.id}>
                  <td>
                    <strong>{l.nom}</strong>
                    <div className="caps text-muted" style={{ fontSize: '.72rem' }}>{l.matricule}</div>
                  </td>
                  <td><span className={`badge ${TON_TYPE[l.type_participant] || 'text-bg-secondary'}`}>
                    {l.type_participant}
                  </span></td>
                  <td>
                    <Link className="fw-semibold text-decoration-none"
                          to={`/edt/presences?seance=${l.seance_id}&date=${l.date_seance}`}>
                      {l.seance}
                    </Link>
                    <div className="caps text-muted" style={{ fontSize: '.72rem' }}>{l.groupe || ''}</div>
                  </td>
                  <td><code>{l.date_seance}</code></td>
                  <td><code>{formatHeure(l.timestamp_entree)}</code></td>
                  <td>
                    <code>{formatHeure(l.timestamp_sortie)}</code>
                    <div className="caps text-muted" style={{ fontSize: '.72rem' }}>
                      {l.heartbeats} heartbeat{l.heartbeats > 1 ? 's' : ''}
                    </div>
                  </td>
                  <td className="text-end">{l.duree_minutes !== null && l.duree_minutes !== undefined ? `${l.duree_minutes} min` : '—'}</td>
                  <td>
                    {l.mode === 'MANUEL'
                      ? <span className="badge text-bg-warning"><i className="bi bi-pencil-square me-1"></i>Manuel</span>
                      : <span className="badge text-bg-success"><i className="bi bi-qr-code me-1"></i>QR</span>}
                    {l.motif_manuel && (
                      <div className="text-muted" style={{ fontSize: '.72rem', maxWidth: '20ch' }}>
                        {l.motif_manuel}{l.auteur_manuel ? ` · ${l.auteur_manuel}` : ''}
                      </div>
                    )}
                  </td>
                  <td>
                    {l.verdict_geofence
                      ? <span className={`badge ${TON_VERDICT[l.verdict_geofence] || 'text-bg-secondary'}`}>
                          {LIBELLE_VERDICT[l.verdict_geofence] || l.verdict_geofence}
                        </span>
                      : <span className="text-muted">—</span>}
                    <div className="text-muted" style={{ fontSize: '.72rem' }}>
                      {l.accuracy_m !== null && l.accuracy_m !== undefined ? `±${Math.round(l.accuracy_m)} m` : '—'}
                    </div>
                  </td>
                  <td>{badgeStatutLigne(l)}</td>
                  <td>
                    {(l.anomalies || []).length > 0
                      ? l.anomalies.map((a) => (
                          <span key={a} className="badge text-bg-danger me-1">{a}</span>
                        ))
                      : <span className="text-muted">—</span>}
                  </td>
                </tr>
              ))}
              {!charge && lignes.length === 0 && (
                <tr><td colSpan={11} className="text-center text-muted py-5">
                  Aucune présence ne correspond à ces critères.
                </td></tr>
              )}
              {charge && (
                <tr><td colSpan={11} className="text-center py-5">
                  <div className="loading"><div className="spinner"></div></div>
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="pqr-panel-corps pt-0">
          <p className="pqr-legende">
            Les coordonnées GPS brutes ne sont jamais affichées publiquement : seuls le verdict
            de conformité, la précision annoncée et les anomalies sont restitués. La collecte
            est limitée au badge d’entrée, aux heartbeats pendant la séance et à la sortie.
          </p>
        </div>
      </div>

      {/* ── Exceptions : émargement manuel et corrections ─────────── */}
      <div className="pqr-panel">
        <div className="pqr-panel-tete">
          <div>
            <div className="pqr-surtitre">Exceptions</div>
            <h2 className="pqr-panel-titre">Émargement manuel et corrections</h2>
          </div>
          <span className="caps text-muted" style={{ fontSize: '.75rem' }}>RBAC · MOTIF · AUDIT</span>
        </div>
        <div className="pqr-panel-corps">
          <div className="pqr-filtres">
            <div style={{ flex: 1, minWidth: 240 }}>
              <label className="label" htmlFor="pqr-exc-seance">Séance du {dateFin}</label>
              <select id="pqr-exc-seance" className="input"
                      value={seanceExc ? String(seanceExc.id) : ''}
                      onChange={(e) => setSeanceExc(
                        seancesJour.find((s) => String(s.id) === e.target.value) || null)}>
                <option value="">— Choisir une séance —</option>
                {seancesJour.map((s) => (
                  <option key={s.id} value={s.id}>
                    {formatHeure(s.debut)} · {s.intitule} · {s.groupe_libelle || 'sans groupe'}
                  </option>
                ))}
              </select>
            </div>
            {seanceExc && (
              <Link className="btn btn-outline-secondary"
                    to={`/edt/presences?seance=${seanceExc.id}&date=${dateFin}`}>
                <i className="bi bi-box-arrow-up-right me-1"></i>Émargement complet de la séance
              </Link>
            )}
          </div>
          <p className="text-muted mt-2 mb-0" style={{ fontSize: '.88rem' }}>
            L’acteur du badgeage manuel est le compte connecté, tracé par le serveur
            (motif obligatoire, commentaire exigé pour « Autre »).
          </p>
        </div>
        {seanceExc && (
          <div className="table-container">
            <table className="table edt-table mb-0">
              <thead><tr><th>Participant</th><th>Entrée</th><th>Statut</th><th>Canal</th><th /></tr></thead>
              <tbody>
                {lignesExc.map((l) => (
                  <tr key={l.participant}>
                    <td><strong>{l.nom}</strong> <small className="text-muted">{l.matricule}</small></td>
                    <td>{l.badge_entree ? formatHeure(l.badge_entree) : '—'}</td>
                    <td>{l.statut || <span className="text-muted">— non pointé —</span>}</td>
                    <td>{badgeCanalBase(l)}</td>
                    <td className="text-end">
                      <button className="btn btn-dfrc btn-sm" onClick={() => setBadgeageManuel(l)}>
                        <i className="bi bi-pencil-square me-1"></i>Badger manuellement
                      </button>
                    </td>
                  </tr>
                ))}
                {lignesExc.length === 0 && (
                  <tr><td colSpan={5} className="text-center text-muted py-4">
                    Aucun participant (séance sans groupe rattaché ou registre vide).
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {badgeageManuel && seanceExc && (
        <ModalBadgeageManuel
          seance={seanceExc} date={dateFin} ligne={badgeageManuel}
          onClose={() => setBadgeageManuel(null)}
          onSaved={(message) => { showToast(message); chargerLignesExc(); charger() }}
        />
      )}
    </div>
  )
}
