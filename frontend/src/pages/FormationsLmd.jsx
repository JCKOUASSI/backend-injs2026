import React, { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../services/api'
import '../styles/campagnes.css'
import '../styles/formationsLmd.css'

/**
 * Formations LMD — écran du référentiel officiel INJS-LMD (lot L6).
 *
 * Affiche la chaîne
 *     FORMATIONS INJS → PARCOURS → NIVEAUX → SEMESTRES → MAQUETTES → UE → ECUE
 *
 * Source unique : `GET /api/formations/lmd/formations/`. La séparation entre le
 * référentiel INJS et le corpus legacy CPFAE/Sygepcpfae est appliquée **côté
 * serveur** (queryset `perimetre = INJS`) : cet écran n'applique aucun filtre
 * métier local, il rend ce que l'API retourne. Si une formation étrangère
 * parvenait à l'API, elle serait visible ici — c'est la traçabilité en bout de
 * chaîne, pas une protection supplémentaire.
 */

const ENDPOINT = '/formations/lmd/formations/'

function BlocNiveaux({ niveaux }) {
  if (!niveaux?.length) {
    return <p className="flmd-vide">Aucun niveau LMD actif.</p>
  }
  return (
    <div className="flmd-niveaux">
      {niveaux.map((n) => (
        <div key={n.id} className="flmd-niveau">
          <div className="flmd-niveau-head">
            <strong>{n.code}</strong> — {n.libelle}
          </div>
          <div className="flmd-niveau-meta">
            {n.credits_requis} ECTS ·{' '}
            {n.semestres.map((s) => s.libelle).join(' / ') || 'aucun semestre'}
          </div>
        </div>
      ))}
    </div>
  )
}

function BlocMaquettes({ maquettes }) {
  if (!maquettes?.length) {
    return (
      <p className="flmd-vide">
        Aucune maquette rattachée. Les UE/ECUE ne sont pas créés sans source
        officielle.
      </p>
    )
  }
  return (
    <ul className="flmd-maquettes">
      {maquettes.map((m) => (
        <li key={m.id} className="flmd-maquette">
          <div className="flmd-maquette-head">
            <span className="flmd-maquette-lib">{m.libelle}</span>
            <span className="flmd-chip">{m.annee_academique}</span>
            <span className="flmd-chip flmd-chip--ghost">v{m.version}</span>
            <span className="badge text-bg-secondary flmd-chip">{m.statut}</span>
            <span className="flmd-chip flmd-chip--blue">{m.total_credits} ECTS</span>
          </div>
          {m.ues.length === 0 ? (
            <div className="flmd-vide mt-2">Aucune UE renseignée.</div>
          ) : (
            <ul className="flmd-ues">
              {m.ues.map((ue) => (
                <li key={ue.id} className="flmd-ue">
                  <span className="flmd-ue-code">UE {ue.code}</span> — {ue.intitule} (
                  {ue.credits} ECTS)
                  {ue.ecues.length > 0 && (
                    <span className="flmd-ecues">
                      <span className="flmd-ecues-label">ECUE</span>
                      {ue.ecues.map((e) => (
                        <span key={e.id} className="flmd-chip flmd-chip--ghost">
                          {e.code}
                        </span>
                      ))}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  )
}

export default function FormationsLmd() {
  const [donnees, setDonnees] = useState(null)
  const [charge, setCharge] = useState(true)
  const [erreur, setErreur] = useState('')
  const [recherche, setRecherche] = useState('')

  const charger = useCallback(async () => {
    setCharge(true)
    setErreur('')
    try {
      const res = await api.get(ENDPOINT)
      setDonnees(res.data)
    } catch (e) {
      setErreur(
        e.response?.data?.error || 'Chargement du référentiel impossible.',
      )
    } finally {
      setCharge(false)
    }
  }, [])

  useEffect(() => {
    charger()
  }, [charger])

  const filieres = useMemo(() => {
    const liste = donnees?.filieres || []
    const q = recherche.trim().toUpperCase()
    if (!q) return liste
    return liste.filter((f) =>
      [f.code, f.sigle, f.libelle, f.ecole]
        .filter(Boolean)
        .some((v) => v.toUpperCase().includes(q)),
    )
  }, [donnees, recherche])

  // Synthèse du périmètre : nombres fournis par l'API et comptes dérivés du
  // référentiel reçu (aucun appel supplémentaire, aucune donnée inventée).
  const stats = useMemo(() => {
    const listeCycles = (donnees?.filieres || []).flatMap((f) => f.cycles || [])
    const listeMaquettes = listeCycles.flatMap((c) => c.maquettes || [])
    return {
      filieresChargees: donnees?.nb_filieres_chargees ?? 0,
      filieresAttendues: donnees?.nb_filieres_attendues ?? 0,
      cyclesInjs: donnees?.integrite?.nb_cycles_injs ?? 0,
      cyclesLegacy: donnees?.integrite?.nb_cycles_legacy ?? 0,
      maquettes: listeMaquettes.length,
      ues: listeMaquettes.reduce((total, m) => total + (m.ues?.length || 0), 0),
    }
  }, [donnees])

  if (charge) {
    return (
      <div className="container-fluid py-4 camp-page formations-lmd-container">
        <div className="card camp-panel">
          <div className="camp-panel-body text-center py-4">
            <div className="spinner-border spinner-border-sm text-primary me-2" role="status" />
            <span className="text-muted">Chargement du référentiel INJS…</span>
          </div>
        </div>
      </div>
    )
  }
  if (erreur) {
    return (
      <div className="container-fluid py-4 camp-page formations-lmd-container">
        <div className="alert alert-danger d-flex align-items-start gap-2">
          <i className="bi bi-exclamation-octagon-fill mt-1" aria-hidden="true"></i>
          <span>{erreur}</span>
        </div>
      </div>
    )
  }
  if (!donnees) return null

  const integrite = donnees.integrite || {}

  return (
    <div className="container-fluid py-4 camp-page formations-lmd-container">
      {/* ── Bandeau du référentiel ── */}
      <div className="camp-hero">
        <div className="camp-hero-text">
          <span className="plaquette plaquette-primary">
            <i className="bi bi-patch-check" aria-hidden="true"></i>
            Référentiel officiel validé
          </span>
          <h1 className="h4 mb-0 camp-hero-title">
            <i className="bi bi-diagram-3" aria-hidden="true"></i>
            Formations LMD — référentiel officiel INJS
          </h1>
          <p className="mb-0 camp-hero-sub">
            Source : {donnees.source} · {donnees.credits_par_semestre} ECTS/semestre ·{' '}
            {donnees.credits_par_niveau} ECTS/niveau
          </p>
        </div>
        <div className="camp-hero-side">
          <span className="plaquette plaquette-primary">
            <i className="bi bi-check2-circle" aria-hidden="true"></i>
            {stats.filieresChargees}/{stats.filieresAttendues} filières chargées
          </span>
          <span className="plaquette plaquette-soft">
            <i className="bi bi-mortarboard" aria-hidden="true"></i>
            {stats.cyclesInjs} cycles INJS
          </span>
        </div>
      </div>

      {/* ── Synthèse du périmètre ── */}
      <div className="camp-kpi-row">
        <div className="camp-kpi flmd-kpi">
          <div>
            <span className="camp-kpi-label">Filières chargées</span>
            <span className="camp-kpi-value">
              {stats.filieresChargees}/{stats.filieresAttendues}
            </span>
          </div>
          <div className="camp-kpi-icon is-blue">
            <i className="bi bi-diagram-3-fill" aria-hidden="true"></i>
          </div>
        </div>
        <div className="camp-kpi flmd-kpi">
          <div>
            <span className="camp-kpi-label">Cycles INJS</span>
            <span className="camp-kpi-value">{stats.cyclesInjs}</span>
          </div>
          <div className="camp-kpi-icon is-green">
            <i className="bi bi-mortarboard-fill" aria-hidden="true"></i>
          </div>
        </div>
        <div className="camp-kpi flmd-kpi">
          <div>
            <span className="camp-kpi-label">Maquettes rattachées</span>
            <span className="camp-kpi-value">{stats.maquettes}</span>
            <span className="flmd-kpi-sub">{stats.ues} UE au total</span>
          </div>
          <div className="camp-kpi-icon is-amber">
            <i className="bi bi-layers-fill" aria-hidden="true"></i>
          </div>
        </div>
        <div className="camp-kpi flmd-kpi">
          <div>
            <span className="camp-kpi-label">Cycles legacy hors périmètre</span>
            <span className="camp-kpi-value">{stats.cyclesLegacy}</span>
          </div>
          <div className="camp-kpi-icon is-slate">
            <i className="bi bi-archive-fill" aria-hidden="true"></i>
          </div>
        </div>
      </div>

      {integrite.cycles_etrangers_inclus?.length > 0 && (
        <div className="alert alert-warning d-flex align-items-start gap-2">
          <i className="bi bi-exclamation-triangle-fill mt-1" aria-hidden="true"></i>
          <span>
            Cycles étrangers détectés dans le périmètre INJS :{' '}
            {integrite.cycles_etrangers_inclus.join(', ')}
          </span>
        </div>
      )}

      {/* ── Filtre du référentiel ── */}
      <div className="card camp-panel">
        <div className="camp-panel-head">
          <h2 className="camp-panel-title">
            <i className="bi bi-funnel" aria-hidden="true"></i>
            Filtrer le référentiel
          </h2>
          <span className="camp-count-pill">
            {filieres.length} / {donnees.filieres.length} filière
            {donnees.filieres.length > 1 ? 's' : ''}
          </span>
        </div>
        <div className="card-body camp-panel-body">
          <div className="row g-3 align-items-end camp-form">
            <div className="col-md-5">
              <label className="form-label" htmlFor="flmd-recherche">Filtrer une filière</label>
              <div className="input-group flmd-search">
                <span className="input-group-text">
                  <i className="bi bi-search" aria-hidden="true"></i>
                </span>
                <input
                  id="flmd-recherche"
                  type="search"
                  className="form-control"
                  placeholder="Filtrer une filière…"
                  value={recherche}
                  onChange={(e) => setRecherche(e.target.value)}
                  aria-label="Filtrer une filière"
                />
                {recherche && (
                  <button
                    type="button"
                    className="btn btn-outline-secondary"
                    onClick={() => setRecherche('')}
                    aria-label="Effacer la recherche"
                  >
                    <i className="bi bi-x" aria-hidden="true"></i>
                  </button>
                )}
              </div>
            </div>
            <div className="col-md-7">
              <p className="form-text mb-0">
                La recherche porte sur le code, le sigle, le libellé et l'école de la
                filière. Cycles, niveaux, maquettes et UE proviennent du serveur :
                aucune donnée n'est complétée par approximation.
              </p>
            </div>
          </div>
        </div>
      </div>

      {filieres.length === 0 ? (
        <div className="card camp-panel">
          <div className="camp-empty">
            <i className="bi bi-search" aria-hidden="true"></i>
            Aucune filière ne correspond à « {recherche.trim()} ».
          </div>
        </div>
      ) : filieres.map((f) => (
        <section key={f.code} className="card camp-panel">
          <div className="camp-panel-head">
            <div className="flmd-filiere-head">
              <h2 className="camp-panel-title">
                <i className="bi bi-mortarboard" aria-hidden="true"></i>
                {f.code} — {f.libelle}
              </h2>
              <p className="flmd-filiere-sub">
                {f.ecole}
                {f.domaine ? ` · ${f.domaine}` : ''} · diplômes attestés :{' '}
                {f.diplomes_attestes.join(', ') || 'non documentés'}
              </p>
            </div>
            <div className="flmd-chips">
              <span className="badge text-bg-info flmd-chip">{f.sigle}</span>
              <span className="flmd-chip">
                {f.cycles.length} cycle{f.cycles.length > 1 ? 's' : ''}
              </span>
              {!f.chargee && (
                <span className="badge text-bg-warning flmd-chip">
                  filière déclarée, non chargée
                </span>
              )}
            </div>
          </div>
          <div className="card-body camp-panel-body">
            {f.cycles.length === 0 ? (
              <p className="flmd-vide">
                Aucun cycle enregistré pour cette filière.
              </p>
            ) : (
              <div className="flmd-body">
                {f.cycles.map((c) => (
                  <article key={c.id} className="flmd-cycle">
                    <div className="flmd-cycle-head">
                      <h3 className="flmd-cycle-title">
                        {c.intitule}
                        {c.type_diplome && (
                          <span className="badge bg-light text-dark border flmd-chip">
                            {c.type_diplome}
                          </span>
                        )}
                      </h3>
                      <div className="flmd-cycle-meta">
                        <span className="flmd-chip">
                          <i className="bi bi-hourglass-split" aria-hidden="true"></i>
                          {c.duree_annees
                            ? `${c.duree_annees} an(s)`
                            : 'durée non documentée'}
                        </span>
                        {c.nb_semestres ? (
                          <span className="flmd-chip">{c.nb_semestres} semestres</span>
                        ) : null}
                        {c.nb_credites ? (
                          <span className="flmd-chip flmd-chip--blue">
                            {c.nb_credites} ECTS
                          </span>
                        ) : null}
                        {c.source ? (
                          <span className="flmd-chip flmd-chip--ghost">
                            source : {c.source}
                          </span>
                        ) : null}
                      </div>
                    </div>

                    <div className="flmd-blocs">

                      <div className="flmd-bloc">
                        <span className="flmd-bloc-title">Parcours</span>
                        {c.parcours.length ? (
                          <ul className="flmd-parcours">
                            {c.parcours.map((p) => (
                              <li key={p.id} className="flmd-chip">
                                {p.code} — {p.intitule}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="flmd-vide">
                            Aucun parcours défini (à valider — aucun parcours n'est
                            inventé).
                          </p>
                        )}
                      </div>

                      <div className="flmd-bloc">
                        <span className="flmd-bloc-title">
                          Niveaux &amp; semestres
                        </span>
                        <BlocNiveaux niveaux={c.niveaux} />
                      </div>

                      <div className="flmd-bloc flmd-bloc--large">
                        <span className="flmd-bloc-title">
                          Maquettes · UE · ECUE
                        </span>
                        <BlocMaquettes maquettes={c.maquettes} />
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        </section>
      ))}
    </div>
  )
}
