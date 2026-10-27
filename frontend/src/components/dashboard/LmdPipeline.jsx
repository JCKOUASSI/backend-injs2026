import React from 'react'

export default function LmdPipeline({ steps = [] }) {
  // 8 étapes canoniques de la maquette INJS Marcory
  const defaultSteps = [
    { id: 'candidature', label: 'Candidature', value: '2 340', icon: 'bi-person' },
    { id: 'selection', label: 'Sélection', value: '1 892', icon: 'bi-check2-circle' },
    { id: 'admission', label: 'Admission', value: '1 562', icon: 'bi-card-checklist' },
    { id: 'inscription', label: 'Inscription', value: '1 248', icon: 'bi-person-check' },
    { id: 'enseignement', label: 'Enseignement', value: '1 186', icon: 'bi-journal-bookmark' },
    { id: 'evaluation', label: 'Évaluation', value: '982', icon: 'bi-clipboard-check' },
    { id: 'jury', label: 'Jury', value: '654', icon: 'bi-award' },
    { id: 'diplome', label: 'Diplôme', value: '482', icon: 'bi-mortarboard' },
  ]

  // Fusion avec les données dynamiques reçues de l'API / tests
  const activeSteps = defaultSteps.map((defStep) => {
    const found = steps.find((s) =>
      s.id === defStep.id ||
      (defStep.id === 'diplome' && s.id === 'diplomation') ||
      (defStep.id === 'candidature' && s.id === 'candidatures') ||
      (defStep.id === 'enseignement' && s.id === 'cours')
    )
    if (found) {
      return {
        ...defStep,
        value: typeof found.value === 'number' ? found.value.toLocaleString('fr-FR') : (found.value ?? defStep.value),
        active: found.active ?? true,
      }
    }
    return defStep
  })

  return (
    <div className="glass-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div className="pipeline-card-header">
        <div>
          <h3 style={{ fontSize: '0.98rem', fontWeight: 800, color: '#0B1F3A', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <i className="bi bi-diagram-3-fill" style={{ color: '#2F80ED' }}></i>
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
