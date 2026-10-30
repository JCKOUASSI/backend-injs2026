import React from 'react'

export default function LmdPipeline({ steps = [] }) {
  // 8 étapes canoniques du parcours LMD : les LIBELLÉS sont ceux de la
  // maquette, mais plus aucun effectif n'est inventé. Ces étapes affichaient
  // des valeurs figées (2 340 candidatures, 1 248 inscriptions, 482 diplômes)
  // qui se présentaient comme les cohortes réelles de l'établissement.
  const etapesCanoniques = [
    { id: 'candidature', label: 'Candidature', icon: 'bi-person' },
    { id: 'selection', label: 'Sélection', icon: 'bi-check2-circle' },
    { id: 'admission', label: 'Admission', icon: 'bi-card-checklist' },
    { id: 'inscription', label: 'Inscription', icon: 'bi-person-check' },
    { id: 'enseignement', label: 'Enseignement', icon: 'bi-journal-bookmark' },
    { id: 'evaluation', label: 'Évaluation', icon: 'bi-clipboard-check' },
    { id: 'jury', label: 'Jury', icon: 'bi-award' },
    { id: 'diplome', label: 'Diplôme', icon: 'bi-mortarboard' },
  ]

  // Correspondance entre les identifiants de l'API et ceux de la maquette.
  const equivalents = {
    candidature: ['candidature', 'candidatures'],
    diplome: ['diplome', 'diplomation'],
    enseignement: ['enseignement', 'cours'],
  }

  const affiche = (valeur) => {
    if (valeur === null || valeur === undefined || valeur === '') return '—'
    return typeof valeur === 'number' ? valeur.toLocaleString('fr-FR') : String(valeur)
  }

  const activeSteps = etapesCanoniques.map((etape) => {
    const ids = equivalents[etape.id] || [etape.id]
    const trouvee = steps.find((s) => ids.includes(s.id))
    return {
      ...etape,
      // Aucune valeur de repli : une étape sans donnée affiche « — ».
      value: trouvee ? affiche(trouvee.value) : '—',
      active: trouvee ? (trouvee.active ?? true) : false,
    }
  })

  return (
    <div className="glass-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div className="pipeline-card-header">
        <div>
          <h3 style={{ fontSize: '0.98rem', fontWeight: 800, color: '#071B3A', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <i className="bi bi-diagram-3-fill" style={{ color: '#1267D6' }}></i>
            Parcours LMD – De la candidature au diplôme
          </h3>
          <span style={{ fontSize: '0.75rem', color: '#64748B', fontWeight: 500 }}>
            Cycle de Vie Académique LMD (INJS 2026) · Progression intégrée des cohortes
          </span>
        </div>
        <span className="plaquette plaquette-primary">
          <i className="bi bi-clock-history"></i> En temps réel
        </span>
      </div>

      <div className="pipeline-stepper-track">
        {activeSteps.map((step, idx) => (
          <React.Fragment key={step.id}>
            <div className="pipeline-node">
              <div className="pipeline-node-badge">
                <i className={`bi ${step.icon}`}></i>
              </div>
              <div className="pipeline-node-title">{step.label}</div>
              <div className="pipeline-node-count">{step.value}</div>
            </div>
            {idx < activeSteps.length - 1 && (
              <div className="pipeline-connector-arrow">
                <i className="bi bi-chevron-right"></i>
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}
