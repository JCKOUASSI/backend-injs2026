/**
 * Panneau du DIFFÉRENTIEL DE DROITS obligatoire (C2 §2, règle d'interface S2).
 * Affiche en vert les permissions gagnées et en rouge celles perdues,
 * regroupées par module, ainsi que les rôles ajoutés/retirés et les
 * avertissements. L'acquittement est requis avant toute validation.
 */
import { useMemo } from 'react'
import {
  differentialAvertissementBloquant,
  libelleDomaine,
  resumerDifferential,
} from '@/utils/habilitations'

function BlocModule({ titre, modules, classe, icone }) {
  const entrees = Object.entries(modules).sort((a, b) => b[1] - a[1])
  if (entrees.length === 0) return null
  return (
    <div className={classe} data-testid={`diff-${classe}`}>
      <strong><i className={`bi ${icone} me-1`} />{titre}</strong>
      <ul className="mb-1">
        {entrees.map(([module, nombre]) => (
          <li key={module}>{libelleDomaine(module.toUpperCase()) || module} : <strong>{nombre}</strong> permission(s)</li>
        ))}
      </ul>
    </div>
  )
}

export default function DifferentialPanel({
  differentiel,
  acquitte,
  onAcquitte,
  bloquerInteraction = false,
}) {
  const resume = useMemo(() => resumerDifferential(differentiel), [differentiel])
  if (!differentiel) return null
  const bloquant = differentialAvertissementBloquant(resume)

  return (
    <div className="hab-carte" data-testid="differential-panel" style={{ borderColor: bloquant ? '#c62828' : undefined }}>
      <h3><i className="bi bi-scales me-2" />Différentiel de droits</h3>
      {resume.vide ? (
        <p className="hab-muted mb-0">Aucun changement de permissions : les droits restent identiques.</p>
      ) : (
        <>
          <p className="hab-muted">
            {resume.totalCible} permission(s) après modification contre {resume.totalActuel} actuellement.
          </p>
          {resume.rolesAjoutes.length > 0 && (
            <p className="hab-diff-gagne mb-1">Rôles ajoutés : {resume.rolesAjoutes.join(', ')}</p>
          )}
          {resume.rolesRetires.length > 0 && (
            <p className="hab-diff-perdu mb-1">Rôles retirés : {resume.rolesRetires.join(', ')}</p>
          )}
          <BlocModule titre={`Droits gagnés (${resume.totalGagnes})`} modules={resume.gagnesParModule}
                      classe="hab-diff-gagne" icone="bi-box-arrow-up-right" />
          <BlocModule titre={`Droits perdus (${resume.totalPerdus})`} modules={resume.perdusParModule}
                      classe="hab-diff-perdu" icone="bi-box-arrow-down-left" />
          <details>
            <summary className="hab-muted">Voir le détail des permissions</summary>
            <div className="hab-diff-liste">
              {resume.gagnes.map((c) => <div key={`g-${c}`} className="hab-diff-gagne">+ {c}</div>)}
              {resume.perdus.map((c) => <div key={`p-${c}`} className="hab-diff-perdu">− {c}</div>)}
            </div>
          </details>
        </>
      )}

      {resume.avertissements.map((a, i) => (
        <div key={i} className={`hab-avertissement${a.code === 'SEUIL_ADMINISTRATEURS' ? ' bloquant' : ''}`}
             data-testid="diff-avertissement">
          <i className="bi bi-exclamation-triangle me-1" />{a.message}
        </div>
      ))}

      {!resume.vide && (
        <label className="d-block mt-2" style={{ fontWeight: 600 }}>
          <input
            type="checkbox"
            className="me-2"
            checked={acquitte}
            disabled={bloquerInteraction || bloquant}
            onChange={(e) => onAcquitte(e.target.checked)}
            data-testid="diff-acquittement"
          />
          J'ai pris connaissance des droits gagnés et perdus et je confirme cette modification.
        </label>
      )}
      {bloquant && (
        <p className="text-danger fw-bold mb-0" data-testid="diff-bloque">
          Opération bloquante : le seuil minimal d'administrateurs serait franchi.
        </p>
      )}
    </div>
  )
}
