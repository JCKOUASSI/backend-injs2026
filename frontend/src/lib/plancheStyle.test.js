import { describe, it, expect } from 'vitest'
import {
  CATEGORIES,
  PREFIXE_JETON,
  classerJeton,
  extraireJetons,
  filtrerJetons,
  hexVersRgb,
  jetonsDepuisFeuilles,
  jetonsDepuisStyleCalcule,
  largeurDisponible,
  luminanceRelative,
  PAIRES_CONTRASTE,
  pointDeRupture,
  ratioContraste,
  regrouperParCategorie,
  tableContraste,
  verdictContraste,
} from '@/lib/plancheStyle'

describe('lib/plancheStyle — classement des jetons', () => {
  it('reconnaît les familles du socle', () => {
    expect(classerJeton('--injs-blue-royal').id).toBe('couleur')
    expect(classerJeton('--injs-success').id).toBe('couleur')
    expect(classerJeton('--injs-fs-lg').id).toBe('typographie')
    expect(classerJeton('--injs-font-mono').id).toBe('typographie')
    expect(classerJeton('--injs-space-4').id).toBe('espace')
    expect(classerJeton('--injs-radius-md').id).toBe('forme')
    expect(classerJeton('--injs-shadow-card').id).toBe('forme')
    expect(classerJeton('--injs-glass-1-bg').id).toBe('verre')
    expect(classerJeton('--injs-bp-tablet').id).toBe('verre')
    expect(classerJeton('--injs-transition').id).toBe('mouvement')
    expect(classerJeton('--injs-focus-ring').id).toBe('mouvement')
  })

  it('ne confond pas un préfixe court avec un mot plus long', () => {
    // « surface » commence par « s », pas par « fs » ; « space » n'est pas
    // capturé par « bp ». Le classement doit se faire sur le séparateur.
    expect(classerJeton('--injs-surface').id).toBe('couleur')
    expect(classerJeton('--injs-border-strong').id).toBe('couleur')
  })

  it('range l’inconnu dans « divers » plutôt que de le perdre', () => {
    expect(classerJeton('--injs-inedit').id).toBe('divers')
    expect(classerJeton('').id).toBe('divers')
    expect(classerJeton(undefined).id).toBe('divers')
  })

  it('accepte un nom sans préfixe', () => {
    expect(classerJeton('danger').id).toBe('couleur')
  })
})

describe('lib/plancheStyle — lecture réelle des jetons', () => {
  it('lit les noms exposés par le style calculé, et seulement le préfixe du socle', () => {
    const style = { 0: '--injs-navy', 1: 'color', 2: '--injs-sky', length: 3 }
    expect(jetonsDepuisStyleCalcule(style)).toEqual(['--injs-navy', '--injs-sky'])
  })

  it('tolère une déclaration vide ou sans longueur (environnement de test)', () => {
    expect(jetonsDepuisStyleCalcule(null)).toEqual([])
    expect(jetonsDepuisStyleCalcule({})).toEqual([])
    expect(jetonsDepuisStyleCalcule({ length: 0 })).toEqual([])
  })

  it('parcourt les feuilles, y compris les règles groupantes', () => {
    const feuille = {
      cssRules: [
        { style: { 0: '--injs-navy', 1: 'margin', length: 2 } },
        { cssRules: [{ style: { 0: '--injs-space-4', length: 1 } }] },
      ],
    }
    expect(jetonsDepuisFeuilles([feuille]).sort()).toEqual(['--injs-navy', '--injs-space-4'])
  })

  it('ignore une feuille d’une autre origine sans faire échouer la lecture', () => {
    const interdite = {
      get cssRules() {
        throw new DOMException('SecurityError')
      },
    }
    const lisible = { cssRules: [{ style: { 0: '--injs-teal', length: 1 } }] }
    expect(jetonsDepuisFeuilles([interdite, lisible])).toEqual(['--injs-teal'])
    expect(jetonsDepuisFeuilles(undefined)).toEqual([])
  })

  it('associe la valeur lue au jeton et signale un jeton non déclaré', () => {
    const valeurs = { '--injs-navy': ' #071B3A ', '--injs-fantome': '   ' }
    const jetons = extraireJetons((nom) => valeurs[nom] ?? '', ['--injs-navy', '--injs-fantome', 'color'])
    expect(jetons).toHaveLength(2) // « color » n'est pas un jeton du socle
    expect(jetons[0]).toMatchObject({ nom: '--injs-navy', valeur: '#071B3A', categorie: { id: 'couleur' } })
    expect(jetons[1]).toMatchObject({ nom: '--injs-fantome', valeur: null })
  })

  it('n’invente jamais de valeur : un accesseur muet donne null', () => {
    expect(extraireJetons(() => undefined, ['--injs-navy'])[0].valeur).toBeNull()
  })
})

describe('lib/plancheStyle — filtrage et regroupement', () => {
  const jetons = extraireJetons(
    (nom) => ({ '--injs-danger': '#DC3545', '--injs-navy': '#071B3A', '--injs-space-4': '1rem' }[nom] ?? ''),
    ['--injs-danger', '--injs-navy', '--injs-space-4'],
  )

  it('rend tout sans requête', () => {
    expect(filtrerJetons(jetons, '')).toHaveLength(3)
    expect(filtrerJetons(jetons, '   ')).toHaveLength(3)
  })

  it('filtre sur le nom, sans tenir compte de la casse', () => {
    expect(filtrerJetons(jetons, 'NAVY').map((j) => j.nom)).toEqual(['--injs-navy'])
  })

  it('filtre aussi sur la valeur', () => {
    expect(filtrerJetons(jetons, 'dc3545').map((j) => j.nom)).toEqual(['--injs-danger'])
  })

  it('regroupe dans l’ordre des catégories et omet les groupes vides', () => {
    const groupes = regrouperParCategorie(jetons)
    expect(groupes.map((g) => g.id)).toEqual(['couleur', 'espace'])
    expect(groupes[0].jetons).toHaveLength(2)
    expect(groupes[1].libelle).toBe('Espacements')
  })

  it('expose les catégories dans un ordre stable', () => {
    expect(CATEGORIES.map((c) => c.id)).toEqual([
      'couleur', 'typographie', 'espace', 'forme', 'mouvement', 'verre',
    ])
    expect(PREFIXE_JETON).toBe('--injs-')
  })
})

describe('lib/plancheStyle — contraste WCAG 2.2', () => {
  it('convertit les notations hexadécimales courtes et longues', () => {
    expect(hexVersRgb('#fff')).toEqual({ r: 255, g: 255, b: 255 })
    expect(hexVersRgb('071B3A')).toEqual({ r: 7, g: 27, b: 58 })
    expect(hexVersRgb('#DC3545')).toEqual({ r: 220, g: 53, b: 69 })
  })

  it('refuse les notations non hexadécimales plutôt que de deviner', () => {
    expect(hexVersRgb('rgba(255,255,255,0.5)')).toBeNull()
    expect(hexVersRgb('')).toBeNull()
    expect(hexVersRgb(null)).toBeNull()
    expect(luminanceRelative('rebeccapurple')).toBeNull()
    expect(ratioContraste('#fff', 'transparent')).toBeNull()
  })

  it('donne les ratios de référence du WCAG', () => {
    expect(ratioContraste('#000000', '#FFFFFF')).toBeCloseTo(21, 5)
    expect(ratioContraste('#FFFFFF', '#FFFFFF')).toBeCloseTo(1, 5)
    // L'ordre des arguments ne change pas le ratio (symétrie).
    expect(ratioContraste('#071B3A', '#FFFFFF')).toBeCloseTo(ratioContraste('#FFFFFF', '#071B3A'), 10)
  })

  it('applique les seuils AA (4,5) et AAA (7)', () => {
    expect(verdictContraste(21)).toMatchObject({ niveau: 'AAA', conformeAA: true, conformeAAA: true })
    expect(verdictContraste(7)).toMatchObject({ niveau: 'AAA' })
    expect(verdictContraste(4.5)).toMatchObject({ niveau: 'AA', conformeAA: true, conformeAAA: false })
    expect(verdictContraste(3.24)).toMatchObject({ niveau: 'AA — grand texte', conformeAA: false })
    expect(verdictContraste(2.1)).toMatchObject({ niveau: 'Insuffisant', conformeAA: false })
    expect(verdictContraste(null)).toMatchObject({ niveau: 'non calculable', conformeAA: false })
  })

  it('calcule la table de contraste sans arrondir à la place du verdict', () => {
    const table = tableContraste()
    expect(table).toHaveLength(PAIRES_CONTRASTE.length)
    for (const ligne of table) {
      expect(ligne.ratio).toBeGreaterThan(1)
      expect(ligne.ratioAffiche).toMatch(/^\d+\.\d{2} : 1$/)
      expect(typeof ligne.verdict.conformeAA).toBe('boolean')
    }
    // Cas réel documenté : le vert succès du socle n'atteint pas AA sur blanc.
    const vert = table.find((l) => l.libelle.includes('Vert succès'))
    expect(vert.ratio).toBeCloseTo(3.24, 2)
    expect(vert.verdict.conformeAA).toBe(false)
    // Le blanc sur marine, lui, dépasse largement AAA.
    const inverse = table.find((l) => l.libelle.includes('inversé'))
    expect(inverse.verdict.conformeAAA).toBe(true)
  })
})

describe('lib/plancheStyle — repère responsive', () => {
  it('nomme le point de rupture actif, bornes incluses', () => {
    expect(pointDeRupture(360)).toMatch(/mobile/)
    expect(pointDeRupture(480)).toMatch(/mobile/)
    expect(pointDeRupture(481)).toMatch(/tablette/)
    expect(pointDeRupture(768)).toMatch(/tablette/)
    expect(pointDeRupture(1024)).toMatch(/petit portable/)
    expect(pointDeRupture(1366)).toMatch(/bureau/)
    expect(pointDeRupture(1920)).toMatch(/grand écran/)
  })

  it('ne produit pas de point de rupture absurde sur une mesure invalide', () => {
    expect(pointDeRupture(0)).toMatch(/grand écran/)
    expect(pointDeRupture(undefined)).toMatch(/grand écran/)
  })

  it('mesure la largeur du conteneur, sinon celle de la fenêtre', () => {
    expect(largeurDisponible({ clientWidth: 900 }, { innerWidth: 1440 })).toBe(900)
    expect(largeurDisponible(null, { innerWidth: 1440 })).toBe(1440)
    expect(largeurDisponible({ clientWidth: 0 }, { innerWidth: 0 })).toBe(0)
    expect(largeurDisponible(undefined, undefined)).toBe(0)
  })
})

/**
 * Invariant de couverture : la planche doit refléter le **socle réel**.
 * Ces tests lisent `designSystem.css` sur disque — si un jeton y est ajouté
 * sans que la planche sache le classer, le test échoue plutôt que de laisser
 * un jeton invisible passer inaperçu.
 */
describe('lib/plancheStyle — couverture du socle réel', () => {
  const fs = require('node:fs')
  const path = require('node:path')
  const cheminCss = path.resolve(process.cwd(), 'src/styles/designSystem.css')
  const css = fs.readFileSync(cheminCss, 'utf8')
  const nomsSocle = [...new Set([...css.matchAll(/(--injs-[a-z0-9-]+)\s*:/g)].map((m) => m[1]))]

  it('le socle déclare bien des jetons', () => {
    // 73 déclarations dans designSystem.css à la date de rédaction ; le seuil
    // bas sert de garde-fou (fichier tronqué, import cassé), pas de mesure.
    expect(nomsSocle.length).toBeGreaterThan(60)
  })

  it('aucun jeton du socle ne tombe dans la catégorie « divers »', () => {
    const orphelins = nomsSocle.filter((nom) => classerJeton(nom).id === 'divers')
    expect(orphelins).toEqual([])
  })

  it('la table de contraste n’utilise que des teintes présentes au socle', () => {
    const socle = css.toUpperCase()
    const absentes = PAIRES_CONTRASTE
      .flatMap((paire) => [paire.texte, paire.fond])
      .filter((couleur) => !socle.includes(couleur.toUpperCase()))
    expect(absentes).toEqual([])
  })

  it('chaque catégorie du socle est représentée par au moins un jeton', () => {
    const idsUtilises = new Set(nomsSocle.map((nom) => classerJeton(nom).id))
    for (const categorie of CATEGORIES) {
      expect(idsUtilises, `catégorie vide : ${categorie.id}`).toContain(categorie.id)
    }
  })
})

/**
 * L'utilitaire `.visually-hidden` est employé par plusieurs écrans (évaluations,
 * planche de style). Il n'était défini NULLE PART en CSS : le texte réservé aux
 * lecteurs d'écran s'affichait à l'écran. Ce test empêche la réapparition du
 * défaut (classe utilisée sans définition).
 */
describe('socle — utilitaire .visually-hidden', () => {
  const fs = require('node:fs')
  const path = require('node:path')
  const css = fs.readFileSync(path.resolve(process.cwd(), 'src/styles/designSystem.css'), 'utf8')

  it('est défini dans le socle', () => {
    expect(css).toMatch(/\.visually-hidden\s*\{/)
  })

  it('masque réellement le contenu (1 px, clip, sans bord)', () => {
    const bloc = css.match(/\.visually-hidden\s*\{([\s\S]*?)\}/)[1]
    expect(bloc).toMatch(/position:\s*absolute/)
    expect(bloc).toMatch(/width:\s*1px/)
    expect(bloc).toMatch(/height:\s*1px/)
    expect(bloc).toMatch(/clip:\s*rect\(0, 0, 0, 0\)/)
  })
})
