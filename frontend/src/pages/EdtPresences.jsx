import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import QRCode from 'qrcode'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import '../styles/edts.css'

/**
 * Émargement des séances LMD (modèle fonctionnel MODULE 08, lot C) :
 * QR de séance (badgeage automatique par les auditeurs) + liste nominative
 * « cases de l'enseignant » (émargement manuel à motif) + clôture automatique.
 * Chemin : /edt/presences.
 */

const API = '/presences/seances-edt'

const STATUTS = [
  { valeur: '', libelle: '— non renseigné —' },
  { valeur: 'PRESENT', libelle: 'Présent' },
  { valeur: 'RETARD', libelle: 'Retard' },
  { valeur: 'ABSENT', libelle: 'Absent' },
  { valeur: 'ABSENCE_JUSTIFIEE', libelle: 'Absence justifiée' },
  { valeur: 'EXCUSE', libelle: 'Excusé' },
]

function badgeEntree(ligne) {
  if (!ligne.badge_entree) return <span className="text-muted">—</span>
  const heure = new Date(ligne.badge_entree).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  const sortie = ligne.badge_sortie
    ? ` → ${new Date(ligne.badge_sortie).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`
    : ' (en salle)'
  return <code title={`Badge : ${ligne.statut_badgeage || ''}`}>{heure}{sortie}</code>
}

function ModalQR({ seance, date, onClose }) {
  const canvasRef = useRef(null)
  const [etat, setEtat] = useState({ loading: true, token: null, expire: null, erreur: '' })

  const charger = useCallback(async (regenerer) => {
    setEtat((e) => ({ ...e, loading: true, erreur: '' }))
    try {
      const res = regenerer
        ? await api.post(`${API}/${seance.id}/qr/?date=${date}`)
        : await api.get(`${API}/${seance.id}/qr/?date=${date}`)
      const donnees = res.data
      if (!donnees.token) {
        setEtat({ loading: false, token: null, expire: null, erreur: '' })
        return
      }
      setEtat({ loading: false, token: donnees.token, expire: donnees.expire_a, erreur: '' })
    } catch (err) {
      setEtat({ loading: false, token: null, expire: null,
                erreur: err.response?.data?.detail || 'Erreur réseau' })
    }
  }, [seance.id, date])

  useEffect(() => { charger(false) }, [charger])

  useEffect(() => {
    if (etat.token && canvasRef.current) {
      QRCode.toCanvas(canvasRef.current, etat.token, { width: 260, margin: 1 }, () => {})
    }
  }, [etat.token])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" style={{ maxWidth: 380 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h6 className="mb-0"><i className="bi bi-qr-code me-2"></i>QR de séance — {seance.intitule}</h6>
          <button type="button" className="btn btn-sm btn-outline-secondary" onClick={onClose}>×</button>
        </div>
        <div className="modal-body text-center">
          {etat.loading && <div className="loading"><div className="spinner"></div></div>}
          {etat.erreur && <div className="error-message">{etat.erreur}</div>}
          {!etat.loading && !etat.erreur && !etat.token && (
            <div>
              <p className="text-muted">Aucun QR actif pour cette séance.</p>
              <button className="btn btn-dfrc" onClick={() => charger(true)}>
                <i className="bi bi-qr-code me-1"></i>Ouvrir le QR de séance
              </button>
            </div>
          )}
          {etat.token && (
            <>
              <canvas ref={canvasRef} className="mb-2" />
              <div><small className="text-muted">À scanner par les auditeurs depuis leur appli mobile.
                Valide jusqu’à {etat.expire ? new Date(etat.expire).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : 'la fin de séance'}.</small></div>
              <div className="mt-2 d-flex justify-content-center gap-2">
                <button className="btn btn-outline-secondary btn-sm" onClick={() => charger(true)}>
                  <i className="bi bi-arrow-repeat me-1"></i>Régénérer
                </button>
                <button className="btn btn-outline-danger btn-sm" onClick={() => {
                  navigator.clipboard?.writeText(etat.token)
                }}><i className="bi bi-clipboard me-1"></i>Copier le jeton</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function EdtPresences() {
  const { showToast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const [date, setDate] = useState(() => searchParams.get('date')
    || new Date().toLocaleDateString('en-CA'))
  const [seances, setSeances] = useState([])
  const [charge, setCharge] = useState(true)
  const [erreur, setErreur] = useState('')
  const [selection, setSelection] = useState(null)   // séance choisie
  const [qrOuvert, setQrOuvert] = useState(false)
  const [emargement, setEmargement] = useState(null) // {lignes, motif, envoi}
  const [clotureInfo, setClotureInfo] = useState('')

  const chargerSeances = useCallback(async () => {
    setCharge(true)
    setErreur('')
    try {
      const res = await api.get(`${API}/du-jour/?date=${date}`)
      const liste = Array.isArray(res.data) ? res.data : (res.data.results || [])
      setSeances(liste)
      const idSel = Number(searchParams.get('seance'))
      const trouvee = liste.find((s) => s.id === idSel) || null
      setSelection(trouvee)
    } catch {
      setErreur('Erreur lors du chargement des séances du jour.')
    } finally {
      setCharge(false)
    }
  }, [date, searchParams])

  useEffect(() => { chargerSeances() }, [chargerSeances])

  const selectionner = (seance) => {
    setSelection(seance)
    setClotureInfo('')
    const sp = new URLSearchParams(searchParams)
    sp.set('seance', String(seance.id))
    sp.set('date', date)
    setSearchParams(sp, { replace: true })
  }

  const chargerEmargement = useCallback(async () => {
    if (!selection) return
    try {
      const res = await api.get(`${API}/${selection.id}/presences/?date=${date}`)
      setEmargement({
        lignes: (res.data.lignes || []).map((l) => ({ ...l, statut_choisi: l.statut || '' })),
        effectif: res.data.effectif,
        presents: res.data.presents,
        motif: '',
        envoi: false,
      })
    } catch (err) {
      showToast(err.response?.data?.detail || 'Liste nominative indisponible', 'error')
    }
  }, [selection, date, showToast])

  useEffect(() => { chargerEmargement() }, [chargerEmargement])

  const soumettreEmargement = async () => {
    // Seuls les écarts sont postés : une ligne déjà conforme (badge ou statut
    // identique) n'est pas renvoyée — pas de faux « forçage » inutile.
    const entries = emargement.lignes
      .filter((l) => l.statut_choisi && l.statut_choisi !== (l.statut || ''))
      .map((l) => ({ participant: l.participant, statut: l.statut_choisi,
                     ...(emargement.motif ? { motif: emargement.motif } : {}) }))
    if (!entries.length) { showToast('Aucun statut sélectionné', 'error'); return }
    setEmargement((e) => ({ ...e, envoi: true }))
    try {
      const res = await api.post(`${API}/${selection.id}/emargement/?date=${date}`, { entries })
      showToast(res.data.detail || 'Émargement enregistré')
      chargerEmargement()
    } catch (err) {
      showToast(err.response?.data?.detail || 'Émargement refusé', 'error')
    } finally {
      setEmargement((e) => ({ ...e, envoi: false }))
    }
  }

  const badgerTousPresents = () => {
    setEmargement((e) => e && { ...e, lignes: e.lignes.map((l) => ({ ...l, statut_choisi: l.statut_choisi || 'PRESENT' })) })
  }

  const cloturer = async () => {
    try {
      const res = await api.post(`${API}/${selection.id}/autoclore/?date=${date}`)
      const d = res.data
      setClotureInfo(`Séance clôturée : ${d.pointages_clotures} pointage(s) refermé(s), ${d.absents_marques} absent(s) marqué(s).`)
      showToast('Clôture automatique effectuée')
      chargerEmargement()
    } catch (err) {
      showToast(err.response?.data?.detail || 'Clôture impossible', 'error')
    }
  }

  const modifies = useMemo(
    () => (emargement ? emargement.lignes.filter((l) => l.statut_choisi && l.statut_choisi !== (l.statut || '')).length : 0),
    [emargement],
  )

  return (
    <div className="edt-page">
      <div className="edt-hero">
        <div className="edt-hero-text">
          <span className="edt-hero-badge"><i className="bi bi-qr-code" /> PRÉSENCES</span>
          <h6 className="edt-hero-title">
            <i className="bi bi-qr-code" />Présences de séance LMD
          </h6>
          <p className="edt-hero-intro">
            QR de séance pour le badgeage automatique des auditeurs, émargement manuel à motif
            et clôture automatique (modèle 08 appliqué à l’EDT).
          </p>
        </div>
        <div className="edt-hero-actions">
          <label className="edt-date-label" htmlFor="edt-presences-date">Date des séances</label>
          <input id="edt-presences-date" type="date" className="input" value={date}
                 onChange={(e) => { setDate(e.target.value); setSelection(null) }} />
        </div>
      </div>

      {erreur && <div className="error-message">{erreur}</div>}

      <div className="card edt-panel">
        <div className="card-header-bar" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
          <span><i className="bi bi-calendar3 me-2" />Séances du {date}</span>
          <span className="d-flex gap-2">
            <span className="badge badge-bg-secondary">{seances.length} séance(s)</span>
          </span>
        </div>
        <div className="card-body-flush">
          {charge ? (
            <div className="loading"><div className="spinner"></div></div>
          ) : seances.length === 0 ? (
            <div className="text-center py-5 text-muted edt-empty">
              <i className="bi bi-calendar-x" style={{ fontSize: '2rem' }}></i>
              <p className="mt-2">Aucune séance planifiée ce jour pour votre périmètre.</p>
            </div>
          ) : (
            <div className="table-container">
              <table className="table edt-table">
                <thead>
                  <tr><th>Horaire</th><th>Intitulé</th><th>Groupe</th><th>Salle</th><th>Enseignant</th><th /></tr>
                </thead>
                <tbody>
                  {seances.map((s) => (
                    <tr key={s.id} style={selection?.id === s.id ? { background: 'rgba(21,101,192,.07)' } : undefined}>
                      <td><code>{new Date(s.debut).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                        {'–'}{new Date(s.fin).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</code></td>
                      <td><strong>{s.intitule}</strong> <small className="text-muted">({s.nature})</small></td>
                      <td>{s.groupe_libelle || '—'}</td>
                      <td>{s.salle || '—'}</td>
                      <td>{s.enseignant_nom || '—'}</td>
                      <td className="text-end">
                        <button className="btn btn-outline-secondary btn-sm me-1" onClick={() => selectionner(s)}>
                          {selection?.id === s.id ? 'Fermer' : 'Émarger'}
                        </button>
                        {s.peut_gerer && (
                          <button className="btn btn-dfrc btn-sm" onClick={() => { selectionner(s); setQrOuvert(true) }}>
                            <i className="bi bi-qr-code me-1"></i>QR
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {selection && selection.peut_gerer && emargement && (
        <div className="card edt-panel">
          <div className="card-header-bar" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
            <span>
              <i className="bi bi-check2-square me-2" />Liste d’émargement — {selection.intitule}
            </span>
            <span className="d-flex gap-2 align-items-center">
              <span className="badge badge-bg-secondary">{emargement.presents}/{emargement.effectif} présents</span>
              {modifies > 0 && (
                <span className="badge badge-bg-warning" title="Statuts modifiés non encore enregistrés">
                  {modifies} correction(s)
                </span>
              )}
              <button className="btn btn-outline-secondary btn-sm" onClick={badgerTousPresents}
                      title="Présupposer tous les inscrits présents (puis corriger les exceptions)">
                <i className="bi bi-check2-all me-1"></i>Tous présents
              </button>
              <button className="btn btn-outline-danger btn-sm" onClick={cloturer}
                      title="Fermer la séance : sorties auto + absents non badgés marqués">
                <i className="bi bi-stop-circle me-1"></i>Clôturer
              </button>
            </span>
          </div>
          {clotureInfo && <div className="alert alert-success mb-0" style={{ borderRadius: 0 }}>{clotureInfo}</div>}
          <div className="card-body-flush">
            <div className="table-container">
              <table className="table edt-table">
                <thead>
                  <tr><th>Auditeur</th><th>Badge QR</th><th>Statut séance</th><th>Forçage tracé</th></tr>
                </thead>
                <tbody>
                  {emargement.lignes.map((l) => (
                    <tr key={l.participant}>
                      <td>
                        <strong>{l.nom}</strong> <small className="text-muted">{l.matricule}</small>
                      </td>
                      <td>{badgeEntree(l)}</td>
                      <td style={{ maxWidth: 220 }}>
                        <select
                          className="input"
                          value={l.statut_choisi}
                          onChange={(e) => setEmargement((em) => ({
                            ...em,
                            lignes: em.lignes.map((x) => (x.participant === l.participant
                              ? { ...x, statut_choisi: e.target.value } : x)),
                          }))}
                        >
                          {STATUTS.map((st) => <option key={st.valeur} value={st.valeur}>{st.libelle}</option>)}
                        </select>
                      </td>
                      <td>
                        {l.pointage_id && l.statut_choisi && l.statut_choisi !== (l.statut || '')
                          ? <span className="badge-bg-warning">correction à justifier</span>
                          : <span className="text-muted">—</span>}
                      </td>
                    </tr>
                  ))}
                  {emargement.lignes.length === 0 && (
                    <tr><td colSpan={4} className="text-center text-muted py-4">
                      Séance sans groupe rattaché — rattachez un groupe dans l’EDT pour émarger.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {emargement.lignes.length > 0 && (
              <div className="card-body d-flex align-items-end gap-2">
                <div style={{ flex: 1 }}>
                  <label className="label" htmlFor="edt-emargement-motif">
                    Motif global {modifies > 0 && <span className="text-danger">(obligatoire pour {modifies} correction(s))</span>}
                  </label>
                  <input
                    id="edt-emargement-motif"
                    className="input"
                    placeholder="ex. coupure réseau du terminal de badgeage"
                    value={emargement.motif}
                    onChange={(e) => setEmargement((em) => ({ ...em, motif: e.target.value }))}
                  />
                </div>
                <button className="btn btn-dfrc" onClick={soumettreEmargement} disabled={emargement.envoi}>
                  {emargement.envoi ? 'Envoi…' : `Valider l’émargement (${modifies || emargement.lignes.filter((l) => l.statut_choisi).length})`}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {qrOuvert && selection && (
        <ModalQR seance={selection} date={date} onClose={() => setQrOuvert(false)} />
      )}
    </div>
  )
}
