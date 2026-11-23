import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import QRCode from 'qrcode'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import '../styles/edts.css'
import '../styles/presences.css'
import { identifiantPermanent } from './presences/commun'

/**
 * Émargement des séances LMD (modèle fonctionnel MODULE 08, lot C) :
 * QR de séance (badgeage automatique par les auditeurs) + liste nominative
 * « cases de l'enseignant » (émargement manuel à motif) + clôture automatique.
 * Chemin : /edt/presences.
 */

const API = '/presences/seances-edt'

// Catalogue normalisé des motifs de badgeage manuel (miroir backend :
// presences.seances_edt_services.MOTIFS_EMARGEMENT_MANUEL — le serveur
// reste l'autorité : motif obligatoire, commentaire exigé pour AUTRE).
const MOTIFS_MANUELS = [
  { valeur: 'QR_NON_LISIBLE', libelle: 'QR illisible ou non fonctionnel' },
  { valeur: 'GPS_INDISPONIBLE', libelle: 'GPS indisponible sur l’appareil' },
  { valeur: 'PANNE_RESEAU', libelle: 'Panne réseau au moment du badgeage' },
  { valeur: 'PROBLEME_TECHNIQUE', libelle: 'Problème technique (appareil, application)' },
  { valeur: 'PARTICIPANT_PRESENT_SANS_BADGE', libelle: 'Participant présent mais sans badge' },
  { valeur: 'AUTRE', libelle: 'Autre motif (commentaire obligatoire)' },
]

// Erreur affichable : code métier + message + action recommandée
// (jamais de HTML brut ni de détail technique incompréhensible).
function messageErreur(err, repli) {
  const d = err?.response?.data || {}
  const code = d.code_normalise || d.code || ''
  const message = d.message || d.detail || repli
  const action = d.action_recommandee ? ` — ${d.action_recommandee}` : ''
  return `${code ? `[${code}] ` : ''}${message}${action}`
}

// Canal d'une présence : badgeage QR automatique vs badgeage manuel
// identifiable sans ambiguïté (mode explicite posé par le serveur).
function badgeCanal(ligne) {
  if (!ligne.pointage_id) return <span className="text-muted">—</span>
  if (ligne.mode === 'MANUEL') {
    return (
      <span className="badge text-bg-warning" title={`Motif : ${ligne.motif_manuel || '—'}`}>
        <i className="bi bi-pencil-square me-1"></i>Manuel{ligne.motif_manuel ? ` · ${ligne.motif_manuel}` : ''}
      </span>
    )
  }
  if (ligne.mode === 'QR_AUTOMATIQUE') {
    return (
      <span className="badge text-bg-success">
        <i className="bi bi-qr-code me-1"></i>QR
        {ligne.type_sortie === 'SORTIE_AUTOMATIQUE_FIN_SEANCE' ? ' · sortie auto.' : ''}
      </span>
    )
  }
  return <span className="badge text-bg-secondary">Non renseigné</span>
}

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

/** Jeton QR d'une séance : lecture/ouverture partagées (modale, panneau). */
function useJetonQr(seance, date) {
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
  return { etat, charger }
}

function ModalQR({ seance, date, onClose }) {
  const canvasRef = useRef(null)
  const { etat, charger } = useJetonQr(seance, date)

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

const PALETTE_AVATAR = [
  ['#1267D6', '#38BDF8'], ['#8A5A00', '#F5B544'], ['#0A2A5C', '#1267D6'],
  ['#14663C', '#2BD97B'], ['#5B2EA6', '#B79CED'], ['#9C2B2E', '#E88'],
]

function AvatarParticipant({ nom, matricule }) {
  const morceaux = (nom || '?').trim().split(/\s+/).filter(Boolean)
  const initiales = ((morceaux[0]?.[0] || '?') + (morceaux[1]?.[0] || '')).toUpperCase()
  let h = 0
  const cle = matricule || nom || '?'
  for (let i = 0; i < cle.length; i += 1) h = (h * 31 + cle.charCodeAt(i)) % 997
  const [a, b] = PALETTE_AVATAR[h % PALETTE_AVATAR.length]
  return (
    <span className="pqr-avatar" style={{ background: `linear-gradient(135deg, ${a}, ${b})` }}>
      {initiales}
    </span>
  )
}

/** Panneau QR de séance (design premium) : jeton réel, jamais un faux QR. */
function PanneauQR({ seance, date, onAgrandir }) {
  const canvasRef = useRef(null)
  const { etat, charger } = useJetonQr(seance, date)

  useEffect(() => {
    if (etat.token && canvasRef.current) {
      QRCode.toCanvas(canvasRef.current, etat.token, { width: 168, margin: 1 }, () => {})
    }
  }, [etat.token])

  return (
    <div className="pqr-panel pqr-entree">
      <div className="pqr-panel-tete">
        <div>
          <div className="pqr-surtitre">Session QR temporaire</div>
          <h2 className="pqr-panel-titre">QR de séance</h2>
        </div>
        {etat.token
          ? <span className="badge text-bg-success">● Ouverte</span>
          : <span className="badge text-bg-secondary">Fermée</span>}
      </div>
      <div className="pqr-panel-corps">
        {etat.loading && <div className="loading"><div className="spinner"></div></div>}
        {etat.erreur && <div className="error-message">{etat.erreur}</div>}
        {!etat.loading && !etat.erreur && !etat.token && (
          <div className="text-center py-2">
            <p className="text-muted">Aucun QR actif pour cette séance.</p>
            <button className="btn btn-dfrc" onClick={() => charger(true)}>
              <i className="bi bi-qr-code me-1"></i>Ouvrir la session
            </button>
          </div>
        )}
        {etat.token && (
          <div className="d-flex gap-3 flex-wrap align-items-center">
            <span className="pqr-qr-cadre"><canvas ref={canvasRef} /></span>
            <div style={{ flex: 1, minWidth: 190 }}>
              <div className="mb-2">
                <div className="caps text-muted" style={{ fontSize: '.7rem' }}>Expire à</div>
                <span className="pqr-compte">
                  {etat.expire
                    ? new Date(etat.expire).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
                    : 'fin de séance'}
                </span>
              </div>
              <div className="mb-1">
                <div className="caps text-muted" style={{ fontSize: '.7rem' }}>Identifiant permanent</div>
                <code>{identifiantPermanent(seance.id)}</code>
              </div>
              <div className="d-flex gap-2 flex-wrap mt-3">
                <button className="btn btn-dfrc btn-sm" onClick={() => charger(true)}>
                  <i className="bi bi-arrow-repeat me-1"></i>Régénérer
                </button>
                <button className="btn btn-outline-secondary btn-sm" onClick={onAgrandir}>
                  <i className="bi bi-arrows-fullscreen me-1"></i>Agrandir
                </button>
                <button className="btn btn-outline-secondary btn-sm"
                        onClick={() => navigator.clipboard?.writeText(etat.token)}>
                  <i className="bi bi-clipboard me-1"></i>Copier le jeton
                </button>
              </div>
            </div>
          </div>
        )}
        <p className="text-muted mt-3 mb-0" style={{ fontSize: '.86rem' }}>
          Les étudiants scannent ce QR depuis leur application : le serveur vérifie
          jeton, inscription au groupe, périmètre et doublon avant toute validation.
        </p>
      </div>
    </div>
  )
}

export function ModalBadgeageManuel({ seance, date, ligne, onClose, onSaved }) {
  const [statut, setStatut] = useState(ligne.statut || 'PRESENT')
  const [motif, setMotif] = useState('')
  const [commentaire, setCommentaire] = useState('')
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState('')

  const commentaireRequis = motif === 'AUTRE'
  const valide = Boolean(motif) && (!commentaireRequis || commentaire.trim().length > 0)

  const soumettre = async () => {
    setEnvoi(true)
    setErreur('')
    try {
      const res = await api.post(
        `${API}/${seance.id}/emargement/unitaire/?date=${date}`,
        { participant: ligne.participant, statut, motif,
          ...(commentaire.trim() ? { commentaire: commentaire.trim() } : {}) },
      )
      onSaved(res.data.detail || 'Badgeage manuel enregistré.')
      onClose()
    } catch (err) {
      setErreur(messageErreur(err, 'Badgeage manuel refusé.'))
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" style={{ maxWidth: 440 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h6 className="mb-0"><i className="bi bi-pencil-square me-2"></i>Badgeage manuel — {ligne.nom}</h6>
          <button type="button" className="btn btn-sm btn-outline-secondary" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <p className="text-muted">
            Le badgeage manuel est une exception tracée (acteur, motif, horodatage) :
            le motif est obligatoire et le motif « Autre » exige un commentaire.
          </p>
          {erreur && <div className="error-message">{erreur}</div>}
          <div className="mb-2">
            <label className="label" htmlFor="badgeage-manuel-statut">Statut constaté</label>
            <select id="badgeage-manuel-statut" className="input" value={statut}
                    onChange={(e) => setStatut(e.target.value)}>
              {STATUTS.filter((st) => st.valeur).map((st) => (
                <option key={st.valeur} value={st.valeur}>{st.libelle}</option>
              ))}
            </select>
          </div>
          <div className="mb-2">
            <label className="label" htmlFor="badgeage-manuel-motif">Motif <span className="text-danger">*</span></label>
            <select id="badgeage-manuel-motif" className="input" value={motif}
                    onChange={(e) => setMotif(e.target.value)}>
              <option value="">— Choisir un motif —</option>
              {MOTIFS_MANUELS.map((m) => (
                <option key={m.valeur} value={m.valeur}>{m.libelle}</option>
              ))}
            </select>
          </div>
          <div className="mb-3">
            <label className="label" htmlFor="badgeage-manuel-commentaire">
              Commentaire {commentaireRequis && <span className="text-danger">(obligatoire pour « Autre »)</span>}
            </label>
            <textarea id="badgeage-manuel-commentaire" className="input" rows={2}
                      value={commentaire} onChange={(e) => setCommentaire(e.target.value)}
                      placeholder="Précisez le contexte du badgeage manuel" />
          </div>
          <div className="d-flex justify-content-end gap-2">
            <button className="btn btn-outline-secondary" onClick={onClose}>Annuler</button>
            <button className="btn btn-dfrc" onClick={soumettre} disabled={!valide || envoi}>
              {envoi ? 'Envoi…' : 'Enregistrer le badgeage'}
            </button>
          </div>
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
  const [badgeageManuel, setBadgeageManuel] = useState(null) // ligne ciblée (badgeage unitaire)
  const [recherchePresence, setRecherchePresence] = useState('')
  const [filtrePresence, setFiltrePresence] = useState('tous')

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
      const lignesBrutes = res.data.lignes || []
      setEmargement({
        lignes: lignesBrutes.map((l) => ({ ...l, statut_choisi: l.statut || '' })),
        effectif: res.data.effectif,
        presents: res.data.presents,
        presencesManuelles: res.data.presences_manuelles || 0,
        retards: res.data.retards ?? lignesBrutes.filter((l) => l.statut === 'RETARD').length,
        absents: res.data.absents ?? 0,
        anomaliesGps: res.data.anomalies_gps
          ?? lignesBrutes.filter((l) => l.statut_badgeage === 'HORS_LIGNE_SUSPECT').length,
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
      showToast(messageErreur(err, 'Émargement refusé'), 'error')
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
      showToast(messageErreur(err, 'Clôture impossible'), 'error')
    }
  }

  const lignesAffichees = useMemo(() => {
    if (!emargement) return []
    let out = emargement.lignes
    if (filtrePresence === 'present') out = out.filter((l) => Boolean(l.pointage_id))
    if (filtrePresence === 'absent') out = out.filter((l) => !l.pointage_id)
    if (filtrePresence === 'manuel') out = out.filter((l) => l.mode === 'MANUEL')
    if (recherchePresence.trim()) {
      const q = recherchePresence.trim().toLowerCase()
      out = out.filter((l) => `${l.nom} ${l.matricule}`.toLowerCase().includes(q))
    }
    return out
  }, [emargement, filtrePresence, recherchePresence])

  const modifies = useMemo(
    () => (emargement ? emargement.lignes.filter((l) => l.statut_choisi && l.statut_choisi !== (l.statut || '')).length : 0),
    [emargement],
  )

  const enCours = Boolean(selection
    && new Date(selection.debut) <= new Date() && new Date() <= new Date(selection.fin))
  const tauxSeance = emargement?.effectif
    ? Math.round((emargement.presents / emargement.effectif) * 100) : 0
  const nbQr = emargement ? emargement.lignes.filter((l) => l.mode === 'QR_AUTOMATIQUE').length : 0
  const nbManuel = emargement ? emargement.lignes.filter((l) => l.mode === 'MANUEL').length : 0
  const nbPointes = nbQr + nbManuel
  const CERCLE = 2 * Math.PI * 44
  const changerJour = (delta) => {
    const d = new Date(`${date}T12:00:00`)
    d.setDate(d.getDate() + delta)
    setDate(d.toLocaleDateString('en-CA'))
    setSelection(null)
  }

  return (
    <div className="edt-page">
      {/* ── Bandeau nuit ─────────────────────────────────────────── */}
      <div className="pqr-hero2">
        <div style={{ position: 'relative', zIndex: 1 }}>
          <div className="d-flex gap-2 flex-wrap align-items-center">
            <span className="pqr-hero-badge"><i className="bi bi-qr-code me-1" />PRÉSENCES · BADGEAGE DE SÉANCE LMD</span>
            {enCours && (
              <span className="pqr-live"><span className="pqr-live-point"></span>EN DIRECT</span>
            )}
          </div>
          <h1 className="pqr-hero-title">
            Présences de séance <span className="or">LMD</span>
          </h1>
          <p className="pqr-hero-intro">
            QR de séance pour le badgeage automatique des étudiants, émargement manuel
            motivé et clôture automatique — Institut National de la Jeunesse et des
            Sports d’Abidjan (Marcory).
          </p>
          {selection && (
            <p className="mb-0 mt-2" style={{ color: '#A8D4F8' }}>
              <i className="bi bi-mortarboard me-1"></i>
              {selection.intitule} · {selection.groupe_libelle || 'sans groupe'} · {selection.salle || 'salle non renseignée'}
            </p>
          )}
        </div>
        <div className="pqr-hero-actions" style={{ position: 'relative', zIndex: 1 }}>
          <div>
            <label className="form-label text-white-50 mb-1" htmlFor="edt-presences-date">Date des séances</label>
            <input id="edt-presences-date" type="date" className="pqr-date-verre" value={date}
                   onChange={(e) => { setDate(e.target.value); setSelection(null) }} />
          </div>
        </div>
      </div>

      {erreur && <div className="error-message mt-3">{erreur}</div>}

      {/* ── Séances du jour ──────────────────────────────────────── */}
      <div className="pqr-panel mt-4">
        <div className="pqr-panel-tete">
          <div>
            <div className="pqr-surtitre">{date}</div>
            <h2 className="pqr-panel-titre">Séances du jour</h2>
          </div>
          <span className="badge badge-bg-secondary">{seances.length} séance(s)</span>
        </div>
        {charge ? (
          <div className="loading py-4"><div className="spinner"></div></div>
        ) : seances.length === 0 ? (
          <div className="pqr-panel-corps">
            <div className="pqr-vide">
              <div className="rond"><i className="bi bi-calendar-x"></i></div>
              <h3 className="h5 fw-bold" style={{ color: '#0A2A5C' }}>
                Aucune séance planifiée ce jour pour votre périmètre.
              </h3>
              <p className="text-muted mx-auto" style={{ maxWidth: '52ch' }}>
                Les séances proviennent des emplois du temps publiés par GET INJS APP :
                choisissez une autre date ou vérifiez la publication de l’emploi du temps.
              </p>
              <div className="d-flex gap-2 justify-content-center flex-wrap">
                <button className="btn btn-outline-secondary" onClick={() => changerJour(-1)}>
                  ← Jour précédent
                </button>
                <button className="btn btn-dfrc" onClick={() => changerJour(1)}>
                  Jour suivant →
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="table-container">
            <table className="table edt-table mb-0">
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

      {selection && selection.peut_gerer && (
        <div className="pqr-grille-premium mt-3">
          {/* ── Colonne gauche : QR + synthèse ─────────────────────── */}
          <div>
            <PanneauQR seance={selection} date={date} onAgrandir={() => setQrOuvert(true)} />
            {emargement && (
              <div className="pqr-panel pqr-entree mt-3" style={{ animationDelay: '.08s' }}>
                <div className="pqr-panel-tete">
                  <div>
                    <div className="pqr-surtitre">Synthèse serveur</div>
                    <h2 className="pqr-panel-titre">État de la séance</h2>
                  </div>
                  <span className="badge text-bg-info">Temps réel</span>
                </div>
                <div className="pqr-panel-corps">
                  <div className="d-flex gap-3 align-items-center flex-wrap">
                    <svg width="104" height="104" viewBox="0 0 104 104" role="img"
                         aria-label={`Taux de présence ${tauxSeance} pour cent`}>
                      <circle cx="52" cy="52" r="44" fill="none" stroke="#E3EDF7" strokeWidth="10" />
                      <circle className="pqr-anneau-cercle" cx="52" cy="52" r="44" fill="none"
                              stroke="#1267D6" strokeWidth="10" strokeLinecap="round"
                              strokeDasharray={CERCLE}
                              strokeDashoffset={CERCLE * (1 - tauxSeance / 100)}
                              transform="rotate(-90 52 52)" />
                      <text x="52" y="58" textAnchor="middle" fontSize="20" fontWeight="800" fill="#0A2A5C">
                        {tauxSeance} %
                      </text>
                    </svg>
                    <div className="pqr-mini-stats">
                      <div className="pqr-mini-stat"><div className="v">{emargement.effectif ?? 0}</div><div className="l">Attendus</div></div>
                      <div className="pqr-mini-stat"><div className="v">{emargement.presents}</div><div className="l">Présents ({emargement.retards} retard(s))</div></div>
                      <div className="pqr-mini-stat"><div className="v">{emargement.presencesManuelles}</div><div className="l">Présences manuelles</div></div>
                      <div className="pqr-mini-stat"><div className="v">{emargement.anomaliesGps}</div><div className="l">Anomalies GPS</div></div>
                    </div>
                  </div>
                  <div className="mt-3">
                    <div className="d-flex justify-content-between" style={{ fontSize: '.85rem' }}>
                      <span className="text-muted">Badgeage QR automatique</span><strong>{nbQr}</strong>
                    </div>
                    <div className="pqr-barre pqr-barre-degradee my-1">
                      <div className="pqr-barre-remplissage"
                           style={{ width: `${nbPointes ? (nbQr / nbPointes) * 100 : 0}%` }} />
                    </div>
                    <div className="d-flex justify-content-between" style={{ fontSize: '.85rem' }}>
                      <span className="text-muted">Émargement manuel motivé</span><strong>{nbManuel}</strong>
                    </div>
                    <div className="pqr-barre pqr-barre-or my-1">
                      <div className="pqr-barre-remplissage"
                           style={{ width: `${nbPointes ? (nbManuel / nbPointes) * 100 : 0}%` }} />
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* ── Colonne droite : liste d’émargement ────────────────── */}
          <div>
            {emargement ? (
              <div className="pqr-panel pqr-entree" style={{ animationDelay: '.14s' }}>
                <div className="pqr-panel-tete" style={{ flexWrap: 'wrap' }}>
                  <div>
                    <div className="pqr-surtitre">{selection.groupe_libelle || 'Séance'} · Liste nominative</div>
                    <h2 className="pqr-panel-titre">Liste d’émargement — {selection.intitule}</h2>
                  </div>
                  <span className="d-flex gap-2 align-items-center flex-wrap">
                    <span className="badge badge-bg-secondary">{emargement.presents}/{emargement.effectif} présents</span>
                    {emargement.presencesManuelles > 0 && (
                      <span className="badge badge-bg-warning" title="Présences issues d'un badgeage manuel (émargement)">
                        {emargement.presencesManuelles} manuelle(s)
                      </span>
                    )}
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
                <div className="pqr-panel-corps py-2 d-flex gap-2 flex-wrap align-items-center">
                  <input type="search" className="input" style={{ maxWidth: 240 }}
                         placeholder="Nom ou matricule…"
                         aria-label="Rechercher un étudiant"
                         value={recherchePresence}
                         onChange={(e) => setRecherchePresence(e.target.value)} />
                  <div className="pqr-segmente" role="tablist" aria-label="Filtrer les présences">
                    {[['tous', 'Tous'], ['present', 'Présents'], ['absent', 'Absents'], ['manuel', 'Manuels']]
                      .map(([valeur, libelle]) => (
                        <button key={valeur} type="button"
                                className={filtrePresence === valeur ? 'actif' : ''}
                                onClick={() => setFiltrePresence(valeur)}>
                          {libelle}
                        </button>
                      ))}
                  </div>
                  <span className="text-muted ms-auto" style={{ fontSize: '.85rem' }}>
                    {lignesAffichees.length} étudiant(s) affiché(s)
                  </span>
                </div>
                <div className="table-container">
                  <table className="table edt-table mb-0">
                    <thead>
                      <tr><th>Étudiant</th><th>Badge QR</th><th>Canal</th><th>Statut séance</th><th>Forçage tracé</th><th /></tr>
                    </thead>
                    <tbody>
                      {lignesAffichees.map((l) => (
                        <tr key={l.participant}>
                          <td>
                            <span className="d-inline-flex align-items-center gap-2">
                              <AvatarParticipant nom={l.nom} matricule={l.matricule} />
                              <span><strong>{l.nom}</strong> <small className="text-muted">{l.matricule}</small></span>
                            </span>
                          </td>
                          <td>{badgeEntree(l)}</td>
                          <td>{badgeCanal(l)}</td>
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
                          <td className="text-end">
                            <button className="btn btn-outline-secondary btn-sm"
                                    onClick={() => setBadgeageManuel(l)}
                                    title="Badger manuellement ce participant (motif obligatoire, tracé)">
                              <i className="bi bi-pencil-square me-1"></i>Badger
                            </button>
                          </td>
                        </tr>
                      ))}
                      {emargement.lignes.length === 0 && (
                        <tr><td colSpan={6} className="text-center text-muted py-4">
                          Séance sans groupe rattaché — rattachez un groupe dans l’EDT pour émarger.
                        </td></tr>
                      )}
                      {emargement.lignes.length > 0 && lignesAffichees.length === 0 && (
                        <tr><td colSpan={6} className="text-center text-muted py-4">
                          Aucun étudiant ne correspond au filtre.
                        </td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
                {emargement.lignes.length > 0 && (
                  <div className="pqr-panel-corps d-flex align-items-end gap-2">
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
                <p className="pqr-legende">
                  Le canal est toujours identifiable : <strong>QR automatique</strong> (serveur) ou
                  <strong> manuel motivé et audité</strong>. Aucune présence n’est validée par le navigateur.
                </p>
              </div>
            ) : (
              <div className="pqr-panel"><div className="loading py-5"><div className="spinner"></div></div></div>
            )}
          </div>
        </div>
      )}

      {qrOuvert && selection && (
        <ModalQR seance={selection} date={date} onClose={() => setQrOuvert(false)} />
      )}

      {badgeageManuel && selection && (
        <ModalBadgeageManuel
          seance={selection} date={date} ligne={badgeageManuel}
          onClose={() => setBadgeageManuel(null)}
          onSaved={(message) => { showToast(message); chargerEmargement() }}
        />
      )}
    </div>
  )
}
