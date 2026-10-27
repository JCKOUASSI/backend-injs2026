import React, { useEffect, useState } from 'react'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'

/** Lot L1/L3 — espace étudiant minimal : fiche, notes, attestations (L4). */
export default function MonEspace() {
  const toast = useToast()
  const [fiche, setFiche] = useState(null)
  const [chargement, setChargement] = useState(true)

  useEffect(() => {
    api.get('/scan/me/fiche/')
      .then((res) => setFiche(res.data))
      .catch(() => toast.showToast('Fiche personnelle indisponible.', 'error'))
      .finally(() => setChargement(false))
  }, [toast])

  const telechargerNotes = async () => {
    try {
      const participantId = fiche?.profil?.id
      if (!participantId) {
        toast.showToast('Aucun dossier étudiant rattaché à ce compte.', 'error')
        return
      }
      const { blob } = await api.getBlob(
        `/presences/participant/${participantId}/notes-fiche/export/pdf/`,
      )
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `releve-notes-${fiche.profil.numero || participantId}.pdf`
      a.click()
      window.URL.revokeObjectURL(url)
    } catch {
      toast.showToast('Téléchargement du relevé de notes impossible.', 'error')
    }
  }

  if (chargement) {
    return <div className="container-fluid py-4"><div className="spinner-border" /></div>
  }

  const profil = fiche?.profil || {}

  return (
    <div className="container-fluid py-4">
      <h1 className="h4 mb-3"><i className="bi bi-person-circle me-2"></i>Mon espace étudiant</h1>

      <div className="card mb-3">
        <div className="card-body">
          <h2 className="h6 card-title">Ma fiche</h2>
          <p className="mb-1">
            <strong>{profil.prenom} {profil.nom}</strong>
            {profil.numero && <> — matricule {profil.numero}</>}
          </p>
          <p className="mb-0 text-muted">
            {fiche?.stats?.nb_modules_inscrits ?? 0} module(s) inscrit(s) ·{' '}
            {fiche?.stats?.taux_presence ?? '—'}% de présence
          </p>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-body">
          <h2 className="h6 card-title"><i className="bi bi-journal-text me-1"></i>Mes notes</h2>
          <p className="text-muted small">
            Relevé de notes officiel avec décision finale, au format PDF.
          </p>
          <button className="btn btn-primary btn-sm" onClick={telechargerNotes}>
            <i className="bi bi-download me-1"></i>Télécharger mon relevé de notes
          </button>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-body">
          <h2 className="h6 card-title"><i className="bi bi-file-earmark-text me-1"></i>Mes attestations</h2>
          <p className="mb-0 text-muted small">
            Les attestations de scolarité et de réussite seront disponibles ici
            (lot L4 — documents officiels).
          </p>
        </div>
      </div>
    </div>
  )
}
