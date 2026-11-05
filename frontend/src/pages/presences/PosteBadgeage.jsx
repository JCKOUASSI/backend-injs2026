import React, { useCallback, useEffect, useRef, useState } from 'react'
import QRCode from 'qrcode'
import api from '../../services/api'
import { formatHeure, messageErreur } from './commun'
import '../../styles/presences.css'

/**
 * Poste de badgeage web — terminal de badgeage du hub Présences QR.
 *
 * Le navigateur ne fait que collecter : jeton QR de la séance, position
 * (latitude, longitude, précision) et horodatage. Toute décision —
 * validité du jeton, appartenance à la séance, périmètre, doublon —
 * revient au serveur (`POST /presences/seances-edt/scan/`, heartbeat
 * `/api/scan/secure/heartbeat/`, sortie `/api/scan/secure/exit/`).
 * Aucune présence n'est affichée comme validée avant la réponse serveur.
 */

const ETATS = [
  ['PRET', 'Prêt à badger'],
  ['VERIFICATION', 'Vérification'],
  ['VALIDEE', 'Présence validée'],
  ['REFUSEE', 'Présence refusée'],
  ['HEARTBEAT', 'Heartbeat actif'],
  ['TERMINEE', 'Séance terminée'],
]

const CLE_DEVICE = 'injs.poste.device_id'

function deviceIdPoste() {
  try {
    let id = window.localStorage.getItem(CLE_DEVICE)
    if (!id) {
      id = `WEB-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
      window.localStorage.setItem(CLE_DEVICE, id)
    }
    return id
  } catch {
    return 'WEB-POSTE'
  }
}

export default function PosteBadgeage() {
  const [seances, setSeances] = useState([])
  const [seanceId, setSeanceId] = useState('')
  const [jeton, setJeton] = useState(null)
  const [position, setPosition] = useState(null)
  const [gpsErreur, setGpsErreur] = useState('')
  const [etat, setEtat] = useState('PRET')
  const [resultat, setResultat] = useState(null)
  const [erreur, setErreur] = useState('')
  const [heartbeatActif, setHeartbeatActif] = useState(false)
  const [evaluation, setEvaluation] = useState('')
  const canvasRef = useRef(null)
  const timerRef = useRef(null)
  const positionRef = useRef(null)
  positionRef.current = position

  const chargerSeances = useCallback(async () => {
    try {
      const res = await api.get('/presences/seances-edt/du-jour/')
      const liste = Array.isArray(res.data) ? res.data : (res.data.results || [])
      setSeances(liste)
      if (liste.length > 0) setSeanceId((id) => id || String(liste[0].id))
    } catch (err) {
      setErreur(messageErreur(err, 'Séances du jour indisponibles.'))
    }
  }, [])

  useEffect(() => { chargerSeances() }, [chargerSeances])

  const ouvrirQr = useCallback(async (regenerer = false) => {
    if (!seanceId) return
    setErreur('')
    try {
      const res = regenerer
        ? await api.post(`/presences/seances-edt/${seanceId}/qr/`)
        : await api.get(`/presences/seances-edt/${seanceId}/qr/`)
      setJeton(res.data?.token || null)
      if (!res.data?.token && !regenerer) {
        const res2 = await api.post(`/presences/seances-edt/${seanceId}/qr/`)
        setJeton(res2.data?.token || null)
      }
    } catch (err) {
      setErreur(messageErreur(err, 'Ouverture du QR de séance impossible (réservé à l’enseignant de la séance).'))
    }
  }, [seanceId])

  useEffect(() => { setJeton(null); setResultat(null); setEtat('PRET') }, [seanceId])
  useEffect(() => { if (seanceId) ouvrirQr(false) }, [seanceId, ouvrirQr])

  useEffect(() => {
    if (jeton && canvasRef.current) {
      QRCode.toCanvas(canvasRef.current, jeton, { width: 230, margin: 1 }, () => {})
    }
  }, [jeton])

  const activerGps = useCallback(() => {
    setGpsErreur('')
    if (!('geolocation' in navigator)) {
      setGpsErreur('Géolocalisation non disponible sur ce terminal : le badgeage géolocalisé est impossible ici (émargement manuel motivé GPS_INDISPONIBLE).')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setPosition({
        latitude: pos.coords.latitude,
        longitude: pos.coords.longitude,
        accuracy_m: pos.coords.accuracy,
      }),
      () => setGpsErreur('Position refusée ou indisponible : activez la localisation du terminal puis réessayez.'),
      { enableHighAccuracy: true, timeout: 15000 },
    )
  }, [])

  const arreterHeartbeat = useCallback(() => {
    if (timerRef.current) window.clearInterval(timerRef.current)
    timerRef.current = null
    setHeartbeatActif(false)
  }, [])

  useEffect(() => arreterHeartbeat, [arreterHeartbeat])

  const envoyerHeartbeat = useCallback(async () => {
    if (!jeton) return
    const pos = positionRef.current || {}
    try {
      const res = await api.post('/scan/secure/heartbeat/', {
        token_qr: jeton,
        device_id: deviceIdPoste(),
        latitude: pos.latitude,
        longitude: pos.longitude,
        accuracy_m: pos.accuracy_m,
      })
      setEvaluation(res.data?.evaluation || '')
      if (res.data?.action === 'SORTIE_AUTO') {
        arreterHeartbeat()
        setEtat('TERMINEE')
        setResultat({ action: 'SORTIE_AUTO', message: 'Sortie automatique (hors périmètre confirmé).' })
      }
    } catch (err) {
      setEvaluation('')
      if ((err.response?.data?.code || '') === 'NO_OPEN_SESSION') {
        arreterHeartbeat()
        setEtat('TERMINEE')
      }
    }
  }, [jeton, arreterHeartbeat])

  const demarrerHeartbeat = useCallback(() => {
    arreterHeartbeat()
    setHeartbeatActif(true)
    setEtat('HEARTBEAT')
    timerRef.current = window.setInterval(envoyerHeartbeat, 30000)
  }, [arreterHeartbeat, envoyerHeartbeat])

  const badger = async () => {
    if (!jeton) { setErreur('Ouvrez d’abord le QR de la séance.'); return }
    setEtat('VERIFICATION')
    setErreur('')
    setResultat(null)
    try {
      const res = await api.post('/presences/seances-edt/scan/', {
        token_qr: jeton,
        device_id: deviceIdPoste(),
        ...(position || {}),
      })
      setResultat(res.data)
      setEtat('VALIDEE')
      if (res.data?.action === 'ENTREE') demarrerHeartbeat()
      if (res.data?.action === 'SORTIE') arreterHeartbeat()
    } catch (err) {
      setEtat('REFUSEE')
      setErreur(messageErreur(err, 'Badgeage refusé par le serveur.'))
    }
  }

  const sortir = async () => {
    if (!jeton) return
    setEtat('VERIFICATION')
    setErreur('')
    try {
      const res = await api.post('/scan/secure/exit/', {
        token_qr: jeton,
        device_id: deviceIdPoste(),
        ...(position || {}),
      })
      setResultat(res.data)
      setEtat('VALIDEE')
      arreterHeartbeat()
    } catch (err) {
      setEtat('REFUSEE')
      setErreur(messageErreur(err, 'Sortie refusée par le serveur.'))
    }
  }

  const seance = seances.find((s) => String(s.id) === String(seanceId))

  return (
    <div>
      <div className="pqr-hero">
        <div>
          <span className="pqr-hero-badge"><i className="bi bi-phone me-1"></i>TERMINAL DE BADGEAGE</span>
          <h1 className="pqr-hero-title">Poste de badgeage</h1>
          <p className="pqr-hero-intro">
            Étudiants · Enseignants · Encadrants. Le terminal collecte le jeton et la position ;
            le serveur décide (jeton, séance, groupe, périmètre, doublon).
          </p>
        </div>
      </div>

      <div className="pqr-panel">
        <div className="pqr-panel-corps">
          <div className="pqr-etats" role="status" aria-label="État du badgeage">
            {ETATS.map(([code, libelle]) => (
              <span key={code}
                    className={`pqr-etat${etat === code ? (code === 'VALIDEE' ? ' succes' : code === 'REFUSEE' ? ' echec' : ' actif') : ''}`}>
                {libelle}
              </span>
            ))}
            {heartbeatActif && <span className="pqr-etat actif">Heartbeat : {evaluation || 'actif'}</span>}
          </div>
        </div>
      </div>

      {erreur && <div className="error-message">{erreur}</div>}
      {gpsErreur && <div className="error-message">{gpsErreur}</div>}

      <div className="row g-3">
        <div className="col-lg-5">
          <div className="pqr-panel h-100">
            <div className="pqr-panel-tete"><span><i className="bi bi-qr-code me-2"></i>QR de séance</span></div>
            <div className="pqr-panel-corps">
              <label className="label" htmlFor="pqr-poste-seance">Séance du jour</label>
              <select id="pqr-poste-seance" className="input mb-3" value={seanceId}
                      onChange={(e) => setSeanceId(e.target.value)}>
                {seances.length === 0 && <option value="">Aucune séance ce jour</option>}
                {seances.map((s) => (
                  <option key={s.id} value={s.id}>
                    {formatHeure(s.debut)} · {s.intitule} ({s.groupe_libelle || 'sans groupe'})
                  </option>
                ))}
              </select>
              <div className="text-center">
                {jeton
                  ? <canvas ref={canvasRef} className="mb-2" />
                  : <p className="text-muted">QR non ouvert pour cette séance.</p>}
              </div>
              <div className="d-flex gap-2 justify-content-center">
                <button className="btn btn-dfrc btn-sm" onClick={() => ouvrirQr(false)} disabled={!seanceId}>
                  <i className="bi bi-qr-code me-1"></i>Ouvrir le QR
                </button>
                <button className="btn btn-outline-secondary btn-sm" onClick={() => ouvrirQr(true)} disabled={!seanceId}>
                  <i className="bi bi-arrow-repeat me-1"></i>Régénérer
                </button>
              </div>
              {seance && (
                <p className="text-muted mt-3 mb-0">
                  {seance.intitule} · {seance.groupe_libelle || 'sans groupe'} · {seance.salle || 'salle non renseignée'}.
                  Les participants scannent ce QR depuis leur application ; le QR est temporaire et propre à la séance.
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="col-lg-7">
          <div className="pqr-panel h-100">
            <div className="pqr-panel-tete"><span><i className="bi bi-geo-alt me-2"></i>Badgeage du compte connecté</span></div>
            <div className="pqr-panel-corps">
              <div className="pqr-fiche mb-3">
                {position ? (
                  <span>
                    Position du terminal : <code>{position.latitude?.toFixed(6)}, {position.longitude?.toFixed(6)}</code>
                    {' '}· précision ±{Math.round(position.accuracy_m || 0)} m.
                    Le verdict de périmètre est calculé par le serveur, jamais par ce terminal.
                  </span>
                ) : (
                  <span>Position non mesurée : le serveur refusera un badgeage géolocalisé sans position (GPS_INDISPONIBLE).</span>
                )}
              </div>
              <div className="d-flex flex-wrap gap-2">
                <button className="btn btn-outline-secondary" onClick={activerGps}>
                  <i className="bi bi-crosshair me-1"></i>Mesurer ma position
                </button>
                <button className="btn btn-dfrc" onClick={badger} disabled={!jeton || etat === 'VERIFICATION'}>
                  <i className="bi bi-qr-code-scan me-1"></i>Badger (entrée / sortie)
                </button>
                <button className="btn btn-outline-danger" onClick={sortir} disabled={!jeton || etat === 'VERIFICATION'}>
                  <i className="bi bi-box-arrow-right me-1"></i>Enregistrer ma sortie
                </button>
                {heartbeatActif && (
                  <button className="btn btn-outline-secondary" onClick={arreterHeartbeat}>
                    <i className="bi bi-stop-circle me-1"></i>Arrêter le heartbeat
                  </button>
                )}
              </div>

              {resultat && (
                <div className="alert alert-success mt-3 mb-0">
                  <strong>{resultat.action === 'ENTREE' ? 'Entrée enregistrée' : resultat.action === 'SORTIE' ? 'Sortie enregistrée' : (resultat.message || 'Réponse serveur reçue')}</strong>
                  {resultat.seance_intitule && <> · Séance : {resultat.seance_intitule}</>}
                  {resultat.timestamp && <> · Heure : {formatHeure(resultat.timestamp)}</>}
                  {resultat.mode && <> · Mode : {resultat.mode === 'MANUEL' ? 'Manuel' : 'QR automatique'}</>}
                  {resultat.type_sortie && <> · Sortie : {resultat.type_sortie === 'SORTIE_QR' ? 'volontaire (QR)' : 'automatique'}</>}
                </div>
              )}
              <p className="text-muted mt-3 mb-0">
                Après une entrée validée, le heartbeat envoie la position toutes les 30 secondes
                pendant la séance ; deux sorties de périmètre confirmées déclenchent la sortie
                automatique côté serveur. Aucun suivi n’a lieu hors séance ouverte.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
