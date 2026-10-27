import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { genererEdtsCoordonne } from '../services/edts'

/** Libellés français des statuts globaux retournés par l’orchestrateur (LOT 3). */
export const LIBELLES_STATUT_COORDONNE = {
  COORDONNEE_OK: {
    libelle: 'Génération coordonnée réussie',
    variante: 'success',
    icone: 'bi-check2-circle',
  },
  COORDONNEE_PARTIELLE: {
    libelle: 'Génération coordonnée incomplète',
    variante: 'warning',
    icone: 'bi-exclamation-triangle',
  },
  COORDONNEE_CONFLITS: {
    libelle: 'Génération coordonnée conflictuelle',
    variante: 'danger',
    icone: 'bi-x-octagon',
  },
  COORDONNEE_IMPOSSIBLE: {
    libelle: 'Génération coordonnée impossible',
    variante: 'danger',
    icone: 'bi-x-circle',
  },
  COORDONNEE_ERREUR: {
    libelle: 'Erreur de génération coordonnée',
    variante: 'danger',
    icone: 'bi-bug',
  },
}

/** Libellés des statuts par EDT (moteur de génération). */
const LIBELLES_STATUT_EDT = {
  GENERATION_OK: 'Généré',
  GENERATION_PARTIELLE: 'Partiel',
  GENERATION_IMPOSSIBLE: 'Impossible',
  GENERATION_ERREUR: 'Erreur',
}

/** Motifs d’échec globaux → message français non technique. */
const LIBELLES_MOTIF = {
  AUCUNE_FORMATION_INJS_PLANIFIABLE:
    'Aucune formation INJS planifiable pour cette année académique.',
  AUCUN_EDT_PLACE: 'Aucune séance n’a pu être placée.',
  CONFLITS_INTER_EDT_NON_RESOLUS: 'Des conflits subsistent entre les emplois du temps.',
  EDT_STATUT_NON_MODIFIABLE: 'Un emploi du temps existant n’accepte pas l’écriture.',
  ANNEE_ACADEMIQUE_REQUISE: 'L’année académique est obligatoire.',
  ANNEE_ACADEMIQUE_INTROUVABLE: 'L’année académique sélectionnée est introuvable.',
  GENERATION_IMPOSSIBLE: 'La génération n’a pas pu aboutir.',
  BUDGET_EXHAUSTED: 'La recherche a été arrêtée faute de budget de calcul suffisant.',
  ERREUR_GENERATION_FORMATION: 'Une erreur technique a empêché cette formation d’être générée.',
  ERREUR_PERSISTANCE_EDT: 'Le plan a été généré mais n’a pas pu être enregistré.',
}

/** Motifs de refus de persistance (par EDT). */
const LIBELLES_MOTIF_PERSISTANCE = {
  EDT_CREE_IMPOSSIBLE: 'Aucun EDT cible disponible pour cette formation.',
  EDT_STATUT_NON_MODIFIABLE: 'EDT existant non modifiable (statut verrouillé).',
  PLAN_VIDE: 'Aucun placement à enregistrer.',
  VALIDATION_BLOQUANTE: 'Plan refusé par les contrôles de cohérence.',
}

/** Catégories d'erreur affichables à l'écran (jamais de 500 opaque). */
export const CATEGORIES_ERREUR = {
  VALIDATION: { libelle: 'Requête invalide', icone: 'bi-exclamation-circle' },
  AUTORISATION: { libelle: 'Action non autorisée', icone: 'bi-shield-lock' },
  INTROUVABLE: { libelle: 'Ressource introuvable', icone: 'bi-search' },
  CONFLIT: { libelle: 'Conflit métier', icone: 'bi-x-octagon' },
  RESEAU: { libelle: 'Serveur injoignable', icone: 'bi-wifi-off' },
  SERVEUR: { libelle: 'Erreur du serveur', icone: 'bi-bug' },
}

/**
 * Traduit une erreur réseau/HTTP en catégorie + message affichables.
 * Le corps métier du backend est `{motif_echec, detail:{explication, action_recommandee}}`.
 */
export function categoriserErreur(err) {
  const data = err?.response?.data || null
  const status = err?.response?.status || null
  const detail = data?.detail && typeof data.detail === 'object' ? data.detail : {}
  const base = {
    statut: status,
    motif: data?.motif_echec || null,
    explication: detail.explication || null,
    action: detail.action_recommandee || null,
  }
  if (!status) {
    return { ...base, categorie: 'RESEAU', message: 'Le serveur n’a pas répondu. Vérifiez votre connexion puis réessayez.' }
  }
  if (status === 400) {
    return { ...base, categorie: 'VALIDATION', message: base.explication || 'La requête a été refusée : paramètres invalides.' }
  }
  if (status === 401 || status === 403) {
    return { ...base, categorie: 'AUTORISATION', message: base.explication || 'Votre rôle ne permet pas la génération coordonnée.' }
  }
  if (status === 404) {
    return { ...base, categorie: 'INTROUVABLE', message: base.explication || 'Ressource introuvable (année académique absente ?).' }
  }
  if (status === 409) {
    return { ...base, categorie: 'CONFLIT', message: base.explication || 'L’opération entre en conflit avec l’existant.' }
  }
  return { ...base, categorie: 'SERVEUR', message: base.explication || `Erreur serveur (HTTP ${status}).` }
}

/** Message lisible d’un motif d’échec métier (backend). */
export function libelleMotif(motif) {
  if (!motif) return null
  return LIBELLES_MOTIF[motif] || LIBELLES_MOTIF_PERSISTANCE[motif] || motif
}

/** Extrait les totaux affichables du bilan (défensif : champs absents). */
export function resumeBilan(bilan) {
  const totaux = bilan?.totaux || {}
  return {
    statusGlobal: bilan?.status_global || null,
    motifEchec: bilan?.motif_echec || null,
    annee: bilan?.annee_academique_id ?? null,
    semaines: bilan?.semaines || null,
    nbFormations: bilan?.nb_formations ?? 0,
    attendues: totaux.seances_attendues ?? 0,
    placees: totaux.seances_placees ?? 0,
    nonPlacees: totaux.seances_non_placees ?? 0,
    nbEdt: totaux.nb_edt ?? 0,
    nbEdtComplets: totaux.nb_edt_complets ?? 0,
    nbEdtIncomplets: totaux.nb_edt_incomplets ?? 0,
    nbEdtPersistes: totaux.nb_edt_persistes ?? 0,
    tauxCouverture: totaux.taux_couverture ?? null,
    persistenceDemandee: Boolean(bilan?.persistence_demandee),
    conflits: bilan?.conflits || { statut: 'NON_APPLIQUE', conflits: [] },
  }
}

/**
 * Panneau « Génération coordonnée » (LOT 3) — интегration dans /edt.
 *
 * Périmètre : toutes les formations INJS de l'année académique, périmètre
 * dérivé côté serveur (aucune liste de formations transmise). Aucune
 * publication n'est effectuée : la validation/publication reste le parcours
 * `POST /api/edts/lmd/{id}/publish/`.
 */
export default function GenerationCoordonnee({
  annees = [],
  anneeSelectionnee = '',
  onAnneeChange,
  onResultat,
  refresh,
  compact = false,
}) {
  const { showToast } = useToast()
  const [bilan, setBilan] = useState(null)
  const [chargement, setChargement] = useState(false)
  const [erreur, setErreur] = useState(null)
  const [persister, setPersister] = useState(false)

  const anneeId = anneeSelectionnee ? Number(anneeSelectionnee) : null
  const executer = async () => {
    setChargement(true)
    setErreur(null)
    try {
      const reponse = await genererEdtsCoordonne({
        annee_academique_id: anneeId,
        persister,
      })
      const donnees = reponse?.data || {}
      setBilan(donnees)
      const resume = resumeBilan(donnees)
      const complet = resume.statusGlobal === 'COORDONNEE_OK'
      if (complet) {
        showToast(resume.persistenceDemandee
          ? 'Génération coordonnée complète et enregistrée.'
          : 'Génération coordonnée complète (prévisualisation).')
      } else {
        showToast('Génération coordonnée incomplète : consultez le bilan.', 'info')
      }
      if (typeof onResultat === 'function') onResultat(donnees)
      if (typeof refresh === 'function') refresh()
    } catch (err) {
      const categorie = categoriserErreur(err)
      setErreur(categorie)
      showToast(categorie.message, 'error')
    } finally {
      setChargement(false)
    }
  }

  const resume = bilan ? resumeBilan(bilan) : null
  const statutInfo = resume ? (LIBELLES_STATUT_COORDONNE[resume.statusGlobal] || {
    libelle: 'Statut inconnu', variante: 'secondary', icone: 'bi-question-circle',
  }) : null

  return (
    <div className={`card edt-panel${compact ? ' mb-0' : ' mb-3'}`} data-testid="generation-coordonnee">
      <div className="card-header edt-panel-head">
        <span className="edt-panel-title"><i className="bi bi-diagram-3" /> Génération coordonnée (toutes formations INJS)</span>
        {statutInfo && (
          <span className={`badge text-bg-${statutInfo.variante}`} data-testid="bilan-statut">
            <i className={`bi ${statutInfo.icone} me-1`} />{statutInfo.libelle}
          </span>
        )}
      </div>
      <div className="card-body">
        <div className="row g-2 align-items-end">
          <div className="col-md-4">
            <label className="form-label small text-muted mb-1" htmlFor="gc-annee">Année académique <span className="text-danger">*</span></label>
            <select
              id="gc-annee"
              className="form-select form-select-sm"
              value={anneeSelectionnee}
              onChange={(e) => onAnneeChange && onAnneeChange(e.target.value)}
              disabled={chargement}
            >
              <option value="">— Sélectionnez —</option>
              {annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
            </select>
          </div>
          <div className="col-md-4">
            <div className="form-check mt-3">
              <input
                id="gc-persister"
                className="form-check-input"
                type="checkbox"
                checked={persister}
                onChange={(e) => setPersister(e.target.checked)}
                disabled={chargement}
              />
              <label className="form-check-label small" htmlFor="gc-persister">
                Enregistrer les plans dans les EDT (remplace les séances générées antérieures)
              </label>
            </div>
          </div>
          <div className="col-md-4 d-flex gap-2 justify-content-md-end">
            <button
              type="button"
              className="btn btn-sm btn-primary"
              onClick={executer}
              disabled={chargement || !anneeId}
            >
              {chargement
                ? <><span className="spinner-border spinner-border-sm me-2" />Génération…</>
                : <><i className="bi bi-play-circle me-1" />Générer</>}
            </button>
            {bilan && (
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary"
                onClick={executer}
                disabled={chargement}
                data-testid="gc-refresh"
              >
                <i className="bi bi-arrow-clockwise me-1" />Rafraîchir
              </button>
            )}
          </div>
        </div>

        {chargement && (
          <div className="text-center py-4" data-testid="gc-loading">
            <div className="spinner-border text-primary" role="status" />
            <p className="text-muted small mt-2 mb-0">Génération coordonnée en cours…</p>
          </div>
        )}

        {erreur && (
          <div className={`alert alert-${erreur.categorie === 'RESEAU' || erreur.categorie === 'SERVEUR' ? 'danger' : 'warning'} mt-3 mb-0`} role="alert" data-testid="gc-erreur">
            <div className="fw-semibold">
              <i className={`bi ${CATEGORIES_ERREUR[erreur.categorie]?.icone || 'bi-exclamation-triangle'} me-1`} />
              {CATEGORIES_ERREUR[erreur.categorie]?.libelle || 'Erreur'}
            </div>
            <div className="small mt-1">{erreur.message}</div>
            {erreur.motif && <div className="small mt-1"><code>{erreur.motif}</code> — {libelleMotif(erreur.motif)}</div>}
            {erreur.action && <div className="small mt-1 text-muted">Action recommandée : {erreur.action}</div>}
          </div>
        )}

        {resume && !chargement && (
          <div className="mt-3" data-testid="gc-bilan">
            <div className="row g-2 text-center">
              <div className="col-6 col-md-2">
                <div className="border rounded p-2">
                  <div className="fs-5 fw-semibold">{resume.nbFormations}</div>
                  <div className="small text-muted">Formation(s)</div>
                </div>
              </div>
              <div className="col-6 col-md-2">
                <div className="border rounded p-2">
                  <div className="fs-5 fw-semibold">{resume.attendues}</div>
                  <div className="small text-muted">Séance(s) attendue(s)</div>
                </div>
              </div>
              <div className="col-6 col-md-2">
                <div className="border rounded p-2">
                  <div className="fs-5 fw-semibold text-success">{resume.placees}</div>
                  <div className="small text-muted">Séance(s) placée(s)</div>
                </div>
              </div>
              <div className="col-6 col-md-2">
                <div className="border rounded p-2">
                  <div className="fs-5 fw-semibold text-warning">{resume.nonPlacees}</div>
                  <div className="small text-muted">Séance(s) non placée(s)</div>
                </div>
              </div>
              <div className="col-6 col-md-2">
                <div className="border rounded p-2">
                  <div className="fs-5 fw-semibold">{resume.tauxCouverture != null ? `${resume.tauxCouverture} %` : '—'}</div>
                  <div className="small text-muted">Taux de couverture</div>
                </div>
              </div>
              <div className="col-6 col-md-2">
                <div className="border rounded p-2">
                  <div className="fs-5 fw-semibold">{resume.nbEdtPersistes}</div>
                  <div className="small text-muted">EDT enregistré(s)</div>
                </div>
              </div>
            </div>

            {resume.motifEchec && (
              <div className="alert alert-warning mt-3 mb-0 small">
                <i className="bi bi-exclamation-triangle me-1" />
                <code>{resume.motifEchec}</code> — {libelleMotif(resume.motifEchec)}
              </div>
            )}

            {resume.nbEdtIncomplets > 0 && (
              <div className="alert alert-warning mt-3 mb-0 small" data-testid="gc-partiel">
                <i className="bi bi-exclamation-triangle me-1" />
                {resume.nbEdtIncomplets} emploi(s) du temps incomplet(s) sur {resume.nbEdt} : l’opération n’est pas entièrement réussie.
              </div>
            )}

            {resume.conflits?.statut === 'CONFLITS' && (
              <div className="alert alert-danger mt-3 mb-0 small" data-testid="gc-conflits">
                <i className="bi bi-x-octagon me-1" />
                Conflits inter-EDT détectés : {(resume.conflits.conflits || []).length}.
              </div>
            )}

            {bilan?.edts?.length > 0 && (
              <div className="table-responsive mt-3">
                <table className="table table-sm align-middle mb-0">
                  <thead>
                    <tr>
                      <th>Formation</th>
                      <th>Statut</th>
                      <th>Placées / attendues</th>
                      <th>Enregistrement</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bilan.edts.map((edt) => (
                      <tr key={edt.ref_formation_id}>
                        <td>{edt.ref_formation_id}{edt.edt_id ? ` (EDT #${edt.edt_id})` : ''}</td>
                        <td>
                          <span className={`badge text-bg-${edt.status === 'GENERATION_OK' ? 'success' : edt.status === 'GENERATION_ERREUR' ? 'danger' : 'warning'}`}>
                            {LIBELLES_STATUT_EDT[edt.status] || edt.status}
                          </span>
                        </td>
                        <td>{edt.metrics?.seances_placees ?? 0} / {edt.metrics?.seances_attendues ?? 0}</td>
                        <td>
                          {edt.persistence
                            ? (edt.persistence.effectuee
                              ? `Enregistré (${edt.persistence.nb_seances ?? '—'} séance(s))`
                              : `Refusé — ${libelleMotif(edt.persistence.motif_refus) || edt.persistence.motif_refus}`)
                            : '— (prévisualisation)'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <p className="small text-muted mt-2 mb-0">
              <i className="bi bi-info-circle me-1" />
              Aucune publication n’est effectuée : la validation et la publication restent des actions distinctes sur chaque EDT.
            </p>
          </div>
        )}

      </div>
    </div>
  )
}
