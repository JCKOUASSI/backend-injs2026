import { useEffect, useState } from 'react'
import api from '../../services/api'
import { fmtDuration } from '../FinanceStatsGrid'

const NON_DISPONIBLE = 'Non disponible'
const ONGLETS = [
  { id: 'profil', label: 'Profil', icon: 'bi-person-badge' },
  { id: 'enseignements', label: 'Enseignements LMD', icon: 'bi-journal-bookmark' },
  { id: 'charge', label: 'Charge annuelle', icon: 'bi-clock-history' },
  { id: 'evaluation', label: 'Évaluation', icon: 'bi-clipboard-check' },
]
const nombre = (v) => v == null ? NON_DISPONIBLE : new Intl.NumberFormat('fr-FR').format(v)
const texte = (v) => v || NON_DISPONIBLE

function Champ({ label, value }) {
  return <div className="ens-fiche-champ"><dt>{label}</dt><dd>{texte(value)}</dd></div>
}

/** Fiche pédagogique : aucune donnée de paie legacy ni agrégation académique côté React. */
export default function FormateurFicheModal({ formateur, onClose, onExport, exporting }) {
  const [fiche, setFiche] = useState(null)
  const [erreur, setErreur] = useState('')
  const [onglet, setOnglet] = useState('profil')

  useEffect(() => {
    let actif = true
    setFiche(null)
    setErreur('')
    setOnglet('profil')
    api.get(`/formations/formateurs/${formateur.id}/fiche/`)
      .then(res => { if (actif) setFiche(res.data) })
      .catch(() => { if (actif) setErreur('Impossible de charger la fiche pédagogique. Aucune donnée financière de substitution n’est affichée.') })
    return () => { actif = false }
  }, [formateur.id])

  useEffect(() => {
    const fermer = e => { if (e.key === 'Escape' && !exporting) onClose() }
    document.addEventListener('keydown', fermer)
    return () => document.removeEventListener('keydown', fermer)
  }, [onClose, exporting])

  const charge = fiche?.charge
  return (
    <div className="px-modal-overlay" onClick={() => !exporting && onClose()}>
      <section className="px-modal ens-fiche-modal" role="dialog" aria-modal="true" aria-labelledby="ens-fiche-titre" onClick={e => e.stopPropagation()}>
        <header className="ens-fiche-hero">
          <span className="ens-avatar" aria-hidden="true">{formateur.nom?.[0]}{formateur.prenom?.[0]}</span>
          <div>
            <span className="px-hero-eyebrow">Corps enseignant · {fiche?.annee_academique || 'Année courante'}</span>
            <h2 id="ens-fiche-titre">{formateur.nom} {formateur.prenom}</h2>
            <p>{texte(fiche?.grade_label)} · {texte(fiche?.specialite)}</p>
            {fiche?.est_exemple && <span className="badge-bg-warning" aria-label="Données d’exemple">[Exemple]</span>}
          </div>
          <button type="button" className="px-modal-close" onClick={onClose} aria-label="Fermer la fiche"><i className="bi bi-x-lg" /></button>
        </header>

        {erreur ? <div className="error-message m-3" role="alert">{erreur}</div> : !fiche ? (
          <div className="loading py-5" role="status"><div className="spinner" /><span>Chargement de la fiche…</span></div>
        ) : <>
          <div className="ens-fiche-kpis" aria-label="Chiffres clés de l’enseignant">
            <div><span>Formations LMD</span><strong>{nombre(fiche.nb_formations)}</strong></div>
            <div><span>ECUE distinctes</span><strong>{nombre(fiche.nb_ecue)}</strong></div>
            <div><span>Heures affectées</span><strong>{nombre(fiche.heures_affectees)} h</strong></div>
            <div><span>Heures effectuées</span><strong className="ens-fiche-indisponible">{NON_DISPONIBLE}</strong></div>
          </div>
          <div className="px-tabs" role="tablist" aria-label="Rubriques de la fiche enseignant">
            {ONGLETS.map(t => <button key={t.id} type="button" role="tab" aria-selected={onglet === t.id} className={`px-tab ${onglet === t.id ? 'active' : ''}`} onClick={() => setOnglet(t.id)}><i className={`bi ${t.icon}`} />{t.label}</button>)}
          </div>
          <div className="ens-fiche-body" role="tabpanel">
            {onglet === 'profil' && <>
              <dl className="ens-fiche-grille">
                <Champ label="Identifiant" value={fiche.numerobadge} />
                <Champ label="Grade académique" value={fiche.grade_label} />
                <Champ label="Fonction" value={fiche.fonction} />
                <Champ label="Statut" value={fiche.statut_enseignant} />
                <Champ label="Spécialité" value={fiche.specialite} />
                <Champ label="Organisation" value={fiche.organisation} />
                <Champ label="Courriel" value={fiche.email} />
                <Champ label="Téléphone" value={fiche.telephone} />
              </dl>
              <h3>Observations</h3><p className="ens-fiche-observations">{texte(fiche.observations)}</p>
            </>}
            {onglet === 'enseignements' && (fiche.affectations.length ? (
              <div className="table-container"><table className="table px-table">
                <thead><tr><th>ECUE / UE</th><th>Formation</th><th>Groupe</th><th>Volume</th><th>Statut</th></tr></thead>
                <tbody>{fiche.affectations.map(a => <tr key={a.id}>
                  <td><strong>{a.ecue_code} · {a.ecue_intitule}</strong><small>{a.ue} {a.est_exemple && <span className="badge-bg-warning">[Exemple]</span>}</small></td>
                  <td>{a.formation}<small>{a.filiere} · {a.niveau} · {a.semestre}</small></td>
                  <td>{texte(a.groupe)}</td><td>{nombre(a.heures)} h · {a.type_enseignement}</td><td>{a.statut_label}</td>
                </tr>)}</tbody>
              </table></div>
            ) : <div className="finance-empty">Aucune affectation pédagogique pour l’année courante.</div>)}
            {onglet === 'charge' && (charge ? <>
              <p className="px-panel-sub">Volumes des affectations de {fiche.annee_academique}, hors affectations annulées. Un statut « réalisée » n’est pas une mesure d’heures effectuées.</p>
              <dl className="ens-fiche-grille">
                <Champ label="Charge prévue (maquette)"
                       value={charge.prevue_disponible === false ? NON_DISPONIBLE : `${nombre(charge.prevue)} h`} />
                <Champ label="Charge affectée" value={`${nombre(charge.affectee)} h`} />
                <Champ label="Volume validé" value={`${nombre(charge.validee)} h`} />
                <Champ label="Volume planifié" value={`${nombre(charge.planifiee)} h`} />
                <Champ label="Volume au statut réalisé" value={`${nombre(charge.realisee)} h`} />
                <Champ label="Seuil d’alerte" value={`${nombre(charge.seuil)} h`} />
                <Champ label="Alerte de surcharge" value={charge.surcharge ? 'Oui' : 'Non'} />
              </dl>
            </> : <div className="finance-empty">Charge annuelle : {NON_DISPONIBLE}.</div>)}
            {onglet === 'evaluation' && <>
              <dl className="ens-fiche-grille">
                <Champ label="Heures effectuées" value={fiche.heures_effectuees == null ? NON_DISPONIBLE : fmtDuration(fiche.heures_effectuees * 60)} />
                <Champ label="Présence de l’enseignant" value={fiche.taux_presence == null ? NON_DISPONIBLE : `${fiche.taux_presence} %`} />
                <Champ label="Satisfaction étudiants" value={fiche.satisfaction_etudiants == null ? NON_DISPONIBLE : fiche.satisfaction_etudiants} />
              </dl>
              <p className="ens-fiche-observations">{fiche.disponibilite_indicateurs}</p>
            </>}
          </div>
        </>}
        <footer className="px-modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Fermer</button>
          <button type="button" className="btn btn-outline-success" disabled={!fiche || !!exporting} onClick={() => onExport(fiche, 'xlsx')}><i className="bi bi-file-earmark-spreadsheet me-1" />Export Excel</button>
          <button type="button" className="btn btn-dfrc" disabled={!fiche || !!exporting} onClick={() => onExport(fiche, 'pdf')}><i className="bi bi-file-earmark-pdf me-1" />{exporting ? 'Export…' : 'Export PDF'}</button>
        </footer>
      </section>
    </div>
  )
}
