/**
 * Jauge de complétude d'un dossier — autonome.
 *
 * Elle reposait sur `.progress` / `.bg-*` / `.d-flex` de Bootstrap, absent du
 * bundle : la piste restait grise pleine largeur, le remplissage invisible et
 * le compteur passait à la ligne sous la barre. Le balisage et les styles sont
 * donc portés par le design system `.cand-jauge*` (voir candidatures.css).
 */
const VARIANTES = {
  complet: 'succes',
  partiel: 'attention',
  faible: 'danger',
}

export default function CompletudeBar({ validees = 0, total = 0, taux }) {
  const pourcentage = taux ?? (total ? Math.round((validees * 100) / total) : 0)
  const borne = Math.max(0, Math.min(100, Math.round(pourcentage)))
  const variante = borne === 100 ? VARIANTES.complet : borne >= 50 ? VARIANTES.partiel : VARIANTES.faible

  return (
    <div className="cand-jauge">
      <div
        className={`cand-jauge-piste cand-jauge-piste--${variante}`}
        role="progressbar"
        aria-label={`Pièces validées : ${validees} sur ${total}`}
        aria-valuenow={borne}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <span className={`cand-jauge-part cand-jauge-part--${variante}`} style={{ width: `${borne}%` }} />
      </div>
      <span className="cand-jauge-valeur">
        {validees}/{total}
      </span>
    </div>
  )
}
