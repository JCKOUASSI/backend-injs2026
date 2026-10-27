import { useState, useRef } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'

/** Colonnes feuille « Séances » — grade/groupe/vague requis pour matcher le module. */
const SEANCES_IMPORT_COLUMNS = [
  'module_titre', 'grade', 'groupe', 'vague',
  'date_journee', 'numero', 'intitule', 'heure_debut', 'heure_fin',
]

/** Colonnes feuille « Formations » / import type cours (aligné import_excel + modèle Excel). */
const FORMATIONS_IMPORT_COLUMNS = [
  'N°', 'Formation', 'Module (titre)', 'Site', 'Bâtiment', 'Salle',
  'Date début', 'Date fin', 'Volume horaire (h)', 'Catégorie', 'Grade', 'Groupe', 'Vague',
]

/** Colonnes feuille « Auditeurs » / import type participants. */
const PARTICIPANTS_IMPORT_COLUMNS = [
  "N° d'inscription", 'Nom', 'Prénoms', 'Genre', 'Date de naissance', 'Lieu de naissance',
  'E-mail', 'Téléphone 1', 'Téléphone 2', 'Type concours', 'Libellé concours',
  'Catégorie', 'Grade', 'Groupe', 'Grade-Groupe', 'Vague', 'Formation(s)',
]

/** Colonnes feuille « Formateurs ». */
const FORMATEURS_IMPORT_COLUMNS = [
  'Numéro', 'Nom', 'Prénom', 'E-mail', 'Téléphone', 'Spécialité', 'Organisation',
]

/** Lignes d'exemple pour les modèles CSV (séparateur ; — compatible Excel FR). */
const CSV_EXAMPLE_ROWS = {
  formations: [
    [1, 'FORMATION EN ADMINISTRATION DE BASE', 'Déontologie de la Fonction Publique', 'INJS', '', 'SALLE A', '2026-05-05 08:00', '2026-05-09 17:00', 40, 'FAB A', 'A4', 'GROUPE 1', 'SESSION 2026'],
    [2, 'FORMATION EN ADMINISTRATION DE BASE', 'Protocole et Savoir-vivre', 'INJS', '', 'SALLE A', '2026-05-12 08:00', '2026-05-13 17:00', 16, 'FAB A', 'A4', 'GROUPE 1', 'SESSION 2026'],
  ],
  participants: [
    ['FNCP26-001', 'KOUAME', 'Jean-Marc', 'MASCULIN', '15/03/1990', 'Abidjan', 'jm.kouame@gouv.ci', '0701001001', '', 'Concours direct', 'Administrateur Civil', 'FAB A', 'A4', 'GROUPE 1', 'A4/GROUPE 1', 'SESSION 2026', 'FORMATION EN ADMINISTRATION DE BASE'],
    ['FNCP26-002', 'DIALLO', 'Mariam', 'FEMININ', '22/07/1992', 'Bouaké', 'diallo.m@gouv.ci', '0702002002', '', 'Concours direct', 'Administrateur Civil', 'FAB A', 'A4', 'GROUPE 1', 'A4/GROUPE 1', 'SESSION 2026', 'FORMATION EN ADMINISTRATION DE BASE'],
  ],
  formateurs: [
    ['F0001', 'CHRAIBI', 'Nadia', 'nadia.chraibi@expert.ci', '0700000001', 'Rédaction administrative', 'INJS'],
    ['F0002', 'BERRADA', 'Karim', 'karim.berrada@expert.ci', '0700000002', 'Droit administratif', 'ENA'],
  ],
  seances: [
    ['Déontologie de la Fonction Publique', 'A4', 'GROUPE 1', 'SESSION 2026', '05/05/2026', 1, 'Matin', '08:30', '12:00'],
    ['Déontologie de la Fonction Publique', 'A4', 'GROUPE 1', 'SESSION 2026', '05/05/2026', 2, 'Après-midi', '14:00', '17:00'],
  ],
}

function csvCell(value) {
  const s = value == null ? '' : String(value)
  return /[;"\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function downloadTemplate(filename, columns, examples = []) {
  const lines = [columns.map(csvCell).join(';')]
  for (const row of examples) {
    lines.push(row.map(csvCell).join(';'))
  }
  const blob = new Blob(['\uFEFF' + lines.join('\n') + '\n'], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

function ImportCard({ type, title, icon, color, columns, examples, onImport, loading }) {
  const fileRef = useRef()

  const handleClick = () => {
    const file = fileRef.current?.files[0]
    if (!file) { onImport(type, null); return }
    onImport(type, file, () => { if (fileRef.current) fileRef.current.value = '' })
  }

  return (
    <div className="card">
      <div className="import-card-header" style={{ background: color }}>
        <i className={`bi ${icon} me-2`}></i>{title}
      </div>
      <div className="card-body">
        <div className="form-group">
          <label className="form-label fw-semibold">Fichier Excel (.xlsx)</label>
          <input type="file" className="form-control" accept=".xlsx,.xls" ref={fileRef} />
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button onClick={handleClick} className="btn btn-dfrc btn-sm" disabled={loading}>
            <i className="bi bi-upload me-1"></i>{loading ? 'Import...' : 'Importer'}
          </button>
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => downloadTemplate(`modele_${type}.csv`, columns, examples)}>
            <i className="bi bi-download me-1"></i>Modèle CSV
          </button>
        </div>
        <div className="mt-3">
          <small className="text-muted fw-semibold">Colonnes attendues :</small>
          <div className="mt-2" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
            {columns.map((col) => (
              <span key={col} className="badge-bg-secondary" style={{ fontSize: '0.7rem' }}>{col}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function SeanceFileInput({ onImport, loading }) {
  const fileRef = useRef()
  const handleClick = () => {
    const file = fileRef.current?.files[0]
    if (!file) { onImport('seances', null); return }
    onImport('seances', file, () => { if (fileRef.current) fileRef.current.value = '' })
  }
  return (
    <div className="form-group">
      <label className="form-label fw-semibold">Fichier Excel (.xlsx)</label>
      <input type="file" className="form-control" accept=".xlsx,.xls" ref={fileRef} />
      <div style={{ marginTop: '0.5rem' }}>
        <button onClick={handleClick} className="btn btn-dfrc btn-sm" disabled={loading}
          style={{ background: '#5C6BC0', borderColor: '#5C6BC0' }}>
          <i className="bi bi-upload me-1"></i>{loading ? 'Import...' : 'Importer les séances'}
        </button>
      </div>
    </div>
  )
}

export default function ImportExcel() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const [loading, setLoading] = useState(false)

  if (!['CHEF_SECRETARIAT', 'SECRETARIAT', 'ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'].includes(user?.role)) {
    return (
      <div className="card">
        <div className="card-body text-center text-muted py-5">
          <i className="bi bi-lock" style={{ fontSize: '2rem' }}></i>
          <p className="mt-2 fw-semibold">Accès réservé au Secrétariat / INJS Admin</p>
        </div>
      </div>
    )
  }

  const handleImport = async (type, file, resetFile) => {
    if (!file) { showToast('Veuillez sélectionner un fichier', 'error'); return }

    setLoading(true)
    const formData = new FormData()
    formData.append('file', file)
    formData.append('type', type)

    try {
      const response = await api.post('/formations/import-excel/', formData)
      const data = response.data
      const typeLabels = { formations: 'Modules', participants: 'Étudiants', formateurs: 'Enseignants', seances: 'Séances' }
      const label = typeLabels[type] || type

      if (data.errors?.length > 0) {
        const detail = data.errors.slice(0, 2).join(' · ')
        const suffix = data.errors.length > 2 ? '…' : ''
        const counts = [`${data.created || 0} créé(s)`]
        if (data.updated > 0) counts.push(`${data.updated} mis à jour`)
        showToast(
          `${label} — ${data.errors.length} erreur(s), ${counts.join(', ')}. ${detail}${suffix}`,
          'error',
        )
      } else {
        const parts = []
        if (data.created > 0) parts.push(`${data.created} créé(s)`)
        if (data.updated > 0) parts.push(`${data.updated} mis à jour`)
        const msg = parts.length > 0 ? parts.join(', ') : 'Aucun élément traité'
        const accountsHint = data.accounts_deferred && (type === 'participants' || type === 'formateurs')
          ? ' — Comptes badge : lancer create_auditeur_accounts sur le serveur.'
          : ''
        showToast(`${label} — Import réussi ! ${msg}${accountsHint}`, 'success')
      }
      if (resetFile) resetFile()
    } catch (err) {
      showToast(err.response?.data?.error || err.response?.data?.detail || "Erreur lors de l'import", 'error')
    } finally { setLoading(false) }
  }

  return (
    <div>
      <div className="card">
        <div className="card-body">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div className="stat-icon bg-warning"><i className="bi bi-info-circle-fill"></i></div>
            <div>
              <strong>Comment importer des données ?</strong>
              <p className="text-muted mb-0" style={{ fontSize: '0.85rem' }}>
                Préparez un fichier Excel (.xlsx) avec les colonnes attendues pour chaque type, puis cliquez sur « Importer ».
                Ordre recommandé : <strong>Modules</strong> → <strong>Enseignants</strong> → <strong>Étudiants</strong> → <strong>Séances</strong>.
                Les séances doivent reprendre exactement le même <em>module_titre</em>, <em>grade</em>, <em>groupe</em> et <em>vague</em> que les modules déjà importés.
                Plusieurs modules peuvent appartenir à la même formation (même valeur dans la colonne <em>Formation</em>).
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid-2">
        <ImportCard type="formations" title="Modules" icon="bi-mortarboard" color="var(--ci-success-dark)"
          columns={FORMATIONS_IMPORT_COLUMNS}
          examples={CSV_EXAMPLE_ROWS.formations}
          onImport={handleImport} loading={loading} />
        <ImportCard type="participants" title="Étudiants" icon="bi-people" color="var(--ci-blue)"
          columns={PARTICIPANTS_IMPORT_COLUMNS}
          examples={CSV_EXAMPLE_ROWS.participants}
          onImport={handleImport} loading={loading} />
        <ImportCard type="formateurs" title="Enseignants" icon="bi-person-video3" color="var(--ci-warning)"
          columns={FORMATEURS_IMPORT_COLUMNS}
          examples={CSV_EXAMPLE_ROWS.formateurs}
          onImport={handleImport} loading={loading} />

        {/* Séances */}
        <div className="card">
          <div className="import-card-header" style={{ background: '#5C6BC0' }}>
            <i className="bi bi-calendar3 me-2"></i>Séances
          </div>
          <div className="card-body">
            <SeanceFileInput onImport={handleImport} loading={loading} />
            <button type="button" className="btn btn-outline-secondary btn-sm mt-1"
              onClick={() => downloadTemplate('modele_seances.csv', SEANCES_IMPORT_COLUMNS, CSV_EXAMPLE_ROWS.seances)}>
              <i className="bi bi-download me-1"></i>Modèle CSV
            </button>
            <div className="mt-3">
              <small className="text-muted fw-semibold">Colonnes attendues (feuille « Séances ») :</small>
              <div className="mt-1" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                {SEANCES_IMPORT_COLUMNS.map(col => (
                  <span key={col} className="badge-bg-secondary" style={{ fontSize: '0.7rem' }}>{col}</span>
                ))}
              </div>
              <div className="mt-2" style={{ background: '#f0f4ff', borderRadius: 6, padding: '0.4rem 0.6rem' }}>
                <small>
                  <i className="bi bi-info-circle me-1"></i>
                  <em>module_titre</em>, <em>grade</em>, <em>groupe</em> et <em>vague</em> sont obligatoires pour rattacher chaque séance au bon module.
                  Date : JJ/MM/AAAA · heure : HH:MM · numéro : 1, 2, 3…
                </small>
              </div>
              <div className="mt-2" style={{ background: '#f8f9fa', borderRadius: 6, padding: '0.4rem 0.6rem' }}>
                <small className="text-muted">
                  Depuis la fiche d'une formation, l'import de séances peut se limiter à
                  <em> date_journee</em>, <em>numero</em>, <em>intitule</em>, <em>heure_debut</em>, <em>heure_fin</em>
                  (le module est déjà connu).
                </small>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
