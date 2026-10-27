import { Link } from 'react-router-dom'
import { financeNavHref } from '../../utils/financePeriod'
import FinancePeriodFilter from '../FinancePeriodFilter'

export default function FinancePageShell({
  title,
  subtitle,
  icon = 'bi-cash-coin',
  actions,
  period,
  onPeriodChange,
  onPeriodApply,
  periodApplying,
  periodeInfo,
  children,
  showPeriodFilter = true,
}) {
  return (
    <div className="finance-page">
      <header className="finance-hero">
        <div className="finance-hero-title">
          <div className="finance-hero-icon">
            <i className={`bi ${icon}`}></i>
          </div>
          <div>
            <h1>{title}</h1>
            {subtitle && <p>{subtitle}</p>}
          </div>
        </div>
        {actions && (
          <div className="finance-hero-actions">{actions}</div>
        )}
      </header>

      {showPeriodFilter && period && (
        <div className="finance-filter-panel">
          <div className="finance-filter-panel-inner">
            <FinancePeriodFilter
              period={period}
              onChange={onPeriodChange}
              onApply={onPeriodApply}
              applying={periodApplying}
              embedded
            />
          </div>
          {periodeInfo?.label && (
            <div className="finance-period-badge">
              <i className="bi bi-calendar-check"></i>
              <div>
                <strong>{periodeInfo.label}</strong>
                {periodeInfo.periode_label && (
                  <span className="ms-1">— {periodeInfo.periode_label}</span>
                )}
                {periodeInfo.description && (
                  <div style={{ opacity: 0.85, marginTop: '0.15rem', fontSize: '0.8rem' }}>
                    {periodeInfo.description}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {children}
    </div>
  )
}

export function FinanceNavActions({ active, pendingAjustements = 0 }) {
  return (
    <>
      <Link
        to={financeNavHref('/finance-dashboard')}
        className={`btn btn-sm ${active === 'dashboard' ? 'btn-finance-accent' : ''}`}
      >
        <i className="bi bi-speedometer2 me-1"></i>Tableau de bord
      </Link>
      <Link
        to={financeNavHref('/formateurs')}
        className={`btn btn-sm ${active === 'formateurs' ? 'btn-finance-accent' : ''}`}
      >
        <i className="bi bi-people me-1"></i>Enseignants
      </Link>
      <Link
        to={financeNavHref('/finance-encadrants')}
        className={`btn btn-sm ${active === 'encadrants' ? 'btn-finance-accent' : ''}`}
      >
        <i className="bi bi-person-badge me-1"></i>Encadrants
      </Link>
      <Link
        to={financeNavHref('/finance-ajustements')}
        className={`btn btn-sm ${active === 'ajustements' ? 'btn-finance-accent' : ''}`}
      >
        <i className="bi bi-arrow-left-right me-1"></i>Ajustements
        {pendingAjustements > 0 && (
          <span className="badge bg-danger ms-1">{pendingAjustements}</span>
        )}
      </Link>
      <Link
        to={financeNavHref('/finance-parametrage')}
        className={`btn btn-sm ${active === 'parametrage' ? 'btn-finance-accent' : ''}`}
      >
        <i className="bi bi-sliders me-1"></i>Paramétrage
      </Link>
    </>
  )
}
