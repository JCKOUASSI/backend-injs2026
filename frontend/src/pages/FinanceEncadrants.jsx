import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { fmtDuration } from '../components/FinanceStatsGrid'
import FinancePageShell, { FinanceNavActions } from '../components/finance/FinancePageShell'
import {
  buildFinanceListSearchParams,
  buildFinanceQuery,
  FINANCE_QUERY_STORAGE_KEY,
  resolveFinancePeriod,
  saveFinancePeriod,
} from '../utils/financePeriod'
import { usePersistedListQuery } from '../hooks/usePersistedListQuery'

export default function FinanceEncadrants() {
  const { showToast } = useToast()
  const [searchParams] = useSearchParams()
  const [period, setPeriod] = useState(() => resolveFinancePeriod())
  const [appliedPeriod, setAppliedPeriod] = useState(() => resolveFinancePeriod())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState(null)
  const [exporting, setExporting] = useState(false)

  usePersistedListQuery(
    FINANCE_QUERY_STORAGE_KEY,
    () => buildFinanceListSearchParams(resolveFinancePeriod(), {}),
    [searchParams],
  )

  const loadData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const qs = buildFinanceQuery(appliedPeriod).toString()
      const path = qs ? `/formations/finance/encadrants/?${qs}` : '/formations/finance/encadrants/'
      const res = await api.get(path)
      setData(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Impossible de charger le rapport encadrants.')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [appliedPeriod])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleApply = () => {
    saveFinancePeriod(period)
    setAppliedPeriod({ ...period })
  }

  const downloadBlob = (blob, filename) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  const exportEncadrants = async (format) => {
    const ext = format === 'pdf' ? 'pdf' : 'xlsx'
    const qs = buildFinanceQuery(appliedPeriod).toString()
    const base = format === 'pdf'
      ? '/exports/finance/encadrants/pdf/'
      : '/exports/finance/encadrants/excel/'
    const path = qs ? `${base}?${qs}` : base
    setExporting(true)
    try {
      const { blob, fileName } = await api.getBlob(path)
      downloadBlob(blob, fileName || `liste_encadrants.${ext}`)
      showToast(`Liste encadrants exportée (${ext.toUpperCase()})`)
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur export encadrants', 'error')
    } finally {
      setExporting(false)
    }
  }

  const encadrants = Array.isArray(data?.encadrants) ? data.encadrants : []
  const totaux = data?.totaux || {}

  return (
    <FinancePageShell
      title="Encadrants"
      subtitle="Volumes horaires planifiés et réalisés par encadrant et par groupe"
      icon="bi-person-badge"
      actions={<FinanceNavActions active="encadrants" />}
      period={period}
      onPeriodChange={setPeriod}
      onPeriodApply={handleApply}
      periodApplying={loading}
    >
      <div className="finance-card mb-3">
        <div className="d-flex flex-wrap align-items-center justify-content-between gap-2">
          <p className="text-muted small mb-0">
            Rapport basé sur les modules supervisés (encadrant assigné au module).
          </p>
          <div className="d-flex flex-wrap gap-2">
            <button
              type="button"
              className="btn btn-outline-success btn-sm"
              disabled={exporting || loading}
              onClick={() => exportEncadrants('excel')}
            >
              <i className="bi bi-file-earmark-spreadsheet me-1"></i>
              {exporting ? 'Export…' : 'Encadrants Excel'}
            </button>
            <button
              type="button"
              className="btn btn-outline-danger btn-sm"
              disabled={exporting || loading}
              onClick={() => exportEncadrants('pdf')}
            >
              <i className="bi bi-file-earmark-pdf me-1"></i>
              {exporting ? 'Export…' : 'Encadrants PDF'}
            </button>
          </div>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {loading ? (
        <div className="loading py-5"><div className="spinner"></div></div>
      ) : (
        <>
          <div className="finance-hero-kpis mb-4">
            <div className="finance-hero-kpi finance-hero-kpi--rate">
              <div className="finance-hero-kpi-label">
                <i className="bi bi-person-badge me-1"></i>
                Encadrants
              </div>
              <div className="finance-hero-kpi-value">{totaux.encadrants_count ?? 0}</div>
            </div>
            <div className="finance-hero-kpi finance-hero-kpi--plan">
              <div className="finance-hero-kpi-label">
                <i className="bi bi-clock me-1"></i>
                Volume planifié
              </div>
              <div className="finance-hero-kpi-value">{fmtDuration(totaux.planned_minutes)}</div>
            </div>
            <div className="finance-hero-kpi finance-hero-kpi--time">
              <div className="finance-hero-kpi-label">
                <i className="bi bi-clock-history me-1"></i>
                Volume réalisé
              </div>
              <div className="finance-hero-kpi-value">{fmtDuration(totaux.realized_minutes)}</div>
            </div>
          </div>

          {encadrants.length === 0 ? (
            <div className="finance-empty">
              <i className="bi bi-person-badge"></i>
              Aucun encadrant avec activité sur la période sélectionnée.
            </div>
          ) : (
            encadrants.map((block) => (
              <section key={block.encadrant_id} className="finance-section mb-4">
                <div className="finance-section-header">
                  <h2>
                    <i className="bi bi-person-badge"></i>
                    {block.encadrant_label || block.encadrant_username}
                  </h2>
                  <span className="badge-bg-secondary">
                    {fmtDuration(block.sous_total?.planned_minutes)} planifié ·{' '}
                    {fmtDuration(block.sous_total?.realized_minutes)} réalisé
                  </span>
                </div>
                <div className="finance-table-wrap">
                  <table className="finance-table">
                    <thead>
                      <tr>
                        <th>Groupe</th>
                        <th>Grade</th>
                        <th>Module</th>
                        <th>Formation</th>
                        <th>Séances</th>
                        <th>Planifié</th>
                        <th>Réalisé</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(block.lignes || []).map((ligne) => (
                        <tr key={ligne.module_id}>
                          <td><strong>{ligne.groupe}</strong></td>
                          <td>{ligne.grade || '—'}</td>
                          <td>{ligne.module_intitule || '—'}</td>
                          <td className="small text-muted">{ligne.formation_intitule || '—'}</td>
                          <td><span className="badge-bg-secondary">{ligne.sessions_count ?? 0}</span></td>
                          <td style={{ whiteSpace: 'nowrap' }}>{fmtDuration(ligne.planned_minutes)}</td>
                          <td style={{ whiteSpace: 'nowrap' }}>{fmtDuration(ligne.realized_minutes)}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr>
                        <td colSpan={5} style={{ fontWeight: 600 }}>Sous-total</td>
                        <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
                          {fmtDuration(block.sous_total?.planned_minutes)}
                        </td>
                        <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
                          {fmtDuration(block.sous_total?.realized_minutes)}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </section>
            ))
          )}
        </>
      )}
    </FinancePageShell>
  )
}
