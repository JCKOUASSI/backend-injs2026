const STATUT_CONFIG = {
  ok: { label: 'Conforme', className: 'badge-bg-success' },
  alerte: { label: 'Dans la tolérance', className: 'badge-bg-warning' },
  anomalie: { label: 'Hors tolérance', className: 'badge-bg-danger' },
  ecart: { label: 'Écart', className: 'badge-bg-secondary' },
  na: { label: '—', className: 'badge-bg-secondary' },
}

export default function FinanceToleranceBadge({ tolerance, showInactive = false }) {
  if (!tolerance) return null
  if (!tolerance.tolerance_active && !showInactive) {
    if (tolerance.statut === 'ecart') {
      const cfg = STATUT_CONFIG.ecart
      return <span className={`badge ${cfg.className}`}>{cfg.label}</span>
    }
    return null
  }
  const cfg = STATUT_CONFIG[tolerance.statut] || STATUT_CONFIG.na
  return <span className={`badge ${cfg.className}`}>{tolerance.statut_label || cfg.label}</span>
}
