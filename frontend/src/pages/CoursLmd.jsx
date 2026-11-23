import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../services/api'
import '../styles/coursLmd.css'

/**
 * Cours (LMD) — vue « Enseignement » du modèle fonctionnel 04 : la ligne de
 * cours = affectation pédagogique (ECUE × groupe × enseignant × type) jointe
 * au planning EDT, à l'effectif du groupe et aux séances réalisées (présences
 * du lot C). Lecture seule ; chemin /cours.
 *
 * Habillage « variante A — clair raffiné » (styles scopés `.cours-*` dans
 * `src/styles/coursLmd.css`) : hero à vignette, pipeline du modèle 04 en
 * chips, barre de filtres dédiée, panneau à filet d'ancrage, pastilles
 * d'état. La logique de chargement/filtrage est inchangée.
 */

const ENDPOINT = '/scolarite/pedagogie/cours/'
const TYPES = [
  { valeur: '', libelle: 'Tous types' },
  { valeur: 'CM', libelle: 'CM' },
  { valeur: 'TD', libelle: 'TD' },
  { valeur: 'TP', libelle: 'TP' },
]
const STATUTS = ['', 'PROPOSEE', 'VALIDEE', 'PLANIFIEE', 'REALISEE']

/** Étapes du modèle 04, reprises de l'introduction (libellés, pas de données). */
const ETAPES_MODELE = [
  'Année', 'Cycle', 'Niveau', 'Semestre', 'ECUE', 'Enseignant', 'Groupe', 'Séances',
]

/** Pastille d'état associée au statut d'une ligne de cours. */
const STATUT_CLASSE = {
  PROPOSEE: 'cours-statut--proposee',
  VALIDEE: 'cours-statut--validee',
  PLANIFIEE: 'cours-statut--planifiee',
  REALISEE: 'cours-statut--realisee',
}

/** Initiales de l'enseignant (avatar de colonne). */
const initiales = (nom) => String(nom).trim().split(/\s+/)
  .map((m) => m[0]).slice(0, 2).join('').toUpperCase()

function ProgressionSeances({ ligne }) {
  const planifiees = ligne.nb_seances_planifiees || 0
  const realisees = ligne.nb_seances_realisees || 0
  if (!planifiees) {
    return (
      <span className="cours-alert-pill" title="Aucun créneau EDT rattaché à ce groupe/cycle">
        <i className="bi bi-calendar-x" aria-hidden="true"></i>
        planification manquante
      </span>
    )
  }
  const ratio = Math.min(100, Math.round((realisees / planifiees) * 100))
  return (
    <div
      className="cours-prog"
      title={`${realisees} séance(s) réalisée(s) sur ${planifiees} planifiée(s)`}
    >
      <div className="cours-prog-labels">
        <small className="cours-prog-count">{realisees}/{planifiees}</small>
        <small className="cours-prog-pct">{ratio}%</small>
      </div>
      <div className="cours-prog-track">
        <div
          className={`cours-prog-fill${ratio >= 100 ? ' cours-prog-fill--done' : ''}`}
          style={{ width: `${ratio}%` }}
        />
      </div>
    </div>
  )
}

export default function CoursLmd() {
  const [lignes, setLignes] = useState([])
  const [charge, setCharge] = useState(true)
  const [erreur, setErreur] = useState('')
  const [filtres, setFiltres] = useState({ q: '', type: '', statut: '' })
  const [detail, setDetail] = useState(null)

  const charger = useCallback(async () => {
    setCharge(true)
    setErreur('')
    try {
      const params = new URLSearchParams()
      if (filtres.q.trim()) params.set('q', filtres.q.trim())
      if (filtres.type) params.set('type_enseignement', filtres.type)
      if (filtres.statut) params.set('statut', filtres.statut)
      const res = await api.get(`${ENDPOINT}?${params.toString()}`)
      const donnees = res.data || {}
      const liste = donnees.resultats || (Array.isArray(donnees) ? donnees : [])
      setLignes(liste)
      setDetail((d) => (d ? liste.find((l) => l.id === d.id) || null : null))
    } catch {
      setErreur('Erreur lors du chargement des enseignements.')
    } finally {
      setCharge(false)
    }
  }, [filtres.q, filtres.type, filtres.statut])

  useEffect(() => { charger() }, [charger])

  const stats = useMemo(() => {
    const avecPlanning = lignes.filter((l) => l.nb_seances_planifiees > 0)
    return {
      total: lignes.length,
      sansPlanning: lignes.length - avecPlanning.length,
      effectifTotal: lignes.reduce((acc, l) => acc + (l.effectif || 0), 0),
    }
  }, [lignes])

  const majFiltre = (cle) => (e) => setFiltres((f) => ({ ...f, [cle]: e.target.value }))
  const nbCriteres = [filtres.q.trim(), filtres.type, filtres.statut].filter(Boolean).length

  return (
    <div>
      {/* BANDEAU */}
      <div className="cours-hero">
        <span className="cours-hero-icon" aria-hidden="true"><i className="bi bi-journal-bookmark"></i></span>
        <div className="cours-hero-text">
          <span className="cours-hero-eyebrow">Modèle 04 · Enseignement</span>
          <h1 className="cours-hero-title">Cours (LMD)</h1>
          <p className="cours-hero-intro">
            Ligne de cours = affectation pédagogique (ECUE × groupe × enseignant × type) jointe au
            planning EDT, à l’effectif du groupe et aux séances réalisées (QR / émargement).
          </p>
          <ol className="cours-pipeline" aria-label="Chaîne du modèle fonctionnel 04">
            {ETAPES_MODELE.map((etape, i) => (
              <React.Fragment key={etape}>
                {i > 0 && <li className="cours-pipeline-sep" aria-hidden="true">→</li>}
                <li className="cours-pipeline-step">{etape}</li>
              </React.Fragment>
            ))}
          </ol>
        </div>
        <div className="cours-hero-side">
          {lignes[0]?.annee && (
            <span className="cours-plaquette">
              <i className="bi bi-calendar3" aria-hidden="true"></i>
              {lignes[0].annee}
            </span>
          )}
          <span className="cours-plaquette cours-plaquette--soft">
            <i className="bi bi-eye" aria-hidden="true"></i>
            Lecture seule
          </span>
        </div>
      </div>

      {erreur && <div className="error-message cours-error">{erreur}</div>}

      {/* FILTRES */}
      <div className="cours-toolbar">
        <div className="cours-toolbar-head">
          <h2 className="cours-toolbar-title">
            <i className="bi bi-funnel" aria-hidden="true"></i>Filtres et recherche
          </h2>
          <span className={`cours-count-pill${nbCriteres === 0 ? ' cours-count-pill--muted' : ''}`}>
            {nbCriteres === 0
              ? 'Aucun critère'
              : `${nbCriteres} critère${nbCriteres > 1 ? 's' : ''} actif${nbCriteres > 1 ? 's' : ''}`}
          </span>
        </div>
        <div className="cours-toolbar-body">
          <div className="cours-field cours-field--recherche">
            <label className="cours-field-label" htmlFor="cours-recherche">Rechercher</label>
            <div className="cours-search">
              <i className="bi bi-search" aria-hidden="true"></i>
              <input
                id="cours-recherche"
                className="cours-input"
                type="search"
                placeholder="Rechercher ECUE, enseignant, groupe…"
                value={filtres.q}
                onChange={majFiltre('q')}
              />
            </div>
          </div>
          <div className="cours-field cours-field--filtre">
            <label className="cours-field-label" htmlFor="cours-type">Type d'enseignement</label>
            <select id="cours-type" className="cours-input cours-select" value={filtres.type} onChange={majFiltre('type')}>
              {TYPES.map((t) => <option key={t.valeur} value={t.valeur}>{t.libelle}</option>)}
            </select>
          </div>
          <div className="cours-field cours-field--filtre">
            <label className="cours-field-label" htmlFor="cours-statut">Statut</label>
            <select id="cours-statut" className="cours-input cours-select" value={filtres.statut} onChange={majFiltre('statut')}>
              {STATUTS.map((st) => <option key={st || 'tous'} value={st}>{st || 'Tous statuts'}</option>)}
            </select>
          </div>
          {nbCriteres > 0 && (
            <div className="cours-toolbar-actions">
              <button
                type="button"
                className="btn btn-outline-secondary btn-sm"
                onClick={() => setFiltres({ q: '', type: '', statut: '' })}
              >
                <i className="bi bi-arrow-counterclockwise" aria-hidden="true"></i>
                Réinitialiser
              </button>
            </div>
          )}
        </div>
      </div>

      {/* RÉSULTATS */}
      <div className="card cours-panel">
        <div className="card-header-bar cours-panel-head">
          <h2 className="cours-panel-title">
            <i className="bi bi-list-ul" aria-hidden="true"></i>Enseignements de l'année courante
          </h2>
          <span className="cours-count-group">
            <span className="cours-count-pill">{stats.total} ligne(s)</span>
            {stats.sansPlanning > 0 && (
              <span className="cours-count-pill cours-count-pill--warn" title="Créneaux EDT à publier pour ces groupes">{stats.sansPlanning} sans planning</span>
            )}
            <span className="cours-count-pill cours-count-pill--muted">{stats.effectifTotal} étudiant(s)</span>
            <button
              type="button"
              className="btn cours-refresh"
              onClick={charger}
              title="Recharger depuis le serveur"
              aria-label="Recharger depuis le serveur"
            >
              <i className={`bi bi-arrow-clockwise${charge ? ' spin' : ''}`}></i>
            </button>
          </span>
        </div>
        <div className="card-body-flush">
          {charge ? (
            <div className="cours-state cours-state--loading" role="status">
              <div className="loading"><div className="spinner"></div></div>
              <span className="cours-state-text">Chargement des enseignements…</span>
            </div>
          ) : lignes.length === 0 ? (
            <div className="cours-state">
              <i className="bi bi-journal-x cours-state-icon" aria-hidden="true"></i>
              <span className="cours-state-title">Aucun enseignement</span>
              <span className="cours-state-text">
                Aucun enseignement pour ce filtre — chargez les affectations pédagogiques
                (charge par groupe) et publiez l'EDT.
              </span>
            </div>
          ) : (
            <div className="table-container">
              <table className="table cours-table">
                <thead>
                  <tr>
                    <th>ECUE</th><th>Type</th><th>Groupe</th><th>Enseignant</th>
                    <th>Planning</th><th>Effectif</th><th>Séances</th><th>Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {lignes.map((l) => (
                    <tr
                      key={l.id}
                      className={`cours-row${detail?.id === l.id ? ' cours-row--active' : ''}`}
                      onClick={() => setDetail(l)}
                    >
                      <td>
                        <span className="cours-code">{l.ecue}</span>
                        <span className="cours-intitule">{l.ecue_intitule}</span>
                        <small className="cours-cursus">{l.cycle || 'cycle non rattaché'} · {l.niveau} · {l.semestre}</small>
                      </td>
                      <td><span className={`cours-type cours-type--${String(l.type_enseignement || '').toLowerCase()}`}>{l.type_enseignement}</span></td>
                      <td>{l.groupe_nom ? <span className="cours-chip">{l.groupe_nom}</span> : <span className="text-muted">—</span>}</td>
                      <td>
                        {l.enseignant ? (
                          <span className="cours-teacher">
                            <span className="cours-avatar" aria-hidden="true">{initiales(l.enseignant)}</span>
                            <span>{l.enseignant}</span>
                          </span>
                        ) : <em className="text-muted">à désigner</em>}
                      </td>
                      <td>
                        {l.planning?.length ? (
                          <span className="cours-planif">
                            {l.planning.map((c) => (
                              <span className="cours-chip" key={`${l.id}-${c.id}`}>
                                {c.jour} {c.horaire}{c.salle ? ` · ${c.salle}` : ''}
                              </span>
                            ))}
                          </span>
                        ) : <span className="text-muted">—</span>}
                      </td>
                      <td className={`cours-effectif${l.capacite_max && l.effectif >= l.capacite_max * 0.9 ? ' cours-effectif--full' : ''}`}>
                        <span className="cours-effectif-val">{l.effectif ?? '—'}</span>
                        {l.capacite_max ? <span className="cours-effectif-max">/{l.capacite_max}</span> : null}
                      </td>
                      <td><ProgressionSeances ligne={l} /></td>
                      <td><span className={`cours-statut ${STATUT_CLASSE[l.statut] || ''}`}>{l.statut}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {detail && (
        <div className="card cours-detail">
          <div className="card-header-bar cours-detail-head">
            <span className="cours-detail-title">
              <i className="bi bi-eye" aria-hidden="true"></i>
              Détail — {detail.ecue} {detail.ecue_intitule} ({detail.groupe_nom || 'sans groupe'})
            </span>
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setDetail(null)}>Fermer</button>
          </div>
          <div className="card-body cours-detail-body">
            <div className="row">
              <div className="col-md-6">
                <dl className="cours-deflist">
                  <div className="cours-deflist-item">
                    <dt>Cursus</dt>
                    <dd>{detail.annee} · {detail.cycle || '—'}{detail.parcours ? ` · ${detail.parcours}` : ''}</dd>
                  </div>
                  <div className="cours-deflist-item">
                    <dt>Position</dt>
                    <dd>{detail.niveau} · {detail.semestre} · {detail.ue}</dd>
                  </div>
                  <div className="cours-deflist-item">
                    <dt>Volume</dt>
                    <dd>{detail.volume_horaire} h — {detail.credits ?? '—'} crédits</dd>
                  </div>
                  <div className="cours-deflist-item">
                    <dt>Enseignant</dt>
                    <dd>{detail.enseignant || 'à désigner'}</dd>
                  </div>
                  <div className="cours-deflist-item">
                    <dt>Dates</dt>
                    <dd>{detail.dates?.debut || '—'} → {detail.dates?.fin || '—'}</dd>
                  </div>
                </dl>
              </div>
              <div className="col-md-6">
                <h6 className="cours-detail-subtitle">
                  <i className="bi bi-calendar-week" aria-hidden="true"></i>Séances planifiées (EDT)
                </h6>
                {!detail.planning?.length && <div className="text-muted small">Aucun créneau publié pour ce groupe/cycle.</div>}
                <ul className="cours-timeline">
                  {(detail.planning || []).map((c) => (
                    <li key={`${c.id}-${c.jour}`}>
                      <span className="cours-chip cours-chip--day">{c.jour} {c.horaire}</span>
                      <small className="text-muted">{c.salle || 'salle à préciser'} · {c.nature} · {c.semaines}</small>
                      <Link className="btn btn-outline-secondary btn-sm" to={`/edt/presences?seance=${c.id}`}>
                        <i className="bi bi-check2-square me-1"></i>Présences
                      </Link>
                    </li>
                  ))}
                </ul>
                <ProgressionSeances ligne={detail} />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
