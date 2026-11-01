import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import '../../styles/candidatures.css'
import '../../styles/referentiels.css'

/**
 * Tableau de bord du module « Référentiels ».
 *
 * Tout est piloté par l'API `/referentiels/tableau-de-bord/`, elle-même générée
 * depuis le registre backend : aucune liste de référentiels n'est codée en dur
 * ici. Ajouter un référentiel côté serveur le fait apparaître immédiatement.
 */

const BADGE_FIABILITE = {
  OFFICIEL: { classes: 'ref-fiab ref-fiab--officiel', libelle: 'Officiel' },
  MODELISE: { classes: 'ref-fiab ref-fiab--modelise', libelle: 'Modélisé' },
  CADRAGE: { classes: 'ref-fiab ref-fiab--cadrage', libelle: 'Cadrage' },
  A_RENSEIGNER: { classes: 'ref-fiab ref-fiab--a-renseigner', libelle: 'À renseigner' },
}

function etatCompletude(entree) {
  if (entree.total === 0) {
    return { niveau: 'vide', libelle: 'Non renseigné', icone: 'bi-exclamation-circle' }
  }
  if (entree.a_renseigner === null) {
    return { niveau: 'partiel', libelle: 'Provenance non suivie', icone: 'bi-dash-circle' }
  }
  if (entree.a_renseigner === 0) {
    return { niveau: 'complet', libelle: 'Complet', icone: 'bi-check-circle' }
  }
  return {
    niveau: 'partiel',
    libelle: `${entree.a_renseigner} à renseigner`,
    icone: 'bi-exclamation-circle',
  }
}

export default function TableauDeBordReferentiels() {
  const [donnees, setDonnees] = useState(null)
  const [chargement, setChargement] = useState(true)
  const [erreur, setErreur] = useState('')
  const [recherche, setRecherche] = useState('')
  const [categorieActive, setCategorieActive] = useState('')

  const charger = useCallback(async () => {
    setChargement(true)
    setErreur('')
    try {
      const res = await api.get('/referentiels/tableau-de-bord/')
      setDonnees(res.data)
    } catch (e) {
      setErreur(
        e.response?.data?.detail
        || 'Chargement du tableau de bord des référentiels impossible.',
      )
    } finally {
      setChargement(false)
    }
  }, [])

  useEffect(() => {
    charger()
  }, [charger])

  const categories = useMemo(() => {
    const source = donnees?.categories || []
    const q = recherche.trim().toLowerCase()
    return source
      .filter((c) => !categorieActive || c.cle === categorieActive)
      .map((c) => ({
        ...c,
        entrees: q
          ? c.entrees.filter((e) => (
            e.libelle.toLowerCase().includes(q)
            || (e.description || '').toLowerCase().includes(q)
            || e.slug.includes(q)
          ))
          : c.entrees,
      }))
      .filter((c) => c.entrees.length > 0)
  }, [donnees, recherche, categorieActive])

  if (chargement) {
    return (
      <div className="cand-page ref-page">
        <section className="cand-panel" aria-live="polite">
          <div className="cand-chargement">
            <span className="spinner-border" role="status" aria-hidden="true"></span>
            Chargement des référentiels…
          </div>
        </section>
      </div>
    )
  }

  if (erreur) {
    return (
      <div className="cand-page ref-page">
        <div className="cand-alerte" role="alert">
          <i className="bi bi-exclamation-octagon" aria-hidden="true"></i>
          <span>{erreur}</span>
          <button type="button" className="cand-btn-fantome" onClick={charger}>
            Réessayer
          </button>
        </div>
      </div>
    )
  }

  const synthese = donnees?.synthese || {}

  return (
    <div className="cand-page ref-page">
      <header className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-sliders"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">
              <i className="bi bi-database-check" aria-hidden="true"></i>
              Source unique de vérité
            </span>
            <h1 className="cand-hero-title">Référentiels de l’INJS</h1>
            <p className="cand-hero-sub">
              Données officielles de l’établissement : écoles, filières, maquettes,
              lieux et nomenclatures pédagogiques.
            </p>
          </div>
        </div>
        <div className="ref-hero-pastilles">
          <span className="ref-pastille ref-pastille--primary">
            <i className="bi bi-collection" aria-hidden="true"></i>
            {synthese.nb_referentiels} référentiels
          </span>
          <span className="ref-pastille ref-pastille--neutre">
            <i className="bi bi-123" aria-hidden="true"></i>
            {synthese.nb_valeurs} valeurs
          </span>
        </div>
      </header>

      <div className="cand-kpi-row">
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-blue" aria-hidden="true">
            <i className="bi bi-collection"></i>
          </span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{synthese.nb_referentiels}</span>
            <span className="cand-kpi-label">Référentiels</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-green" aria-hidden="true">
            <i className="bi bi-list-ol"></i>
          </span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{synthese.nb_valeurs}</span>
            <span className="cand-kpi-label">Valeurs référencées</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-amber" aria-hidden="true">
            <i className="bi bi-exclamation-circle"></i>
          </span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">{synthese.nb_a_renseigner}</span>
            <span className="cand-kpi-label">À renseigner</span>
          </div>
        </div>
        <div className="cand-kpi">
          <span className="cand-kpi-icon is-slate" aria-hidden="true">
            <i className="bi bi-patch-check"></i>
          </span>
          <div className="cand-kpi-texte">
            <span className="cand-kpi-value">
              {synthese.taux_tracabilite === null || synthese.taux_tracabilite === undefined
                ? '—'
                : `${Math.round(synthese.taux_tracabilite * 100)} %`}
            </span>
            <span className="cand-kpi-label">Taux de traçabilité</span>
          </div>
        </div>
      </div>

      <section className="cand-panel">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title">
            <i className="bi bi-funnel" aria-hidden="true"></i>
            Explorer le catalogue
          </h2>
          <span className="cand-count-pill">
            {categories.reduce((total, c) => total + c.entrees.length, 0)} référentiel(s)
          </span>
        </header>
        <div className="cand-panel-body">
          <div className="ref-filtres">
            <div className="cand-champ ref-champ-recherche">
              <label className="cand-etiquette" htmlFor="ref-recherche">
                Rechercher un référentiel
              </label>
              <div className="cand-search">
                <i className="bi bi-search" aria-hidden="true"></i>
                <input
                  id="ref-recherche"
                  type="search"
                  className="cand-input"
                  placeholder="Filière, école, salle, décision…"
                  value={recherche}
                  onChange={(e) => setRecherche(e.target.value)}
                />
              </div>
            </div>
            <div className="ref-categories" role="tablist" aria-label="Catégories de référentiels">
              <button
                type="button"
                role="tab"
                aria-selected={categorieActive === ''}
                className={`ref-categorie-puce${categorieActive === '' ? ' is-active' : ''}`}
                onClick={() => setCategorieActive('')}
              >
                Toutes
              </button>
              {(donnees?.catalogue || []).map((c) => (
                <button
                  key={c.cle}
                  type="button"
                  role="tab"
                  aria-selected={categorieActive === c.cle}
                  className={`ref-categorie-puce${categorieActive === c.cle ? ' is-active' : ''}`}
                  onClick={() => setCategorieActive(c.cle)}
                >
                  <i className={`bi ${c.icone}`} aria-hidden="true"></i>
                  {c.libelle}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {categories.length === 0 && (
        <section className="cand-panel">
          <div className="cand-vide">
            <span className="cand-vide-icone" aria-hidden="true">
              <i className="bi bi-search"></i>
            </span>
            <p className="cand-vide-titre">Aucun référentiel trouvé</p>
            <p className="cand-vide-texte">
              Aucun référentiel ne correspond à « {recherche.trim()} ».
            </p>
          </div>
        </section>
      )}

      {categories.map((categorie) => (
        <section key={categorie.cle} className="ref-categorie" aria-labelledby={`cat-${categorie.cle}`}>
          <div className="ref-categorie-entete">
            <span className="ref-categorie-icone" aria-hidden="true">
              <i className={`bi ${categorie.icone}`}></i>
            </span>
            <div>
              <h2 className="ref-categorie-titre" id={`cat-${categorie.cle}`}>
                {categorie.libelle}
              </h2>
              <p className="ref-categorie-desc">{categorie.description}</p>
            </div>
          </div>
          <div className="ref-grille">
            {categorie.entrees.map((entree) => {
              const etat = etatCompletude(entree)
              return (
                <article key={entree.slug} className="ref-carte">
                  <header className="ref-carte-head">
                    <span className="ref-carte-icone" aria-hidden="true">
                      <i className={`bi ${entree.icone}`}></i>
                    </span>
                    <div className="ref-carte-titres">
                      <h3 className="ref-carte-titre">{entree.libelle}</h3>
                      <p className="ref-carte-desc">{entree.description}</p>
                    </div>
                  </header>
                  <div className="ref-carte-mesures">
                    <span className="ref-mesure">
                      <strong>{entree.total}</strong>
                      <span>valeur{entree.total > 1 ? 's' : ''}</span>
                    </span>
                    {entree.a_renseigner !== null && entree.a_renseigner > 0 && (
                      <span className="ref-mesure ref-mesure--alerte">
                        <strong>{entree.a_renseigner}</strong>
                        <span>à renseigner</span>
                      </span>
                    )}
                    {entree.archives > 0 && (
                      <span className="ref-mesure ref-mesure--douce">
                        <strong>{entree.archives}</strong>
                        <span>archivée(s)</span>
                      </span>
                    )}
                  </div>
                  <footer className="ref-carte-pied">
                    <span className={`ref-etat ref-etat--${etat.niveau}`}>
                      <i className={`bi ${etat.icone}`} aria-hidden="true"></i>
                      {etat.libelle}
                    </span>
                    {entree.editable ? (
                      <Link className="ref-lien" to={`/referentiels/gestion/${entree.slug}`}>
                        {entree.libelle_bouton || 'Gérer'}
                        <i className="bi bi-arrow-right" aria-hidden="true"></i>
                      </Link>
                    ) : entree.route_ui ? (
                      <Link
                        className={`ref-lien${entree.libelle_bouton ? '' : ' ref-lien--douce'}`}
                        to={entree.route_ui}
                      >
                        {entree.libelle_bouton || 'Consulter'}
                        <i className="bi bi-arrow-right" aria-hidden="true"></i>
                      </Link>
                    ) : (
                      // Aucun écran ne gère ce référentiel : plutôt qu'un lien
                      // vers une route inexistante, on l'annonce tel quel.
                      <span className="ref-etat ref-etat--neutre">
                        <i className="bi bi-file-earmark-text" aria-hidden="true"></i>
                        Sans écran dédié
                      </span>
                    )}
                  </footer>
                </article>
              )
            })}
          </div>
        </section>
      ))}

      <section className="cand-panel ref-note">
        <div className="cand-panel-body">
          <p className="ref-note-texte">
            <i className="bi bi-info-circle" aria-hidden="true"></i>
            Chaque valeur importée conserve le document qui l’atteste et son degré de
            fiabilité : <span className={BADGE_FIABILITE.OFFICIEL.classes}>Officiel</span>{' '}
            pour ce que la source affirme,{' '}
            <span className={BADGE_FIABILITE.MODELISE.classes}>Modélisé</span> pour les
            inventaires proposés par la source,{' '}
            <span className={BADGE_FIABILITE.CADRAGE.classes}>Cadrage</span> pour les
            catégories de travail et{' '}
            <span className={BADGE_FIABILITE.A_RENSEIGNER.classes}>À renseigner</span>{' '}
            lorsqu’aucune source ne fournit la valeur.
          </p>
        </div>
      </section>
    </div>
  )
}
