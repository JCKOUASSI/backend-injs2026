import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { useDebounce } from '../../hooks/useDebounce'
import '../../styles/candidatures.css'
import '../../styles/hub.css'

/**
 * Hub premium partagé des modules (tâche 34).
 *
 * Avant ce kit, ~31 sous-modules (Stages, Jurys, Finances étudiantes…)
 * s'affichaient en tableaux génériques bruts : en-têtes techniques, dates
 * ISO, statuts en codes, parfois branchés sur de mauvaises sources. Le hub
 * donne à chaque module une page unique à onglets (un par sous-module) :
 * bandeau, indicateurs réels, colonnes métier formatées (JJ/MM/AAAA,
 * montants FCFA, badges teintés), recherche, filtres et pagination
 * (serveur quand l'API pagine, cliente sinon).
 *
 * Configuration (par page fine du module) :
 *   titre, badge, icone, introduction
 *   statsEndpoint + tuiles(data) → [{ valeur, libelle, sub, icone, ton }]
 *   onglets: [{ id, libelle, icone, endpoint, colonnes, rechercheParam,
 *               filtres: [{ param, libelle, options }], note }]
 *   ongletInitial (selon la route du sous-module)
 * Formats de cellule : texte (défaut), date, datetime, nombre, montant,
 * badge (tons : { valeur: ton }), booleen, lienEtudiant (avec idCle).
 */

const formatNombre = (n) => Number(n || 0).toLocaleString('fr-FR')

const formatDate = (iso) => {
  if (!iso) return '—'
  const [annee, mois, jour] = String(iso).slice(0, 10).split('-')
  return annee && mois && jour ? `${jour}/${mois}/${annee}` : '—'
}

const formatDateHeure = (iso) => {
  if (!iso) return '—'
  const [datePart, heurePart = ''] = String(iso).split('T')
  const heure = heurePart.slice(0, 5)
  return `${formatDate(datePart)}${heure ? ` ${heure}` : ''}`
}

const formatMontant = (valeur) => {
  if (valeur === null || valeur === undefined || valeur === '') return '—'
  const nombre = Number(valeur)
  return Number.isNaN(nombre) ? '—' : `${formatNombre(nombre)} FCFA`
}

const TONS_DEFAUT = {
  VALIDEE: 'green', VALIDE: 'green', SIGNEE: 'green', TERMINEE: 'slate', TERMINE: 'slate',
  EN_COURS: 'blue', ACTIF: 'green', OUVERTE: 'blue', OUVERT: 'blue',
  BROUILLON: 'amber', SOUMISE: 'indigo', EN_ATTENTE: 'amber', PROPOSEE: 'amber',
  EN_INSTRUCTION: 'indigo', A_VALIDER: 'indigo', PLANIFIEE: 'cyan',
  REFUSEE: 'red', REFUSE: 'red', ANNULEE: 'slate', ANNULE: 'slate',
  SUSPENDUE: 'red', REJETEE: 'red', IMPAYE: 'red', EN_RETARD: 'red',
  PAYEE: 'green', PAYE: 'green', SOLDEE: 'green', PARTIEL: 'amber',
  RECU: 'blue', ENVOYE: 'cyan', ARCHIVEE: 'slate', ARCHIVE: 'slate',
  SOUTENUE: 'green', VALIDEE_JURY: 'green', ADMIS: 'green', AJOURNE: 'red',
  PRESENT: 'green', ABSENT: 'red', CONVOQUE: 'indigo',
  TRES_BIEN: 'green', BIEN: 'green', ASSEZ_BIEN: 'cyan', PASSABLE: 'amber',
  INSUFFISANT: 'red',
}

function Cellule({ colonne, ligne }) {
  const brut = ligne[colonne.cle]
  const affichable = colonne.texte ? colonne.texte(ligne) : brut
  switch (colonne.format) {
    case 'date':
      return <span className="hub-valeur-numerique">{formatDate(brut)}</span>
    case 'datetime':
      return <span className="hub-valeur-numerique">{formatDateHeure(brut)}</span>
    case 'nombre':
      return <span className="hub-valeur-numerique">{brut === null || brut === undefined ? '—' : formatNombre(brut)}</span>
    case 'montant':
      return <span className="hub-valeur-numerique hub-montant">{formatMontant(brut)}</span>
    case 'booleen':
      return brut
        ? <span className="hub-badge is-green">Oui</span>
        : <span className="hub-badge is-slate">Non</span>
    case 'badge': {
      if (brut === null || brut === undefined || brut === '') return <span className="hub-vide">—</span>
      const libelle = colonne.libelleCle
        ? ligne[colonne.libelleCle]
        : colonne.libelleTexte?.[brut] ?? affichable
      const ton = (colonne.tons && colonne.tons[brut]) || TONS_DEFAUT[brut] || 'slate'
      return <span className={`hub-badge is-${ton}`}>{libelle || brut}</span>
    }
    case 'lienEtudiant': {
      const idEtudiant = ligne[colonne.idCle || 'etudiant_id']
      if (!idEtudiant || !affichable) return <span className="hub-vide">—</span>
      return (
        <Link to={`/scolarite/etudiants/${idEtudiant}`} className="hub-lien">
          {affichable}
          {colonne.sousCle && ligne[colonne.sousCle] ? (
            <span className="hub-lien-sous">{ligne[colonne.sousCle]}</span>
          ) : null}
        </Link>
      )
    }
    default:
      if (affichable === null || affichable === undefined || affichable === '') {
        return <span className="hub-vide">—</span>
      }
      return <span className={colonne.gras ? 'hub-gras' : undefined}>{String(affichable)}</span>
  }
}

function OngletTable({ onglet, actif }) {
  const toast = useToast()
  const [lignes, setLignes] = useState([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [page, setPage] = useState(1)
  const [serveur, setServeur] = useState(false)
  const [chargement, setChargement] = useState(false)
  const [charge, setCharge] = useState(false)
  const [recherche, setRecherche] = useState('')
  const rechercheAttendue = useDebounce(recherche)
  const [valeursFiltres, setValeursFiltres] = useState(
    () => Object.fromEntries((onglet.filtres || []).map((f) => [f.param, f.valeurInitiale || ''])),
  )

  const charger = useCallback(async () => {
    setChargement(true)
    try {
      const params = { ...(onglet.paramsBase || {}) }
      for (const [cle, valeur] of Object.entries(valeursFiltres)) {
        if (valeur) params[cle] = valeur
      }
      if (onglet.rechercheParam && rechercheAttendue.trim()) {
        params[onglet.rechercheParam] = rechercheAttendue.trim()
      }
      if (serveur) {
        params.page = page
        params.page_size = 25
      }
      const res = await api.get(onglet.endpoint, { params })
      const data = res.data
      const resultats = Array.isArray(data) ? data : (data?.results || data?.items || [])
      let liste = Array.isArray(resultats) ? resultats : []
      // Recherche locale pour les API sans paramètre de recherche serveur
      // (listes complètes non paginées) : filtrage insensible aux accents.
      if (onglet.rechercheLocale?.length && rechercheAttendue.trim()) {
        const normaliser = (v) => String(v ?? '').normalize('NFD')
          .replace(/[\u0300-\u036f]/g, '').toLowerCase()
        const terme = normaliser(rechercheAttendue.trim())
        liste = liste.filter((ligne) => onglet.rechercheLocale
          .some((cle) => normaliser(ligne[cle]).includes(terme)))
      }
      const pages = !Array.isArray(data) && typeof data?.total_pages === 'number'
        ? data.total_pages : null
      if (pages !== null && !serveur) setServeur(true)
      setLignes(liste)
      setTotal(
        !Array.isArray(data) && typeof data?.count === 'number' ? data.count : liste.length,
      )
      setTotalPages(Math.max(1, pages ?? Math.ceil(liste.length / 25) ?? 1))
      setCharge(true)
    } catch (err) {
      const data = err.response?.data
      toast.showToast(
        (typeof data?.error === 'string' && data.error)
          || `Chargement de « ${onglet.libelle} » impossible.`,
        'error',
      )
    } finally {
      setChargement(false)
    }
  }, [onglet, valeursFiltres, rechercheAttendue, serveur, page, toast])

  useEffect(() => {
    if (actif) charger()
  }, [actif, charger])

  const lignesPage = useMemo(() => {
    if (serveur) return lignes
    const debut = (page - 1) * 25
    return lignes.slice(debut, debut + 25)
  }, [lignes, page, serveur])

  const pagesEffectives = serveur ? totalPages : Math.max(1, Math.ceil(lignes.length / 25))

  if (!actif) return null

  return (
    <section className="cand-panel" aria-label={onglet.libelle}>
      <header className="cand-panel-head">
        <h2 className="cand-panel-title">
          <i className={`bi ${onglet.icone || 'bi-table'}`} aria-hidden="true"></i>{onglet.libelle}
        </h2>
        <span className="cand-count-pill">{formatNombre(total)} élément{total > 1 ? 's' : ''}</span>
      </header>
      {(onglet.rechercheParam || onglet.rechercheLocale || (onglet.filtres || []).length > 0 || onglet.note) && (
        <div className="cand-panel-body hub-filtres-zone">
          <div className="hub-filtres">
            {(onglet.rechercheParam || onglet.rechercheLocale) && (
              <div className="hub-filtre hub-filtre--large">
                <label className="cand-etiquette" htmlFor={`hub-rech-${onglet.id}`}>Rechercher</label>
                <div className="cand-search hub-recherche">
                  <i className="bi bi-search" aria-hidden="true"></i>
                  <input
                    id={`hub-rech-${onglet.id}`} type="search" className="cand-input"
                    placeholder={onglet.recherchePlaceholder || 'Rechercher…'}
                    value={recherche}
                    onChange={(e) => { setRecherche(e.target.value); setPage(1) }}
                  />
                </div>
              </div>
            )}
            {(onglet.filtres || []).filter((f) => !f.masque).map((f) => (
              <div className="hub-filtre" key={f.param}>
                <label className="cand-etiquette" htmlFor={`hub-f-${onglet.id}-${f.param}`}>
                  {f.libelle}
                </label>
                <select
                  id={`hub-f-${onglet.id}-${f.param}`} className="cand-filter-select"
                  value={valeursFiltres[f.param] || ''}
                  onChange={(e) => {
                    setValeursFiltres((v) => ({ ...v, [f.param]: e.target.value }))
                    setPage(1)
                  }}>
                  <option value="">{f.tousLibelle || `Tous — ${f.libelle.toLowerCase()}`}</option>
                  {(f.options || []).map((o) => (
                    <option key={String(o.valeur)} value={o.valeur}>{o.libelle}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          {onglet.note && (
            <p className="hub-note">
              <i className="bi bi-info-circle" aria-hidden="true"></i>{onglet.note}
            </p>
          )}
        </div>
      )}
      <div className="cand-table-wrap">
        <table className="cand-table hub-table">
          <thead>
            <tr>
              {onglet.colonnes.map((c) => (
                <th scope="col" key={c.cle + c.libelle}>{c.libelle}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {chargement && !charge ? (
              <tr>
                <td colSpan={onglet.colonnes.length}>
                  <div className="cand-chargement">
                    <span className="spinner-border" role="status" aria-hidden="true"></span>
                    Chargement…
                  </div>
                </td>
              </tr>
            ) : lignesPage.length === 0 ? (
              <tr>
                <td colSpan={onglet.colonnes.length}>
                  <div className="cand-vide">
                    <span className="cand-vide-icone" aria-hidden="true">
                      <i className="bi bi-inbox"></i>
                    </span>
                    <p className="cand-vide-titre">{onglet.videTitre || 'Aucun élément enregistré.'}</p>
                    <p className="cand-vide-texte">
                      {onglet.videTexte || 'Aucune donnée ne correspond aux critères sélectionnés.'}
                    </p>
                  </div>
                </td>
              </tr>
            ) : lignesPage.map((ligne, index) => (
              <tr key={ligne.id ?? ligne.pk ?? index}>
                {onglet.colonnes.map((c) => (
                  <td key={c.cle + c.libelle}><Cellule colonne={c} ligne={ligne} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="hub-pagination">
        <span className="hub-pagination-infos">
          Page <strong>{page}</strong> sur <strong>{formatNombre(pagesEffectives)}</strong>
          {' '}— {formatNombre(total)} élément{total > 1 ? 's' : ''} au total
        </span>
        <div className="hub-pagination-actions">
          <button
            type="button" className="cand-btn-fantome" disabled={page <= 1 || chargement}
            onClick={() => setPage((p) => Math.max(1, p - 1))}>
            <i className="bi bi-chevron-left" aria-hidden="true"></i>Précédent
          </button>
          <button
            type="button" className="cand-btn-fantome"
            disabled={page >= pagesEffectives || chargement}
            onClick={() => setPage((p) => Math.min(pagesEffectives, p + 1))}>
            Suivant<i className="bi bi-chevron-right" aria-hidden="true"></i>
          </button>
        </div>
      </div>
      <p className="cand-defile" aria-hidden="true">
        <i className="bi bi-arrow-left-right"></i>
        Faites défiler le tableau horizontalement
      </p>
    </section>
  )
}

export default function ModuleHub({
  titre, badge, icone, introduction, pastilles,
  statsEndpoint, tuiles, onglets, ongletInitial,
}) {
  const [ongletActif, setOngletActif] = useState(ongletInitial || onglets[0]?.id)
  const [stats, setStats] = useState(null)

  useEffect(() => {
    if (!statsEndpoint) return
    let annule = false
    api.get(statsEndpoint)
      .then((res) => {
        const data = res.data
        if (!annule && data && !Array.isArray(data) && typeof data === 'object') {
          setStats(data)
        }
      })
      .catch(() => {})
    return () => { annule = true }
  }, [statsEndpoint])

  const tuilesData = useMemo(
    () => (stats && tuiles ? tuiles(stats) : []),
    [stats, tuiles],
  )
  const pastillesData = useMemo(
    () => (stats && pastilles ? pastilles(stats) : []),
    [stats, pastilles],
  )

  return (
    <div className="cand-page hub-page">
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className={`bi ${icone}`}></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">{badge}</span>
            <h1 className="cand-hero-title">{titre}</h1>
            <p className="cand-hero-sub">{introduction}</p>
          </div>
        </div>
        {pastillesData.length > 0 && (
          <div className="cand-hero-actions">
            {pastillesData.map((p, i) => (
              <span
                key={i}
                className={`hub-pastille ${i === 0 ? 'hub-pastille--primary' : 'hub-pastille--neutre'}`}>
                {p.icone && <i className={`bi ${p.icone}`} aria-hidden="true"></i>}
                {p.texte}
              </span>
            ))}
          </div>
        )}
      </div>

      {tuilesData.length > 0 && (
        <div className="cand-kpi-row">
          {tuilesData.map((t, i) => (
            <div className="cand-kpi" key={i}>
              <span className={`cand-kpi-icon is-${t.ton || 'blue'}`} aria-hidden="true">
                <i className={`bi ${t.icone || 'bi-grid'}`}></i>
              </span>
              <div className="cand-kpi-texte">
                <span className="cand-kpi-value">{t.valeur}</span>
                <span className="cand-kpi-label">{t.libelle}</span>
                {t.sub && <span className="hub-kpi-sub">{t.sub}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="hub-onglets" role="tablist" aria-label={`Sous-modules — ${titre}`}>
        {onglets.map((o) => (
          <button
            key={o.id}
            type="button" role="tab" aria-selected={ongletActif === o.id}
            className={`hub-onglet${ongletActif === o.id ? ' is-active' : ''}`}
            onClick={() => setOngletActif(o.id)}>
            <i className={`bi ${o.icone || 'bi-table'}`} aria-hidden="true"></i>
            {o.libelle}
          </button>
        ))}
      </div>

      {onglets.map((o) => (
        <OngletTable key={o.id} onglet={o} actif={ongletActif === o.id} />
      ))}
    </div>
  )
}
