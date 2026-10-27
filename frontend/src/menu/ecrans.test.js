/**
 * Descripteurs d'écrans génériques — validité des sources de données.
 *
 * Le moteur générique (`components/generique/`) ne connaît rien du métier : tout
 * vient de `src/menu/ecrans.js`. Un endpoint mal orthographié ne provoque donc
 * aucune erreur de compilation, seulement un écran vide en production. Ce test
 * compare chaque chemin appelé par un descripteur au **catalogue d'URL réel du
 * backend** (fixture générée depuis le résolveur Django), en évaluant les
 * fonctions `endpoint`/`chemin` avec une ligne fictive.
 *
 * Régénérer la fixture après un ajout d'endpoint côté backend :
 *   cd backend && USE_SQLITE=1 .venv/bin/python ../arena/genere-catalogues-menu.py
 */
import { describe, it, expect } from 'vitest'
import { ECRANS, RESSOURCES, ecranParId, idsEcrans } from './ecrans'
import ENDPOINTS from './__fixtures__/catalogue-endpoints.json'

/** Ligne fictive : assez de champs pour que les gabarits produisent un chemin. */
const FAUSSE_LIGNE = {
  id: 1,
  pk: 1,
  numero: 'X-1',
  code: 'X-1',
  statut: 'ACTIF',
  formation_id: 1,
  module_id: 1,
  groupe_id: 1,
  annee_academique_id: 1,
  session_id: 1,
  convention_id: 1,
  facture_id: 1,
  paiement_id: 1,
  agent_id: 1,
  etudiant_id: 1,
  compte_id: 1,
}

/** Motif du catalogue → expression régulière JavaScript ancrée. */
function motifEnRegExp(motif) {
  // Les motifs `re_path` sont déjà des expressions (ancres retirées à la
  // génération) ; les motifs `path` sont littéraux, `{}` marquant un segment.
  if (/[*+?()|[\]\\]/.test(motif)) return new RegExp(`^${motif}$`)
  const echappe = motif.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\\\{\\\}/g, '[^/]+')
  return new RegExp(`^${echappe}$`)
}

const MOTIFS = [...ENDPOINTS.motifs, ...ENDPOINTS.motifs_regex].map(motifEnRegExp)

/** Normalise un chemin de descripteur en chemin d'API concret. */
function normaliser(chemin) {
  const sansQuery = String(chemin).split('?')[0]
  const cible = sansQuery.startsWith('/api/') ? sansQuery : `/api${sansQuery}`
  return cible.endsWith('/') ? cible : `${cible}/`
}

function resoutDansApi(chemin) {
  const cible = normaliser(chemin)
  return MOTIFS.some((rex) => rex.test(cible) || rex.test(cible.replace(/\/$/, '')))
}

/** Évalue une valeur de descripteur (littéral ou fonction) en chemin concret. */
function concret(valeur, ...args) {
  if (typeof valeur === 'function') {
    try {
      return valeur(...args)
    } catch {
      return null
    }
  }
  return typeof valeur === 'string' ? valeur : null
}

/** Tous les chemins d'API appelés par un descripteur, avec leur origine. */
function cheminsApi(ecran) {
  const trouves = []
  const noter = (origine, valeur, ...args) => {
    const chemin = concret(valeur, ...args)
    if (chemin) trouves.push({ origine, chemin })
  }

  noter('endpoint', ecran.endpoint)
  for (const onglet of ecran.onglets || []) noter(`onglets[${onglet.id}]`, onglet.endpoint)
  if (ecran.detail) noter('detail.endpoint', ecran.detail.endpoint, FAUSSE_LIGNE)
  for (const action of [...(ecran.actions || []), ...(ecran.actionsGlobales || [])]) {
    // `vers` cible une route **frontend**, pas l'API : exclu du contrôle.
    if (action.chemin) noter(`action « ${action.libelle} »`, action.chemin, FAUSSE_LIGNE)
  }
  for (const document of ecran.documents || []) {
    const valeurs = Object.fromEntries((document.parametres || []).map((p) => [p.cle, 1]))
    for (const format of document.formats || [{ id: 'pdf' }]) {
      noter(`document « ${document.libelle} » (${format.id})`, document.chemin, valeurs, format)
    }
  }
  return trouves
}

describe('catalogue d\'endpoints (fixture)', () => {
  it('couvre l\'ensemble des URL de l\'API', () => {
    expect(ENDPOINTS.mode).toBe('django')
    expect(ENDPOINTS.nombre).toBeGreaterThan(400)
    expect(ENDPOINTS.motifs.some((m) => m.includes('audit-logs'))).toBe(true)
  })
})

describe('descripteurs : forme minimale', () => {
  it('chaque descripteur a un titre, un fil et une introduction', () => {
    const manquants = Object.entries(ECRANS)
      .filter(([, ecran]) => !ecran.titre || !ecran.fil || !ecran.introduction)
      .map(([cle, ecran]) => [
        cle,
        !ecran.titre && 'titre',
        !ecran.fil && 'fil',
        !ecran.introduction && 'introduction',
      ].filter(Boolean).join(' : '))
    expect(manquants).toEqual([])
  })

  it('ecranParId et idsEcrans sont cohérents avec ECRANS', () => {
    expect(idsEcrans().length).toBe(Object.keys(ECRANS).length)
    for (const id of idsEcrans()) {
      expect(ecranParId(id), id).toBe(ECRANS[id])
    }
    expect(ecranParId('inexistant')).toBeNull()
  })
})

describe('descripteurs : chaque chemin appelé existe côté backend', () => {
  const tousChemins = Object.entries(ECRANS).flatMap(([cle, ecran]) =>
    cheminsApi(ecran).map(({ origine, chemin }) => ({ ecran: cle, origine, chemin })))

  it('les descripteurs appellent un nombre significatif d\'endpoints', () => {
    expect(tousChemins.length).toBeGreaterThan(80)
  })

  it('aucun endpoint inventé (tous résolus par le catalogue d\'URL)', () => {
    const introuvables = tousChemins
      .filter(({ chemin }) => !resoutDansApi(chemin))
      .map(({ ecran, origine, chemin }) => `${ecran} · ${origine} → ${normaliser(chemin)}`)
    expect(introuvables).toEqual([])
  })

  it('les endpoints d\'options des filtres existent aussi', () => {
    const introuvables = Object.entries(RESSOURCES)
      .filter(([, ressource]) => !resoutDansApi(ressource.optionsEndpoint))
      .map(([cle, ressource]) => `${cle} → ${ressource.optionsEndpoint}`)
    expect(introuvables).toEqual([])
  })
})

describe('descripteurs : navigation interne', () => {
  it('une action `vers` produit une route frontend absolue', () => {
    for (const [cle, ecran] of Object.entries(ECRANS)) {
      for (const action of [...(ecran.actions || []), ...(ecran.actionsGlobales || [])]) {
        if (!action.vers) continue
        const cible = action.vers(FAUSSE_LIGNE)
        if (cible == null) continue // bouton désactivé : cas géré à l'écran
        expect(typeof cible, `${cle} : action « ${action.libelle} »`).toBe('string')
        expect(cible.startsWith('/'), `${cle} : ${cible}`).toBe(true)
      }
    }
  })

  it('une action `vers` sans cible exploitable renvoie null (jamais undefined)', () => {
    for (const [cle, ecran] of Object.entries(ECRANS)) {
      for (const action of ecran.actions || []) {
        if (!action.vers) continue
        const cible = action.vers({})
        expect(cible === null || typeof cible === 'string', `${cle} : ${action.libelle}`).toBe(true)
      }
    }
  })
})

describe('descripteurs : filtres et documents', () => {
  it('les filtres déclarent un paramètre et un libellé', () => {
    for (const [cle, ecran] of Object.entries(ECRANS)) {
      for (const filtre of ecran.filtres || []) {
        expect(filtre.param, `${cle} : filtre sans paramètre`).toBeTruthy()
        expect(filtre.libelle, `${cle} : filtre sans libellé`).toBeTruthy()
        for (const option of filtre.options || []) {
          expect(option.valeur === undefined || option.valeur !== null, cle).toBe(true)
          expect(option.libelle, cle).toBeTruthy()
        }
      }
    }
  })

  it('les documents déclarent au moins un format et un chemin', () => {
    for (const [cle, ecran] of Object.entries(ECRANS)) {
      for (const document of ecran.documents || []) {
        expect(document.libelle, `${cle} : document sans libellé`).toBeTruthy()
        expect((document.formats || []).length, `${cle} : ${document.id} sans format`)
          .toBeGreaterThan(0)
        expect(typeof document.chemin, `${cle} : ${document.id} sans chemin`).toBe('function')
      }
    }
  })

  it('les paramètres de document ont une clef et un libellé', () => {
    for (const [cle, ecran] of Object.entries(ECRANS)) {
      for (const document of ecran.documents || []) {
        for (const parametre of document.parametres || []) {
          expect(parametre.cle, `${cle} : ${document.id}`).toBeTruthy()
          expect(parametre.libelle, `${cle} : ${document.id}`).toBeTruthy()
        }
      }
    }
  })
})
