import { useState, useEffect, useCallback } from 'react'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import ArchiveModuleBrowser from '../../components/archives/ArchiveModuleBrowser'
import '../../styles/archives.css'

const ACCENT = '#104A8E'

const MENTION_LABELS = {
  TRES_BIEN: 'Très bien', BIEN: 'Bien', ASSEZ_BIEN: 'Assez bien',
  PASSABLE: 'Passable', INSUFFISANT: 'Insuffisant', '': '—',
}
const MENTION_CLASSES = {
  TRES_BIEN: 'archives-mention--tres-bien',
  BIEN: 'archives-mention--bien',
  ASSEZ_BIEN: 'archives-mention--assez-bien',
  PASSABLE: 'archives-mention--passable',
  INSUFFISANT: 'archives-mention--insuffisant',
  '': 'archives-mention--vide',
}

function MentionBadge({ mention }) {
  const cle = MENTION_CLASSES[mention] ? mention : ''
  return (
    <span className={`archives-mention ${MENTION_CLASSES[cle]}`}>
      {MENTION_LABELS[cle] || '—'}
    </span>
  )
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function formatTaux(taux) {
  const n = Number(taux)
  return Number.isNaN(n) ? '—' : `${Math.round(n * 100) / 100}%`
}

/** Vue lecture seule d'une liste de notes (relevé archivé d'un module). */
function ListeNoteDocument({ module, onBack }) {
  const { showToast } = useToast()
  const formationId = module.id
  const moduleId = module.module_id
  const [colonnes, setColonnes] = useState([])
  const [rows, setRows] = useState([])
  const [criteres, setCriteres] = useState({ seuil_admission: 12, taux_presence_min: 80 })
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [printing, setPrinting] = useState(null)

  const fetchData = useCallback(async (signal) => {
    setLoading(true)
    try {
      const res = await api.get(`/formations/${formationId}/modules/${moduleId}/notes/`, signal ? { signal } : {})
      setColonnes(res.data.colonnes || [])
      setRows(res.data.rows || [])
      if (res.data.criteres) setCriteres(res.data.criteres)
    } catch (err) {
      if (err?.name !== 'AbortError' && err?.code !== 'ERR_CANCELED' && err?.name !== 'CanceledError') {
        showToast('Erreur lors du chargement des notes.', 'error')
      }
    } finally {
      setLoading(false)
    }
  }, [formationId, moduleId, showToast])

  useEffect(() => {
    const ac = new AbortController()
    fetchData(ac.signal)
    return () => ac.abort()
  }, [fetchData])

  const handlePrintFiche = async (participant = null) => {
    const key = participant ? `p-${participant.participant_id}` : 'module'
    const path = participant
      ? `/formations/${formationId}/modules/${moduleId}/notes/fiche/${participant.participant_id}/pdf/`
      : `/formations/${formationId}/modules/${moduleId}/notes/fiche/pdf/`
    const fallback = participant
      ? `fiche_notes_${participant.nom}_${participant.prenom}.pdf`.replace(/\s+/g, '_')
      : `fiche_notes_module_${moduleId}.pdf`

    setPrinting(key)
    try {
      const { blob, fileName } = await api.getBlob(path)
      downloadBlob(blob, fileName || fallback)
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur lors de la génération de la fiche', 'error')
    } finally {
      setPrinting(null)
    }
  }

  const filtered = rows.filter(n =>
    !search ||
    `${n.nom} ${n.prenom}`.toLowerCase().includes(search.toLowerCase()) ||
    (n.matricule || '').toLowerCase().includes(search.toLowerCase()) ||
    (n.grade || '').toLowerCase().includes(search.toLowerCase())
  )

  // Indicateurs calculés sur les données réelles du relevé
  const nbSaisies = rows.filter(n => Object.values(n.notes || {}).some(c => c?.note != null)).length
  const moyennes = rows
    .map(n => (n.moyenne != null && n.moyenne !== '' ? parseFloat(n.moyenne) : null))
    .filter(v => v != null && !Number.isNaN(v))
  const moyenneClasse = moyennes.length
    ? moyennes.reduce((a, b) => a + b, 0) / moyennes.length
    : null
  const evalues = rows.filter(n => n.moyenne != null && n.taux_presence != null)
  const nbAdmis = evalues.filter(n => n.admissible).length
  const moyenneParColonne = colonnes.map(c => {
    const valeurs = rows
      .map(n => n.notes?.[String(c.id)]?.note)
      .filter(v => v != null)
    return valeurs.length ? valeurs.reduce((a, b) => a + Number(b), 0) / valeurs.length : null
  })
  const tauxMoyen = rows.filter(n => n.taux_presence != null).length
    ? rows.reduce((a, n) => a + (n.taux_presence != null ? Number(n.taux_presence) : 0), 0)
      / rows.filter(n => n.taux_presence != null).length
    : null

  const tauxClasse = (taux) => {
    if (taux >= criteres.taux_presence_min) return 'archives-taux--bon'
    if (taux >= 50) return 'archives-taux--moyen'
    return 'archives-taux--faible'
  }

  return (
    <div className="archives-notes">
      <section className="archives-notes-hero">
        <button type="button" className="archives-cahier-retour" onClick={onBack}>
          <i className="bi bi-arrow-left"></i>Retour aux modules
        </button>
        <div className="archives-notes-hero-main">
          <span className="archives-cahier-icone"><i className="bi bi-card-checklist"></i></span>
          <div className="archives-notes-titres">
            <span className="archives-hero-badge"><i className="bi bi-archive"></i>Archives · Relevé de notes</span>
            <h2>Liste de notes</h2>
            <p>
              <strong>{module.module}</strong> · {module.formation}
              {module.grade && <> · {module.grade}</>}{module.groupe && <> · {module.groupe}</>}
              {module.secretariat_nom && <> · {module.secretariat_nom}</>}
            </p>
          </div>
          <button
            type="button"
            className="archives-export archives-notes-print"
            onClick={() => handlePrintFiche()}
            disabled={printing !== null || rows.length === 0}
            title="Imprimer la fiche de notes du module (tous les étudiants)"
          >
            {printing === 'module'
              ? <><span className="spinner-border spinner-border-sm"></span>Génération…</>
              : <><i className="bi bi-printer"></i>Imprimer la fiche</>}
          </button>
        </div>
        <div className="archives-notes-kpis">
          <div className="archives-cahier-kpi">
            <i className="bi bi-people"></i>
            <div><strong>{rows.length}</strong><span>étudiant{rows.length !== 1 ? 's' : ''}</span></div>
          </div>
          <div className="archives-cahier-kpi">
            <i className="bi bi-pencil-square"></i>
            <div><strong>{nbSaisies}</strong><span>noté{nbSaisies !== 1 ? 's' : ''} sur {rows.length}</span></div>
          </div>
          <div className="archives-cahier-kpi">
            <i className="bi bi-calculator"></i>
            <div><strong>{moyenneClasse != null ? `${moyenneClasse.toFixed(2)}/20` : '—'}</strong><span>moyenne de la classe</span></div>
          </div>
          <div className="archives-cahier-kpi">
            <i className="bi bi-patch-check"></i>
            <div><strong>{nbAdmis}</strong><span>admis sur {evalues.length} évalué{evalues.length !== 1 ? 's' : ''}</span></div>
          </div>
        </div>
        <p className="archives-notes-criteres">
          <i className="bi bi-info-circle"></i>
          Admis si moyenne ≥ <strong>{criteres.seuil_admission}/20</strong> et temps de cours effectué ≥ <strong>{criteres.taux_presence_min}%</strong>
        </p>
      </section>

      <div className="archives-cahier-toolbar">
        <label className="archives-cahier-recherche">
          <i className="bi bi-search"></i>
          <input
            className="form-control"
            placeholder="Rechercher par nom, matricule, grade…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            aria-label="Rechercher un étudiant"
          />
        </label>
        <span className="archives-cahier-compteur">
          {filtered.length} étudiant{filtered.length !== 1 ? 's' : ''} affiché{filtered.length !== 1 ? 's' : ''}
        </span>
      </div>

      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : rows.length === 0 ? (
        <div className="empty-state archives-cahier-vide">
          <i className="bi bi-people"></i>
          <p>Aucun étudiant inscrit à ce module.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state archives-cahier-vide">
          <i className="bi bi-search"></i>
          <p>Aucun étudiant ne correspond à « {search} ».</p>
        </div>
      ) : (
        <div className="archives-cahier-carte">
          <table className="archives-cahier-table archives-notes-table">
            <thead>
              <tr>
                <th className="col-rang">#</th>
                <th className="col-etudiant">Étudiant</th>
                <th className="col-grade">Grade</th>
                {colonnes.map(c => (
                  <th key={c.id} className="col-note">
                    <span className="seance-date">{c.libelle}</span>
                    <span className="seance-libelle">/ {c.note_max}</span>
                  </th>
                ))}
                <th className="col-total">Moy. /20</th>
                <th className="col-total">Mention</th>
                <th className="col-total">Temps de cours effectué</th>
                <th className="col-total">Admis</th>
                <th className="col-total">Fiche</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((n, idx) => {
                const moyNum = n.moyenne != null && n.moyenne !== '' ? parseFloat(n.moyenne) : null
                const taux = n.taux_presence
                return (
                  <tr key={n.participant_id} className="archives-cahier-ligne" style={{ animationDelay: `${Math.min(idx * 35, 350)}ms` }}>
                    <td className="col-rang">{idx + 1}</td>
                    <td className="col-etudiant">
                      <span className="etudiant-nom">{n.nom} {n.prenom}</span>
                      <span className="etudiant-matricule">{n.matricule || '—'}</span>
                    </td>
                    <td className="col-grade">
                      {n.grade && <span className="archives-notes-grade">{n.grade}</span>}
                    </td>
                    {colonnes.map(c => {
                      const cell = n.notes?.[String(c.id)]
                      return (
                        <td key={c.id} className="col-note">
                          {cell?.note != null
                            ? <span className="archives-notes-valeur">{cell.note}</span>
                            : <span className="archives-presence--non">—</span>}
                        </td>
                      )
                    })}
                    <td className="col-total">
                      {moyNum != null && !Number.isNaN(moyNum)
                        ? <span className={`archives-taux ${moyNum >= criteres.seuil_admission ? 'archives-taux--bon archives-moyenne--ok' : 'archives-taux--faible'}`}>{moyNum.toFixed(2)}</span>
                        : <span className="archives-presence--non">—</span>}
                    </td>
                    <td className="col-total"><MentionBadge mention={n.mention || ''} /></td>
                    <td className="col-total">
                      {taux != null
                        ? <span className={`archives-taux ${tauxClasse(Number(taux))}`}>{formatTaux(taux)}</span>
                        : <span className="archives-presence--non">—</span>}
                    </td>
                    <td className="col-total">
                      {moyNum != null && taux != null ? (
                        n.admissible
                          ? <span className="archives-admis archives-admis--oui"><i className="bi bi-check-circle-fill"></i>Oui</span>
                          : <span className="archives-admis archives-admis--non"><i className="bi bi-x-circle"></i>Non</span>
                      ) : <span className="archives-presence--non">—</span>}
                    </td>
                    <td className="col-total">
                      <button
                        type="button"
                        className="archives-notes-fiche"
                        onClick={() => handlePrintFiche(n)}
                        disabled={printing !== null}
                        title={`Imprimer la fiche de notes de ${n.nom} ${n.prenom}`}
                        aria-label={`Imprimer la fiche de notes de ${n.nom} ${n.prenom}`}
                      >
                        {printing === `p-${n.participant_id}`
                          ? <span className="spinner-border spinner-border-sm"></span>
                          : <i className="bi bi-printer"></i>}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot>
              <tr>
                <td className="col-rang"></td>
                <td className="col-etudiant">Moyenne de la classe</td>
                <td className="col-grade"></td>
                {moyenneParColonne.map((moy, i) => (
                  <td key={colonnes[i].id} className="col-note">
                    {moy != null ? moy.toFixed(2) : '—'}
                  </td>
                ))}
                <td className="col-total">{moyenneClasse != null ? moyenneClasse.toFixed(2) : '—'}</td>
                <td className="col-total">—</td>
                <td className="col-total">{tauxMoyen != null ? formatTaux(tauxMoyen) : '—'}</td>
                <td className="col-total">{nbAdmis}/{evalues.length} admis</td>
                <td className="col-total"></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}

export default function ArchiveListesNotes() {
  return (
    <ArchiveModuleBrowser
      title="Listes de notes"
      description="Consultez les relevés de notes archivés par module (catégorie, grade, groupe) — le classement de référence des archives de la scolarité."
      icon="bi-card-checklist"
      accent={ACCENT}
      documentVerb="Voir les notes"
      renderDocument={(module, onBack) => <ListeNoteDocument module={module} onBack={onBack} />}
    />
  )
}
