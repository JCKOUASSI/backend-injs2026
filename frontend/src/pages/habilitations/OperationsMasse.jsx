/**
 * OperationsMasse (U4/U5, C3) — import tabulaire : prévisualisation
 * intégrale, exécution en UNE transaction et annulation unitaire par
 * RÉFÉRENCE d'exécution. Tant que le drapeau ``flag.curp_import_masse`` est
 * fermé, l'écriture renvoie un 403 explicite : l'aperçu reste utilisable.
 */
import { useState } from 'react'
import {
  simulerImport, executerImport, annulerImport, recupererImport,
  messageErreur,
} from '@/services/habilitations'
import { analyserCsv, lignesCsvVersImport } from '@/utils/habilitations'
import { useToast } from '@/context/ToastContext'
import MotifModal from './MotifModal'
import './habilitations.css'

const ENTETE = 'identifiant;nom;prenoms;email;mot_de_passe;roles;canal'
const EXEMPLE = 'curp_demo1;Traore;Salif;demo1@injs.ci;Essai#2026;ENSEIGNANT;MOBILE'

function telechargerModele() {
  const blob = new Blob([`${ENTETE}\n${EXEMPLE}\n`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'modele_import_comptes.csv'
  a.click()
  URL.revokeObjectURL(url)
}

function RapportExecution({ execution, onAnnule }) {
  const { showToast } = useToast()
  const [aAnnuler, setAAnnuler] = useState(null)

  const confirmer = async (motif) => {
    try {
      const resultat = await annulerImport(aAnnuler.reference, motif)
      showToast(`Import ${resultat.reference} annulé : tous les comptes sont désactivés.`, 'success')
      setAAnnuler(null)
      onAnnule(resultat)
    } catch (e) {
      showToast(messageErreur(e), 'error')
    }
  }

  return (
    <div className="hab-carte" data-testid="rapport-execution">
      <h3 className="h6">
        Exécution <span className="font-monospace">{execution.reference}</span>
      </h3>
      <p className="mb-1">
        État : <strong>{execution.statut_libelle || execution.statut}</strong> ·{' '}
        {execution.crees} compte(s) créé(s) sur {execution.total} ligne(s)
        {execution.nom_fichier ? ` · ${execution.nom_fichier}` : ''}
      </p>
      {execution.statut === 'ANNULE' && (
        <div className="hab-avertissement">
          <i className="bi bi-arrow-counterclockwise me-1" />
          Import annulé{execution.motif_annulation ? ` : ${execution.motif_annulation}` : '.'}{' '}
          Aucun compte n'a été supprimé physiquement : tous ont été désactivés (S5).
        </div>
      )}
      <div className="d-flex gap-2 mt-2 flex-wrap">
        {execution.statut === 'TERMINE' && (
          <button className="btn btn-outline-danger btn-sm" data-testid="bouton-annuler-import"
                  onClick={() => setAAnnuler(execution)}>
            <i className="bi bi-arrow-counterclockwise me-1" />Annuler tout cet import
          </button>
        )}
      </div>
      {aAnnuler && (
        <MotifModal
          titre="Annuler l'import"
          action={`Annuler l'exécution ${aAnnuler.reference} (${execution.crees} comptes)`}
          consequences="Chaque compte créé par cet import passe en DÉSACTIVÉ (machine à états A5) ; aucune suppression physique."
          confirmationLabel="Annuler l'import"
          onConfirmer={confirmer}
          onAnnuler={() => setAAnnuler(null)}
        />
      )}
    </div>
  )
}

export default function OperationsMasse() {
  const { showToast } = useToast()
  const [lignes, setLignes] = useState([])
  const [nomFichier, setNomFichier] = useState('')
  const [rapport, setRapport] = useState(null)
  const [execution, setExecution] = useState(null)
  const [enCours, setEnCours] = useState(false)
  const [referenceARetrouver, setReferenceARetrouver] = useState('')

  const lireFichier = async (fichier) => {
    setEnCours(true)
    try {
      const texte = await fichier.text()
      const parsed = lignesCsvVersImport(analyserCsv(texte))
      if (parsed.length === 0) {
        showToast("Le fichier ne contient aucune ligne de données.", 'error')
      } else {
        setLignes(parsed)
        setNomFichier(fichier.name)
        setRapport(await simulerImport(parsed))
        setExecution(null)
      }
    } catch (e) {
      showToast(messageErreur(e, "Lecture du fichier impossible."), 'error')
    } finally {
      setEnCours(false)
    }
  }

  const executer = async () => {
    setEnCours(true)
    try {
      const resultat = await executerImport(lignes, nomFichier)
      setExecution(resultat)
      setRapport(null)
      showToast(`Import ${resultat.reference} exécuté : ${resultat.crees} compte(s).`, 'success')
    } catch (e) {
      showToast(messageErreur(e), 'error')
    } finally {
      setEnCours(false)
    }
  }

  const retrouver = async (e) => {
    e?.preventDefault()
    try {
      setExecution(await recupererImport(referenceARetrouver.trim()))
    } catch (e2) {
      showToast(messageErreur(e2, "Exécution introuvable."), 'error')
    }
  }

  const aucuneErreur = rapport && rapport.erreurs === 0 && lignes.length > 0

  return (
    <section data-testid="ecran-operations-masse">
      <div className="hab-carte">
        <h2 className="h5">Création de comptes en masse</h2>
        <div className="hab-avertissement">
          <i className="bi bi-info-circle me-1" />
          Prévisualisation intégrale, puis exécution en une seule transaction (une seule ligne en
          erreur annule tout). Chaque exécution reçoit une référence permettant d'annuler
          globalement le lot. Aucune suppression physique n'est jamais faite.
        </div>
        <div className="d-flex gap-2 align-items-center flex-wrap">
          <input type="file" accept=".csv,text/csv" className="form-control" style={{ maxWidth: 420 }}
                 data-testid="fichier-import"
                 onChange={(e) => e.target.files[0] && lireFichier(e.target.files[0])} />
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={telechargerModele}>
            <i className="bi bi-download me-1" />Modèle CSV
          </button>
        </div>
        {enCours && <p className="hab-muted mt-2">Traitement…</p>}
      </div>

      {rapport && (
        <div className="hab-carte" data-testid="rapport-import">
          <h3 className="h6">Rapport de prévisualisation</h3>
          <p>
            {rapport.total} ligne(s) · <span className="hab-diff-gagne">{rapport.valides} valide(s)</span> ·{' '}
            <span className="hab-diff-perdu">{rapport.erreurs} en erreur</span>
          </p>
          <table className="hab-table">
            <thead><tr><th>Ligne</th><th>Identifiant</th><th>Nom</th><th>Rôles</th><th>État / problèmes</th></tr></thead>
            <tbody>
              {rapport.lignes.map((l) => (
                <tr key={l.numero} data-testid={`ligne-import-${l.numero}`}>
                  <td>{l.numero}</td>
                  <td>{l.valeurs.username}</td>
                  <td>{[l.valeurs.prenoms, l.valeurs.nom].filter(Boolean).join(' ')}</td>
                  <td>{l.valeurs.roles}</td>
                  <td>
                    {l.etat === 'VALIDE'
                      ? <span className="hab-diff-gagne">Valide{l.roles ? ` — ${l.roles.join(', ')}` : ''}</span>
                      : <span className="hab-diff-perdu">{l.problemes.join(' ')}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button className="btn btn-success mt-2" data-testid="bouton-ecrire"
                  disabled={!aucuneErreur || enCours} onClick={executer}
                  title={aucuneErreur ? "Crée tous les comptes en une transaction" : "Corrigez les lignes en erreur"}>
            <i className="bi bi-hdd-stack me-1" />Exécuter l'import ({rapport.valides} comptes)
          </button>
        </div>
      )}

      {execution && <RapportExecution execution={execution} onAnnule={setExecution} />}

      <div className="hab-carte">
        <h3 className="h6">Retrouver / annuler une exécution</h3>
        <form className="d-flex gap-2" onSubmit={retrouver}>
          <input className="form-control" style={{ maxWidth: 300 }} placeholder="Référence IMP-AAAAMMJJ-NNNN"
                 value={referenceARetrouver} data-testid="reference-recherche"
                 onChange={(e) => setReferenceARetrouver(e.target.value)} />
          <button className="btn btn-outline-secondary btn-sm" data-testid="bouton-retrouver">Retrouver</button>
        </form>
      </div>
    </section>
  )
}
