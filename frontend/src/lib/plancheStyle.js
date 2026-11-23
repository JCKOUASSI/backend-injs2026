/**
 * Planche de style — fonctions **pures** (aucun effet de bord, aucun React,
 * aucun appel réseau) consommées par `pages/design/PlancheDeStyle.jsx`.
 *
 * Objectif : que la planche de style affichée dans l'application montre le
 * **socle réel** (`src/styles/designSystem.css`) et non une maquette figée.
 * Les valeurs affichées sont donc lues par le navigateur
 * (`getComputedStyle(root).getPropertyValue('--injs-…')`) ; ce module ne
 * transporte que la logique de lecture, de classement, de filtrage et de
 * calcul, ce qui la rend vérifiable en test unitaire.
 *
 * Aucune donnée métier, aucun chiffre inventé : les seuls nombres produits ici
 * sont **calculés** (ratios de contraste WCAG, point de rupture courant).
 */

/** Préfixe des jetons du socle. */
export const PREFIXE_JETON = '--injs-'

/**
 * Catégories de classement, dans l'ordre d'affichage de la planche.
 * L'ordre des préfixes compte : `--injs-blue-pale` doit tomber dans
 * « Couleurs » avant qu'un préfixe plus général ne le capture.
 */
export const CATEGORIES = [
  { id: 'couleur', libelle: 'Couleurs', prefixes: ['indigo', 'navy', 'blue', 'sky', 'cyan', 'success', 'warning', 'danger', 'info', 'teal', 'bg', 'surface', 'border', 'text', 'gradient'] },
  { id: 'typographie', libelle: 'Typographie', prefixes: ['font', 'fs', 'lh'] },
  { id: 'espace', libelle: 'Espacements', prefixes: ['space'] },
  { id: 'forme', libelle: 'Rayons et ombres', prefixes: ['radius', 'shadow'] },
  { id: 'mouvement', libelle: 'Mouvement et focus', prefixes: ['transition', 'focus'] },
  { id: 'verre', libelle: 'Verre et points de rupture', prefixes: ['glass', 'bp'] },
]

export const CATEGORIE_INCONNUE = { id: 'divers', libelle: 'Divers' }

/**
 * Catégorie d'un jeton d'après son suffixe.
 *
 * @param {string} nom nom complet du jeton, avec ou sans le préfixe `--injs-`
 * @returns {{id: string, libelle: string}}
 */
export function classerJeton(nom) {
  const suffixe = String(nom || '').replace(PREFIXE_JETON, '').toLowerCase()
  if (!suffixe) return CATEGORIE_INCONNUE
  // `fs`, `lh`, `bp` sont des préfixes courts : on exige un séparateur pour
  // éviter que « surface » ne soit classé comme « fs » ou « space ».
  for (const categorie of CATEGORIES) {
    const trouve = categorie.prefixes.some(
      (prefixe) => suffixe === prefixe || suffixe.startsWith(`${prefixe}-`),
    )
    if (trouve) return { id: categorie.id, libelle: categorie.libelle }
  }
  return CATEGORIE_INCONNUE
}

/**
 * Noms de jetons exposés par une **déclaration calculée** (`getComputedStyle`).
 *
 * Les navigateurs modernes énumèrent aussi les propriétés personnalisées ; on
 * ne retient que le préfixe du socle. Un objet sans `length` (environnement de
 * test, navigateur ancien) renvoie une liste vide : l'appelant complète alors
 * avec `jetonsDepuisFeuilles`.
 *
 * @param {CSSStyleDeclaration|object} styleCalcule
 * @returns {string[]}
 */
export function jetonsDepuisStyleCalcule(styleCalcule) {
  const noms = []
  const total = Number(styleCalcule?.length)
  if (!Number.isFinite(total) || total <= 0) return noms
  for (let index = 0; index < total; index += 1) {
    const nom = styleCalcule[index]
    if (typeof nom === 'string' && nom.startsWith(PREFIXE_JETON)) noms.push(nom)
  }
  return noms
}

/**
 * Noms de jetons déclarés dans les **feuilles de style** du document.
 *
 * C'est la source la plus fiable pour une application dont les CSS sont
 * locaux : elle énumère les déclarations `--injs-…` réellement écrites, y
 * compris celles qu'un `getComputedStyle` n'exposerait pas. Les feuilles
 * d'une autre origine lèvent une exception à la lecture de `cssRules` : elles
 * sont ignorées, comme le fait le navigateur lui-même.
 *
 * @param {StyleSheetList|Array} feuilles
 * @returns {string[]}
 */
export function jetonsDepuisFeuilles(feuilles) {
  const noms = new Set()
  const liste = feuilles ? Array.from(feuilles) : []
  for (const feuille of liste) {
    let regles = null
    try {
      regles = feuille?.cssRules ?? null
    } catch {
      continue // feuille d'une autre origine : non lisible, on l'ignore
    }
    if (!regles) continue
    const parcourir = (listeRegles) => {
      for (const regle of Array.from(listeRegles)) {
        // Règles groupantes (@media, @supports) : on descend pour ne pas
        // manquer les jetons redéfinis dans un point de rupture.
        if (regle?.cssRules) {
          try {
            parcourir(regle.cssRules)
          } catch {
            // Sous-feuille illisible : on garde ce qui a déjà été collecté.
          }
        }
        const declarations = regle?.style
        if (!declarations || typeof declarations.length !== 'number') continue
        for (let index = 0; index < declarations.length; index += 1) {
          const nom = declarations[index]
          if (typeof nom === 'string' && nom.startsWith(PREFIXE_JETON)) noms.add(nom)
        }
      }
    }
    parcourir(regles)
  }
  return [...noms]
}

/**
 * Extrait les jetons du socle depuis une déclaration de style calculée.
 *
 * @param {(nom: string) => string} lire  accesseur, typiquement
 *   `(n) => getComputedStyle(document.documentElement).getPropertyValue(n)`
 * @param {string[]} noms noms complets des jetons à interroger (`--injs-…`)
 * @returns {Array<{nom: string, valeur: string, categorie: object}>}
 */
export function extraireJetons(lire, noms) {
  const jetons = []
  for (const nom of noms) {
    if (!String(nom).startsWith(PREFIXE_JETON)) continue
    const brute = lire(nom)
    const valeur = typeof brute === 'string' ? brute.trim() : ''
    // Un jeton non déclaré (ou vide) ne doit pas apparaître comme une valeur :
    // la planche affiche « non déclaré » plutôt qu'une case vide trompeuse.
    jetons.push({ nom, valeur: valeur || null, categorie: classerJeton(nom) })
  }
  return jetons
}

/**
 * Filtre la liste des jetons sur le nom **ou** la valeur, sans casse.
 *
 * @param {Array<{nom: string, valeur: ?string}>} jetons
 * @param {string} requete
 */
export function filtrerJetons(jetons, requete) {
  const q = String(requete || '').trim().toLowerCase()
  if (!q) return jetons
  return jetons.filter(
    (jeton) => jeton.nom.toLowerCase().includes(q)
      || String(jeton.valeur || '').toLowerCase().includes(q),
  )
}

/** Regroupe des jetons par catégorie, dans l'ordre de `CATEGORIES`. */
export function regrouperParCategorie(jetons) {
  const ordre = [...CATEGORIES.map((c) => c.id), CATEGORIE_INCONNUE.id]
  const groupes = new Map(ordre.map((id) => [id, []]))
  for (const jeton of jetons) {
    const liste = groupes.get(jeton.categorie.id) || groupes.get(CATEGORIE_INCONNUE.id)
    liste.push(jeton)
  }
  return ordre
    .map((id) => {
      const liste = groupes.get(id)
      const libelle = [...CATEGORIES, CATEGORIE_INCONNUE].find((c) => c.id === id).libelle
      return { id, libelle, jetons: liste }
    })
    .filter((groupe) => groupe.jetons.length > 0)
}

/* ────────────────────────────── Contraste WCAG ───────────────────────────── */

/**
 * Convertit une couleur CSS hexadécimale (`#abc`, `#aabbcc`, avec ou sans
 * dièse) en composantes 0–255. Toute autre notation renvoie `null` : la
 * planche n'invente pas de conversion, elle signale « non calculable ».
 */
export function hexVersRgb(couleur) {
  const brut = String(couleur || '').trim().replace(/^#/, '')
  if (!/^([0-9a-f]{3}|[0-9a-f]{6})$/i.test(brut)) return null
  const complet = brut.length === 3
    ? brut.split('').map((c) => c + c).join('')
    : brut
  return {
    r: parseInt(complet.slice(0, 2), 16),
    g: parseInt(complet.slice(2, 4), 16),
    b: parseInt(complet.slice(4, 6), 16),
  }
}

/** Luminance relative WCAG 2.2 (formule officielle, canal linéarisé). */
export function luminanceRelative(couleur) {
  const rgb = hexVersRgb(couleur)
  if (!rgb) return null
  const canal = (v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * canal(rgb.r) + 0.7152 * canal(rgb.g) + 0.0722 * canal(rgb.b)
}

/**
 * Ratio de contraste entre deux couleurs, de 1 à 21.
 * Renvoie `null` si l'une des deux couleurs n'est pas calculable.
 */
export function ratioContraste(couleurA, couleurB) {
  const a = luminanceRelative(couleurA)
  const b = luminanceRelative(couleurB)
  if (a === null || b === null) return null
  const clair = Math.max(a, b)
  const sombre = Math.min(a, b)
  return (clair + 0.05) / (sombre + 0.05)
}

/**
 * Verdict WCAG 2.2 AA / AAA pour du **texte courant**.
 *
 * AA exige 4,5:1 ; AAA exige 7:1 ; 3:1 suffit pour un élément non textuel ou
 * un grand texte, ce que la planche signale explicitement plutôt que de le
 * présenter comme conforme pour du texte courant.
 */
export function verdictContraste(ratio) {
  if (ratio === null) return { niveau: 'non calculable', conformeAA: false, conformeAAA: false, usage: 'Couleur non hexadécimale' }
  if (ratio >= 7) return { niveau: 'AAA', conformeAA: true, conformeAAA: true, usage: 'Texte courant' }
  if (ratio >= 4.5) return { niveau: 'AA', conformeAA: true, conformeAAA: false, usage: 'Texte courant' }
  if (ratio >= 3) return { niveau: 'AA — grand texte', conformeAA: false, conformeAAA: false, usage: 'Grand texte et éléments d’interface uniquement' }
  return { niveau: 'Insuffisant', conformeAA: false, conformeAAA: false, usage: 'À réserver aux aplats décoratifs' }
}

/**
 * Paires réellement à démontrer : chaque couleur fonctionnelle du socle,
 * en texte sur fond blanc et en texte sur fond marine (`--injs-navy`).
 * Les couleurs sont des jetons du socle, pas des valeurs inventées.
 */
export const PAIRES_CONTRASTE = [
  { libelle: 'Texte principal sur surface', texte: '#0F1F33', fond: '#FFFFFF' },
  { libelle: 'Texte atténué sur surface', texte: '#64748B', fond: '#FFFFFF' },
  { libelle: 'Bleu royal sur surface (lien, action)', texte: '#1267D6', fond: '#FFFFFF' },
  { libelle: 'Vert succès sur surface', texte: '#16A36A', fond: '#FFFFFF' },
  { libelle: 'Orange attention sur surface', texte: '#F59E0B', fond: '#FFFFFF' },
  { libelle: 'Rouge destructif sur surface', texte: '#DC3545', fond: '#FFFFFF' },
  { libelle: 'Violet analytique sur surface', texte: '#805AD5', fond: '#FFFFFF' },
  { libelle: 'Turquoise information sur surface', texte: '#0D9488', fond: '#FFFFFF' },
  { libelle: 'Texte inversé sur marine', texte: '#FFFFFF', fond: '#071B3A' },
  { libelle: 'Accent ciel sur marine', texte: '#35BDF5', fond: '#071B3A' },
]

/** Calcule la table de contraste complète (ratio arrondi + verdict). */
export function tableContraste(paires = PAIRES_CONTRASTE) {
  return paires.map((paire) => {
    const ratio = ratioContraste(paire.texte, paire.fond)
    return {
      ...paire,
      ratio,
      ratioAffiche: ratio === null ? '—' : `${ratio.toFixed(2)} : 1`,
      verdict: verdictContraste(ratio),
    }
  })
}

/* ───────────────────────────── Point de rupture ──────────────────────────── */

/** Points de rupture du socle (`--injs-bp-*`), en pixels. */
export const POINTS_DE_RUPTURE = [
  { max: 480, libelle: '≤ 480 px — mobile' },
  { max: 768, libelle: '≤ 768 px — tablette' },
  { max: 1024, libelle: '≤ 1024 px — petit portable' },
  { max: 1366, libelle: '≤ 1366 px — bureau' },
  { max: Infinity, libelle: '> 1366 px — grand écran' },
]

/** Point de rupture actif pour une largeur de fenêtre donnée. */
export function pointDeRupture(largeur) {
  const w = Number(largeur)
  if (!Number.isFinite(w) || w <= 0) return POINTS_DE_RUPTURE[POINTS_DE_RUPTURE.length - 1].libelle
  return POINTS_DE_RUPTURE.find((point) => w <= point.max).libelle
}

/* ──────────────────────── Estimation de la largeur ───────────────────────── */

/**
 * Mesure la largeur disponible pour la planche.
 *
 * On interroge d'abord l'élément racine de la planche (largeur réelle du
 * contenu, barre latérale déduite), et on retombe sur la fenêtre si l'élément
 * n'est pas encore monté (premier rendu, environnement de test).
 */
export function largeurDisponible(element, fenetre) {
  const largeurElement = element?.clientWidth
  if (Number.isFinite(largeurElement) && largeurElement > 0) return largeurElement
  const largeurFenetre = fenetre?.innerWidth
  return Number.isFinite(largeurFenetre) && largeurFenetre > 0 ? largeurFenetre : 0
}
