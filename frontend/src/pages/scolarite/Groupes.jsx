import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useToast } from '../../context/ToastContext'
import {
  getAnneeCourante,
  getEffectifsGroupes,
  getRefFormations,
  getRefScolarite,
  messageErreur,
  repartirGroupes,
} from '../../services/scolarite'
import '../../styles/groupes.css'

export default function Groupes() {
  const { showToast } = useToast()
  const [annee, setAnnee] = useState(null)
  const [groupes, setGroupes] = useState([])
  const [formations, setFormations] = useState([])
  const [niveaux, setNiveaux] = useState([])
  const [filtres, setFiltres] = useState({ ref_formation_id: '', niveau_id: '' })
  const [loading, setLoading] = useState(true)
  const [repartition, setRepartition] = useState(null)
  const [action, setAction] = useState(false)

  const charger = useCallback(async () => {
    setLoading(true)
    try {
      const params = { ...filtres }
      if (annee?.id) params.annee_academique_id = annee.id
      const res = await getEffectifsGroupes(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '')),
      )
      setGroupes(res.data)
    } catch (err) {
      showToast(messageErreur(err, 'Chargement des groupes impossible'), 'error')
    } finally {
      setLoading(false)
    }
  }, [filtres, annee, showToast])

  useEffect(() => {
    (async () => {
      const [anneeCourante, formationsRes, niveauxRes] = await Promise.all([
        getAnneeCourante().catch(() => null),
        getRefFormations().catch(() => ({ data: [] })),
        getRefScolarite('niveaux', { actif: 1 }).catch(() => ({ data: [] })),
      ])
      setAnnee(anneeCourante)
      setFormations(formationsRes.data || [])
      setNiveaux(niveauxRes.data || [])
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
    return { totalGroupes, actifs, tauxMoyen }
  }, [groupes])

  return (
    <div className="container-fluid py-4 grp-page">
      {/* ── Bandeau d'accueil (matière de la référence LMD2026) ── */}
      <div className="grp-hero">
        <div className="grp-hero-text">
          <span className="grp-hero-badge">
            <i className="bi bi-people-fill"></i>Scolarité — Groupes
          </span>
          <h1 className="grp-hero-title">
            <i className="bi bi-diagram-3-fill"></i>
            Groupes pédagogiques
          </h1>
          <p className="grp-hero-sub">
            {annee ? `Année académique ${annee.libelle}` : 'Année courante non définie'}
            {' · '}{totalEffectif} étudiant(s) affecté(s) aux sections TD/TP.
          </p>
        </div>
        <button
          type="button"
          className="grp-action"
          disabled={action}
          onClick={repartir}
        >
          {action ? (
            <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
          ) : (
            <i className="bi bi-diagram-3"></i>
          )}
          Répartir automatiquement
        </button>
      </div>

      {/* ── Tuiles KPI ── */}
      <div className="grp-kpi-row">
        <div className="grp-kpi">
          <div>
            <span className="grp-kpi-label">Total Groupes</span>
            <span className="grp-kpi-value">{stats.totalGroupes}</span>
          </div>
          <div className="grp-kpi-icon is-blue"><i className="bi bi-grid-3x3-gap-fill"></i></div>
        </div>

        <div className="grp-kpi">
          <div>
            <span className="grp-kpi-label">Étudiants Affectés</span>
            <span className="grp-kpi-value">{totalEffectif}</span>
          </div>
          <div className="grp-kpi-icon is-green"><i className="bi bi-person-check-fill"></i></div>
        </div>

        <div className="grp-kpi">
          <div>
            <span className="grp-kpi-label">Taux Remplissage</span>
            <span className={`grp-kpi-value${stats.tauxMoyen !== null ? ' is-green' : ''}`}>
              {stats.tauxMoyen !== null ? `${stats.tauxMoyen}%` : '—'}
            </span>
          </div>
          <div className="grp-kpi-icon is-amber"><i className="bi bi-pie-chart-fill"></i></div>
        </div>

        <div className="grp-kpi">
          <div>
            <span className="grp-kpi-label">Groupes Actifs</span>
            <span className="grp-kpi-value">{stats.actifs}</span>
          </div>
          <div className="grp-kpi-icon is-slate"><i className="bi bi-check2-circle"></i></div>
        </div>
      </div>

      {/* ── Filtres & Liste ── */}
      <div className="card grp-panel">
        <div className="grp-panel-head">
          <h2 className="grp-panel-title">
            <i className="bi bi-list-check"></i>Répartition par groupe
          </h2>
          <span className="grp-count-pill">
            {groupes.length} groupe{groupes.length > 1 ? 's' : ''}
          </span>
        </div>
        <div className="grp-panel-body">
          <div className="grp-filters">
            <div className="grp-field">
              <label className="grp-field-label" htmlFor="groupe-formation">Formation</label>
              <select
                id="groupe-formation"
                className="form-select"
                value={filtres.ref_formation_id}
                onChange={(e) => setFiltres({ ...filtres, ref_formation_id: e.target.value })}
              >
                <option value="">Toutes les formations</option>
                {formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
              </select>
            </div>
            <div className="grp-field">
              <label className="grp-field-label" htmlFor="groupe-niveau">Niveau</label>
              <select
                id="groupe-niveau"
                className="form-select"
                value={filtres.niveau_id}
                onChange={(e) => setFiltres({ ...filtres, niveau_id: e.target.value })}
              >
                <option value="">Tous les niveaux</option>
                {niveaux.map((n) => <option key={n.id} value={n.id}>{n.code}</option>)}
              </select>
            </div>
          </div>

          {repartition?.echecs?.length > 0 && (
            <div className="grp-alert" role="alert">
              <i className="bi bi-exclamation-triangle-fill"></i>
              <div>
                <strong>{repartition.echecs.length} étudiant(s) non affecté(s)</strong>
                <div className="grp-alert-detail">{repartition.echecs[0].motif}</div>
              </div>
            </div>
          )}

          {loading ? (
            <div className="grp-loading">
              <span className="spinner-border" role="status" aria-hidden="true"></span>
              <span>Chargement des groupes…</span>
            </div>
          ) : (
            <div className="grp-table-wrap">
              <table className="table table-hover align-middle grp-table">
                <thead>
                  <tr>
                    <th>Groupe</th>
                    <th>Formation</th>
                    <th>Niveau</th>
                    <th>Effectif</th>
                    <th style={{ minWidth: '180px' }}>Remplissage</th>
                    <th>État</th>
                  </tr>
                </thead>
                <tbody>
                  {groupes.map((g) => {
                    const taux = g.capacite_max ? Math.round((g.effectif * 100) / g.capacite_max) : null
                    return (
                      <tr key={g.id}>
                        <td>
                          <span className="grp-nom">{g.nom}</span>
                        </td>
                        <td className="grp-formation">{g.ref_formation}</td>
                        <td><span className="badge bg-light text-dark border">{g.niveau}</span></td>
                        <td>
                          <span className="grp-effectif">{g.effectif}</span>
                          {g.capacite_max ? <span className="grp-effectif-cap"> / {g.capacite_max}</span> : ''}
                        </td>
                        <td>
                          {taux === null ? (
                            <span className="grp-sans-limite">Sans limite</span>
                          ) : (
                            <div className="grp-progress">
                              <div className="grp-progress-meta">
                                <span className={taux >= 100 ? 'is-over' : undefined}>{taux}%</span>
                                <span>{g.effectif}/{g.capacite_max}</span>
                              </div>
                              <div className="progress">
                                <div
                                  className={`progress-bar bg-${taux >= 100 ? 'danger' : taux >= 80 ? 'warning' : 'success'}`}
                                  style={{ width: `${Math.min(taux, 100)}%` }}
                                />
                              </div>
                            </div>
                          )}
                        </td>
                        <td>
                          {g.actif ? (
                            <span className="badge bg-success-subtle text-success border border-success-subtle">
                              Actif
                            </span>
                          ) : (
                            <span className="badge bg-secondary-subtle text-secondary border border-secondary-subtle">
                              Inactif
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                  {groupes.length === 0 && (
                    <tr>
                      <td colSpan={6} className="grp-empty">
                        <i className="bi bi-inbox"></i>
                        Aucun groupe défini pour les filtres sélectionnés.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
