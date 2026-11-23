import React, {
  useCallback, useEffect, useMemo, useState,
} from 'react'
import { Link } from 'react-router-dom'
import api from '@/services/api'
import { useToast } from '../../context/ToastContext'

/**
 * « Étudiants inscrits » — POPULATIONS LMD (refonte du module).
 *
 * Population réelle d'une année académique, toutes origines : étudiants
 * inscrits par le processus INJS2026 (inscriptions administratives
 * validées, source « Base ») et étudiants lus dans un fichier externe
 * (source « Import »). L'API fusionne, déduplique (la base fait foi),
 * filtre (recherche, formation, niveau) et pagine à 25 par page ; les
 * indicateurs « sur la page affichée » (femmes/hommes, origine import)
 * sont calculés sur la page réellement reçue — rien n'est inventé.
 */

// Répartition femmes/hommes et origine import DE LA PAGE AFFICHÉE.
function comptePage(lignes) {
  return lignes.reduce((acc, l) => {
    if (l.sexe === 'F') acc.femmes += 1
    if (l.sexe === 'M') acc.hommes += 1
    if (l.source === 'Import') acc.imports += 1
    return acc
  }, { femmes: 0, hommes: 0, imports: 0 })
}

export default function EtudiantsInscrits() {
  const { showToast } = useToast()
  const [annees, setAnnees] = useState([])
  const [anneeId, setAnneeId] = useState('')
  const [donnees, setDonnees] = useState(null)
  const [chargement, setChargement] = useState(false)

  // Filtres en cours de saisie, puis appliqués au clic « Filtrer ».
  const [recherche, setRecherche] = useState('')
  const [formation, setFormation] = useState('')
  const [niveau, setNiveau] = useState('')
  const [appliques, setAppliques] = useState({ q: '', formation: '', niveau: '' })
  const [page, setPage] = useState(1)

  useEffect(() => {
    let actif = true
    api.get('/scolarite/ref/annees/')
      .then(({ data }) => {
        if (!actif) return
        const liste = Array.isArray(data) ? data : (data?.results || [])
        setAnnees(liste)
        const courante = liste.find((a) => a.courante) || liste[0]
        if (courante) setAnneeId(String(courante.id))
      })
      .catch(() => showToast('Impossible de charger les années académiques.', 'error'))
    return () => { actif = false }
  }, [showToast])

  const charger = useCallback(async () => {
    if (!anneeId) return
    setChargement(true)
    try {
      const params = { annee: anneeId, page }
      if (appliques.q) params.q = appliques.q
      if (appliques.formation) params.formation = appliques.formation
      if (appliques.niveau) params.niveau = appliques.niveau
      const { data } = await api.get('/edts/lmd/inscrits/', { params })
      setDonnees(data)
    } catch {
      showToast('Impossible de charger les étudiants inscrits.', 'error')
      setDonnees(null)
    } finally {
      setChargement(false)
    }
  }, [anneeId, appliques, page, showToast])

  useEffect(() => { charger() }, [charger])

  const filtrer = (e) => {
    e.preventDefault()
    setPage(1)
    setAppliques({
      q: recherche.trim(),
      formation,
      niveau,
    })
  }

  const reinitialiser = () => {
    setRecherche('')
    setFormation('')
    setNiveau('')
    setPage(1)
    setAppliques({ q: '', formation: '', niveau: '' })
  }

  const resultats = useMemo(() => donnees?.resultats || [], [donnees])
  const compte = useMemo(() => comptePage(resultats), [resultats])
  const total = donnees?.total || 0
  const totalPages = donnees?.total_pages || 0
  const pageCourante = donnees?.page || page

  return (
    <div className="getinjs gen-page imp-page insc-page" data-testid="etudiants-inscrits">
      {/* ── En-tête clair : sur-titre, titre, actions (format du module) ── */}
      <div className="imp-entete">
        <div>
          <div className="imp-surtitre">Populations LMD</div>
          <h1 className="imp-titre">Étudiants inscrits</h1>
          <p className="imp-sous">
            Population issue du processus d'inscription de backend-injs2026 ou
            d'un fichier externe importé. Chaque étudiant est rattaché à un
            parcours complet : filière, formation, niveau, groupe, vague et
            semestres.
          </p>
        </div>
        <div className="imp-actions">
          <Link className="btn btn-outline-primary" to="/edt/import-etudiants">
            Importer un fichier
          </Link>
          <Link className="btn btn-dark gen-btn-lancer" to="/edt">
            Emplois du temps
          </Link>
        </div>
      </div>

      {/* ── Indicateurs : total filtré, page, répartition de la page ────── */}
      <div className="insc-kpis">
        <div className="insc-kpi">
          <div className="insc-kpi-label">Étudiants filtrés</div>
          <div className="insc-kpi-valeur">{total.toLocaleString('fr-FR')}</div>
          <div className="insc-kpi-sous">Base + imports, année sélectionnée</div>
        </div>
        <div className="insc-kpi">
          <div className="insc-kpi-label">Page</div>
          <div className="insc-kpi-valeur">
            {pageCourante} / {totalPages || 1}
          </div>
          <div className="insc-kpi-sous">25 par page</div>
        </div>
        <div className="insc-kpi">
          <div className="insc-kpi-label">Femmes / Hommes</div>
          <div className="insc-kpi-valeur">{compte.femmes} / {compte.hommes}</div>
          <div className="insc-kpi-sous">Sur la page affichée</div>
        </div>
        <div className="insc-kpi">
          <div className="insc-kpi-label">Origine import</div>
          <div className="insc-kpi-valeur">{compte.imports}</div>
          <div className="insc-kpi-sous">Sur la page affichée</div>
        </div>
      </div>

      {/* ── Filtres : année, recherche, formation, niveau ───────────────── */}
      <form className="card mb-3" onSubmit={filtrer}>
        <div className="card-body">
          <div className="row g-3 align-items-end">
            <div className="col-md-2">
              <label className="insc-filtre-label" htmlFor="insc-annee">
                Année académique
              </label>
              <select
                id="insc-annee"
                className="form-select"
                value={anneeId}
                onChange={(e) => { setAnneeId(e.target.value); setPage(1) }}
              >
                {annees.map((a) => (
                  <option key={a.id} value={a.id}>{a.libelle}</option>
                ))}
              </select>
            </div>
            <div className="col-md-4">
              <label className="insc-filtre-label" htmlFor="insc-recherche">
                Recherche (matricule, nom, prénom)
              </label>
              <input
                id="insc-recherche"
                type="search"
                className="form-control"
                placeholder="Ex. INJS-2026-000001 ou Kouassi"
                value={recherche}
                onChange={(e) => setRecherche(e.target.value)}
              />
            </div>
            <div className="col-md-2">
              <label className="insc-filtre-label" htmlFor="insc-formation">
                Formation
              </label>
              <select
                id="insc-formation"
                className="form-select"
                value={formation}
                onChange={(e) => setFormation(e.target.value)}
              >
                <option value="">Toutes</option>
                {(donnees?.formations || []).map((f) => (
                  <option key={f.id} value={f.id}>{f.intitule}</option>
                ))}
              </select>
            </div>
            <div className="col-md-2">
              <label className="insc-filtre-label" htmlFor="insc-niveau">
                Niveau
              </label>
              <select
                id="insc-niveau"
                className="form-select"
                value={niveau}
                onChange={(e) => setNiveau(e.target.value)}
              >
                <option value="">Tous</option>
                {(donnees?.niveaux || []).map((n) => (
                  <option key={n.id} value={n.id}>{n.code}</option>
                ))}
              </select>
            </div>
            <div className="col-md-2 d-flex gap-2">
              <button type="submit" className="btn btn-dark flex-grow-1">
                Filtrer
              </button>
              <button
                type="button"
                className="btn btn-outline-secondary"
                onClick={reinitialiser}
              >
                Réinitialiser
              </button>
            </div>
          </div>
        </div>
      </form>

      {/* ── Liste des étudiants ─────────────────────────────────────────── */}
      <div className="card mb-3">
        <div className="card-body pb-0">
          <div className="d-flex align-items-start flex-wrap gap-2">
            <div>
              <div className="imp-card-titre">Liste des étudiants</div>
              <p className="imp-card-sous">
                Rattachement académique complet, prêt pour la génération et
                les présences
              </p>
            </div>
            <div className="ms-auto d-flex align-items-center gap-2">
              <span className="insc-source-note">Source : base + imports</span>
              <span className="imp-journal-count">
                {total.toLocaleString('fr-FR')} étudiant(s)
              </span>
            </div>
          </div>
        </div>
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0 imp-journal-table">
            <thead>
              <tr>
                <th>Matricule</th>
                <th>Nom et prénoms</th>
                <th>Sexe</th>
                <th>Formation</th>
                <th>Niveau</th>
                <th>Groupe</th>
                <th>Vague</th>
                <th>Statut</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {resultats.map((l) => (
                <tr key={`${l.source}-${l.matricule}`}>
                  <td className="insc-matricule">{l.matricule}</td>
                  <td>
                    <strong>{l.nom}</strong>
                    {l.prenoms ? ` ${l.prenoms}` : ''}
                  </td>
                  <td>{l.sexe || '—'}</td>
                  <td>
                    {l.formation_code
                      ? (
                        <>
                          <div className="fw-bold">{l.formation_code}</div>
                          <div className="insc-formation-sous">{l.formation}</div>
                        </>
                      )
                      : <span className="fw-bold">{l.formation}</span>}
                  </td>
                  <td>{l.niveau}</td>
                  <td>{l.groupe || '—'}</td>
                  <td>{l.vague || '—'}</td>
                  <td>
                    <span className={
                      l.statut === 'Inscrit'
                        ? 'insc-statut insc-statut-inscrit'
                        : 'insc-statut insc-statut-autre'
                    }
                    >
                      {l.statut}
                    </span>
                  </td>
                  <td>
                    <span className={
                      l.source === 'Import' ? 'insc-source insc-source-import'
                        : 'insc-source insc-source-base'
                    }
                    >
                      {l.source}
                    </span>
                  </td>
                </tr>
              ))}
              {!chargement && resultats.length === 0 && (
                <tr>
                  <td colSpan={9} className="text-center text-muted py-4">
                    Aucun étudiant inscrit ne correspond à ces critères.
                  </td>
                </tr>
              )}
              {chargement && (
                <tr>
                  <td colSpan={9} className="text-center text-muted py-4">
                    Chargement de la population…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="insc-pagination">
            <span>
              Page {pageCourante} sur {totalPages} — {total.toLocaleString('fr-FR')}
              {' '}étudiant(s)
            </span>
            <span className="d-flex gap-2">
              <button
                type="button"
                className="btn btn-outline-primary btn-sm"
                disabled={pageCourante <= 1 || chargement}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Précédent
              </button>
              <button
                type="button"
                className="btn btn-outline-primary btn-sm"
                disabled={pageCourante >= totalPages || chargement}
                onClick={() => setPage((p) => p + 1)}
              >
                Suivant
              </button>
            </span>
          </div>
        )}
      </div>

      <p className="imp-pied">
        GET INJS APP · module intégré à INJS2026 · Institut National de la
        Jeunesse et des Sports (INJS) - Marcory · Moteur LMD déterministe
      </p>
    </div>
  )
}
