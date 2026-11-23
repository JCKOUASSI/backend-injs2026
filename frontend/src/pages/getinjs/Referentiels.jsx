import React, {
  useCallback, useEffect, useState,
} from 'react'
import { Link } from 'react-router-dom'
import api from '@/services/api'
import { useToast } from '../../context/ToastContext'

/**
 * « Référentiels » — Données de référence INJS (refonte du sous-module).
 *
 * Filières, formations, maquettes LMD, infrastructures, enseignants,
 * groupes et vagues qui alimentent directement le moteur de génération.
 * Toutes les valeurs viennent de `GET /edts/lmd/referentiels/` et sont
 * recalculées depuis leur source : mentions et écoles officielles,
 * maquettes actives (« publiées ») ou en brouillon (« paramétrables »),
 * modules = ECUE des maquettes actives de l'année, effectifs réels des
 * groupes (affectations actives + inscriptions importées rattachées).
 */

const COMPTEURS = [
  { cle: 'filieres', libelle: 'Filières' },
  { cle: 'formations', libelle: 'Formations' },
  { cle: 'modules', libelle: 'Modules' },
  { cle: 'groupes', libelle: 'Groupes' },
  { cle: 'vagues', libelle: 'Vagues' },
  { cle: 'salles', libelle: 'Salles' },
  { cle: 'enseignants', libelle: 'Enseignants' },
]

const ONGLETS = [
  { id: 'filieres', libelle: 'Filières & formations' },
  { id: 'maquettes', libelle: 'Maquettes & modules' },
  { id: 'salles', libelle: 'Bâtiments & salles' },
  { id: 'enseignants', libelle: 'Enseignants' },
  { id: 'groupes', libelle: 'Groupes & vagues' },
]

const ouTiret = (v) => (v === null || v === undefined || v === '' ? '—' : v)

export default function Referentiels() {
  const { showToast } = useToast()
  const [annees, setAnnees] = useState([])
  const [anneeId, setAnneeId] = useState('')
  const [donnees, setDonnees] = useState(null)
  const [onglet, setOnglet] = useState('filieres')
  const [chargement, setChargement] = useState(false)

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
      const { data } = await api.get('/edts/lmd/referentiels/', {
        params: { annee: anneeId },
      })
      setDonnees(data)
    } catch {
      showToast('Impossible de charger les référentiels.', 'error')
      setDonnees(null)
    } finally {
      setChargement(false)
    }
  }, [anneeId, showToast])

  useEffect(() => { charger() }, [charger])

  const voirConception = async () => {
    try {
      const { blob, fileName } = await api.getBlob('/edts/lmd/conception/')
      const url = URL.createObjectURL(blob)
      const lien = document.createElement('a')
      lien.href = url
      lien.download = fileName || 'Conception-GET-INJS.txt'
      document.body.appendChild(lien)
      lien.click()
      lien.remove()
      URL.revokeObjectURL(url)
    } catch {
      showToast('Document de conception indisponible.', 'error')
    }
  }

  const anneeChoisie = annees.find((a) => String(a.id) === String(anneeId))
  const compteurs = donnees?.compteurs || {}

  return (
    <div className="getinjs gen-page imp-page ref-page" data-testid="referentiels">
      {/* ── En-tête clair : sur-titre, titre annuel, actions ────────────── */}
      <div className="imp-entete">
        <div>
          <div className="imp-surtitre">Référentiels INJS</div>
          <h1 className="imp-titre">
            Données de référence {anneeChoisie?.libelle || ''}
          </h1>
          <p className="imp-sous">
            Filières, formations, maquettes LMD, infrastructures, enseignants,
            groupes et vagues issues des documents officiels de l'INJS. Ces
            référentiels alimentent directement le moteur de génération.
          </p>
        </div>
        <div className="imp-actions">
          <select
            className="form-select w-auto"
            aria-label="Année académique"
            value={anneeId}
            onChange={(e) => setAnneeId(e.target.value)}
          >
            {annees.map((a) => (
              <option key={a.id} value={a.id}>{a.libelle}</option>
            ))}
          </select>
          <Link className="btn btn-dark gen-btn-lancer" to="/edt/generation-annuelle">
            Générer depuis ces référentiels
          </Link>
          <button type="button" className="btn btn-outline-primary" onClick={voirConception}>
            Voir la conception
          </button>
        </div>
      </div>

      {/* ── Compteurs des référentiels ──────────────────────────────────── */}
      <div className="ref-kpis" aria-label="Compteurs des référentiels">
        {COMPTEURS.map(({ cle, libelle }) => (
          <div className="ref-kpi" key={cle}>
            <div className="ref-kpi-label">{libelle}</div>
            <div className="ref-kpi-valeur">
              {(compteurs[cle] ?? 0).toLocaleString('fr-FR')}
            </div>
          </div>
        ))}
      </div>

      {/* ── Onglets du sous-module ──────────────────────────────────────── */}
      <div className="ref-tabs" role="tablist" aria-label="Référentiels">
        {ONGLETS.map(({ id, libelle }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={onglet === id}
            className={onglet === id ? 'ref-tab actif' : 'ref-tab'}
            onClick={() => setOnglet(id)}
          >
            {libelle}
          </button>
        ))}
      </div>

      {chargement && !donnees && (
        <div className="card"><div className="card-body text-muted">
          Chargement des référentiels…
        </div></div>
      )}

      {donnees && onglet === 'filieres' && (
        <div className="row g-3">
          <div className="col-lg-5">
            <div className="card h-100">
              <div className="card-body pb-0">
                <div className="imp-card-titre">Filières (mentions)</div>
                <p className="imp-card-sous">Écoles et mentions de l'INJS</p>
              </div>
              <div className="table-responsive">
                <table className="table table-hover align-middle mb-0 imp-journal-table">
                  <thead>
                    <tr><th>Code</th><th>Filière</th><th>École</th></tr>
                  </thead>
                  <tbody>
                    {donnees.mentions.map((m) => (
                      <tr key={m.code}>
                        <td className="fw-bold">{m.code}</td>
                        <td>{m.nom}</td>
                        <td>
                          {m.ecole
                            ? <span className="ref-ecole">{m.ecole}</span>
                            : '—'}
                        </td>
                      </tr>
                    ))}
                    {donnees.mentions.length === 0 && (
                      <tr><td colSpan={3} className="text-center text-muted py-4">
                        Aucune mention officielle référencée.
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <div className="col-lg-7">
            <div className="card h-100">
              <div className="card-body pb-0">
                <div className="imp-card-titre">Formations (parcours)</div>
                <p className="imp-card-sous">
                  Cycle universitaire LMD, maquette publiée ou paramétrable
                </p>
              </div>
              <div className="table-responsive">
                <table className="table table-hover align-middle mb-0 imp-journal-table">
                  <thead>
                    <tr>
                      <th>Code</th><th>Formation</th><th>Filière</th>
                      <th>Maquette</th><th className="text-end">Groupes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {donnees.parcours.map((p) => (
                      <tr key={p.code}>
                        <td className="fw-bold">{p.code}</td>
                        <td>{p.libelle}</td>
                        <td>{ouTiret(p.mention)}</td>
                        <td>
                          <span className={
                            p.maquette === 'publiée'
                              ? 'ref-maquette ref-maquette-publiee'
                              : 'ref-maquette ref-maquette-param'
                          }
                          >
                            {p.maquette}
                          </span>
                        </td>
                        <td className="text-end fw-bold">{p.groupes}</td>
                      </tr>
                    ))}
                    {donnees.parcours.length === 0 && (
                      <tr><td colSpan={5} className="text-center text-muted py-4">
                        Aucune filière métier référencée.
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {donnees && onglet === 'maquettes' && (
        <div className="card">
          <div className="card-body pb-0">
            <div className="imp-card-titre">Maquettes & modules</div>
            <p className="imp-card-sous">
              Maquettes LMD de l'année : publiée = active pour le moteur,
              paramétrable = encore en préparation
            </p>
          </div>
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0 imp-journal-table">
              <thead>
                <tr>
                  <th>Formation</th><th>Niveau</th><th>Version</th><th>Statut</th>
                  <th className="text-end">UE</th>
                  <th className="text-end">Modules</th>
                  <th className="text-end">Crédits</th>
                </tr>
              </thead>
              <tbody>
                {donnees.maquettes.map((m) => (
                  <tr key={m.id}>
                    <td className="fw-bold">{m.formation}</td>
                    <td>{m.niveau}</td>
                    <td>v{m.version}</td>
                    <td>
                      <span className={
                        m.publiee
                          ? 'ref-maquette ref-maquette-publiee'
                          : 'ref-maquette ref-maquette-param'
                      }
                      >
                        {m.statut_libelle}
                      </span>
                    </td>
                    <td className="text-end">{m.ues}</td>
                    <td className="text-end">{m.modules}</td>
                    <td className="text-end">{m.credits}</td>
                  </tr>
                ))}
                {donnees.maquettes.length === 0 && (
                  <tr><td colSpan={7} className="text-center text-muted py-4">
                    Aucune maquette pour cette année académique.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {donnees && onglet === 'salles' && (
        <div className="card">
          <div className="card-body pb-0">
            <div className="imp-card-titre">Bâtiments & salles</div>
            <p className="imp-card-sous">
              {donnees.infrastructure.sites} site(s) ·{' '}
              {donnees.infrastructure.batiments} bâtiment(s) — espaces
              mobilisables par les emplois du temps
            </p>
          </div>
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0 imp-journal-table">
              <thead>
                <tr>
                  <th>Code</th><th>Salle</th><th>Bâtiment</th><th>Site</th>
                  <th className="text-end">Capacité</th><th>Type</th>
                </tr>
              </thead>
              <tbody>
                {donnees.infrastructure.salles.map((s) => (
                  <tr key={s.code || s.nom}>
                    <td className="fw-bold">{ouTiret(s.code)}</td>
                    <td>{s.nom}</td>
                    <td>{ouTiret(s.batiment)}</td>
                    <td>{ouTiret(s.site)}</td>
                    <td className="text-end">{ouTiret(s.capacite)}</td>
                    <td>{s.type}</td>
                  </tr>
                ))}
                {donnees.infrastructure.salles.length === 0 && (
                  <tr><td colSpan={6} className="text-center text-muted py-4">
                    Aucune salle active référencée.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {donnees && onglet === 'enseignants' && (
        <div className="card">
          <div className="card-body pb-0">
            <div className="imp-card-titre">Enseignants</div>
            <p className="imp-card-sous">
              Enseignants référencés pour les affectations du moteur de
              génération
            </p>
          </div>
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0 imp-journal-table">
              <thead>
                <tr>
                  <th>Nom et prénoms</th><th>Spécialité</th><th>Grade</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {donnees.enseignants.map((e) => (
                  <tr key={`${e.nom}-${e.prenom}`}>
                    <td><strong>{e.nom}</strong>{e.prenom ? ` ${e.prenom}` : ''}</td>
                    <td>{ouTiret(e.specialite)}</td>
                    <td>{ouTiret(e.grade)}</td>
                    <td>{ouTiret(e.statut)}</td>
                  </tr>
                ))}
                {donnees.enseignants.length === 0 && (
                  <tr><td colSpan={4} className="text-center text-muted py-4">
                    Aucun enseignant référencé.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {donnees && onglet === 'groupes' && (
        <div className="row g-3">
          <div className="col-lg-8">
            <div className="card h-100">
              <div className="card-body pb-0">
                <div className="imp-card-titre">Groupes</div>
                <p className="imp-card-sous">
                  Groupes pédagogiques de l'année et leur effectif réel
                  (affectations actives et inscriptions importées)
                </p>
              </div>
              <div className="table-responsive">
                <table className="table table-hover align-middle mb-0 imp-journal-table">
                  <thead>
                    <tr>
                      <th>Groupe</th><th>Formation</th><th>Niveau</th><th>Vague</th>
                      <th className="text-end">Capacité</th>
                      <th className="text-end">Effectif</th>
                    </tr>
                  </thead>
                  <tbody>
                    {donnees.groupes.map((g) => (
                      <tr key={`${g.formation}-${g.nom}`}>
                        <td className="fw-bold">{g.nom}</td>
                        <td>{g.formation}</td>
                        <td>{g.niveau}</td>
                        <td>{ouTiret(g.vague)}</td>
                        <td className="text-end">{ouTiret(g.capacite)}</td>
                        <td className="text-end fw-bold">{g.effectif}</td>
                      </tr>
                    ))}
                    {donnees.groupes.length === 0 && (
                      <tr><td colSpan={6} className="text-center text-muted py-4">
                        Aucun groupe pour cette année académique.
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <div className="col-lg-4">
            <div className="card h-100">
              <div className="card-body pb-0">
                <div className="imp-card-titre">Vagues</div>
                <p className="imp-card-sous">Vagues d'inscription actives</p>
              </div>
              <div className="table-responsive">
                <table className="table table-hover align-middle mb-0 imp-journal-table">
                  <thead>
                    <tr><th>Code</th><th>Vague</th><th className="text-end">Groupes</th></tr>
                  </thead>
                  <tbody>
                    {donnees.vagues.map((v) => (
                      <tr key={v.libelle}>
                        <td className="fw-bold">{ouTiret(v.code)}</td>
                        <td>{v.libelle}</td>
                        <td className="text-end fw-bold">{v.groupes}</td>
                      </tr>
                    ))}
                    {donnees.vagues.length === 0 && (
                      <tr><td colSpan={3} className="text-center text-muted py-4">
                        Aucune vague active.
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      <p className="imp-pied">
        GET INJS APP · module intégré à INJS2026 · Institut National de la
        Jeunesse et des Sports (INJS) - Marcory · Moteur LMD déterministe
      </p>
    </div>
  )
}
