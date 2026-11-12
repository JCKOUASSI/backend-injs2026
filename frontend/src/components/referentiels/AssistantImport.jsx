import React, { useCallback, useMemo, useRef, useState } from 'react'
import {
  MODES_IMPORT,
  EXTENSIONS_ACCEPTEES,
  analyserImport,
  controlerFichier,
  genererCsvAnomalies,
  importerReferentiel,
  telechargerBlob,
} from '../../services/referentiels'
import '../../styles/referentiels.css'

/**
 * Assistant d'import d'un référentiel — 5 étapes.
 *
 * 1. Téléversement contrôlé (format, taille) ;
 * 2. Prévisualisation : lignes et colonnes reconnues, colonnes manquantes,
 *    doublons, et correspondance de colonnes ajustable ;
 * 3. Validation : rapport d'erreurs par numéro de ligne, sans écriture ;
 * 4. Importation transactionnelle (ajouter / mettre à jour / les deux) ;
 * 5. Rapport final : durée, compteurs et téléchargement des anomalies.
 *
 * Aucune logique métier n'est dupliquée ici : le backend valide, décide et
 * journalise. L'écran ne fait que présenter ce que le serveur a réellement
 * analysé (jamais d'estimation locale du contenu du fichier).
 */

const ETAPES = [
  { numero: 1, libelle: 'Téléversement' },
  { numero: 2, libelle: 'Prévisualisation' },
  { numero: 3, libelle: 'Validation' },
  { numero: 4, libelle: 'Importation' },
  { numero: 5, libelle: 'Rapport' },
]

export default function AssistantImport({ slug, referentiel, onTermine, onFermer }) {
  const [etape, setEtape] = useState(1)
  const [fichier, setFichier] = useState(null)
  const [aEntete, setAEntete] = useState(true)
  const [analyse, setAnalyse] = useState(null)
  const [correspondance, setCorrespondance] = useState({})
  const [mode, setMode] = useState('les_deux')
  const [rapport, setRapport] = useState(null)
  const [erreur, setErreur] = useState('')
  const [occupe, setOccupE] = useState(false)
  const champFichier = useRef(null)

  const reinitialiser = useCallback(() => {
    setEtape(1)
    setFichier(null)
    setAnalyse(null)
    setCorrespondance({})
    setRapport(null)
    setErreur('')
    setOccupE(false)
    if (champFichier.current) champFichier.current.value = ''
  }, [])

  const choisirFichier = (evenement) => {
    const choix = evenement.target.files?.[0] || null
    const probleme = controlerFichier(choix)
    if (probleme) {
      setErreur(probleme)
      setFichier(null)
      return
    }
    setErreur('')
    setFichier(choix)
  }

  /**
   * Étapes 1 → 3 : envoi du fichier pour analyse (aucune écriture serveur).
   *
   * Le premier passage s'arrête à l'étape 2 pour présenter la
   * prévisualisation et laisser l'utilisateur corriger la correspondance de
   * colonnes ; valider cette correspondance relance l'analyse et mène à
   * l'étape 3 (rapport de validation).
   */
  const lancerAnalyse = async (etapeSuivante) => {
    if (!fichier) return
    setOccupE(true)
    setErreur('')
    try {
      const donnees = await analyserImport(slug, fichier, {
        aEntete,
        correspondance: etape >= 2 ? correspondance : undefined,
      })
      setAnalyse(donnees)
      setCorrespondance(donnees.previsualisation?.correspondance || {})
      setEtape(etapeSuivante)
    } catch (e) {
      setErreur(
        e.response?.data?.detail ||
          e.response?.data?.fichier?.[0] ||
          "Analyse impossible : vérifiez le format du fichier.",
      )
    } finally {
      setOccupE(false)
    }
  }

  /** Étape 4 : importation réelle. */
  const lancerImport = async () => {
    if (!fichier) return
    setOccupE(true)
    setErreur('')
    try {
      const resultat = await importerReferentiel(slug, fichier, {
        mode,
        aEntete,
        correspondance,
      })
      setRapport(resultat)
      setEtape(5)
      onTermine?.(resultat)
    } catch (e) {
      setErreur(
        e.response?.data?.detail ||
          e.response?.data?.fichier?.[0] ||
          "Importation impossible. Aucune donnée n'a été modifiée.",
      )
    } finally {
      setOccupE(false)
    }
  }

  const telechargerAnomalies = () => {
    const contenu = genererCsvAnomalies(rapport?.anomalies || [])
    const horodate = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')
    telechargerBlob(
      new Blob(['﻿' + contenu], { type: 'text/csv;charset=utf-8;' }),
      `anomalies_${slug}_${horodate}.csv`,
    )
  }

  /** Étape 2 : relance l'analyse avec la correspondance choisie. */
  const reanalyser = () => lancerAnalyse(3)

  const previsualisation = analyse?.previsualisation
  const validation = analyse?.validation
  const colonnesProposees = useMemo(
    () => previsualisation?.colonnes_reconnues || [],
    [previsualisation],
  )

  return (
    <div className="ref-modale-fond" role="presentation" onMouseDown={onFermer}>
      <div
        className="ref-modale ref-modale--large"
        role="dialog"
        aria-modal="true"
        aria-label={`Importer des données — ${referentiel}`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="ref-modale-entete">
          <div>
            <h2 className="ref-modale-titre">Importer des données</h2>
            <p className="ref-modale-soustitre">{referentiel}</p>
          </div>
          <button type="button" className="ref-btn-fermer" onClick={onFermer} aria-label="Fermer">
            ×
          </button>
        </header>

        <ol className="ref-import-etapes" aria-label="Progression de l'import">
          {ETAPES.map((e) => (
            <li
              key={e.numero}
              className={
                e.numero === etape
                  ? 'ref-import-etape ref-import-etape--active'
                  : e.numero < etape
                    ? 'ref-import-etape ref-import-etape--faite'
                    : 'ref-import-etape'
              }
              aria-current={e.numero === etape ? 'step' : undefined}
            >
              <span className="ref-import-etape-numero">{e.numero}</span>
              <span>{e.libelle}</span>
            </li>
          ))}
        </ol>

        <div className="ref-modale-corps">
          {erreur && (
            <div className="ref-alerte ref-alerte--erreur" role="alert">
              {erreur}
            </div>
          )}

          {/* ── Étape 1 : téléversement contrôlé ── */}
          {etape === 1 && (
            <div className="ref-import-bloc">
              <p className="ref-import-aide">
                Formats acceptés : <strong>Excel (.xlsx, .xls)</strong> et{' '}
                <strong>CSV</strong> (séparateur point-virgule ou virgule, encodage UTF-8).
                Taille maximale : 10 Mio.
              </p>
              <label className="ref-champ">
                <span className="ref-champ-libelle">Fichier à importer</span>
                <input
                  ref={champFichier}
                  type="file"
                  accept={EXTENSIONS_ACCEPTEES}
                  onChange={choisirFichier}
                  className="ref-champ-saisie"
                  data-testid="import-fichier"
                />
              </label>
              <label className="ref-champ ref-champ--case">
                <input
                  type="checkbox"
                  checked={aEntete}
                  onChange={(e) => setAEntete(e.target.checked)}
                />
                <span>La première ligne contient les en-têtes de colonnes</span>
              </label>
              {fichier && (
                <p className="ref-import-fichier">
                  <i className="bi bi-paperclip" aria-hidden="true" /> {fichier.name} —{' '}
                  {Math.max(1, Math.round(fichier.size / 1024))} Ko
                </p>
              )}
            </div>
          )}

          {/* ── Étape 2 : prévisualisation et correspondance ── */}
          {etape === 2 && previsualisation && (
            <div className="ref-import-bloc">
              <p className="ref-import-resume">
                <strong>{previsualisation.total_lignes}</strong> ligne(s) détectée(s) —{' '}
                <strong>{colonnesProposees.length}</strong> colonne(s) reconnue(s).
              </p>

              {previsualisation.colonnes_manquantes?.length > 0 && (
                <div className="ref-alerte ref-alerte--attention" role="alert">
                  Colonnes obligatoires non reconnues :{' '}
                  {previsualisation.colonnes_manquantes.map((c) => c.libelle).join(', ')}.
                  Choisissez-les manuellement ci-dessous.
                </div>
              )}

              {previsualisation.doublons?.length > 0 && (
                <div className="ref-alerte ref-alerte--attention" role="alert">
                  {previsualisation.doublons.length} doublon(s) détecté(s) dans le fichier
                  (ex. « {previsualisation.doublons[0].valeur} » lignes{' '}
                  {previsualisation.doublons[0].premiere_ligne} et{' '}
                  {previsualisation.doublons[0].ligne}).
                </div>
              )}

              <table className="ref-table ref-table--compacte">
                <thead>
                  <tr>
                    <th scope="col">Champ du référentiel</th>
                    <th scope="col">Colonne du fichier</th>
                  </tr>
                </thead>
                <tbody>
                  {(analyse?.validation ? colonnesProposees : colonnesProposees).map((colonne) => (
                    <tr key={colonne.cle}>
                      <td>{colonne.libelle}</td>
                      <td>
                        <select
                          className="ref-champ-saisie"
                          value={correspondance[colonne.cle] ?? ''}
                          onChange={(e) =>
                            setCorrespondance((prec) => ({
                              ...prec,
                              [colonne.cle]:
                                e.target.value === '' ? null : Number(e.target.value),
                            }))
                          }
                          aria-label={`Colonne du fichier pour ${colonne.libelle}`}
                        >
                          <option value="">— Non importé —</option>
                          {previsualisation.entetes_fichier.map((entete, index) => (
                            <option key={`${entete}-${index}`} value={index}>
                              {entete || `Colonne ${index + 1}`}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {previsualisation.apercu?.length > 0 && (
                <details className="ref-import-apercu">
                  <summary>Aperçu des premières lignes</summary>
                  <div className="ref-table-defilement">
                    <table className="ref-table ref-table--compacte">
                      <tbody>
                        {previsualisation.apercu.map((rangee, index) => (
                          <tr key={index}>
                            {rangee.map((cellule, position) => (
                              <td key={position}>{cellule || '—'}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              )}
            </div>
          )}

          {/* ── Étape 3 : validation ── */}
          {etape === 3 && validation && (
            <div className="ref-import-bloc">
              <p className="ref-import-resume">
                <strong>{validation.lignes_valides}</strong> ligne(s) valide(s) —{' '}
                <strong>{validation.lignes_en_erreur}</strong> ligne(s) en erreur sur{' '}
                {validation.total_lignes} analysée(s).
              </p>

              {validation.erreurs?.length > 0 && (
                <div className="ref-table-defilement">
                  <table className="ref-table ref-table--compacte">
                    <thead>
                      <tr>
                        <th scope="col">Ligne</th>
                        <th scope="col">Colonne</th>
                        <th scope="col">Valeur</th>
                        <th scope="col">Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {validation.erreurs.map((anomalie, index) => (
                        <tr key={`${anomalie.ligne}-${index}`}>
                          <td>{anomalie.ligne}</td>
                          <td>{anomalie.colonne || '—'}</td>
                          <td>{anomalie.valeur || '—'}</td>
                          <td>{anomalie.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {validation.lignes_valides === 0 && (
                <div className="ref-alerte ref-alerte--erreur" role="alert">
                  Aucune ligne valide : corrigez le fichier avant de poursuivre.
                </div>
              )}

              <fieldset className="ref-champ">
                <legend className="ref-champ-libelle">Mode d'importation</legend>
                {MODES_IMPORT.map((option) => (
                  <label key={option.cle} className="ref-champ--radio">
                    <input
                      type="radio"
                      name="mode-import"
                      value={option.cle}
                      checked={mode === option.cle}
                      onChange={() => setMode(option.cle)}
                    />
                    <span>
                      <strong>{option.libelle}</strong>
                      <br />
                      <small>{option.description}</small>
                    </span>
                  </label>
                ))}
              </fieldset>
            </div>
          )}

          {/* ── Étape 4 : confirmation ── */}
          {etape === 4 && (
            <div className="ref-import-bloc">
              <p className="ref-import-resume">
                Prêt à importer <strong>{validation?.lignes_valides ?? 0}</strong> ligne(s)
                valide(s) en mode «{' '}
                {MODES_IMPORT.find((m) => m.cle === mode)?.libelle ?? mode} ».
              </p>
              <p className="ref-import-aide">
                L'importation est <strong>transactionnelle</strong> : elle réussit entièrement
                ou n'a aucun effet. Ne fermez pas cette fenêtre pendant l'opération.
              </p>
            </div>
          )}

          {/* ── Étape 5 : rapport final ── */}
          {etape === 5 && rapport && (
            <div className="ref-import-bloc">
              <p className="ref-import-resume">{rapport.resume}</p>
              <ul className="ref-import-compteurs">
                <li>
                  <span className="ref-import-compteur">{rapport.crees}</span> création(s)
                </li>
                <li>
                  <span className="ref-import-compteur">{rapport.mis_a_jour}</span> mise(s) à jour
                </li>
                <li>
                  <span className="ref-import-compteur">{rapport.ignores}</span> ignorée(s)
                </li>
                <li>
                  <span className="ref-import-compteur">{rapport.nb_anomalies}</span> anomalie(s)
                </li>
                <li>
                  durée : <strong>{rapport.duree_secondes} s</strong>
                </li>
              </ul>
              {rapport.nb_anomalies > 0 && (
                <button
                  type="button"
                  className="ref-btn ref-btn--secondaire"
                  onClick={telechargerAnomalies}
                >
                  <i className="bi bi-download" aria-hidden="true" /> Télécharger les anomalies
                  (CSV)
                </button>
              )}
            </div>
          )}
        </div>

        <footer className="ref-modale-pied">
          {etape === 1 && (
            <button
              type="button"
              className="ref-btn ref-btn--primaire"
              disabled={!fichier || occupe}
              onClick={() => lancerAnalyse(2)}
            >
              {occupe ? 'Analyse…' : 'Analyser le fichier'}
            </button>
          )}
          {etape === 2 && (
            <>
              <button
                type="button"
                className="ref-btn ref-btn--secondaire"
                onClick={() => setEtape(1)}
              >
                Précédent
              </button>
              <button
                type="button"
                className="ref-btn ref-btn--primaire"
                disabled={occupe}
                onClick={reanalyser}
              >
                {occupe ? 'Validation…' : 'Valider la correspondance'}
              </button>
            </>
          )}
          {etape === 3 && (
            <>
              <button
                type="button"
                className="ref-btn ref-btn--secondaire"
                onClick={() => setEtape(2)}
                disabled={occupe}
              >
                Précédent
              </button>
              <button
                type="button"
                className="ref-btn ref-btn--primaire"
                disabled={occupe || (validation?.lignes_valides ?? 0) === 0}
                onClick={() => setEtape(4)}
              >
                Continuer
              </button>
            </>
          )}
          {etape === 4 && (
            <>
              <button
                type="button"
                className="ref-btn ref-btn--secondaire"
                onClick={() => setEtape(3)}
                disabled={occupe}
              >
                Précédent
              </button>
              <button
                type="button"
                className="ref-btn ref-btn--primaire"
                disabled={occupe}
                onClick={lancerImport}
              >
                {occupe ? 'Importation en cours…' : 'Importer'}
              </button>
            </>
          )}
          {etape === 5 && (
            <>
              <button
                type="button"
                className="ref-btn ref-btn--secondaire"
                onClick={reinitialiser}
              >
                Importer un autre fichier
              </button>
              <button type="button" className="ref-btn ref-btn--primaire" onClick={onFermer}>
                Terminer
              </button>
            </>
          )}
          <button type="button" className="ref-btn ref-btn--lien" onClick={onFermer}>
            Annuler
          </button>
        </footer>
      </div>
    </div>
  )
}
