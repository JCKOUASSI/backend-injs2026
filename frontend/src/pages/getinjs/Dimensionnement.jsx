import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '@/services/api'
import { useToast } from '../../context/ToastContext'

/**
 * « Dimensionnement » — besoins de planification GET-INJS2026.
 *
 * Tous les chiffres viennent de `GET /edts/lmd/dimensionnement/` et sont
 * **dérivés des données réelles** de l'année : promotions = inscriptions
 * administratives validées (formation × niveau × parcours), groupes
 * nécessaires = effectif ÷ capacité cible paramétrable, emplois du temps
 * à produire = groupes nécessaires (jamais un nombre imposé), séances
 * attendues calculées depuis les maquettes actives par le moteur de
 * besoins. Les manques (groupes, maquettes, salles) sont affichés comme
 * des anomalies à traiter, jamais compensés par des estimations.
 */

const TYPES_ANOMALIE = {
  PROMOTION_SANS_GROUPE: { libelle: 'Sans groupe', classe: 'badge-danger' },
  GROUPES_INSUFFISANTS: { libelle: 'Groupes insuffisants', classe: 'badge-warning' },
  PROMOTION_SANS_MAQUETTE: { libelle: 'Sans maquette active', classe: 'badge-warning' },
  BESOIN_NON_CALCULABLE: { libelle: 'Besoins non calculables', classe: 'badge-danger' },
  EFFECTIF_SUPERIEUR_PLUS_GRANDE_SALLE: {
    libelle: 'Effectif > plus grande salle', classe: 'badge-warning',
  },
}

const ouTiret = (v) => (v === null || v === undefined || v === '' ? '—' : v)
const nombre = (v) => (v === null || v === undefined ? '—' : Number(v).toLocaleString('fr-FR'))

export default function Dimensionnement() {
  const { showToast } = useToast()
  const [annees, setAnnees] = useState([])
  const [anneeId, setAnneeId] = useState('')
  const [capacite, setCapacite] = useState('60')
  const [rapport, setRapport] = useState(null)
  const [chargement, setChargement] = useState(false)
  const [plan, setPlan] = useState(null)
  const [constitutionEnCours, setConstitutionEnCours] = useState(false)

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
      const capaciteValide = parseInt(capacite, 10)
      const { data } = await api.get('/edts/lmd/dimensionnement/', {
        params: {
          annee: anneeId,
          ...(Number.isFinite(capaciteValide) && capaciteValide > 0
            ? { capacite: capaciteValide }
            : {}),
        },
      })
      setRapport(data)
    } catch {
      showToast('Impossible de calculer le dimensionnement.', 'error')
      setRapport(null)
    } finally {
      setChargement(false)
    }
  }, [anneeId, capacite, showToast])

  useEffect(() => { charger() }, [anneeId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Constitution des groupes manquants : prévisualisation (simulation,
  // aucune écriture) puis création confirmée explicitement. La
  // répartition des étudiants dans ces groupes reste l'opération
  // existante de l'écran Groupes (Scolarité).
  const previsualiserConstitution = async () => {
    setConstitutionEnCours(true)
    try {
      const capaciteValide = parseInt(capacite, 10)
      const { data } = await api.post('/edts/lmd/dimensionnement/constituer/', {
        annee_academique_id: anneeId,
        simulation: true,
        ...(Number.isFinite(capaciteValide) && capaciteValide > 0
          ? { capacite: capaciteValide }
          : {}),
      })
      setPlan(data.plan)
    } catch {
      showToast('Prévisualisation impossible (droits de planification requis).', 'error')
    } finally {
      setConstitutionEnCours(false)
    }
  }

  const confirmerConstitution = async () => {
    setConstitutionEnCours(true)
    try {
      const capaciteValide = parseInt(capacite, 10)
      const { data } = await api.post('/edts/lmd/dimensionnement/constituer/', {
        annee_academique_id: anneeId,
        ...(Number.isFinite(capaciteValide) && capaciteValide > 0
          ? { capacite: capaciteValide }
          : {}),
      })
      showToast(`${data.total_crees} groupe(s) constitué(s). Répartissez ensuite les étudiants depuis l'écran Groupes (Scolarité).`, 'success')
      setPlan(null)
      await charger()
    } catch {
      showToast('Constitution impossible (droits de planification requis).', 'error')
    } finally {
      setConstitutionEnCours(false)
    }
  }

  const anneeChoisie = annees.find((a) => String(a.id) === String(anneeId))
  const totaux = rapport?.totaux || {}
  const promotions = rapport?.promotions || []
  const anomalies = rapport?.anomalies || []

  const kpis = [
    { libelle: 'Étudiants à planifier', valeur: rapport?.effectif_total_a_planifier },
    { libelle: 'Promotions', valeur: totaux.promotions_a_planifier },
    { libelle: 'Groupes nécessaires', valeur: totaux.groupes_necessaires },
    { libelle: 'Groupes existants', valeur: totaux.groupes_existants },
    { libelle: 'Déficit de groupes', valeur: totaux.deficit_groupes },
    { libelle: 'EDT de groupe à produire', valeur: totaux.emplois_du_temps_a_produire },
    { libelle: 'Séances à programmer', valeur: totaux.seances_a_programmer },
    { libelle: 'Heures à programmer', valeur: totaux.heures_a_programmer },
    { libelle: 'Salles actives', valeur: totaux.salles_actives },
    { libelle: 'Plus grande salle (places)', valeur: totaux.capacite_max_salle },
  ]

  return (
    <div className="getinjs gen-page imp-page ref-page" data-testid="dimensionnement">
      <div className="imp-entete">
        <div>
          <div className="imp-surtitre">Dimensionnement GET-INJS</div>
          <h1 className="imp-titre">
            Besoins de planification {anneeChoisie?.libelle || ''}
          </h1>
          <p className="imp-sous">
            Promotions réelles (inscriptions validées), groupes nécessaires
            pour la capacité cible choisie et emplois du temps à produire :
            tous ces nombres sont calculés depuis les référentiels de
            l&rsquo;année, jamais fixés à l&rsquo;avance. Les anomalies
            ci-dessous indiquent ce qui doit être constitué ou complété
            avant la génération.
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
          <label className="d-flex align-items-center gap-2">
            <span className="text-muted">Capacité cible / groupe</span>
            <input
              type="number"
              min="1"
              className="form-control"
              style={{ width: '6rem' }}
              aria-label="Capacité cible par groupe"
              value={capacite}
              onChange={(e) => setCapacite(e.target.value)}
            />
          </label>
          <button type="button" className="btn btn-dark gen-btn-lancer" onClick={charger}>
            Recalculer
          </button>
          <Link className="btn btn-outline-primary" to="/edt/generation-annuelle">
            Aller à la génération
          </Link>
        </div>
      </div>

      {chargement && !rapport && (
        <div className="card"><div className="card-body text-muted">
          Calcul du dimensionnement…
        </div></div>
      )}

      {rapport && (
        <>
          <div className="ref-kpis" aria-label="Synthèse du dimensionnement">
            {kpis.map(({ libelle, valeur }) => (
              <div className="ref-kpi" key={libelle}>
                <div className="ref-kpi-label">{libelle}</div>
                <div className="ref-kpi-valeur">{nombre(valeur)}</div>
              </div>
            ))}
          </div>

          {totaux.deficit_groupes > 0 && !plan && (
            <div className="alert alert-warning d-flex flex-wrap align-items-center gap-3" role="alert">
              <span>
                <strong>{nombre(totaux.deficit_groupes)} groupe(s) manquant(s)</strong>{' '}
                pour couvrir les promotions à la capacité cible. Vous pouvez
                constituer ces groupes (contenants vides) ; la répartition
                des étudiants se fera ensuite depuis l&rsquo;écran Groupes.
              </span>
              <button
                type="button"
                className="btn btn-warning"
                onClick={previsualiserConstitution}
                disabled={constitutionEnCours}
              >
                Constituer les groupes manquants
              </button>
            </div>
          )}

          {plan && (
            <div className="card mb-3 border-warning">
              <div className="card-body">
                <div className="imp-card-titre">
                  Plan de constitution — {plan.total_a_creer} groupe(s) à créer
                </div>
                <p className="imp-card-sous">
                  Prévisualisation sans écriture. Les noms prolongent la
                  numérotation existante ; capacité de chaque groupe :{' '}
                  {plan.capacite_cible_par_groupe} étudiants.
                </p>
                <ul className="mb-3">
                  {plan.creations.map((bloc) => (
                    <li key={`${bloc.ref_formation_id}-${bloc.niveau_id}-${bloc.parcours_id ?? 'sans'}`}>
                      <strong>{bloc.formation} — {bloc.niveau}</strong> :{' '}
                      {bloc.groupes_a_creer.map((g) => g.nom).join(', ')}
                    </li>
                  ))}
                </ul>
                <div className="d-flex gap-2">
                  <button
                    type="button"
                    className="btn btn-dark"
                    onClick={confirmerConstitution}
                    disabled={constitutionEnCours}
                  >
                    Confirmer la création
                  </button>
                  <button
                    type="button"
                    className="btn btn-outline-secondary"
                    onClick={() => setPlan(null)}
                    disabled={constitutionEnCours}
                  >
                    Annuler
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="card mb-3">
            <div className="card-body pb-0">
              <div className="imp-card-titre">Promotions à planifier</div>
              <p className="imp-card-sous">
                Inscriptions administratives validées, par formation, niveau
                et parcours — capacité cible : {rapport.capacite_cible_par_groupe}{' '}
                étudiants par groupe
              </p>
            </div>
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0 imp-journal-table">
                <thead>
                  <tr>
                    <th>Formation</th><th>Niveau</th><th>Effectif</th>
                    <th>Groupes existants</th><th>Groupes nécessaires</th>
                    <th>Déficit</th>
                  </tr>
                </thead>
                <tbody>
                  {promotions.map((p) => (
                    <tr key={`${p.ref_formation_id}-${p.niveau_id}-${p.parcours_id ?? 'sans'}`}>
                      <td className="fw-bold">{p.formation}</td>
                      <td>{ouTiret(p.niveau)}</td>
                      <td>{nombre(p.effectif)}</td>
                      <td>
                        {nombre(p.groupes_existants)}
                        {p.groupes_existants > 0 && (
                          <span className="text-muted">
                            {' '}({nombre(p.capacite_groupes_existants)} places)
                          </span>
                        )}
                      </td>
                      <td>{nombre(p.groupes_necessaires)}</td>
                      <td>
                        {p.deficit_groupes > 0
                          ? <span className="badge badge-danger">{p.deficit_groupes}</span>
                          : <span className="badge badge-success">0</span>}
                      </td>
                    </tr>
                  ))}
                  {promotions.length === 0 && (
                    <tr><td colSpan={6} className="text-center text-muted py-4">
                      Aucune inscription administrative validée pour cette
                      année : rien à dimensionner.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <div className="card-body pb-0">
              <div className="imp-card-titre">
                Anomalies à traiter avant génération ({anomalies.length})
              </div>
              <p className="imp-card-sous">
                Informations manquantes ou insuffisances de capacité :
                elles sont signalées telles quelles, aucune donnée
                n&rsquo;est inventée pour les compenser.
              </p>
            </div>
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0 imp-journal-table">
                <thead>
                  <tr><th>Type</th><th>Promotion</th><th>Détail</th></tr>
                </thead>
                <tbody>
                  {anomalies.map((a, i) => {
                    const info = TYPES_ANOMALIE[a.type]
                      || { libelle: a.type, classe: 'badge-neutral' }
                    return (
                      <tr key={`${a.type}-${i}`}>
                        <td><span className={`badge ${info.classe}`}>{info.libelle}</span></td>
                        <td>{ouTiret(a.promotion)}</td>
                        <td>{a.detail}</td>
                      </tr>
                    )
                  })}
                  {anomalies.length === 0 && (
                    <tr><td colSpan={3} className="text-center text-muted py-4">
                      Aucune anomalie : groupes, maquettes et salles couvrent
                      les besoins calculés.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
