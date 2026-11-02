import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useToast } from '../../context/ToastContext'
import CompletudeBar from '../../components/scolarite/CompletudeBar'
import {
  getAnneeCourante,
  getEffectifsGroupes,
  getNonAffectesGroupes,
  getRefFormations,
  getRefScolarite,
  messageErreur,
  repartirGroupes,
} from '../../services/scolarite'
import '../../styles/candidatures.css'
import '../../styles/admissions.css'
import '../../styles/groupes.css'

/** Réponses API tantôt liste, tantôt objet paginé : toujours une liste. */
const enListe = (res) => {
  const data = res?.data
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.resultats)) return data.resultats
  if (Array.isArray(data?.results)) return data.results
  return []
}

export default function Groupes() {
  const { showToast } = useToast()
  const [annee, setAnnee] = useState(null)
  const [groupes, setGroupes] = useState([])
  const [formations, setFormations] = useState([])
  const [niveaux, setNiveaux] = useState([])
  const [filtres, setFiltres] = useState({ ref_formation_id: '', niveau_id: '', actif: '' })
  const [recherche, setRecherche] = useState('')
  const [nonAffectes, setNonAffectes] = useState(null)
  const [loading, setLoading] = useState(true)
  const [repartition, setRepartition] = useState(null)
  const [action, setAction] = useState(false)

  const charger = useCallback(async () => {
    setLoading(true)
    const params = { ...filtres }
    if (annee?.id) params.annee_academique_id = annee.id
    const propres = Object.fromEntries(
      Object.entries(params).filter(([, v]) => v !== ''),
    )
    try {
      const res = await getEffectifsGroupes(propres)
      setGroupes(enListe(res))
    } catch (err) {
      showToast(messageErreur(err, 'Chargement des groupes impossible'), 'error')
    } finally {
      setLoading(false)
    }
    // Étudiants validés encore sans groupe sur le même périmètre.
    try {
      const { actif, ...perimetre } = propres
      const res = await getNonAffectesGroupes(perimetre)
      setNonAffectes(typeof res.data?.non_affectes === 'number' ? res.data.non_affectes : null)
    } catch { setNonAffectes(null) }
  }, [filtres, annee, showToast])

  useEffect(() => {
    (async () => {
      const [anneeCourante, formationsRes, niveauxRes] = await Promise.all([
        getAnneeCourante().catch(() => null),
        getRefFormations().catch(() => ({ data: [] })),
        getRefScolarite('niveaux', { actif: 1 }).catch(() => ({ data: [] })),
      ])
      setAnnee(anneeCourante?.data?.annee ?? anneeCourante?.annee ?? anneeCourante)
      setFormations(enListe(formationsRes))
      setNiveaux(enListe(niveauxRes))
    })()
  }, [])

  useEffect(() => { charger() }, [charger])

  const repartir = async () => {
    if (!filtres.ref_formation_id || !filtres.niveau_id) {
      showToast('Choisissez une formation et un niveau avant de répartir', 'error')
      return
    }
    setAction(true)
    try {
      const res = await repartirGroupes({
        annee_academique_id: annee?.id,
        ref_formation_id: filtres.ref_formation_id,
        niveau_id: filtres.niveau_id,
      })
      setRepartition(res.data)
      showToast(`${res.data.affectations} étudiant(s) affecté(s)`)
      charger()
    } catch (err) {
      showToast(messageErreur(err, 'Répartition impossible'), 'error')
    } finally {
      setAction(false)
    }
  }

  /* Recherche locale sur le nom du groupe et la formation (liste complète
     déjà chargée : aucun aller-retour serveur nécessaire). */
  const groupesVisibles = useMemo(() => {
    const q = recherche.trim().toLowerCase()
    if (!q) return groupes
    return groupes.filter(
      (g) => g.nom.toLowerCase().includes(q)
        || (g.ref_formation || '').toLowerCase().includes(q),
    )
  }, [groupes, recherche])

  /* Regroupement par cohorte (formation × niveau), ordre d'apparition. */
  const cohortes = useMemo(() => {
    const parCohorte = new Map()
    for (const g of groupesVisibles) {
      const cle = `${g.ref_formation}|${g.niveau}`
      if (!parCohorte.has(cle)) {
        parCohorte.set(cle, { formation: g.ref_formation, niveau: g.niveau, groupes: [] })
      }
      parCohorte.get(cle).groupes.push(g)
    }
    return [...parCohorte.values()].map((c) => ({
      ...c,
      effectif: c.groupes.reduce((s, g) => s + g.effectif, 0),
    }))
  }, [groupesVisibles])

  const totalEffectif = useMemo(
    () => groupes.reduce((somme, g) => somme + g.effectif, 0),
    [groupes],
  )

  const stats = useMemo(() => {
    const totalGroupes = groupes.length
    const actifs = groupes.filter((g) => g.actif).length
    const avecCapacite = groupes.filter((g) => g.capacite_max)
    const tauxMoyen = avecCapacite.length
      ? Math.round(
          avecCapacite.reduce((acc, g) => acc + (g.effectif * 100) / g.capacite_max, 0) /
            avecCapacite.length,
        )
      : null
    return {
      totalGroupes,
      actifs,
      inactifs: totalGroupes - actifs,
      tauxMoyen,
      nbFormations: new Set(groupes.map((g) => g.ref_formation)).size,
      nbNiveaux: new Set(groupes.map((g) => g.niveau)).size,
      placesRestantes: groupes.reduce(
        (s, g) => s + (g.places_restantes ?? 0), 0),
    }
  }, [groupes])

  const tauxAffectation = nonAffectes === null
    ? null
    : Math.round((totalEffectif * 100) / Math.max(totalEffectif + nonAffectes, 1))

  /* Une répartition n'a de sens que sur un couple formation + niveau : le
     bouton reste donc désactivé tant que les deux ne sont pas choisis. */
  const peutRepartir = Boolean(filtres.ref_formation_id && filtres.niveau_id)
  const filtreActif = Boolean(filtres.ref_formation_id || filtres.niveau_id)
  const reinitialiser = () => {
    setFiltres({ ref_formation_id: '', niveau_id: '', actif: '' })
    setRecherche('')
  }

  return (
    <div className="cand-page">
      {/* ── Bandeau d'accueil, même matière que les autres écrans Scolarité ── */}
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-diagram-3"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">Scolarité — Groupes</span>
            <h1 className="cand-hero-title">Groupes pédagogiques</h1>
            <p className="cand-hero-sub">
              {annee ? `Année ${annee.libelle}` : 'Année courante non définie'}
              {' · '}{totalEffectif} étudiant(s) affecté(s) aux sections TD/TP
              {tauxAffectation !== null && ` (${tauxAffectation} % des inscrits validés)`}
            </p>
            <div className="grp-etapes" aria-label="Chaîne d’affectation">
              <span className="grp-etape">
                <i className="bi bi-person-badge" aria-hidden="true"></i> Inscription validée
              </span>
              <i className="bi bi-arrow-right grp-etape-fleche" aria-hidden="true"></i>
              <span className="grp-etape grp-etape--actuelle" aria-current="step">
                <i className="bi bi-diagram-3" aria-hidden="true"></i> Sections TD/TP
              </span>
              <i className="bi bi-arrow-right grp-etape-fleche" aria-hidden="true"></i>
              <span className="grp-etape">
                <i className="bi bi-calendar3" aria-hidden="true"></i> Emploi du temps
              </span>
            </div>
          </div>
        </div>
        <div className="grp-hero-actions">
          <button
            type="button"
            className="btn-premium-primary"
            disabled={action}
            onClick={repartir}
            title={peutRepartir
              ? 'Répartir les étudiants de la formation et du niveau choisis'
              : 'Choisissez une formation et un niveau dans les filtres'}
          >
            {action ? (
              <span className="spinner-border" role="status" aria-hidden="true"></span>
            ) : (
              <i className="bi bi-diagram-3" aria-hidden="true"></i>
            )}
            Répartir automatiquement
          </button>
        </div>
      </div>

      {/* ── Indicateurs ── */}
      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true"><i className="bi bi-grid-3x3-gap"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.totalGroupes}</span>
            <span className="cand-kpi-label">Total groupes</span>
            <span className="adm-kpi-sous">
              {stats.nbFormations} formation{stats.nbFormations > 1 ? 's' : ''} · {stats.nbNiveaux} niveau{stats.nbNiveaux > 1 ? 'x' : ''}
            </span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true"><i className="bi bi-person-check"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{totalEffectif.toLocaleString('fr-FR')}</span>
            <span className="cand-kpi-label">Étudiants affectés</span>
            <span className="adm-kpi-sous">
              {nonAffectes === null
                ? 'sections TD/TP'
                : nonAffectes > 0
                  ? `${nonAffectes} sans groupe`
                  : 'tous affectés'}
            </span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true"><i className="bi bi-pie-chart"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.tauxMoyen !== null ? `${stats.tauxMoyen}%` : '—'}</span>
            <span className="cand-kpi-label">Taux de remplissage</span>
            <span className="adm-kpi-sous">
              {stats.placesRestantes.toLocaleString('fr-FR')} place{stats.placesRestantes > 1 ? 's' : ''} restante{stats.placesRestantes > 1 ? 's' : ''}
            </span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true"><i className="bi bi-check2-circle"></i></span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{stats.actifs}</span>
            <span className="cand-kpi-label">Groupes actifs</span>
            <span className="adm-kpi-sous">
              {stats.inactifs} inactif{stats.inactifs > 1 ? 's' : ''}
            </span>
          </div>
        </div>
      </div>

      {nonAffectes > 0 && (
        <div className="cand-alerte cand-alerte--attention" role="status">
          <i className="bi bi-person-dash" aria-hidden="true"></i>
          <div>
            <strong>{nonAffectes} étudiant(s) validé(s) sans groupe</strong>
            <div className="grp-alerte-detail">
              {peutRepartir
                ? 'Lancez la répartition automatique pour les affecter aux sections de la cohorte choisie.'
                : 'Filtrez une formation et un niveau, puis lancez la répartition automatique.'}
            </div>
          </div>
        </div>
      )}

      <section className="cand-panel" aria-labelledby="titre-repartition-groupes">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-repartition-groupes">
            <i className="bi bi-list-check" aria-hidden="true"></i>Répartition par groupe
          </h2>
          <span className="cand-count-pill">
            {groupesVisibles.length} groupe{groupesVisibles.length > 1 ? 's' : ''}
          </span>
        </header>

        <div className="cand-panel-body">
          <div className="cand-filters grp-filtres">
            <div className="adm-recherche grp-recherche">
              <i className="bi bi-search" aria-hidden="true"></i>
              <input
                type="search"
                aria-label="Rechercher un groupe"
                placeholder="Rechercher un groupe (L1-G1…), une formation…"
                value={recherche}
                onChange={(e) => setRecherche(e.target.value)}
              />
            </div>
            <div className="grp-filtre">
              <label className="cand-etiquette" htmlFor="groupe-formation">Formation</label>
              <select
                id="groupe-formation"
                className="cand-filter-select"
                value={filtres.ref_formation_id}
                onChange={(e) => setFiltres({ ...filtres, ref_formation_id: e.target.value })}
              >
                <option value="">Toutes les formations</option>
                {formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
              </select>
            </div>
            <div className="grp-filtre">
              <label className="cand-etiquette" htmlFor="groupe-niveau">Niveau</label>
              <select
                id="groupe-niveau"
                className="cand-filter-select"
                value={filtres.niveau_id}
                onChange={(e) => setFiltres({ ...filtres, niveau_id: e.target.value })}
              >
                <option value="">Tous les niveaux</option>
                {niveaux.map((n) => <option key={n.id} value={n.id}>{n.code}</option>)}
              </select>
            </div>
            <div className="grp-filtre">
              <label className="cand-etiquette" htmlFor="groupe-etat">État</label>
              <select
                id="groupe-etat"
                className="cand-filter-select"
                value={filtres.actif}
                onChange={(e) => setFiltres({ ...filtres, actif: e.target.value })}
              >
                <option value="">Tous les états</option>
                <option value="1">Actifs</option>
                <option value="0">Inactifs</option>
              </select>
            </div>
            <button type="button" className="grp-btn-reinitialiser" onClick={reinitialiser}>
              <i className="bi bi-arrow-counterclockwise" aria-hidden="true"></i>
              Réinitialiser
            </button>
            <p className="grp-aide">
              <i className="bi bi-info-circle" aria-hidden="true"></i>
              {peutRepartir
                ? 'La répartition automatique utilise ces deux filtres.'
                : 'Choisissez une formation et un niveau pour activer la répartition automatique.'}
            </p>
          </div>

          {repartition?.echecs?.length > 0 && (
            <div className="cand-alerte cand-alerte--attention" role="alert">
              <i className="bi bi-exclamation-triangle" aria-hidden="true"></i>
              <div>
                <strong>{repartition.echecs.length} étudiant(s) non affecté(s)</strong>
                <div className="grp-alerte-detail">{repartition.echecs[0].motif}</div>
              </div>
            </div>
          )}

          {loading ? (
            <div className="cand-chargement">
              <span className="spinner-border" role="status" aria-hidden="true"></span>
              Chargement des groupes…
            </div>
          ) : (
            <>
              <div className="cand-table-wrap">
                <table className="cand-table cand-table--groupes">
                  <thead>
                    <tr>
                      <th scope="col">Groupe</th>
                      <th scope="col">Formation</th>
                      <th scope="col">Niveau</th>
                      <th scope="col">Effectif</th>
                      <th scope="col">Remplissage</th>
                      <th scope="col" className="cand-th-actions">État</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cohortes.map((cohorte) => (
                      <React.Fragment key={`${cohorte.formation}|${cohorte.niveau}`}>
                        <tr className="grp-cohorte">
                          <td colSpan={6}>
                            <span className="grp-cohorte-titre">
                              <i className="bi bi-mortarboard" aria-hidden="true"></i>
                              {cohorte.formation}
                            </span>
                            <span className="grp-cohorte-meta">
                              {cohorte.niveau} · {cohorte.groupes.length} groupe{cohorte.groupes.length > 1 ? 's' : ''} · {cohorte.effectif} étudiant{cohorte.effectif > 1 ? 's' : ''}
                            </span>
                          </td>
                        </tr>
                        {cohorte.groupes.map((g) => {
                          const taux = g.capacite_max
                            ? Math.round((g.effectif * 100) / g.capacite_max)
                            : null
                          return (
                            <tr key={g.id} className={g.actif ? undefined : 'grp-ligne--inactif'}>
                              <td>
                                <span className="grp-nom">
                                  <i className="bi bi-people" aria-hidden="true"></i>
                                  {g.nom}
                                </span>
                              </td>
                              <td className="cand-col-formation">
                                <span className="cand-texte-formation" title={g.ref_formation}>
                                  {g.ref_formation}
                                </span>
                              </td>
                              <td><span className="cand-badge-neutre">{g.niveau}</span></td>
                              <td className="cand-col-etroit">
                                <span className="grp-effectif">{g.effectif}</span>
                                {g.capacite_max ? (
                                  <span className="grp-effectif-cap"> / {g.capacite_max}</span>
                                ) : null}
                              </td>
                              <td>
                                {taux === null ? (
                                  <span className="cand-texte-doux">Sans limite</span>
                                ) : (
                                  <>
                                    <CompletudeBar
                                      validees={g.effectif}
                                      total={g.capacite_max}
                                      taux={taux}
                                    />
                                    <span className={`adm-meta ${g.places_restantes === 0 ? 'grp-complet' : ''}`}>
                                      {g.places_restantes === 0
                                        ? 'Complet'
                                        : `${g.places_restantes} place${g.places_restantes > 1 ? 's' : ''} restante${g.places_restantes > 1 ? 's' : ''}`}
                                    </span>
                                  </>
                                )}
                              </td>
                              <td className="cand-col-actions">
                                <span className={`grp-etat grp-etat--${g.actif ? 'actif' : 'inactif'}`}>
                                  <i className={`bi ${g.actif ? 'bi-check2-circle' : 'bi-dash-circle'}`} aria-hidden="true"></i>
                                  {g.actif ? 'Actif' : 'Inactif'}
                                </span>
                              </td>
                            </tr>
                          )
                        })}
                      </React.Fragment>
                    ))}
                    {groupesVisibles.length === 0 && (
                      <tr>
                        <td colSpan={6}>
                          <div className="cand-vide">
                            <span className="cand-vide-icone" aria-hidden="true">
                              <i className="bi bi-diagram-3"></i>
                            </span>
                            <p className="cand-vide-titre">Aucun groupe</p>
                            <p className="cand-vide-texte">
                              Aucun groupe défini pour les filtres sélectionnés.
                              {!filtreActif && !recherche && ' Choisissez une formation et un niveau, puis lancez la répartition automatique.'}
                            </p>
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <p className="cand-defile" aria-hidden="true">
                <i className="bi bi-arrow-left-right"></i>
                Faites défiler le tableau horizontalement
              </p>
            </>
          )}
        </div>
      </section>
    </div>
  )
}
