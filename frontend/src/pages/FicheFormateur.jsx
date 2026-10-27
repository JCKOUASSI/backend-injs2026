import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'

export default function FicheFormateur() {
  const { formateurId, moduleId } = useParams()
  const { showToast } = useToast()
  const [fiche, setFiche] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetch = async () => {
      setLoading(true)
      try {
        const { data } = await api.get(`/suiviEvaluation/formateurs/${formateurId}/modules/${moduleId}/fiche/`)
        setFiche(data)
      } catch (err) {
        showToast(err?.response?.data?.detail || 'Erreur chargement fiche', 'error')
      } finally { setLoading(false) }
    }
    fetch()
    // showToast est stable (useCallback du ToastProvider).
  }, [formateurId, moduleId, showToast])

  const download = async (type) => {
    const path = type === 'pdf'
      ? `/suiviEvaluation/formateurs/${formateurId}/modules/${moduleId}/fiche/export/pdf/`
      : `/suiviEvaluation/formateurs/${formateurId}/modules/${moduleId}/fiche/export/xlsx/`
    try {
      const { blob, fileName } = await api.getBlob(path)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName || `fiche_formateur_${formateurId}_${moduleId}.${type === 'pdf' ? 'pdf' : 'xlsx'}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur export', 'error')
    }
  }

  if (loading) return <div className="loading"><div className="spinner"></div></div>
  if (!fiche) return <div className="empty-state">Fiche introuvable</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2>Fiche enseignant — {fiche.formateur_nom}</h2>
        <div>
          <button className="btn btn-outline-primary btn-sm" onClick={() => download('pdf')}>Export PDF</button>
          <button className="btn btn-outline-secondary btn-sm" style={{ marginLeft: '0.5rem' }} onClick={() => download('xlsx')}>Export Excel</button>
        </div>
      </div>

      <div className="card">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
          <div><strong>Module</strong><div>{fiche.module_intitule}</div></div>
          <div><strong>Heures prévues</strong><div>{fiche.heures_prevues}</div></div>
          <div><strong>Heures effectuées</strong><div>{fiche.heures_effectuees}</div></div>
          <div><strong>Taux présence</strong><div>{fiche.taux_presence ?? '—'}%</div></div>
          <div><strong>Satisfaction étudiants</strong><div>{fiche.satisfaction_auditeurs ?? '—'}</div></div>
        </div>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <h3>Appréciation pédagogique</h3>
        <div className="card" style={{ padding: '0.75rem' }}>{fiche.appreciation_pedagogique || '—'}</div>
      </div>
    </div>
  )
}
