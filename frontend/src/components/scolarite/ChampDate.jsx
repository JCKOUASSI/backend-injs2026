import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

/** ── Saisie de date au format JJ/MM/AAAA ─────────────────────────────────────
 *  Le champ natif <input type="date"> impose un calendrier ou une saisie
 *  segmentée qui varie selon les navigateurs et gêne la frappe libre. Les
 *  formulaires utilisent donc ce champ texte : masque automatique des
 *  séparateurs pendant la frappe, calendrier premium en complément,
 *  validation complète, puis conversion en ISO (AAAA-MM-JJ) pour l'API. */

export function masquerDateFrancaise(valeur) {
  const chiffres = String(valeur ?? '').replace(/\D/g, '').slice(0, 8)
  return [chiffres.slice(0, 2), chiffres.slice(2, 4), chiffres.slice(4, 8)]
    .filter(Boolean)
    .join('/')
}

/** 'JJ/MM/AAAA' → 'AAAA-MM-JJ' ; null si le format est incomplet ou si la
 *  date n'existe pas (31 février, 29 février d'une année non bissextile…). */
export function dateFrancaiseVersIso(valeur) {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(String(valeur ?? '').trim())
  if (!m) return null
  const [, jj, mm, aaaa] = m
  const date = new Date(Number(aaaa), Number(mm) - 1, Number(jj))
  const coherente = date.getFullYear() === Number(aaaa)
    && date.getMonth() === Number(mm) - 1
    && date.getDate() === Number(jj)
  return coherente ? `${aaaa}-${mm}-${jj}` : null
}

/** 'AAAA-MM-JJ' → 'JJ/MM/AAAA' ('' si vide ou illisible). */
export function isoVersDateFrancaise(valeur) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(valeur ?? ''))
  return m ? `${m[3]}/${m[2]}/${m[1]}` : ''
}

/** Message d'erreur de la date de naissance saisie ('' si absente ou valide). */
export function erreurDateNaissance(valeur) {
  if (!String(valeur ?? '').trim()) return ''
  const iso = dateFrancaiseVersIso(valeur)
  if (!iso) {
    return 'Date de naissance invalide : saisissez-la au format JJ/MM/AAAA (par exemple 14/03/2007).'
  }
  const maintenant = new Date()
  const aujourdhui = [
    maintenant.getFullYear(),
    String(maintenant.getMonth() + 1).padStart(2, '0'),
    String(maintenant.getDate()).padStart(2, '0'),
  ].join('-')
  if (iso > aujourdhui) return 'La date de naissance ne peut pas être dans le futur.'
  if (Number(iso.slice(0, 4)) < 1920) {
    return 'Date de naissance invalide : vérifiez l’année saisie (format JJ/MM/AAAA).'
  }
  return ''
}

/** Message d'erreur générique d'une date JJ/MM/AAAA ('' si absente ou valide). */
export function erreurDateFrancaise(valeur, libelle = 'La date') {
  if (!String(valeur ?? '').trim()) return ''
  if (!dateFrancaiseVersIso(valeur)) {
    return `${libelle} est invalide : saisissez-la au format JJ/MM/AAAA (par exemple 14/03/2027).`
  }
  return ''
}

export const MOIS_FR = [
  'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
  'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
]
const JOURS_FR = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
const ANNEE_MIN_DATE = 1920

function dateVersJjMmAaaa(date) {
  const jj = String(date.getDate()).padStart(2, '0')
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  return `${jj}/${mm}/${date.getFullYear()}`
}

function dateVersIsoLocale(date) {
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const jj = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${mm}-${jj}`
}

/** Champ date hybride : saisie libre masquée + bouton ouvrant le calendrier.
 *
 *  Le calendrier est rendu en **portail** (position fixe sur le corps du
 *  document) : les panneaux de formulaire ont un `overflow: hidden` qui
 *  rognerait — jusqu'à l'invisibilité — une fenêtre positionnée en absolu
 *  dans le champ. La position est calculée depuis le champ, retournée vers
 *  le haut si la place manque en dessous, et suivie au défilement.
 *
 *  Props :
 *  - `reculAnnees` : décalage du calendrier à l'ouverture quand aucune date
 *    n'est saisie (20 par défaut — dates de naissance ; 0 pour les dates
 *    de planification).
 *  - `futurInterdit` : dates futures désactivées (vrai par défaut) ; faux
 *    pour les dates à venir (campagnes, épreuves…), années étendues à +5.
 *  - `etiquetteCalendrier` : libellé accessible de la fenêtre du calendrier.
 */
export default function ChampDate({
  id, valeur, onChange,
  reculAnnees = 20, futurInterdit = true,
  etiquetteCalendrier = 'Choisir une date',
  aide = 'Saisie libre (JJ/MM/AAAA) ou via le calendrier',
  autoComplete,
}) {
  const [ouvert, setOuvert] = useState(false)
  const [moisVisible, setMoisVisible] = useState(null)
  const [coords, setCoords] = useState(null)
  const zoneRef = useRef(null)
  const saisieRef = useRef(null)
  const popupRef = useRef(null)

  const fermer = useCallback(() => {
    setOuvert(false)
    setCoords(null)
  }, [])

  const placer = useCallback(() => {
    const champ = saisieRef.current
    if (!champ) return
    const r = champ.getBoundingClientRect()
    const largeur = Math.min(302, window.innerWidth - 16)
    const hauteur = popupRef.current?.offsetHeight || 380
    const left = Math.max(8, Math.min(r.left, window.innerWidth - largeur - 8))
    let top = r.bottom + 8
    if (top + hauteur > window.innerHeight - 8) {
      top = Math.max(8, r.top - hauteur - 8)
    }
    setCoords({ top, left })
  }, [])

  const aujourdhui = useMemo(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  }, [])
  const selectionIso = dateFrancaiseVersIso(valeur)
  const anneeMax = futurInterdit
    ? aujourdhui.getFullYear()
    : aujourdhui.getFullYear() + 5

  const ouvrir = () => {
    if (ouvert) {
      fermer()
      return
    }
    if (selectionIso) {
      const [annee, mois] = selectionIso.split('-').map(Number)
      setMoisVisible({ annee, mois: mois - 1 })
    } else {
      setMoisVisible({
        annee: aujourdhui.getFullYear() - reculAnnees,
        mois: aujourdhui.getMonth(),
      })
    }
    setOuvert(true)
  }

  // Placement initial (le portail vient d'être monté, encore invisible).
  useLayoutEffect(() => {
    if (ouvert) placer()
  }, [ouvert, placer])

  useEffect(() => {
    if (!ouvert) return undefined
    const clicDehors = (e) => {
      const dedans = zoneRef.current?.contains(e.target)
        || popupRef.current?.contains(e.target)
      if (!dedans) fermer()
    }
    const touche = (e) => {
      if (e.key === 'Escape') {
        fermer()
        saisieRef.current?.focus()
      }
    }
    document.addEventListener('mousedown', clicDehors)
    document.addEventListener('keydown', touche)
    window.addEventListener('resize', placer)
    window.addEventListener('scroll', placer, true)
    return () => {
      document.removeEventListener('mousedown', clicDehors)
      document.removeEventListener('keydown', touche)
      window.removeEventListener('resize', placer)
      window.removeEventListener('scroll', placer, true)
    }
  }, [ouvert, fermer, placer])

  const decalerMois = (delta) => setMoisVisible(({ annee, mois }) => {
    const d = new Date(annee, mois + delta, 1)
    return { annee: d.getFullYear(), mois: d.getMonth() }
  })

  const choisir = (date) => {
    onChange(dateVersJjMmAaaa(date))
    fermer()
    saisieRef.current?.focus()
  }

  // Grille de 6 semaines commençant un lundi (jours des mois voisins inclus).
  const cellules = useMemo(() => {
    if (!moisVisible) return []
    const premier = new Date(moisVisible.annee, moisVisible.mois, 1)
    const decalage = (premier.getDay() + 6) % 7 // lundi = première colonne
    const debut = new Date(premier)
    debut.setDate(1 - decalage)
    return Array.from({ length: 42 }, (_, i) => {
      const d = new Date(debut)
      d.setDate(debut.getDate() + i)
      return d
    })
  }, [moisVisible])

  const annees = useMemo(() => {
    const liste = []
    for (let a = anneeMax; a >= ANNEE_MIN_DATE; a -= 1) liste.push(a)
    return liste
  }, [anneeMax])

  const precedentBloque = moisVisible
    && moisVisible.annee === ANNEE_MIN_DATE && moisVisible.mois === 0
  const suivantBloque = moisVisible && (futurInterdit
    ? new Date(moisVisible.annee, moisVisible.mois + 1, 1) > aujourdhui
    : moisVisible.annee === anneeMax && moisVisible.mois === 11)

  return (
    <div className="cand-date" ref={zoneRef}>
      <div className="cand-date-ligne">
        <input
          id={id} type="text" inputMode="numeric" autoComplete={autoComplete}
          className="cand-saisie" value={valeur} ref={saisieRef}
          placeholder="JJ/MM/AAAA" title="Format JJ/MM/AAAA — saisie libre au clavier ou calendrier"
          aria-describedby={`${id}-aide`}
          aria-invalid={valeur.length === 10 && !dateFrancaiseVersIso(valeur)}
          onChange={(e) => onChange(masquerDateFrancaise(e.target.value))}
        />
        <button
          type="button" className="cand-date-bouton" onClick={ouvrir}
          aria-label="Ouvrir le calendrier" aria-haspopup="dialog"
          aria-expanded={ouvert} title="Choisir la date dans le calendrier"
        >
          <i className="bi bi-calendar3" aria-hidden="true"></i>
        </button>
      </div>
      <span className="cand-texte-doux" id={`${id}-aide`}>{aide}</span>

      {ouvert && moisVisible && createPortal(
        <div
          className="cand-cal" role="dialog" aria-label={etiquetteCalendrier}
          ref={popupRef}
          style={{
            top: coords?.top ?? -9999,
            left: coords?.left ?? -9999,
            visibility: coords ? 'visible' : 'hidden',
          }}
        >
          <div className="cand-cal-entete">
            <button
              type="button" className="cand-cal-nav" onClick={() => decalerMois(-1)}
              disabled={precedentBloque} aria-label="Mois précédent"
            >
              <i className="bi bi-chevron-left" aria-hidden="true"></i>
            </button>
            <select
              className="cand-cal-select cand-cal-select--mois" aria-label="Mois affiché"
              value={moisVisible.mois}
              onChange={(e) => setMoisVisible({ ...moisVisible, mois: Number(e.target.value) })}
            >
              {MOIS_FR.map((mois, i) => <option key={mois} value={i}>{mois}</option>)}
            </select>
            <select
              className="cand-cal-select" aria-label="Année affichée"
              value={moisVisible.annee}
              onChange={(e) => setMoisVisible({ ...moisVisible, annee: Number(e.target.value) })}
            >
              {annees.map((annee) => <option key={annee} value={annee}>{annee}</option>)}
            </select>
            <button
              type="button" className="cand-cal-nav" onClick={() => decalerMois(1)}
              disabled={suivantBloque} aria-label="Mois suivant"
            >
              <i className="bi bi-chevron-right" aria-hidden="true"></i>
            </button>
          </div>

          <div className="cand-cal-jours" aria-hidden="true">
            {JOURS_FR.map((jour) => <span key={jour}>{jour}</span>)}
          </div>
          <div className="cand-cal-grille">
            {cellules.map((date) => {
              const iso = dateVersIsoLocale(date)
              const classes = ['cand-cal-jour']
              if (date.getMonth() !== moisVisible.mois) classes.push('cand-cal-jour--hors')
              if (date.getTime() === aujourdhui.getTime()) classes.push('cand-cal-jour--aujourdhui')
              if (iso === selectionIso) classes.push('cand-cal-jour--choisi')
              return (
                <button
                  key={iso} type="button" className={classes.join(' ')}
                  disabled={futurInterdit && date > aujourdhui}
                  aria-label={`${date.getDate()} ${MOIS_FR[date.getMonth()]} ${date.getFullYear()}`}
                  aria-pressed={iso === selectionIso}
                  onClick={() => choisir(date)}
                >
                  {date.getDate()}
                </button>
              )
            })}
          </div>

          <div className="cand-cal-pied">
            <button
              type="button" className="cand-cal-effacer"
              onClick={() => { onChange(''); fermer(); saisieRef.current?.focus() }}
            >
              <i className="bi bi-eraser" aria-hidden="true"></i> Effacer
            </button>
          </div>
        </div>, document.body)}
    </div>
  )
}
