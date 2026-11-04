import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { formatApiErrors } from '../../utils/apiErrors'

/**
 * GET-INJS — « Importer les étudiants inscrits » (Situation 2 · fichier
 * externe). Fenêtre dédiée du sous-module « Import étudiants » : dépôt du
 * fichier, année cible, reconstruction du parcours, génération enchaînée,
 * colonnes acceptées, situations couvertes et journal des imports.
 *
 * L'écran expose uniquement des résultats réels du moteur d'import :
 * rapport ligne par ligne motivé, lots du journal reconstruits depuis les
 * lignes rattachées. Aucun compteur n'est inventé.
 */

function Compte({ libelle, valeur }) {
  return (
    <div className="getinjs-compte">
      <span className="getinjs-compte-valeur">{valeur ?? '—'}</span>
      <span className="getinjs-compte-libelle">{libelle}</span>
    </div>
  )
}

function formatDateJournal(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const jour = d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit' })
  const heure = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  return `${jour} ${heure}`
}

/** Modèle CSV officiel : les en-têtes canoniques reconnus par le moteur. */
const MODELE_CSV = 'matricule;nom;prenoms;sexe;date_naissance;filiere_code;formation;niveau;semestre;groupe;vague;statut\n'

function telechargerBlob(contenu, nom, type = 'text/csv;charset=utf-8') {
  const blob = new Blob([contenu], { type })
  const url = URL.createObjectURL(blob)
  const lien = document.createElement('a')
  lien.href = url
  lien.download = nom
  document.body.appendChild(lien)
  lien.click()
  lien.remove()
  URL.revokeObjectURL(url)
}

const COLONNES_ACCEPTEES = [
  {
    titre: 'Matricule', obligatoire: true,
    alias: 'matricule, code_etudiant, identifiant, numero_matricule',
  },
  {
    titre: 'Identité',
    alias: 'nom, prenoms, sexe, date_naissance',
  },
  {
    titre: 'Cursus',
    alias: 'formation, filiere_code, code_filiere',
  },
  {
    titre: 'Parcours',
    alias: 'parcours, specialite, option',
  },
  {
    titre: 'Classement',
    alias: 'niveau, semestre, groupe, vague',
  },
  {
    titre: 'Scolarité',
    alias: 'statut, statut_inscription, etat',
  },
]

export default function ImportEtudiants() {
  const { showToast } = useToast()
  const [annees, setAnnees] = useState([])
  const [anneeId, setAnneeId] = useState('')
  const [fichier, setFichier] = useState(null)
  const [rapport, setRapport] = useState(null)
  const [journal, setJournal] = useState([])
  const [enCours, setEnCours] = useState('')
  const [reconstruire, setReconstruire] = useState(true)
  const [genererApres, setGenererApres] = useState(true)
  const [semestreGenere, setSemestreGenere] = useState('')
  const [survol, setSurvol] = useState(false)
  const inputFichier = useRef(null)

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

  const chargerJournal = useCallback(async (id) => {
    if (!id) { setJournal([]); return }
    try {
      const { data } = await api.get(
        '/edts/lmd/import/inscrits/journal/', { params: { annee: id } })
      setJournal(Array.isArray(data?.lots) ? data.lots : [])
    } catch { setJournal([]) }
  }, [])

  useEffect(() => { chargerJournal(anneeId) }, [anneeId, chargerJournal])

  const enchaineGeneration = async () => {
    const annee = annees.find((a) => String(a.id) === String(anneeId))
    const horodatage = new Date().toLocaleString('fr-FR')
    const { data: campagne } = await api.post('/edts/campagnes/', {
      annee_academique_id: Number(anneeId),
      libelle: `Génération après import ${annee?.libelle || anneeId} — ${horodatage}`,
      semaines: [1],
      perimetre: {
        formations: [],
        niveaux: [],
        groupes: [],
        semestres: semestreGenere ? [Number(semestreGenere)] : [],
      },
      parametres: {
        persister: true,
        remplacer: true,
        inclure_maquette: true,
        publier_direct: false,
      },
    })
    await api.post(`/edts/campagnes/${campagne.id}/donnees-pretes/`, {})
    await api.post(`/edts/campagnes/${campagne.id}/demarrer/`, { asynchrone: true })
    return campagne
  }

  const envoyerFichier = async (mode) => {
    if (!anneeId) return showToast('Choisissez une année académique.', 'error')
    if (!fichier) return showToast('Choisissez un fichier (.csv ou .xlsx).', 'error')

    setEnCours(mode)
    setRapport(null)
    const donnees = new FormData()
    donnees.append('annee_academique_id', anneeId)
    donnees.append('reconstruire_parcours', reconstruire ? 'true' : 'false')
    donnees.append('fichier', fichier)

    const chemin = mode === 'analyse'
      ? '/edts/lmd/import/inscrits/analyser/'
      : '/edts/lmd/import/inscrits/'

    try {
      const { data } = await api.post(chemin, donnees, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setRapport(data)
      if (mode === 'import') {
        showToast(`${data.creees || 0} inscription(s) créée(s), ${data.mises_a_jour || 0} mise(s) à jour.`, 'success')
        chargerJournal(anneeId)
        if (genererApres) {
          try {
            await enchaineGeneration()
            showToast(
              'Génération annuelle lancée en arrière-plan : suivez-la dans '
              + '« Campagnes de génération ».', 'success')
          } catch (errGen) {
            const corps = errGen?.response?.data
            showToast(
              corps?.detail?.explication || corps?.motif_echec
              || 'Import réussi, mais la génération enchaînée a été refusée.',
              'error',
            )
          }
        }
      } else {
        showToast(`Analyse terminée : ${data.lignes_valides} ligne(s) exploitable(s).`, 'info')
      }
    } catch (err) {
      const corps = err?.response?.data
      if (corps && typeof corps === 'object') setRapport(corps)
      showToast(corps?.motif_echec || formatApiErrors(err?.response?.data) || 'Import refusé.', 'error')
    } finally {
      setEnCours('')
    }
  }

  const exporterJournal = () => {
    const lignes = [
      'fichier;date;lignes;importes;ignores;formations;groupes;vagues',
      ...journal.map((lot) => [
        lot.fichier, formatDateJournal(lot.recu_le), lot.lignes, lot.inscrits,
        lot.ignores, lot.formations, lot.groupes, lot.vagues,
      ].join(';')),
    ]
    telechargerBlob(`${lignes.join('\n')}\n`, 'journal-imports.csv')
  }

  const anneeChoisie = useMemo(
    () => annees.find((a) => String(a.id) === String(anneeId)),
    [annees, anneeId],
  )

  return (
    <div className="getinjs gen-page imp-page">
      <div className="gen-entete">
        <div>
          <span className="gen-sur">Situation 2 · Fichier externe</span>
          <h2 className="gen-titre">Importer les étudiants inscrits</h2>
          <p className="gen-sous">
            Recevoir un fichier d'inscrits produit hors application (scolarité,
            rectorat, partenaire) et générer malgré tout les emplois du temps
            de l'année. Le module reconnaît filière, formation, niveau, groupe
            et vague lorsque le parcours LMD n'existe pas encore.
          </p>
        </div>
        <div className="gen-actions">
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm"
            onClick={() => telechargerBlob(MODELE_CSV, 'modele-inscrits.csv')}
          >
            <i className="bi bi-filetype-csv me-1" aria-hidden="true"></i>
            Modèle CSV
          </button>
          <Link to="/edt/generation-annuelle" className="btn btn-outline-primary btn-sm">
            <i className="bi bi-gear me-1" aria-hidden="true"></i>
            Tableau de génération
          </Link>
        </div>
      </div>

      <div className="row g-3 mb-3">
        <div className="col-xl-7">
          <div className="card h-100 imp-card-depot">
            <div className="card-body">
              <div
                className={`imp-dropzone ${survol ? 'is-survol' : ''}`}
                onDragOver={(e) => { e.preventDefault(); setSurvol(true) }}
                onDragLeave={() => setSurvol(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setSurvol(false)
                  setFichier(e.dataTransfer.files?.[0] || null)
                }}
              >
                <span className="imp-dropzone-icone">
                  <i className="bi bi-cloud-arrow-up" aria-hidden="true"></i>
                </span>
                <span className="imp-dropzone-titre">
                  Déposez ou sélectionnez le fichier des inscrits
                </span>
                <span className="imp-dropzone-sous">
                  CSV, XLSX ou XLS · 20 Mo maximum
                </span>
                {fichier && (
                  <span className="imp-fichier-choisi">
                    <i className="bi bi-file-earmark-check me-1" aria-hidden="true"></i>
                    {fichier.name}
                  </span>
                )}
              </div>

              <div className="d-flex flex-wrap align-items-center gap-2 mt-3">
                <button
                  type="button"
                  className="btn btn-outline-primary btn-sm"
                  onClick={() => inputFichier.current?.click()}
                >
                  <i className="bi bi-folder2-open me-1" aria-hidden="true"></i>
                  Parcourir
                </button>
                <button
                  type="button"
                  className="btn btn-link btn-sm imp-modele"
                  onClick={() => telechargerBlob(MODELE_CSV, 'modele-inscrits.csv')}
                >
                  Télécharger le modèle CSV
                </button>
                <input
                  id="getinjs-fichier"
                  ref={inputFichier}
                  type="file"
                  className="d-none"
                  accept=".csv,.txt,.xlsx,.xlsm"
                  aria-label="Fichier des inscrits"
                  onChange={(e) => setFichier(e.target.files?.[0] || null)}
                />
              </div>

              <div className="d-flex flex-wrap align-items-center gap-2 mt-3">
                <button
                  type="button"
                  className="btn btn-dark gen-btn-lancer"
                  onClick={() => envoyerFichier('import')}
                  disabled={enCours !== ''}
                >
                  <i className="bi bi-upload me-1" aria-hidden="true"></i>
                  {enCours === 'import' ? 'Import…' : 'Importer les inscrits'}
                </button>
                <button
                  type="button"
                  className="btn btn-outline-primary"
                  onClick={() => envoyerFichier('analyse')}
                  disabled={enCours !== ''}
                >
                  <i className="bi bi-search me-1" aria-hidden="true"></i>
                  {enCours === 'analyse' ? 'Analyse…' : 'Analyser sans importer'}
                </button>
                <span className="text-muted small">
                  Automatique : un matricule déjà présent n'est jamais dupliqué
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="col-xl-5">
          <div className="card h-100">
            <div className="card-body">
              <label className="form-label gen-label" htmlFor="imp-annee">Année académique cible</label>
              <select
                id="imp-annee"
                className="form-select mb-3"
                value={anneeId}
                onChange={(e) => setAnneeId(e.target.value)}
              >
                <option value="">— choisir —</option>
                {annees.map((a) => (
                  <option key={a.id} value={a.id}>
                    {`Année académique ${a.libelle}`}{a.courante ? ' (courante)' : ''}
                  </option>
                ))}
              </select>

              <div className="form-check mb-1">
                <input
                  className="form-check-input" type="checkbox" id="imp-reconstruire"
                  checked={reconstruire}
                  onChange={(e) => setReconstruire(e.target.checked)}
                />
                <label className="form-check-label fw-semibold" htmlFor="imp-reconstruire">
                  Reconstruire le parcours
                </label>
                <div className="small text-muted ms-4">
                  Créer groupes et vagues manquants au besoin — formations et
                  niveaux doivent exister au référentiel.
                </div>
              </div>

              <div className="form-check mb-3">
                <input
                  className="form-check-input" type="checkbox" id="imp-generer"
                  checked={genererApres}
                  onChange={(e) => setGenererApres(e.target.checked)}
                />
                <label className="form-check-label fw-semibold" htmlFor="imp-generer">
                  Générer les EDT après import
                </label>
                <div className="small text-muted ms-4">
                  Enchaîner la génération annuelle dès que l'import est terminé
                </div>
              </div>

              <label className="form-label gen-label" htmlFor="imp-semestre">Semestre à générer (optionnel)</label>
              <select
                id="imp-semestre"
                className="form-select"
                value={semestreGenere}
                onChange={(e) => setSemestreGenere(e.target.value)}
                disabled={!genererApres}
              >
                <option value="">Tous / année</option>
                {['1', '2', '3', '4', '5', '6', '7', '8', '9', '10'].map((n) => (
                  <option key={n} value={n}>{`Semestre ${n} (S${n})`}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {rapport && (
        <div className="card mb-3">
          <div className="card-header">
            <strong>Résultat de {rapport.applique ? 'l’import' : 'l’analyse'}</strong>
            {anneeChoisie && (
              <span className="text-muted small ms-2">
                Année académique {anneeChoisie.libelle}
              </span>
            )}
          </div>
          <div className="card-body">
            <div className="getinjs-comptes">
              <Compte libelle="lignes lues" valeur={rapport.lignes_lues} />
              <Compte libelle="valides" valeur={rapport.lignes_valides} />
              <Compte libelle="rejetées" valeur={rapport.lignes_rejetees} />
              <Compte libelle="créées" valeur={rapport.creees} />
              <Compte libelle="mises à jour" valeur={rapport.mises_a_jour} />
              <Compte libelle="effectif" valeur={rapport.effectif_total} />
            </div>

            {rapport.motif_echec && (
              <div className="alert alert-danger mt-3" role="alert">
                <strong>Import refusé — {rapport.motif_echec}</strong>
                {rapport.detail?.explication && <div>{rapport.detail.explication}</div>}
                {rapport.detail?.colonnes_manquantes && (
                  <div>Colonnes manquantes : {rapport.detail.colonnes_manquantes.join(', ')}</div>
                )}
              </div>
            )}

            {rapport.erreurs?.length > 0 && (
              <div className="table-responsive mt-3">
                <table className="table table-sm" aria-label="Lignes rejetées — chaque rejet est motivé">
                  <caption className="text-muted small">
                    Lignes rejetées — chaque rejet est motivé
                    {rapport.erreurs_tronquees > 0 && ` (${rapport.erreurs_tronquees} de plus non affichées)`}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Ligne</th>
                      <th scope="col">Motif</th>
                      <th scope="col">Détail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rapport.erreurs.map((erreur) => (
                      <tr key={`${erreur.ligne}-${erreur.motif}`}>
                        <td>{erreur.ligne}</td>
                        <td><span className="badge badge-danger">{erreur.motif}</span></td>
                        <td>{erreur.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {rapport.cohortes?.length > 0 && (
              <div className="table-responsive mt-3">
                <table className="table table-sm" aria-label="Cohortes reconnues">
                  <caption className="text-muted small">Cohortes reconnues</caption>
                  <thead>
                    <tr>
                      <th scope="col">Formation</th>
                      <th scope="col">Niveau</th>
                      <th scope="col">Groupe</th>
                      <th scope="col">Vague</th>
                      <th scope="col" className="text-end">Effectif</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rapport.cohortes.map((c, index) => (
                      <tr key={`${c.formation}-${c.groupe}-${c.vague}-${index}`}>
                        <td>{c.formation}</td>
                        <td>{c.niveau}</td>
                        <td>{c.groupe || '—'}</td>
                        <td>{c.vague || '—'}</td>
                        <td className="text-end">{c.effectif}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="row g-3 mb-3">
        <div className="col-xl-7">
          <div className="card h-100">
            <div className="card-header">
              <strong>Colonnes acceptées</strong>
              <div className="text-muted small">
                Détection automatique par en-tête, insensible aux accents et à la casse
              </div>
            </div>
            <div className="card-body">
              <div className="imp-colonnes">
                {COLONNES_ACCEPTEES.map((colonne) => (
                  <div key={colonne.titre} className="imp-colonne">
                    <span className="imp-colonne-titre">
                      {colonne.titre}
                      {colonne.obligatoire && <span className="imp-obligatoire">obligatoire</span>}
                    </span>
                    <span className="imp-colonne-alias">{colonne.alias}</span>
                  </div>
                ))}
              </div>
              <p className="imp-note">
                Les colonnes restantes sont ignorées (elles sont listées dans le
                rapport). Sans matricule, la ligne est rejetée avec son motif :
                aucun identifiant n'est inventé. Colonnes obligatoires :
                matricule, nom, formation et niveau.
              </p>
            </div>
          </div>
        </div>

        <div className="col-xl-5">
          <div className="card h-100">
            <div className="card-header">
              <strong>Situations couvertes</strong>
              <div className="text-muted small">
                Deux parcours, un seul moteur de planification
              </div>
            </div>
            <div className="card-body">
              <div className="imp-situation">
                <span className="imp-situation-titre">
                  <i className="bi bi-diagram-3 me-1" aria-hidden="true"></i>
                  Situation 1 — Inscrits dans l'application
                </span>
                <p>
                  Les inscriptions administratives validées dans INJS2026
                  (filière, groupes, vagues et étudiants déjà rattachés à un
                  parcours LMD) alimentent directement le moteur.
                </p>
              </div>
              <div className="imp-situation">
                <span className="imp-situation-titre">
                  <i className="bi bi-file-earmark-arrow-up me-1" aria-hidden="true"></i>
                  Situation 2 — Fichier externe sans parcours
                </span>
                <p>
                  Le fichier arrive sans parcours dans l'application : le
                  module rattache chaque ligne au référentiel INJS 2026 et
                  crée au besoin les groupes et vagues manquants. Une
                  formation ou un niveau inconnu est rejeté, ligne par ligne,
                  avec son motif.
                </p>
              </div>
              <div className="imp-situation">
                <span className="imp-situation-titre">
                  <i className="bi bi-shield-check me-1" aria-hidden="true"></i>
                  Idempotence et sécurité
                </span>
                <p>
                  Réimporter le même fichier ne duplique ni étudiant ni
                  inscription. Le matricule est la clé d'unicité, complétée
                  par l'étudiant, la formation et l'année académique.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header d-flex align-items-center">
          <div>
            <strong>Journal des imports</strong>
            <div className="text-muted small">
              Chaque réception laisse une trace auditable : seuls les lots
              rattachés sont conservés, aucun rejet n'est inventé.
            </div>
          </div>
          <button
            type="button"
            className="btn btn-outline-primary btn-sm ms-auto"
            onClick={exporterJournal}
            disabled={journal.length === 0}
          >
            <i className="bi bi-download me-1" aria-hidden="true"></i>
            Exporter
          </button>
        </div>
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0 gen-table">
            <thead>
              <tr>
                <th scope="col">Fichier</th>
                <th scope="col">Date</th>
                <th scope="col">Lignes</th>
                <th scope="col">Importés</th>
                <th scope="col">Ignorés</th>
                <th scope="col">Formations</th>
                <th scope="col">Groupes</th>
                <th scope="col">Vagues</th>
                <th scope="col">Alertes</th>
                <th scope="col">Durée</th>
              </tr>
            </thead>
            <tbody>
              {journal.length === 0 ? (
                <tr>
                  <td colSpan="10" className="text-center text-muted py-4">
                    Aucun import rattaché pour cette année académique.
                  </td>
                </tr>
              ) : journal.map((lot) => (
                <tr key={`${lot.fichier}-${lot.empreinte}`}>
                  <td className="fw-semibold">
                    <i className="bi bi-file-earmark-spreadsheet me-1 imp-fichier-icone" aria-hidden="true"></i>
                    {lot.fichier}
                  </td>
                  <td className="text-nowrap">{formatDateJournal(lot.recu_le)}</td>
                  <td className="fw-bold">{lot.lignes}</td>
                  <td>{lot.inscrits}</td>
                  <td>{lot.ignores}</td>
                  <td>{lot.formations}</td>
                  <td>{lot.groupes}</td>
                  <td>{lot.vagues}</td>
                  <td><span className="text-muted">—</span></td>
                  <td><span className="text-muted">—</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="imp-pied">
        GET INJS APP · Module intégré à INJS2026 — Institut National de la
        Jeunesse et des Sports (INJS) Marcory · Moteur LMD déterministe
      </p>
    </div>
  )
}
