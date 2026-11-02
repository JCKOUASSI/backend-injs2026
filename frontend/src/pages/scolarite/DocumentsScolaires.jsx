import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { useDebounce } from '../../hooks/useDebounce'
import {
  getAnneeCourante,
  getEffectifsGroupes,
  getRefFormations,
  getRefScolarite,
  messageErreur,
} from '../../services/scolarite'
import '../../styles/candidatures.css'
import '../../styles/admissions.css'
import '../../styles/documents.css'

/** Réponses API tantôt liste, tantôt objet paginé : toujours une liste. */
const enListe = (res) => {
  const data = res?.data
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.resultats)) return data.resultats
  if (Array.isArray(data?.results)) return data.results
  return []
}

/**
 * Documents scolaires — page dédiée (remplace l'ancien descripteur générique).
 *
 * Deux familles bien séparées, car les documents ne puisent pas aux mêmes
 * sources : le **cycle LMD** (listes des groupes TD/TP issus des
 * affectations) et la **formation continue** (listes d'auditeurs, fiches de
 * notes de module, relevés individuels historiques). L'ancien écran
 * mélangeait les deux référentiels (groupes LMD envoyés à l'export
 * auditeurs, formations LMD pour des modules de formation continue…),
 * ce qui produisait des documents vides ou des erreurs.
 */
export default function DocumentsScolaires() {
  const { showToast } = useToast()
  const [annee, setAnnee] = useState(null)
  const [enCours, setEnCours] = useState(null)

  useEffect(() => {
    getAnneeCourante().then(setAnnee).catch(() => setAnnee(null))
  }, [])

  const telecharger = useCallback(async (cle, chemin, libelle) => {
    setEnCours(cle)
    try {
      const { blob, fileName } = await api.getBlob(chemin)
      const url = URL.createObjectURL(blob)
      const lien = window.document.createElement('a')
      lien.href = url
      lien.download = fileName || 'document.pdf'
      window.document.body.appendChild(lien)
      lien.click()
      lien.remove()
      URL.revokeObjectURL(url)
      showToast(`${libelle} téléchargé.`)
    } catch (err) {
      showToast(messageErreur(err, 'Génération refusée par le serveur.'), 'error')
    } finally {
      setEnCours(null)
    }
  }, [showToast])

  return (
    <div className="cand-page">
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-file-earmark-text"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">Scolarité — Documents</span>
            <h1 className="cand-hero-title">Documents scolaires</h1>
            <p className="cand-hero-sub">
              Listes de classe, fiches de notes et relevés produits par le serveur
              {annee ? <> pour l’année <strong>{annee.libelle}</strong></> : ''}.
              Le droit de générer chaque document est vérifié côté serveur à chaque appel.
            </p>
          </div>
        </div>
        <div className="cand-hero-actions">
          <span className="cand-count-pill">
            <i className="bi bi-files" aria-hidden="true"></i> 4 documents
          </span>
          <span className="cand-count-pill">
            <i className="bi bi-gear" aria-hidden="true"></i> Générateur de documents
          </span>
        </div>
      </div>

      <h2 className="doc-section">
        <i className="bi bi-mortarboard" aria-hidden="true"></i>
        Cycle LMD
      </h2>
      <div className="doc-grille">
        <CarteListeGroupe annee={annee} enCours={enCours} telecharger={telecharger} />
        <article className="doc-carte doc-carte--lien">
          <div className="doc-carte-entete">
            <span className="doc-icone doc-icone--violet" aria-hidden="true">
              <i className="bi bi-file-earmark-ruled"></i>
            </span>
            <div>
              <h3 className="doc-carte-titre">Relevés de notes LMD</h3>
              <p className="doc-carte-desc">
                Les relevés individuels du cycle LMD (UE, crédits ECTS, décisions
                de jury) se génèrent depuis le module Évaluations.
              </p>
            </div>
          </div>
          <div className="doc-carte-pied">
            <Link className="doc-lien" to="/evaluations/releves">
              Ouvrir les relevés de notes
              <i className="bi bi-arrow-right" aria-hidden="true"></i>
            </Link>
          </div>
        </article>
      </div>

      <h2 className="doc-section">
        <i className="bi bi-briefcase" aria-hidden="true"></i>
        Formation continue (auditeurs)
      </h2>
      <div className="doc-grille">
        <CarteListeClasse enCours={enCours} telecharger={telecharger} />
        <CarteFicheModule enCours={enCours} telecharger={telecharger} />
        <CarteReleveEtudiant enCours={enCours} telecharger={telecharger} />
      </div>

      <p className="doc-note">
        <i className="bi bi-shield-check" aria-hidden="true"></i>
        Documents générés par le serveur : vos droits sont revérifiés à chaque génération.
      </p>
    </div>
  )
}

/** Boutons de format (PDF rouge doux, Excel vert) d'une carte document. */
function BoutonsFormats({ formats, prefixe, actif, enCours, onGenerer }) {
  return (
    <>
      {formats.map((format) => {
        const cle = `${prefixe}-${format.id}`
        return (
          <button
            key={format.id}
            type="button"
            className={`doc-btn doc-btn--${format.id}`}
            disabled={!actif || enCours === cle}
            title={actif ? `Télécharger en ${format.libelle}` : 'Complétez la sélection pour générer'}
            onClick={() => onGenerer(format)}
          >
            {enCours === cle
              ? <span className="spinner-border" aria-hidden="true"></span>
              : <i className={`bi ${format.icone}`} aria-hidden="true"></i>}
            {format.libelle}
          </button>
        )
      })}
    </>
  )
}

const FORMATS_PDF_EXCEL = [
  { id: 'pdf', libelle: 'PDF', icone: 'bi-file-earmark-pdf' },
  { id: 'excel', libelle: 'Excel', icone: 'bi-file-earmark-excel' },
]

function ChampSelect({ id, libelle, requis, valeur, onChange, children, disabled }) {
  return (
    <div className="doc-champ">
      <label className="doc-etiquette" htmlFor={id}>
        {libelle}
        {requis && <span className="doc-requis" aria-hidden="true"> *</span>}
      </label>
      <select
        id={id}
        className="cand-filter-select doc-select"
        value={valeur}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {children}
      </select>
    </div>
  )
}

/** Liste nominative d'un groupe TD/TP LMD (affectations actives). */
function CarteListeGroupe({ annee, enCours, telecharger }) {
  const [formations, setFormations] = useState([])
  const [niveaux, setNiveaux] = useState([])
  const [groupes, setGroupes] = useState([])
  const [sel, setSel] = useState({ formation: '', niveau: '', groupe: '' })

  useEffect(() => {
    (async () => {
      const [fRes, nRes] = await Promise.all([
        getRefFormations().catch(() => ({ data: [] })),
        getRefScolarite('niveaux', { actif: 1 }).catch(() => ({ data: [] })),
      ])
      setFormations(enListe(fRes))
      setNiveaux(enListe(nRes))
    })()
  }, [])

  useEffect(() => {
    if (!sel.formation || !sel.niveau) { setGroupes([]); return }
    (async () => {
      try {
        const params = { ref_formation_id: sel.formation, niveau_id: sel.niveau, actif: '1' }
        if (annee?.id) params.annee_academique_id = annee.id
        setGroupes(enListe(await getEffectifsGroupes(params)))
      } catch { setGroupes([]) }
    })()
  }, [sel.formation, sel.niveau, annee])

  const groupeChoisi = useMemo(
    () => groupes.find((g) => String(g.id) === String(sel.groupe)) || null,
    [groupes, sel.groupe],
  )

  return (
    <article className="doc-carte">
      <div className="doc-carte-entete">
        <span className="doc-icone doc-icone--bleu" aria-hidden="true">
          <i className="bi bi-people"></i>
        </span>
        <div>
          <h3 className="doc-carte-titre">Liste du groupe TD/TP</h3>
          <p className="doc-carte-desc">
            Liste nominative des étudiants affectés à une section, avec colonne d’émargement.
          </p>
        </div>
      </div>
      <div className="doc-carte-corps">
        <ChampSelect id="doc-grp-formation" libelle="Formation" requis
          valeur={sel.formation}
          onChange={(v) => setSel({ formation: v, niveau: sel.niveau, groupe: '' })}>
          <option value="">— choisir —</option>
          {formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
        </ChampSelect>
        <ChampSelect id="doc-grp-niveau" libelle="Niveau" requis
          valeur={sel.niveau}
          onChange={(v) => setSel({ ...sel, niveau: v, groupe: '' })}>
          <option value="">— choisir —</option>
          {niveaux.map((n) => <option key={n.id} value={n.id}>{n.code}</option>)}
        </ChampSelect>
        <ChampSelect id="doc-grp-groupe" libelle="Groupe" requis
          valeur={sel.groupe}
          disabled={!sel.formation || !sel.niveau}
          onChange={(v) => setSel({ ...sel, groupe: v })}>
          <option value="">
            {sel.formation && sel.niveau ? '— choisir —' : '— formation et niveau d’abord —'}
          </option>
          {groupes.map((g) => (
            <option key={g.id} value={g.id}>
              {g.nom} · {g.effectif} étudiant{g.effectif > 1 ? 's' : ''}
            </option>
          ))}
        </ChampSelect>
        {groupeChoisi && (
          <p className="doc-resume">
            <i className="bi bi-check2-circle" aria-hidden="true"></i>
            {groupeChoisi.nom} — {groupeChoisi.effectif} étudiant{groupeChoisi.effectif > 1 ? 's' : ''} affecté{groupeChoisi.effectif > 1 ? 's' : ''}
          </p>
        )}
        {sel.formation && sel.niveau && groupes.length === 0 && (
          <p className="doc-resume doc-resume--vide">
            <i className="bi bi-info-circle" aria-hidden="true"></i>
            Aucun groupe actif pour cette cohorte.
          </p>
        )}
      </div>
      <div className="doc-carte-pied">
        <BoutonsFormats
          formats={FORMATS_PDF_EXCEL}
          prefixe="groupe"
          actif={Boolean(sel.groupe)}
          enCours={enCours}
          onGenerer={(format) => telecharger(
            `groupe-${format.id}`,
            `/scolarite/groupes/${sel.groupe}/liste/${format.id}/`,
            `Liste du groupe ${groupeChoisi?.nom || ''} (${format.libelle})`,
          )}
        />
      </div>
    </article>
  )
}

/** Liste de classe des auditeurs (formation continue) — endpoint historique. */
function CarteListeClasse({ enCours, telecharger }) {
  const [groupesLegacy, setGroupesLegacy] = useState([])
  const [sel, setSel] = useState({ groupe: '', sexe: '' })

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/formations/participants/list/?page=1&page_size=1')
        setGroupesLegacy(res.data?.filter_options?.groupes || [])
      } catch { setGroupesLegacy([]) }
    })()
  }, [])

  const generer = (format) => {
    const params = new URLSearchParams(
      Object.fromEntries(Object.entries(sel).filter(([, v]) => v)),
    )
    const qs = params.toString()
    telecharger(
      `classe-${format.id}`,
      `/exports/participants/liste-classe/${format.id}/${qs ? `?${qs}` : ''}`,
      `Liste de classe (${format.libelle})`,
    )
  }

  return (
    <article className="doc-carte">
      <div className="doc-carte-entete">
        <span className="doc-icone doc-icone--vert" aria-hidden="true">
          <i className="bi bi-people"></i>
        </span>
        <div>
          <h3 className="doc-carte-titre">Liste de classe</h3>
          <p className="doc-carte-desc">
            Auditeurs par groupe de formation continue. Sans groupe choisi :
            tous les auditeurs, un bloc par groupe.
          </p>
        </div>
      </div>
      <div className="doc-carte-corps">
        <ChampSelect id="doc-classe-groupe" libelle="Groupe (facultatif)"
          valeur={sel.groupe}
          onChange={(v) => setSel({ ...sel, groupe: v })}>
          <option value="">Tous les groupes</option>
          {groupesLegacy.map((g) => <option key={g} value={g}>{g}</option>)}
        </ChampSelect>
        <ChampSelect id="doc-classe-sexe" libelle="Sexe (facultatif)"
          valeur={sel.sexe}
          onChange={(v) => setSel({ ...sel, sexe: v })}>
          <option value="">Femmes et hommes</option>
          <option value="FEMININ">Femmes</option>
          <option value="MASCULIN">Hommes</option>
        </ChampSelect>
      </div>
      <div className="doc-carte-pied">
        <BoutonsFormats
          formats={FORMATS_PDF_EXCEL}
          prefixe="classe"
          actif
          enCours={enCours}
          onGenerer={generer}
        />
      </div>
    </article>
  )
}

/** Fiche de notes d'un module de formation continue (formation → module). */
function CarteFicheModule({ enCours, telecharger }) {
  const [formations, setFormations] = useState([])
  const [modules, setModules] = useState([])
  const [sel, setSel] = useState({ formation: '', module: '' })

  useEffect(() => {
    (async () => {
      try { setFormations(enListe(await api.get('/formations/'))) }
      catch { setFormations([]) }
    })()
  }, [])

  useEffect(() => {
    if (!sel.formation) { setModules([]); return }
    (async () => {
      try { setModules(enListe(await api.get(`/formations/${sel.formation}/modules/`))) }
      catch { setModules([]) }
    })()
  }, [sel.formation])

  return (
    <article className="doc-carte">
      <div className="doc-carte-entete">
        <span className="doc-icone doc-icone--ambre" aria-hidden="true">
          <i className="bi bi-card-checklist"></i>
        </span>
        <div>
          <h3 className="doc-carte-titre">Fiche de notes d’un module</h3>
          <p className="doc-carte-desc">
            Fiche de notes d’un module de formation continue, par auditeur.
          </p>
        </div>
      </div>
      <div className="doc-carte-corps">
        <ChampSelect id="doc-fiche-formation" libelle="Formation" requis
          valeur={sel.formation}
          onChange={(v) => setSel({ formation: v, module: '' })}>
          <option value="">— choisir —</option>
          {formations.map((f) => (
            <option key={f.id} value={f.id}>{f.intitule || f.formation}</option>
          ))}
        </ChampSelect>
        <ChampSelect id="doc-fiche-module" libelle="Module" requis
          valeur={sel.module}
          disabled={!sel.formation}
          onChange={(v) => setSel({ ...sel, module: v })}>
          <option value="">
            {sel.formation ? '— choisir —' : '— formation d’abord —'}
          </option>
          {modules.map((m) => <option key={m.id} value={m.id}>{m.intitule}</option>)}
        </ChampSelect>
      </div>
      <div className="doc-carte-pied">
        <BoutonsFormats
          formats={[{ id: 'pdf', libelle: 'PDF', icone: 'bi-file-earmark-pdf' }]}
          prefixe="fiche"
          actif={Boolean(sel.formation && sel.module)}
          enCours={enCours}
          onGenerer={(format) => telecharger(
            `fiche-${format.id}`,
            `/formations/${sel.formation}/modules/${sel.module}/notes/fiche/pdf/`,
            `Fiche de notes (${format.libelle})`,
          )}
        />
      </div>
    </article>
  )
}

/** Relevé individuel (formation continue) avec recherche d'étudiant. */
function CarteReleveEtudiant({ enCours, telecharger }) {
  const [saisie, setSaisie] = useState('')
  const [resultats, setResultats] = useState([])
  const [choisi, setChoisi] = useState(null)
  const [rechercheEnCours, setRechercheEnCours] = useState(false)
  const saisieDebounced = useDebounce(saisie)
  const zoneRef = useRef(null)

  useEffect(() => {
    const terme = saisieDebounced.trim()
    if (choisi || terme.length < 2) { setResultats([]); return }
    let annule = false
    ;(async () => {
      setRechercheEnCours(true)
      try {
        const res = await api.get(
          `/formations/participants/list/?search=${encodeURIComponent(terme)}&page=1`,
        )
        if (!annule) setResultats(enListe(res).slice(0, 8))
      } catch { if (!annule) setResultats([]) }
      finally { if (!annule) setRechercheEnCours(false) }
    })()
    return () => { annule = true }
  }, [saisieDebounced, choisi])

  const choisir = (p) => {
    setChoisi(p)
    setSaisie(`${p.nom} ${p.prenom}`)
    setResultats([])
  }
  const effacer = () => { setChoisi(null); setSaisie('') }

  return (
    <article className="doc-carte">
      <div className="doc-carte-entete">
        <span className="doc-icone doc-icone--violet" aria-hidden="true">
          <i className="bi bi-person-lines-fill"></i>
        </span>
        <div>
          <h3 className="doc-carte-titre">Relevé d’un étudiant</h3>
          <p className="doc-carte-desc">
            Fiche de notes individuelle (formation continue) d’un étudiant ou auditeur.
          </p>
        </div>
      </div>
      <div className="doc-carte-corps">
        <div className="doc-champ">
          <label className="doc-etiquette" htmlFor="doc-releve-recherche">
            Étudiant<span className="doc-requis" aria-hidden="true"> *</span>
          </label>
          {choisi ? (
            <p className="doc-choisi">
              <span>
                <strong>{choisi.nom} {choisi.prenom}</strong>
                <span className="doc-choisi-mat">{choisi.matricule}</span>
              </span>
              <button type="button" className="doc-choisi-effacer" onClick={effacer}
                aria-label="Changer d’étudiant">
                <i className="bi bi-x-lg" aria-hidden="true"></i>
              </button>
            </p>
          ) : (
            <div className="doc-recherche" ref={zoneRef}>
              <div className="adm-recherche">
                <i className="bi bi-search" aria-hidden="true"></i>
                <input
                  id="doc-releve-recherche"
                  type="search"
                  placeholder="Nom, prénom ou matricule (2 caractères min.)…"
                  value={saisie}
                  onChange={(e) => setSaisie(e.target.value)}
                  autoComplete="off"
                />
                {rechercheEnCours && (
                  <span className="spinner-border" aria-hidden="true"></span>
                )}
              </div>
              {resultats.length > 0 && (
                <ul className="doc-resultats" role="listbox" aria-label="Étudiants trouvés">
                  {resultats.map((p) => (
                    <li key={p.id}>
                      <button type="button" className="doc-resultat" onClick={() => choisir(p)}>
                        <span className="doc-resultat-nom">{p.nom} {p.prenom}</span>
                        <span className="doc-resultat-mat">{p.matricule}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {saisieDebounced.trim().length >= 2 && !rechercheEnCours && resultats.length === 0 && (
                <p className="doc-resume doc-resume--vide">Aucun étudiant trouvé.</p>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="doc-carte-pied">
        <BoutonsFormats
          formats={FORMATS_PDF_EXCEL}
          prefixe="releve"
          actif={Boolean(choisi)}
          enCours={enCours}
          onGenerer={(format) => telecharger(
            `releve-${format.id}`,
            `/participant/${choisi.id}/notes-fiche/export/${format.id}/`,
            `Relevé de ${choisi.nom} ${choisi.prenom} (${format.libelle})`,
          )}
        />
      </div>
    </article>
  )
}
