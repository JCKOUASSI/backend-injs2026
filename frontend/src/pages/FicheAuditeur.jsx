import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'

export default function FicheAuditeur() {
  const { participantId, formationId } = useParams()
  const { showToast } = useToast()
  const [fiche, setFiche] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetch = async () => {
      setLoading(true)
      try {
        const { data } = await api.get(`/suiviEvaluation/auditeurs/${participantId}/formations/${formationId}/fiche/`)
        setFiche(data)
      } catch (err) {
        showToast(err?.response?.data?.detail || 'Erreur chargement fiche', 'error')
      } finally { setLoading(false) }
    }
    fetch()
    // showToast est stable (useCallback du ToastProvider).
  }, [participantId, formationId, showToast])

  const download = async (type) => {
    const path = type === 'pdf'
      ? `/suiviEvaluation/auditeurs/${participantId}/formations/${formationId}/fiche/export/pdf/`
      : `/suiviEvaluation/auditeurs/${participantId}/formations/${formationId}/fiche/export/xlsx/`
    try {
      const { blob, fileName } = await api.getBlob(path)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName || `fiche_auditeur_${participantId}_${formationId}.${type === 'pdf' ? 'pdf' : 'xlsx'}`
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
        <h2>Fiche étudiant — {fiche.participant_nom}</h2>
        <div>
          <button className="btn btn-outline-primary btn-sm" onClick={() => download('pdf')}>Export PDF</button>
          <button className="btn btn-outline-secondary btn-sm" style={{ marginLeft: '0.5rem' }} onClick={() => download('xlsx')}>Export Excel</button>
        </div>
      </div>

      <div className="card">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
          <div><strong>Formation</strong><div>{fiche.formation_libelle}</div></div>
          <div><strong>Moyenne générale</strong><div>{fiche.moyenne_generale ?? '—'}</div></div>
          <div><strong>Classement</strong><div>{fiche.classement ?? '—'}</div></div>
          <div><strong>Décision finale</strong><div>{fiche.decision_finale_detail?.decision_display || '—'}</div></div>
        </div>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <h3>Suivi par module</h3>
        {fiche.suivi_modules.length === 0 ? (
          <div className="empty-state">Aucun module</div>
        ) : (
          <div style={{ display: 'grid', gap: '0.5rem' }}>
            {fiche.suivi_modules.map(s => (
              <div key={s.id} className="card" style={{ padding: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <div style={{ fontWeight: 700 }}>{s.module_intitule}</div>
                  <div style={{ color: 'var(--text-muted)' }}>{s.nb_epreuves} épreuve(s)</div>
                </div>
                <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem' }}>
                  <div><small>Heures présence</small><div>{s.heures_presence}</div></div>
                  <div><small>Heures prévues</small><div>{s.heures_prevues}</div></div>
                  <div><small>Taux présence</small><div>{s.taux_presence ?? '—'}%</div></div>
                  <div><small>Moyenne</small><div>{s.moyenne_module ?? '—'}</div></div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
