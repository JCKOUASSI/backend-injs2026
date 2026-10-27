/**
 * Navigation RBAC — résolution des droits d'affichage (fonctions pures).
 *
 * Couvre le modèle hybride retenu : compte gouverné → permissions effectives
 * CURP ; compte non gouverné → capacités projetées (avec repli statique) ;
 * entrée sans volet CURP → toujours évaluée par le volet legacy.
 */
import { describe, it, expect } from 'vitest'
import {
  FLAG_CONSOLE,
  SOURCES,
  droitRequis,
  estEntreeConsole,
  filtrerArborescence,
  indexParChemin,
  itemAutorise,
  resoudreSource,
} from './autorisation'

/** Utilisateur doté des capacités backend (forme réelle du contrat). */
const userAvecCapacites = (capacites, role = 'SECRETARIAT') => ({
  id: 1,
  username: 'agent',
  role,
  roles: [role],
  capabilities: { capacites },
})

const ARBRE = [
  {
    id: 'scolarite',
    libelle: 'Scolarité',
    enfants: [
      {
        id: 'scolarite.inscriptions',
        libelle: 'Inscriptions',
        chemin: '/scolarite/inscriptions',
        droit: {
          curp: ['scolarite.inscription_administrative.consulter'],
          legacy: [['scolarite', 'voir']],
        },
      },
      {
        id: 'scolarite.pv',
        libelle: 'PV de jury',
        chemin: '/jurys/pv',
        droit: {
          curp: ['jurys.pv.generer', 'jurys.pv.signer'],
          legacy: [['scolarite', 'voir']],
        },
      },
    ],
  },
  {
    id: 'finance',
    libelle: 'Finance historique',
    chemin: '/finance-dashboard',
    // Aucun volet CURP : écran purement legacy, jamais perdu par la bascule.
    droit: { legacy: [['finance', 'voir']] },
  },
  {
    id: 'libre',
    libelle: 'Écran sans droit déclaré',
    chemin: '/aide',
  },
]

describe('resoudreSource — choix de la source applicable', () => {
  it('compte gouverné avec liste de permissions → source CURP', () => {
    const ctx = resoudreSource({
      user: userAvecCapacites({ scolarite: ['voir'] }),
      mesAcces: { gouverne: true, permissions_effectives: ['scolarite.groupe.modifier'] },
    })
    expect(ctx.source).toBe(SOURCES.CURP)
    expect(ctx.gouverne).toBe(true)
    expect(ctx.codes.has('scolarite.groupe.modifier')).toBe(true)
  })

  it('compte gouverné sans aucune permission → CURP, ensemble vide', () => {
    const ctx = resoudreSource({
      user: userAvecCapacites({}),
      mesAcces: { gouverne: true, permissions_effectives: [] },
    })
    expect(ctx.source).toBe(SOURCES.CURP)
    expect(ctx.codes.size).toBe(0)
  })

  it('compte non gouverné → source legacy (abstention du moteur)', () => {
    const ctx = resoudreSource({
      user: userAvecCapacites({ scolarite: ['voir'] }),
      mesAcces: { gouverne: false, mode: 'OBSERVATION' },
    })
    expect(ctx.source).toBe(SOURCES.LEGACY)
    expect(ctx.gouverne).toBe(false)
  })

  it('endpoint mes-acces indisponible → legacy, aucun crash', () => {
    const ctx = resoudreSource({ user: userAvecCapacites({}), mesAcces: null })
    expect(ctx.source).toBe(SOURCES.LEGACY)
    expect(ctx.codes.size).toBe(0)
  })
})

describe('itemAutorise — compte gouverné (permissions CURP)', () => {
  // Le compte fictif détient les capacités legacy « scolarite » et « finance » :
  // ainsi, tout refus observé provient bien du volet CURP, pas du legacy.
  const ctx = (codes) => ({
    source: SOURCES.CURP,
    codes: new Set(codes),
    user: userAvecCapacites({ scolarite: ['voir'], finance: ['voir'] }),
  })

  it('accorde quand un des codes CURP est détenu', () => {
    expect(itemAutorise(ARBRE[0].enfants[0], ctx([
      'scolarite.inscription_administrative.consulter',
    ]))).toBe(true)
  })

  it('refuse quand aucun code CURP n\'est détenu, même si la capacité legacy l\'autorise', () => {
    // C'est le cœur du modèle hybride : pour un compte gouverné, le référentiel
    // CURP fait foi — la capacité legacy ne « repêche » pas l'entrée.
    expect(itemAutorise(ARBRE[0].enfants[1], ctx(['scolarite.groupe.modifier']))).toBe(false)
  })

  it('accepte n\'importe quel code d\'une liste (OU interne)', () => {
    expect(itemAutorise(ARBRE[0].enfants[1], ctx(['jurys.pv.signer']))).toBe(true)
  })

  it('une entrée sans volet CURP reste évaluée par le legacy', () => {
    expect(itemAutorise(ARBRE[1], ctx([]))).toBe(true)
  })

  it('une entrée sans aucun droit déclaré reste visible', () => {
    expect(itemAutorise(ARBRE[2], ctx([]))).toBe(true)
  })
})

describe('itemAutorise — compte non gouverné (capacités projetées)', () => {
  it('accorde sur la capacité backend', () => {
    const ctx = {
      source: SOURCES.LEGACY,
      codes: new Set(),
      user: userAvecCapacites({ scolarite: ['voir'] }),
    }
    expect(itemAutorise(ARBRE[0].enfants[0], ctx)).toBe(true)
  })

  it('refuse quand la capacité est absente du contrat backend', () => {
    const ctx = {
      source: SOURCES.LEGACY,
      codes: new Set(),
      user: userAvecCapacites({ scolarite: ['voir'] }),
    }
    expect(itemAutorise(ARBRE[1], ctx)).toBe(false)
  })

  it('les permissions CURP ne sont pas consultées pour un compte non gouverné', () => {
    const ctx = {
      source: SOURCES.LEGACY,
      codes: new Set(['jurys.pv.signer']),
      user: userAvecCapacites({ scolarite: [] }),
    }
    expect(itemAutorise(ARBRE[0].enfants[1], ctx)).toBe(false)
  })

  it('repli statique par rôles quand aucune capacité n\'est chargée', () => {
    const ctx = {
      source: SOURCES.LEGACY,
      codes: new Set(),
      user: { username: 'archive', role: 'ARCHIVE', roles: ['ARCHIVE'] },
    }
    const entree = {
      id: 'x',
      droit: { legacy: [['finance', 'voir']], roles: ['ARCHIVE', 'DIRECTION'] },
    }
    expect(itemAutorise(entree, ctx)).toBe(true)
  })

  it('entrée inconnue → refus (fermeture par défaut)', () => {
    expect(itemAutorise(null, { source: SOURCES.LEGACY, codes: new Set(), user: null })).toBe(false)
  })
})

describe('verrou kill-switch de la console CURP', () => {
  const ENTREE_CONSOLE = {
    id: 'console',
    console: true,
    droit: { legacy: [['habilitations_admin', 'gerer']] },
  }
  const ctx = (drapeauConsole) => ({
    source: SOURCES.LEGACY,
    codes: new Set(),
    drapeauConsole,
    user: userAvecCapacites({ habilitations_admin: ['gerer'] }),
  })

  it('estEntreeConsole reconnaît les entrées de la console', () => {
    expect(estEntreeConsole(ENTREE_CONSOLE)).toBe(true)
    expect(estEntreeConsole(ARBRE[0].enfants[0])).toBe(false)
    expect(estEntreeConsole(null)).toBe(false)
  })

  it('drapeau fermé : masquée même avec la capacité projetée (cas super-utilisateur)', () => {
    expect(itemAutorise(ENTREE_CONSOLE, ctx(false))).toBe(false)
  })

  it('drapeau inconnu (flags non chargés) : masquée (fermeture par défaut)', () => {
    expect(itemAutorise(ENTREE_CONSOLE, ctx(undefined))).toBe(false)
  })

  it('drapeau ouvert : la capacité projetée décide', () => {
    expect(itemAutorise(ENTREE_CONSOLE, ctx(true))).toBe(true)
    const sansCapacite = { ...ctx(true), user: userAvecCapacites({}) }
    expect(itemAutorise(ENTREE_CONSOLE, sansCapacite)).toBe(false)
  })

  it('une entrée hors console est indifférente au drapeau', () => {
    const ctxFerme = {
      source: SOURCES.LEGACY,
      codes: new Set(),
      drapeauConsole: false,
      user: userAvecCapacites({ scolarite: ['voir'] }),
    }
    expect(itemAutorise(ARBRE[0].enfants[0], ctxFerme)).toBe(true)
  })

  it('la clef de drapeau attendue est celle du kill-switch serveur', () => {
    expect(FLAG_CONSOLE).toBe('flag.curp_ui_admin')
  })
})

describe('filtrerArborescence — masquage des sections', () => {
  const ctxLegacy = (capacites, role = 'SECRETARIAT') => ({
    source: SOURCES.LEGACY,
    codes: new Set(),
    user: userAvecCapacites(capacites, role),
  })

  it('conserve une section dès qu\'un enfant est autorisé', () => {
    const resultat = filtrerArborescence(ARBRE, ctxLegacy({ scolarite: ['voir'] }))
    const scolarite = resultat.find((s) => s.id === 'scolarite')
    expect(scolarite).toBeDefined()
    expect(scolarite.enfants).toHaveLength(2)
  })

  it('supprime une section dont plus aucun enfant n\'est autorisé', () => {
    const resultat = filtrerArborescence(ARBRE, ctxLegacy({}))
    expect(resultat.find((s) => s.id === 'scolarite')).toBeUndefined()
  })

  it('ne filtre que les enfants non autorisés, sans toucher aux autres', () => {
    const arbre = [{
      id: 's',
      enfants: [
        { id: 'a', droit: { legacy: [['scolarite', 'voir']] } },
        { id: 'b', droit: { legacy: [['finance', 'voir']] } },
      ],
    }]
    const resultat = filtrerArborescence(arbre, ctxLegacy({ scolarite: ['voir'] }))
    expect(resultat[0].enfants.map((e) => e.id)).toEqual(['a'])
  })

  it('ne mute jamais l\'arborescence d\'origine', () => {
    const avant = JSON.stringify(ARBRE)
    filtrerArborescence(ARBRE, ctxLegacy({}))
    expect(JSON.stringify(ARBRE)).toBe(avant)
  })

  it('retourne un tableau vide pour une entrée invalide', () => {
    expect(filtrerArborescence(null, ctxLegacy({}))).toEqual([])
  })
})

describe('indexParChemin et droitRequis — outillage', () => {
  it('indexe sections et enfants par chemin (garde de route)', () => {
    const ctx = { source: SOURCES.LEGACY, codes: new Set(), user: userAvecCapacites({ scolarite: ['voir'], finance: ['voir'] }) }
    const index = indexParChemin(filtrerArborescence(ARBRE, ctx))
    expect(index.has('/scolarite/inscriptions')).toBe(true)
    expect(index.has('/finance-dashboard')).toBe(true)
    expect(index.has('/aide')).toBe(true)
  })

  it('n\'indexe pas une entrée masquée', () => {
    const ctx = { source: SOURCES.LEGACY, codes: new Set(), user: userAvecCapacites({}) }
    const index = indexParChemin(filtrerArborescence(ARBRE, ctx))
    expect(index.has('/scolarite/inscriptions')).toBe(false)
  })

  it('droitRequis rend le droit lisible (diagnostic, jamais décision)', () => {
    expect(droitRequis(ARBRE[0].enfants[1])).toEqual({
      curp: ['jurys.pv.generer', 'jurys.pv.signer'],
      legacy: ['scolarite.voir'],
      roles: [],
    })
  })

  it('droitRequis tolère une entrée sans droit', () => {
    expect(droitRequis({})).toEqual({ curp: [], legacy: [], roles: [] })
    expect(droitRequis(null)).toEqual({ curp: [], legacy: [], roles: [] })
  })
})
