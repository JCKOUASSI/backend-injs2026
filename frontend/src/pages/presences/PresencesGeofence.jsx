import React, { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { distanceMetres, messageErreur } from './commun'
import '../../styles/presences.css'

/**
 * Configuration géofence — sites autorisés du badgeage géolocalisé.
 *
 * Source : `formations.RefSite` via `/api/formations/ref/sites/`
 * (lecture/écriture réservées DFRC côté serveur — l'écran n'accorde rien).
 * Le contrôle de périmètre reste calculé par `presences/geofence.py` :
 * l'anneau et la simulation ci-dessous ne sont qu'une aide visuelle, ils
 * ne produisent aucun verdict opposable.
 */

const API_SITES = '/formations/ref/sites/'

function Anneau({ rayon, distance }) {
  const R = 70
  const dedans = distance !== null && distance <= rayon
  const echelle = distance ? Math.min(1, rayon / Math.max(distance, rayon)) : 1
  const rPoint = distance === null ? null : (dedans ? (distance / rayon) * R : R * echelle + 18)
  return (
    <svg width="190" height="190" viewBox="0 0 190 190" role="img" aria-label="Anneau de périmètre">
      <circle cx="95" cy="95" r={R} fill="#EAF5FF" stroke="#1267D6" strokeWidth="2" />
      <circle cx="95" cy="95" r="4" fill="#0a2a5c" />
      <text x="95" y="82" textAnchor="middle" fontSize="10" fill="#0a2a5c">site</text>
      {rPoint !== null && (
        <>
          <circle cx={95 + rPoint * 0.72} cy={95 - rPoint * 0.72} r="6"
                  fill={dedans ? '#14663c' : '#9c2b2e'} stroke="#fff" strokeWidth="2" />
          <text x="95" y="182" textAnchor="middle" fontSize="10" fill={dedans ? '#14663c' : '#9c2b2e'}>
            {dedans ? 'dans le périmètre (simulation)' : 'hors périmètre (simulation)'}
          </text>
        </>
      )}
      <text x="95" y="20" textAnchor="middle" fontSize="10" fill="#5b7186">rayon {rayon} m</text>
    </svg>
  )
}

export default function PresencesGeofence() {
  const { showToast } = useToast()
  const [sites, setSites] = useState([])
  const [selection, setSelection] = useState(null)
  const [form, setForm] = useState({ nom: '', actif: true, geofence_latitude: '', geofence_longitude: '', geofence_rayon_m: 200 })
  const [testPos, setTestPos] = useState({ latitude: '', longitude: '' })
  const [erreur, setErreur] = useState('')
  const [charge, setCharge] = useState(true)

  const charger = useCallback(async () => {
    setCharge(true)
    try {
      const res = await api.get(API_SITES)
      setSites(Array.isArray(res.data) ? res.data : [])
      setErreur('')
    } catch (err) {
      setErreur(messageErreur(err, 'Sites géofence indisponibles (lecture réservée à la direction / DFRC).'))
      setSites([])
    } finally {
      setCharge(false)
    }
  }, [])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    if (selection) {
      setForm({
        nom: selection.nom || '',
        actif: Boolean(selection.actif),
        geofence_latitude: selection.geofence_latitude ?? '',
        geofence_longitude: selection.geofence_longitude ?? '',
        geofence_rayon_m: selection.geofence_rayon_m ?? 200,
      })
    }
  }, [selection])

  const distanceTest = useMemo(() => {
    const lat = parseFloat(testPos.latitude)
    const lon = parseFloat(testPos.longitude)
    if (!selection || Number.isNaN(lat) || Number.isNaN(lon)
      || selection.geofence_latitude === null || selection.geofence_longitude === null) return null
    return Math.round(distanceMetres(lat, lon, selection.geofence_latitude, selection.geofence_longitude))
  }, [testPos, selection])

  const enregistrer = async () => {
    const charge = {
      nom: form.nom,
      actif: form.actif,
      geofence_latitude: form.geofence_latitude === '' ? null : parseFloat(form.geofence_latitude),
      geofence_longitude: form.geofence_longitude === '' ? null : parseFloat(form.geofence_longitude),
      geofence_rayon_m: parseInt(form.geofence_rayon_m, 10) || 200,
    }
    try {
      if (selection) {
        await api.put(`${API_SITES}${selection.id}/`, charge)
        showToast('Site géofence mis à jour')
      } else {
        await api.post(API_SITES, charge)
        showToast('Site géofence créé')
      }
      setSelection(null)
      charger()
    } catch (err) {
      showToast(messageErreur(err, 'Enregistrement refusé par le serveur.'), 'error')
    }
  }

  return (
    <div>
      <div className="pqr-hero">
        <div>
          <span className="pqr-hero-badge"><i className="bi bi-geo-alt me-1"></i>CONFIGURATION</span>
          <h1 className="pqr-hero-title">Configuration géofence</h1>
          <p className="pqr-hero-intro">
            Sites pédagogiques autorisés, coordonnées et rayons de tolérance. Le serveur calcule
            la distance à chaque badgeage : aucun terminal ne déclare « dans le périmètre ».
          </p>
        </div>
      </div>

      {erreur && <div className="error-message">{erreur}</div>}

      <div className="row g-3">
        <div className="col-lg-6">
          <div className="pqr-panel h-100">
            <div className="pqr-panel-tete">
              <span><i className="bi bi-geo me-2"></i>Sites configurés</span>
              <button className="btn btn-dfrc btn-sm" onClick={() => setSelection(null)}>
                <i className="bi bi-plus-lg me-1"></i>Nouveau site
              </button>
            </div>
            <div className="table-container">
              <table className="table edt-table mb-0">
                <thead><tr><th>Site</th><th>Coordonnées</th><th>Rayon</th><th>Actif</th></tr></thead>
                <tbody>
                  {sites.map((s) => (
                    <tr key={s.id} onClick={() => setSelection(s)} style={{ cursor: 'pointer' }}>
                      <td><strong>{s.nom}</strong></td>
                      <td>
                        {s.geofence_latitude !== null && s.geofence_longitude !== null
                          ? <code>{Number(s.geofence_latitude).toFixed(5)}, {Number(s.geofence_longitude).toFixed(5)}</code>
                          : <span className="text-warning">non localisé (aucun contrôle)</span>}
                      </td>
                      <td>{s.geofence_rayon_m ?? 200} m</td>
                      <td>{s.actif ? <span className="badge text-bg-success">actif</span> : <span className="badge text-bg-secondary">inactif</span>}</td>
                    </tr>
                  ))}
                  {!charge && sites.length === 0 && (
                    <tr><td colSpan={4} className="text-center text-muted py-4">Aucun site retourné par le serveur.</td></tr>
                  )}
                  {charge && (
                    <tr><td colSpan={4} className="text-center py-4"><div className="loading"><div className="spinner"></div></div></td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="pqr-panel-corps">
              <small className="text-muted">
                Seuils projet (configurables côté serveur, jamais codés en dur dans l’écran) :
                rayon par défaut 200 m (`MOBILE_GEOFENCE_DEFAULT_RADIUS_M`), précision GPS
                maximale 80 m (`MOBILE_GEOFENCE_MAX_ACCURACY_M`), 2 heartbeats hors périmètre
                avant sortie automatique (`MOBILE_GEOFENCE_OUTSIDE_CONFIRMATIONS`).
              </small>
            </div>
          </div>
        </div>

        <div className="col-lg-6">
          <div className="pqr-panel">
            <div className="pqr-panel-tete">
              <span><i className="bi bi-pencil-square me-2"></i>{selection ? `Modifier « ${selection.nom} »` : 'Nouveau site'}</span>
            </div>
            <div className="pqr-panel-corps">
              <div className="mb-2">
                <label className="label" htmlFor="pqr-site-nom">Nom du site</label>
                <input id="pqr-site-nom" className="input" value={form.nom}
                       onChange={(e) => setForm((f) => ({ ...f, nom: e.target.value }))} />
              </div>
              <div className="row g-2">
                <div className="col-6">
                  <label className="label" htmlFor="pqr-site-lat">Latitude</label>
                  <input id="pqr-site-lat" className="input" inputMode="decimal" value={form.geofence_latitude}
                         onChange={(e) => setForm((f) => ({ ...f, geofence_latitude: e.target.value }))} />
                </div>
                <div className="col-6">
                  <label className="label" htmlFor="pqr-site-lon">Longitude</label>
                  <input id="pqr-site-lon" className="input" inputMode="decimal" value={form.geofence_longitude}
                         onChange={(e) => setForm((f) => ({ ...f, geofence_longitude: e.target.value }))} />
                </div>
                <div className="col-6">
                  <label className="label" htmlFor="pqr-site-rayon">Rayon (m)</label>
                  <input id="pqr-site-rayon" className="input" type="number" min="10" value={form.geofence_rayon_m}
                         onChange={(e) => setForm((f) => ({ ...f, geofence_rayon_m: e.target.value }))} />
                </div>
                <div className="col-6 d-flex align-items-end">
                  <div className="form-check mb-2">
                    <input id="pqr-site-actif" type="checkbox" className="form-check-input" checked={form.actif}
                           onChange={(e) => setForm((f) => ({ ...f, actif: e.target.checked }))} />
                    <label className="form-check-label" htmlFor="pqr-site-actif">Site actif</label>
                  </div>
                </div>
              </div>
              <div className="d-flex justify-content-end gap-2 mt-3">
                <button className="btn btn-dfrc" onClick={enregistrer}>
                  <i className="bi bi-check-lg me-1"></i>Enregistrer
                </button>
              </div>
            </div>
          </div>

          <div className="pqr-panel">
            <div className="pqr-panel-tete"><span><i className="bi bi-bullseye me-2"></i>Simuler une position</span></div>
            <div className="pqr-panel-corps">
              <div className="pqr-anneau-wrap">
                <Anneau rayon={selection?.geofence_rayon_m ?? 200} distance={distanceTest} />
                <div style={{ flex: 1, minWidth: 220 }}>
                  <label className="label" htmlFor="pqr-test-lat">Latitude test</label>
                  <input id="pqr-test-lat" className="input mb-2" inputMode="decimal" value={testPos.latitude}
                         onChange={(e) => setTestPos((t) => ({ ...t, latitude: e.target.value }))} />
                  <label className="label" htmlFor="pqr-test-lon">Longitude test</label>
                  <input id="pqr-test-lon" className="input mb-2" inputMode="decimal" value={testPos.longitude}
                         onChange={(e) => setTestPos((t) => ({ ...t, longitude: e.target.value }))} />
                  {distanceTest !== null
                    ? <p className="mb-0">Distance calculée : <strong>{distanceTest} m</strong> (rayon {selection?.geofence_rayon_m ?? 200} m).</p>
                    : <p className="text-muted mb-0">Sélectionnez un site localisé et saisissez une position pour simuler.</p>}
                  <small className="text-muted">
                    Simulation d’affichage uniquement : le verdict officiel est toujours calculé
                    par le serveur lors du badgeage.
                  </small>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
