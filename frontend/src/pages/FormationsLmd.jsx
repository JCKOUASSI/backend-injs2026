import React, { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../services/api'
import '../styles/candidatures.css'
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
    return (
      <p className="flmd-vide">
        <i className="bi bi-dash-circle" aria-hidden="true"></i>
        Aucun niveau LMD actif.
      </p>
    )
  }
  return (
    <div className="flmd-niveaux">
      {niveaux.map((n) => (
        <div key={n.id} className="flmd-niveau">
          <div className="flmd-niveau-head">
            <span className="flmd-niveau-code">{n.code}</span>
            <span className="flmd-niveau-libelle">{n.libelle}</span>
          </div>
          <div className="flmd-niveau-meta">
            <span className="flmd-puce flmd-puce--ects">
              <i className="bi bi-award" aria-hidden="true"></i>
              {n.credits_requis} ECTS
            </span>
            <span className="flmd-niveau-semestres">
              {n.semestres.map((s) => s.libelle).join(' / ') || 'aucun semestre'}
            </span>
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
        <i className="bi bi-dash-circle" aria-hidden="true"></i>
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
            <span className="flmd-puces">
              <span className="flmd-puce">
                <i className="bi bi-calendar3" aria-hidden="true"></i>
                {m.annee_academique}
              </span>
              <span className="flmd-puce flmd-puce--ghost">v{m.version}</span>
              <span className={`flmd-statut text-bg-secondary ${m.statut === 'ACTIVE' ? 'flmd-statut--active' : ''}`}>
                {m.statut}
              </span>
              <span className="flmd-puce flmd-puce--ects">
                <i className="bi bi-award" aria-hidden="true"></i>
                {m.total_credits} ECTS
              </span>
            </span>
          </div>
          {m.ues.length === 0 ? (
            <p className="flmd-vide flmd-vide--serre">
              <i className="bi bi-dash-circle" aria-hidden="true"></i>
              Aucune UE renseignée.
            </p>
          ) : (
            <ul className="flmd-ues">
              {m.ues.map((ue) => (
                <li key={ue.id} className="flmd-ue">
                  <div className="flmd-ue-ligne">
                    <span className="flmd-ue-code">UE {ue.code}</span>
                    <span className="flmd-ue-intitule">{ue.intitule}</span>
                    <span className="flmd-ue-credits">{ue.credits} ECTS</span>
                  </div>
                  {ue.ecues.length > 0 && (
                    <div className="flmd-ecues">
                      <span className="flmd-ecues-label">ECUE</span>
                      {ue.ecues.map((e) => (
                        <span key={e.id} className="flmd-puce flmd-puce--ghost">{e.code}</span>
                      ))}
                    </div>
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
      <div className="cand-page flmd-page">
        <section className="cand-panel" aria-live="polite">
          <div className="cand-chargement">
            <span className="spinner-border" role="status" aria-hidden="true"></span>
            Chargement du référentiel INJS…
          </div>
        </section>
      </div>
    )
  }

  if (erreur) {
    return (
      <div className="cand-page flmd-page">
        <div className="cand-alerte" role="alert">
          <i className="bi bi-exclamation-octagon" aria-hidden="true"></i>
          <span>{erreur}</span>
        </div>
      </div>
    )
  }

  if (!donnees) return null

  const integrite = donnees.integrite || {}

  return (
    <div className="cand-page flmd-page">
      {/* ── Bandeau du référentiel ── */}
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-diagram-3"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">
              <i className="bi bi-patch-check" aria-hidden="true"></i>
              Référentiel officiel validé
            </span>
            <h1 className="cand-hero-title">Formations LMD — référentiel officiel INJS</h1>
            <p className="cand-hero-sub">
              Source : {donnees.source} · {donnees.credits_par_semestre} ECTS/semestre ·{' '}
              {donnees.credits_par_niveau} ECTS/niveau
            </p>
          </div>
        </div>
        <div className="flmd-hero-pastilles">
          <span className="flmd-pastille flmd-pastille--primary">
            <i className="bi bi-check2-circle" aria-hidden="true"></i>
            {stats.filieresChargees}/{stats.filieresAttendues} filières chargées
          </span>
          <span className="flmd-pastille flmd-pastille--neutre">
            <i className="bi bi-mortarboard" aria-hidden="true"></i>
            {stats.cyclesInjs} cycles INJS
          </span>
        </div>
      </div>

      {/* ── Synthèse du périmètre ── */}
      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true">
            <i className="bi bi-diagram-3"></i>
          </span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.filieresChargees}/{stats.filieresAttendues}</span>
            <span className="cand-kpi-label">Filières chargées</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true">
            <i className="bi bi-mortarboard"></i>
          </span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.cyclesInjs}</span>
            <span className="cand-kpi-label">Cycles INJS</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true">
            <i className="bi bi-layers"></i>
          </span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.maquettes}</span>
            <span className="cand-kpi-label">Maquettes rattachées</span>
            <span className="flmd-kpi-sub">{stats.ues} UE au total</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true">
            <i className="bi bi-archive"></i>
          </span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.cyclesLegacy}</span>
            <span className="cand-kpi-label">Cycles legacy hors périmètre</span>
          </div>
        </div>
      </div>

      {integrite.cycles_etrangers_inclus?.length > 0 && (
        <div className="cand-alerte cand-alerte--attention" role="alert">
          <i className="bi bi-exclamation-triangle" aria-hidden="true"></i>
          <span>
            Cycles étrangers détectés dans le périmètre INJS :{' '}
            {integrite.cycles_etrangers_inclus.join(', ')}
          </span>
        </div>
      )}

      {/* ── Filtre du référentiel ── */}
      <section className="cand-panel" aria-labelledby="titre-filtre-referentiel">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-filtre-referentiel">
            <i className="bi bi-funnel" aria-hidden="true"></i>
            Filtrer le référentiel
          </h2>
          <span className="cand-count-pill">
            {filieres.length} / {donnees.filieres.length} filière
            {donnees.filieres.length > 1 ? 's' : ''}
          </span>
        </header>
        <div className="cand-panel-body">
          <div className="flmd-filtre">
            <div className="cand-champ flmd-champ-recherche">
              <label className="cand-etiquette" htmlFor="flmd-recherche">Filtrer une filière</label>
              <div className="cand-search flmd-recherche">
                <i className="bi bi-search" aria-hidden="true"></i>
                <input
                  id="flmd-recherche"
                  type="search"
                  className="cand-input"
                  placeholder="Filtrer une filière…"
                  value={recherche}
                  onChange={(e) => setRecherche(e.target.value)}
                  aria-label="Filtrer une filière"
                />
                {recherche && (
                  <button
                    type="button"
                    className="flmd-effacer"
                    onClick={() => setRecherche('')}
                    aria-label="Effacer la recherche"
                  >
                    <i className="bi bi-x-lg" aria-hidden="true"></i>
                  </button>
                )}
              </div>
            </div>
            <p className="flmd-aide">
              <i className="bi bi-info-circle" aria-hidden="true"></i>
              La recherche porte sur le code, le sigle, le libellé et l&apos;école de la
              filière. Cycles, niveaux, maquettes et UE proviennent du serveur :
              aucune donnée n&apos;est complétée par approximation.
            </p>
          </div>
        </div>
      </section>

      {filieres.length === 0 ? (
        <section className="cand-panel">
          <div className="cand-vide">
            <span className="cand-vide-icone" aria-hidden="true">
              <i className="bi bi-search"></i>
            </span>
            <p className="cand-vide-titre">Aucune filière trouvée</p>
            <p className="cand-vide-texte">
              Aucune filière ne correspond à « {recherche.trim()} ».
            </p>
          </div>
        </section>
      ) : filieres.map((f) => {
        const diplomes = f.diplomes_attestes || []
        return (
          <section key={f.code} className="cand-panel flmd-filiere" aria-labelledby={`titre-${f.code}`}>
            <header className="cand-panel-head flmd-filiere-head">
              <div className="flmd-filiere-identite">
                <span className="flmd-filiere-code" aria-hidden="true">{f.code}</span>
                <div className="flmd-filiere-texte">
                  <h2 className="cand-panel-title" id={`titre-${f.code}`}>
                    {f.libelle}
                  </h2>
                  <p className="flmd-filiere-sub">
                    {f.ecole}
                    {f.domaine ? ` · ${f.domaine}` : ''} · diplômes attestés :{' '}
                    {diplomes.join(', ') || 'non documentés'}
                  </p>
                </div>
              </div>
              <div className="flmd-chips">
                <span className="flmd-chip flmd-chip--sigle text-bg-info">{f.sigle}</span>
                <span className="flmd-chip flmd-chip--neutre">
                  <i className="bi bi-diagram-3" aria-hidden="true"></i>
                  {f.cycles.length} cycle{f.cycles.length > 1 ? 's' : ''}
                </span>
                {!f.chargee && (
                  <span className="flmd-chip flmd-chip--attention text-bg-warning">
                    <i className="bi bi-exclamation-circle" aria-hidden="true"></i>
                    filière déclarée, non chargée
                  </span>
                )}
              </div>
            </header>
            <div className="cand-panel-body">
              {f.cycles.length === 0 ? (
                <p className="flmd-vide flmd-vide--centre">
                  <i className="bi bi-inbox" aria-hidden="true"></i>
                  Aucun cycle enregistré pour cette filière.
                </p>
              ) : (
                <div className="flmd-body">
                  {f.cycles.map((c) => (
                    <article key={c.id} className="flmd-cycle">
                      <div className="flmd-cycle-head">
                        <h3 className="flmd-cycle-title">
                          <span className="flmd-cycle-puce" aria-hidden="true">
                            <i className="bi bi-mortarboard"></i>
                          </span>
                          <span className="flmd-cycle-intitule">{c.intitule}</span>
                          {c.type_diplome && (
                            <span className="flmd-chip flmd-chip--type">
                              {c.type_diplome}
                            </span>
                          )}
                        </h3>
                        <div className="flmd-cycle-meta">
                          <span className="flmd-puce">
                            <i className="bi bi-hourglass-split" aria-hidden="true"></i>
                            {c.duree_annees
                              ? `${c.duree_annees} an(s)`
                              : 'durée non documentée'}
                          </span>
                          {c.nb_semestres ? (
                            <span className="flmd-puce">
                              <i className="bi bi-calendar3" aria-hidden="true"></i>
                              {c.nb_semestres} semestres
                            </span>
                          ) : null}
                          {c.nb_credites ? (
                            <span className="flmd-puce flmd-puce--ects">
                              <i className="bi bi-award" aria-hidden="true"></i>
                              {c.nb_credites} ECTS
                            </span>
                          ) : null}
                          {c.source ? (
                            <span className="flmd-puce flmd-puce--ghost">
                              source : {c.source}
                            </span>
                          ) : null}
                        </div>
                      </div>

                      <div className="flmd-blocs">
                        <div className="flmd-bloc">
                          <span className="flmd-bloc-title">
                            <i className="bi bi-signpost-split" aria-hidden="true"></i>
                            Parcours
                          </span>
                          {c.parcours.length ? (
                            <ul className="flmd-parcours">
                              {c.parcours.map((p) => (
                                <li key={p.id} className="flmd-parcours-item">
                                  <span className="flmd-parcours-code">{p.code}</span>
                                  {p.intitule}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="flmd-vide">
                              <i className="bi bi-dash-circle" aria-hidden="true"></i>
                              Aucun parcours défini (à valider — aucun parcours n&apos;est
                              inventé).
                            </p>
                          )}
                        </div>

                        <div className="flmd-bloc">
                          <span className="flmd-bloc-title">
                            <i className="bi bi-bar-chart-steps" aria-hidden="true"></i>
                            Niveaux &amp; semestres
                          </span>
                          <BlocNiveaux niveaux={c.niveaux} />
                        </div>

                        <div className="flmd-bloc flmd-bloc--large">
                          <span className="flmd-bloc-title">
                            <i className="bi bi-layers" aria-hidden="true"></i>
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
        )
      })}
    </div>
  )
}
