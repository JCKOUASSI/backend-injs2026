/**
 * Ligne du sélecteur de formateur (module) avec message de conflit visible.
 */
export default function FormateurAssignPickerItem({ formateur, onAssign }) {
  const { nom, prenom, specialite, conflit_assignation: conflit } = formateur
  const occupé = Boolean(conflit)

  return (
    <div
      className={`border rounded p-2 mb-2 ${occupé ? 'bg-light' : ''}`}
      style={{ borderColor: occupé ? 'var(--ci-warning, #f5c10b)' : undefined }}
    >
      <div className="d-flex justify-content-between align-items-start gap-2">
        <div className="min-w-0">
          <div className="fw-semibold">{nom} {prenom}</div>
          {specialite && <div className="text-muted small">{specialite}</div>}
        </div>
        {!occupé && (
          <button
            type="button"
            onClick={() => onAssign(formateur.id)}
            className="btn btn-outline-success btn-sm flex-shrink-0"
            title="Assigner cet enseignant"
          >
            <i className="bi bi-plus"></i>
          </button>
        )}
      </div>
      {occupé && (
        <div className="alert alert-warning py-2 px-2 small mb-0 mt-2" role="status">
          <div className="d-flex align-items-start gap-2">
            <i className="bi bi-calendar-x flex-shrink-0 mt-1" aria-hidden="true"></i>
            <span style={{ lineHeight: 1.45 }}>{conflit}</span>
          </div>
        </div>
      )}
    </div>
  )
}
