import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { formatHeure, messageErreur } from './commun'
import '../../styles/presences.css'

/**
 * Hub « Présences QR » — tableau de bord, design « Nuit INJS Premium ».
 *
 * Bandeau nuit académique (chiffres héros), plaquettes « verre dépoli »,
 * accent doré, contenu clair : séances du jour, anomalies, répartition
 * par population et retard moyen en anneau. Chaque chiffre vient du
 * serveur (supervision des séances LMD du jour + journal d'audit pour
 * heartbeat et derniers pointages) ; aucun taux n'est calculé sur un
 * effectif indéterminable. Terminologie INJS : Étudiants, Enseignants,
 * « En Salle/Espace maintenant ».
 */

const MODULES = [
  { chemin: '/presences/seances', icone: 'bi-broadcast', titre: 'Séances',
    desc: 'Séances LMD du jour en direct : statut, QR, présents, anomalies.' },
  { chemin: '/presences/poste', icone: 'bi-phone', titre: 'Badgeage',
    desc: 'Terminal web : géolocalisation, badgeage, heartbeat et sortie.' },
  { chemin: '/presences/registre', icone: 'bi-journal-check', titre: 'Présences',
    desc: 'Registre historique : entrées, sorties, modes, verdicts de périmètre et exceptions.' },
  { chemin: '/presences/audit', icone: 'bi-clock-history', titre: 'Audit',
    desc: 'Journal d’audit : événements de badgeage et interventions tracées.' },
  { chemin: '/presences/configuration', icone: 'bi-geo-alt', titre: 'Configuration',
    desc: 'Géofence : sites, coordonnées et rayons de périmètre autorisés.' },
  { chemin: '/presences/contrat', icone: 'bi-file-earmark-code', titre: 'Contrat API',
    desc: 'Endpoints, codes d’erreur normalisés et règles d’intégration.' },
  { chemin: '/rattrapages', icone: 'bi-arrow-repeat', titre: 'Rattrapages',
    desc: 'Rattrapages de présence inter-cohorte.' },
]

const STATUTS_DEBUTES = ['EN_COURS', 'TERMINEE', 'CLOTUREE']
const STATUTS_A_VENIR = ['A_VENIR', 'PLANIFIEE', 'PUBLIEE']
const TON_STATUT = {
  EN_COURS: 'text-bg-success', TERMINEE: 'text-bg-secondary', CLOTUREE: 'text-bg-secondary',
  A_VENIR: 'text-bg-info', PLANIFIEE: 'text-bg-info', ANNULEE: 'text-bg-danger',
  PUBLIEE: 'text-bg-primary',
}

function dureeMinutes(s) {
  const m = Math.round((new Date(s.fin) - new Date(s.debut)) / 60000)
  return Number.isFinite(m) && m > 0 ? m : 0
}
function formatHeures(minutes) {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m ? `${h}h${String(m).padStart(2, '0')}` : `${h}h`
}
function Barre({ valeur, max, variante = '' }) {
  const pct = max > 0 ? Math.round((valeur / max) * 100) : 0
  return (
    <div className={`pqr-barre pqr-barre-degradee ${variante}`} role="progressbar"
         aria-valuenow={valeur} aria-valuemax={max}>
      <div className="pqr-barre-remplissage" style={{ width: `${pct}%` }} />
    </div>
  )
}

/** Anneau de progression (retard moyen, échelle 15 minutes). */
function AnneauRetard({ minutes }) {
  const R = 36
  const C = 2 * Math.PI * R
  const ratio = minutes === null ? 0 : Math.min(minutes / 15, 1)
  return (
    <svg width="86" height="86" viewBox="0 0 86 86" role="img"
         aria-label={minutes === null ? 'Aucun retard' : `Retard moyen ${minutes} minutes`}>
      <circle cx="43" cy="43" r={R} fill="none" stroke="#E3EDF7" strokeWidth="9" />
      <circle cx="43" cy="43" r={R} fill="none" stroke="#F5B544" strokeWidth="9"
              strokeLinecap="round" strokeDasharray={C}
              strokeDashoffset={C * (1 - ratio)} transform="rotate(-90 43 43)" />
      <text x="43" y="48" textAnchor="middle" fontSize="17" fontWeight="800" fill="#0A2A5C">
        {minutes === null ? '—' : String(minutes.toFixed(1)).replace('.', ',')}
      </text>
    </svg>
  )
}

export default function PresencesHub() {
  const [date, setDate] = useState(() => new Date().toLocaleDateString('en-CA'))
  const [donnees, setDonnees] = useState(null)
  const [heartbeats, setHeartbeats] = useState(null)
  const [derniers, setDerniers] = useState([])
  const [service, setService] = useState('TOUTES')
  const [charge, setCharge] = useState(true)
  const [erreur, setErreur] = useState('')

  const charger = useCallback(async () => {
    setCharge(true)
    setErreur('')
    try {
      const res = await api.get(`/presences/seances-edt/supervision/?date=${date}`)
      setDonnees(res.data)
    } catch (err) {
      setErreur(messageErreur(err, 'Supervision indisponible.'))
    } finally {
      setCharge(false)
    }
    try {
      const res = await api.get(`/audit-logs/?action=SCAN_HEARTBEAT&date_debut=${date}&date_fin=${date}`)
      setHeartbeats(res.data?.count ?? null)
    } catch {
      setHeartbeats(null)
    }
    try {
      const res = await api.get(`/audit-logs/?date_debut=${date}&date_fin=${date}`)
      setDerniers((res.data?.results || []).filter((l) => (l.action || '').startsWith('SCAN')).slice(0, 8))
    } catch {
      setDerniers([])
    }
  }, [date])

  useEffect(() => { charger() }, [charger])
  useEffect(() => { setService('TOUTES') }, [date])

  const seances = useMemo(() => donnees?.seances || [], [donnees])

  // Services académiques : formations réellement au programme du jour.
  // Sans formation présente, le bloc n'est pas affiché du tout.
  const services = useMemo(() => {
    const vus = new Map()
    for (const s of seances) {
      const cle = s.formation_libelle || s.parcours_libelle
      if (cle && !vus.has(cle)) vus.set(cle, cle)
    }
    return [...vus.values()]
  }, [seances])

  const lignes = useMemo(() => (service === 'TOUTES'
    ? seances
    : seances.filter((s) => (s.formation_libelle || s.parcours_libelle) === service)), [seances, service])

  const ag = useMemo(() => {
    const r = {
      total: lignes.length, enCours: 0, terminees: 0, aVenir: 0,
      presents: 0, attendus: 0, nonPointes: 0, absents: 0, retards: 0,
      manuels: 0, qrOuvertes: 0, enSalle: 0, pointages: 0,
      etudiants: 0, enseignants: 0, encadrants: 0,
      minutesPrevues: 0, minutesDemarrees: 0,
      retardSomme: 0, retardNb: 0, enseignantsAttendus: new Set(),
    }
    for (const s of lignes) {
      const p = s.presences || {}
      if (s.statut === 'EN_COURS') r.enCours += 1
      if (s.statut === 'TERMINEE' || s.statut === 'CLOTUREE') r.terminees += 1
      if (STATUTS_A_VENIR.includes(s.statut)) r.aVenir += 1
      r.presents += p.presents || 0
      r.retards += p.retards || 0
      r.absents += (p.absents_injustifies || 0) + (p.absents_justifies || 0)
      if (s.effectif_attendu) {
        r.attendus += s.effectif_attendu
        r.nonPointes += s.non_pointes || 0
      }
      r.manuels += p.source_manuelle || 0
      if (s.session_qr_ouverte) r.qrOuvertes += 1
      if (s.statut === 'EN_COURS') r.enSalle += p.en_salle || 0
      const pop = p.par_population || {}
      r.etudiants += pop.etudiants || 0
      r.enseignants += pop.enseignants || 0
      r.encadrants += pop.encadrants || 0
      const cleEns = s.formateur_id || s.enseignant_id || s.libelle
      if (cleEns) r.enseignantsAttendus.add(cleEns)
      const minutes = dureeMinutes(s)
      r.minutesPrevues += minutes
      if (STATUTS_DEBUTES.includes(s.statut)) r.minutesDemarrees += minutes
      if (p.entrees_en_retard && p.retard_moyen_min !== null && p.retard_moyen_min !== undefined) {
        r.retardNb += p.entrees_en_retard
        r.retardSomme += p.retard_moyen_min * p.entrees_en_retard
      }
    }
    r.pointages = r.etudiants + r.enseignants + r.encadrants
    r.taux = r.attendus > 0 ? Math.round((r.presents / r.attendus) * 100) : null
    r.retardMoyen = r.retardNb > 0 ? r.retardSomme / r.retardNb : null
    r.enseignantsAttendusNb = r.enseignantsAttendus.size
    return r
  }, [lignes])

  const anomalies = useMemo(() => lignes
    .filter((s) => s.effectif_attendu === null || s.effectif_attendu === undefined
      || (s.presences?.presences_hors_perimetre || 0) > 0)
    .map((s) => {
      const tags = []
      let alerte = false
      if (s.effectif_attendu === null || s.effectif_attendu === undefined) tags.push('SANS GROUPE')
      if ((s.presences?.presences_hors_perimetre || 0) > 0) {
        tags.push(`HORS PÉRIMÈTRE × ${s.presences.presences_hors_perimetre}`)
        alerte = true
      }
      return { seance: s, tags, alerte }
    }), [lignes])

  const prochaines = lignes
    .filter((s) => STATUTS_A_VENIR.includes(s.statut))
    .slice()
    .sort((a, b) => new Date(a.debut) - new Date(b.debut))
  const totalBadges = ag.pointages
  const parPopulation = [
    ['Étudiants', ag.etudiants, ag.attendus, ''],
    ['Enseignants', ag.enseignants, ag.enseignantsAttendusNb, 'pqr-barre-nuit'],
    ['Encadrants', ag.encadrants, Math.max(ag.encadrants, totalBadges ? 1 : 0), 'pqr-barre-or'],
  ]
  const pctVolume = ag.minutesPrevues > 0 ? Math.round((ag.minutesDemarrees / ag.minutesPrevues) * 100) : 0
  const dateLongue = new Date(`${date}T12:00:00`).toLocaleDateString('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  })
  const aujourdhui = new Date().toLocaleDateString('en-CA')
  const hier = new Date(Date.now() - 86400000).toLocaleDateString('en-CA')

  return (
    <div>
      {/* ── Bandeau nuit ─────────────────────────────────────────── */}
      <div className="pqr-hero2">
        <div className="d-flex flex-wrap justify-content-between align-items-start gap-3"
             style={{ position: 'relative', zIndex: 1 }}>
          <div style={{ maxWidth: 640 }}>
            <span className="pqr-hero-badge">
              <i className="bi bi-geo-alt me-1"></i>PRÉSENCES QR · GÉOLOCALISATION — INJS D’Abidjan, Marcory
            </span>
            <h1 className="pqr-hero-title">
              Présences QR code<br />et <span className="or">géolocalisation</span>
            </h1>
            <p className="pqr-hero-intro">
              Étudiants, enseignants et encadrants. Session QR temporaire, badgeage manuel
              motivé, heartbeat continu et contrôle de périmètre calculé côté serveur —
              le tout rattaché à la séance LMD publiée.
            </p>
          </div>
          <div className="d-flex flex-column gap-2 align-items-stretch">
            <input type="date" className="pqr-date-verre" aria-label="Journée de référence"
                   value={date} onChange={(e) => setDate(e.target.value)} />
            <div className="d-flex gap-2">
              <button className={`btn btn-sm ${date === aujourdhui ? 'pqr-btn-or' : 'pqr-btn-verre'}`}
                      onClick={() => setDate(aujourdhui)}>Aujourd’hui</button>
              <button className={`btn btn-sm ${date === hier ? 'pqr-btn-or' : 'pqr-btn-verre'}`}
                      onClick={() => setDate(hier)}>Hier</button>
              <button className="btn btn-sm pqr-btn-verre" onClick={charger}>
                <i className="bi bi-arrow-clockwise me-1"></i>Actualiser
              </button>
            </div>
            <Link to="/presences/poste" className="btn pqr-btn-or">
              <i className="bi bi-phone me-1"></i>Ouvrir le poste de badgeage
            </Link>
          </div>
        </div>

        <div className="pqr-hero-chiffres" style={{ position: 'relative', zIndex: 1 }}>
          <div>
            <div className="pqr-hero-chiffre-valeur">{charge ? '…' : (ag.taux === null ? '—' : `${ag.taux} %`)}</div>
            <div className="pqr-hero-chiffre-libelle">Taux de présence du jour</div>
          </div>
          <div>
            <div className="pqr-hero-chiffre-valeur">{charge ? '…' : `${ag.presents}/${ag.attendus}`}</div>
            <div className="pqr-hero-chiffre-libelle">Étudiants présents / attendus</div>
          </div>
          <div>
            <div className="pqr-hero-chiffre-valeur">{charge ? '…' : ag.qrOuvertes}</div>
            <div className="pqr-hero-chiffre-libelle">Sessions QR ouvertes</div>
          </div>
          <div>
            <div className="pqr-hero-chiffre-valeur">{charge ? '…' : ag.enSalle}</div>
            <div className="pqr-hero-chiffre-libelle">En Salle/Espace maintenant</div>
          </div>
        </div>
      </div>

      {/* ── Plaquettes verre ─────────────────────────────────────── */}
      <div className="pqr-plaqs-verre">
        <div className="pqr-plaq-verre">
          <div className="d-flex justify-content-between align-items-center">
            <span className="pqr-module-icone mb-0"><i className="bi bi-mortarboard"></i></span>
            <span className="badge text-bg-success">● En cours : {ag.enCours}</span>
          </div>
          <div className="pqr-chiffre-valeur mt-2">{charge ? '…' : ag.total}</div>
          <div className="pqr-chiffre-libelle">Cours du jour</div>
          <div className="pqr-chiffre-legende">{ag.enCours} en cours · {ag.terminees} terminés · {ag.aVenir} à venir</div>
        </div>
        <div className="pqr-plaq-verre">
          <div className="d-flex justify-content-between align-items-center">
            <span className="pqr-module-icone mb-0"><i className="bi bi-stopwatch"></i></span>
            <span className="badge text-bg-info">{pctVolume} %</span>
          </div>
          <div className="pqr-chiffre-valeur mt-2">
            {charge ? '…' : `${formatHeures(ag.minutesDemarrees)} / ${formatHeures(ag.minutesPrevues)}`}
          </div>
          <div className="pqr-chiffre-libelle">Volume horaire</div>
          <div className="pqr-chiffre-legende">Effectué / prévu sur la journée de référence</div>
        </div>
        <div className="pqr-plaq-verre">
          <div className="d-flex justify-content-between align-items-center">
            <span className="pqr-module-icone mb-0"><i className="bi bi-broadcast"></i></span>
            <span className="badge text-bg-success">Live</span>
          </div>
          <div className="pqr-chiffre-valeur mt-2" style={{ color: '#14663c' }}>
            {charge ? '…' : ag.pointages}
          </div>
          <div className="pqr-chiffre-libelle">Pointages du jour</div>
          <div className="pqr-chiffre-legende">
            {heartbeats === null
              ? `${ag.manuels} émargement(s) manuel(s) motivé(s)`
              : `dont ${heartbeats} signaux heartbeat · ${ag.manuels} manuel(s) motivé(s)`}
          </div>
        </div>
        <div className="pqr-plaq-verre">
          <div className="d-flex justify-content-between align-items-center">
            <span className="pqr-module-icone mb-0"><i className="bi bi-exclamation-triangle"></i></span>
            <span className="badge text-bg-danger">À traiter</span>
          </div>
          <div className="pqr-chiffre-valeur mt-2" style={{ color: '#B3372C' }}>
            {charge ? '…' : anomalies.length}
          </div>
          <div className="pqr-chiffre-libelle">Anomalies à contrôler</div>
          <div className="pqr-chiffre-legende">GPS, QR, effectifs indéterminés</div>
        </div>
      </div>

      {erreur && <div className="error-message">{erreur}</div>}

      {/* ── Services académiques (formations du jour uniquement) ── */}
      {services.length > 0 && (
        <div className="pqr-services-bande" aria-label="Services académiques">
          <span className="pqr-surtitre me-1"><i className="bi bi-building me-1"></i>Services académiques</span>
          <button className={`pqr-service-chip${service === 'TOUTES' ? ' actif' : ''}`}
                  onClick={() => setService('TOUTES')}>
            Toutes les formations
          </button>
          {services.map((nom) => (
            <button key={nom} className={`pqr-service-chip${service === nom ? ' actif' : ''}`}
                    onClick={() => setService(nom)}>
              {nom}
            </button>
          ))}
        </div>
      )}

      <div className="pqr-grille-premium">
        {/* Séances du jour */}
        <div>
          <div className="pqr-panel">
            <div className="pqr-panel-tete">
              <div>
                <div className="pqr-surtitre">{dateLongue}</div>
                <h2 className="pqr-panel-titre">Séances du jour</h2>
              </div>
              <Link className="lien" to="/presences/registre" style={{ color: '#1267D6', fontWeight: 700, fontSize: '.85rem' }}>
                Registre complet des séances →
              </Link>
            </div>
            <div className="table-container">
              <table className="table edt-table mb-0">
                <thead>
                  <tr><th>Horaire</th><th>ECUE / UE</th><th>Groupe</th><th>Enseignant</th><th>Présents</th><th>Statut</th></tr>
                </thead>
                <tbody>
                  {lignes.map((s) => (
                    <tr key={s.id}>
                      <td><code>{formatHeure(s.debut)} — {formatHeure(s.fin)}</code></td>
                      <td>
                        <Link className="fw-semibold text-decoration-none"
                              to={`/edt/presences?seance=${s.id}&date=${date}`}>
                          {s.ecue_code ? `${s.ecue_code} · ` : ''}{s.ecue_libelle || s.intitule || 'Séance'}
                        </Link>
                        <div className="caps text-muted" style={{ fontSize: '.72rem' }}>
                          {[s.ue_code, s.niveau_libelle, s.semestre_libelle, s.nature_libelle]
                            .filter(Boolean).join(' · ') || 'rattachement LMD non renseigné'}
                        </div>
                      </td>
                      <td>{s.groupe_libelle || <span className="text-danger">sans groupe</span>}</td>
                      <td>{s.libelle || '—'}</td>
                      <td>
                        {s.effectif_attendu === null || s.effectif_attendu === undefined
                          ? '—'
                          : <><strong className="text-success">{s.presences?.presents || 0}</strong>
                              <span className="text-muted">/{s.effectif_attendu}</span></>}
                      </td>
                      <td>
                        <span className={`badge ${TON_STATUT[s.statut] || 'text-bg-secondary'}`}>
                          {s.statut_libelle || s.statut}
                        </span>
                        {s.session_qr_ouverte && (
                          <span className="badge text-bg-primary ms-1" title="Session QR ouverte">QR</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {!charge && lignes.length === 0 && (
                    <tr><td colSpan={6} className="text-center text-muted py-4">
                      Aucune séance programmée pour cette date.
                    </td></tr>
                  )}
                  {charge && (
                    <tr><td colSpan={6} className="text-center py-4">
                      <div className="loading"><div className="spinner"></div></div>
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="pqr-panel-corps pt-0">
              <p className="pqr-legende">
                Une présence est toujours rattachée à une séance LMD publiée par GET INJS APP :
                jamais à un module hors référentiel, jamais à un créneau reconstitué.
              </p>
            </div>
          </div>

          {/* Présences du jour */}
          <div className="pqr-panel mt-3">
            <div className="pqr-panel-tete">
              <div>
                <div className="pqr-surtitre">Journée de référence</div>
                <h2 className="pqr-panel-titre">Présences du {date}</h2>
              </div>
              <span className="badge badge-bg-secondary">
                {ag.presents} présents · {ag.absents} absents · {ag.attendus} attendus
              </span>
            </div>
            <div className="pqr-panel-corps">
              <div className="pqr-barre-jour" role="img" aria-label="Répartition présents absents non pointés">
                {ag.attendus > 0 && (
                  <>
                    <div className="seg-presents" style={{ width: `${(ag.presents / ag.attendus) * 100}%` }} />
                    <div className="seg-absents" style={{ width: `${(ag.absents / ag.attendus) * 100}%` }} />
                  </>
                )}
              </div>
              <div className="d-flex flex-wrap gap-3 mt-2">
                <span><span className="pqr-point d-inline-block me-1" style={{ background: '#1D9E62' }}></span>
                  {ag.attendus ? Math.round((ag.presents / ag.attendus) * 100) : 0} % présents</span>
                <span><span className="pqr-point d-inline-block me-1" style={{ background: '#D45A4E' }}></span>
                  {ag.attendus ? Math.round((ag.absents / ag.attendus) * 100) : 0} % absents</span>
                <span className="text-muted">{ag.nonPointes} non pointés · {ag.retards} retard(s) · {ag.manuels} manuel(s)</span>
              </div>
            </div>
          </div>

          <div className="row g-3 mt-1">
            <div className="col-lg-5">
              <div className="pqr-panel h-100">
                <div className="pqr-panel-tete">
                  <div><div className="pqr-surtitre">À venir</div><h2 className="pqr-panel-titre">Prochaines séances</h2></div>
                </div>
                <div className="pqr-panel-corps py-2">
                  {prochaines.map((s) => (
                    <div key={s.id} className="pqr-cours-ligne">
                      <code>{formatHeure(s.debut)}</code>
                      <div style={{ minWidth: 0 }}>
                        <div className="fw-semibold text-truncate">{s.ecue_libelle || s.intitule || 'Séance'}</div>
                        <div className="caps text-muted" style={{ fontSize: '.72rem' }}>
                          {s.groupe_libelle || 'sans groupe'} · {s.salle_libelle || 'salle non renseignée'}
                        </div>
                      </div>
                    </div>
                  ))}
                  {prochaines.length === 0 && !charge && (
                    <p className="text-muted text-center py-3 mb-0">Plus aucune séance à venir ce jour.</p>
                  )}
                </div>
              </div>
            </div>
            <div className="col-lg-7">
              {derniers.length > 0 && (
                <div className="pqr-panel h-100">
                  <div className="pqr-panel-tete">
                    <div><div className="pqr-surtitre">Journal</div><h2 className="pqr-panel-titre">Derniers pointages</h2></div>
                  </div>
                  <div className="table-container">
                    <table className="table edt-table mb-0">
                      <thead><tr><th>Nom</th><th>Matricule</th><th>Événement</th><th>Heure</th></tr></thead>
                      <tbody>
                        {derniers.map((l) => (
                          <tr key={l.id}>
                            <td><strong>{l.cible_nom}</strong></td>
                            <td><small>{l.cible_numero}</small></td>
                            <td><span className="badge text-bg-primary">{l.action_label || l.action}</span></td>
                            <td><code>{new Date(l.timestamp).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</code></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Colonne de contrôle */}
        <div>
          <div className="pqr-panel">
            <div className="pqr-panel-tete">
              <div><div className="pqr-surtitre">Contrôle</div><h2 className="pqr-panel-titre">Anomalies détectées</h2></div>
              <span className="badge text-bg-warning">{anomalies.length}</span>
            </div>
            <div className="pqr-panel-corps py-2">
              {anomalies.map(({ seance: s, tags, alerte }) => (
                <div key={s.id} className="pqr-anomalie">
                  <span className={`pqr-point ${alerte ? 'alerte' : 'vigilance'}`} />
                  <div style={{ minWidth: 0 }}>
                    <div className="fw-semibold text-truncate">{s.ecue_libelle || s.intitule || 'Séance'}</div>
                    <div className="caps text-muted" style={{ fontSize: '.72rem' }}>
                      {s.groupe_libelle || 'sans groupe'} · {formatHeure(s.debut)}
                    </div>
                    <div className="mt-1 d-flex flex-wrap gap-1">
                      {tags.map((t) => (
                        <span key={t} className={`badge ${alerte ? 'text-bg-danger' : 'text-bg-warning'}`}>{t}</span>
                      ))}
                    </div>
                  </div>
                  <Link className="btn btn-outline-secondary btn-sm ms-auto"
                        to={`/presences/registre?seance=${s.id}&date=${date}`}>
                    Contrôler
                  </Link>
                </div>
              ))}
              {anomalies.length === 0 && !charge && (
                <p className="text-muted text-center py-3 mb-0">Aucune anomalie enregistrée.</p>
              )}
            </div>
          </div>

          <div className="pqr-panel mt-3">
            <div className="pqr-panel-tete">
              <div><div className="pqr-surtitre">Répartition</div><h2 className="pqr-panel-titre">Par type de participant</h2></div>
            </div>
            <div className="pqr-panel-corps">
              {parPopulation.map(([role, n, max, variante]) => (
                <div key={role} className="mb-3">
                  <div className="d-flex justify-content-between align-items-baseline mb-1">
                    <span className="caps fw-bold" style={{ fontSize: '.78rem' }}>{role}</span>
                    <small className="text-muted"><code>{n}/{max}</code> badgés</small>
                  </div>
                  <Barre valeur={n} max={max} variante={variante} />
                </div>
              ))}
              {totalBadges === 0 && (
                <p className="text-muted mb-0">Aucun pointage enregistré.</p>
              )}
              <p className="pqr-legende">
                L’étudiant est contrôlé par son inscription et son groupe, l’enseignant par
                son affectation pédagogique, l’encadrant par sa mission d’activité.
                Aucun rapprochement par nom.
              </p>
            </div>
          </div>

          <div className="pqr-panel mt-3">
            <div className="pqr-panel-tete">
              <div><div className="pqr-surtitre">Qualité opérationnelle</div><h2 className="pqr-panel-titre">Retard moyen</h2></div>
            </div>
            <div className="pqr-panel-corps">
              <div className="pqr-anneau-wrap2">
                <AnneauRetard minutes={charge ? null : ag.retardMoyen} />
                <div>
                  <strong>
                    {ag.retardMoyen === null
                      ? 'Aucun retard'
                      : `${String(ag.retardMoyen.toFixed(1)).replace('.', ',')} min de retard moyen d’entrée`}
                  </strong>
                  <br />
                  <span className="text-muted" style={{ fontSize: '.85rem' }}>
                    {ag.retardNb} entrée(s) en retard · début prévu → premier pointage,
                    journée de référence.
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <h2 className="h5 fw-bold mt-4 mb-3" style={{ color: '#0A2A5C' }}>Modules du hub</h2>
      <div className="pqr-modules">
        {MODULES.map((m) => (
          <Link key={m.chemin} to={m.chemin} className="pqr-module">
            <span className="pqr-module-icone"><i className={`bi ${m.icone}`}></i></span>
            <div className="pqr-module-titre">{m.titre}</div>
            <div className="pqr-module-desc">{m.desc}</div>
            <span className="pqr-module-lien">Ouvrir <i className="bi bi-arrow-right"></i></span>
          </Link>
        ))}
      </div>
    </div>
  )
}
