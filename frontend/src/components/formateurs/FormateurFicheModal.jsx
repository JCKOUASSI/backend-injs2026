import { useEffect, useRef, useState } from 'react'
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
const initiales = (nom, prenom) => `${(nom || '?').trim().charAt(0)}${(prenom || '').trim().charAt(0)}`.toUpperCase()

// Anneau de charge : le pourcentage vient du serveur (taux_charge), le seuil
// aussi. Aucun ratio académique n'est recalculé ici.
const RAYON = 26
const CIRCONFERENCE = 2 * Math.PI * RAYON
function AnneauCharge({ taux, surcharge, seuil, affectee }) {
  if (taux == null) return null
  const borne = Math.min(1, Math.max(0, taux / 100))
  const etat = surcharge || taux > 100 ? 'is-danger' : taux >= 85 ? 'is-warn' : 'is-ok'
  return (
    <div className={`ens-anneau-bloc ${etat}`}>
      <svg viewBox="0 0 62 62" className="ens-anneau" role="img"
           aria-label={`Charge à ${taux} % du seuil d'alerte`}>
        <circle className="ens-anneau-piste" cx="31" cy="31" r={RAYON} fill="none" strokeWidth="8" />
        <circle className="ens-anneau-valeur" cx="31" cy="31" r={RAYON} fill="none" strokeWidth="8"
                strokeLinecap="round" strokeDasharray={CIRCONFERENCE}
                strokeDashoffset={CIRCONFERENCE * (1 - borne)}
                transform="rotate(-90 31 31)" />
        <text x="31" y="36" textAnchor="middle" className="ens-anneau-texte">{taux} %</text>
      </svg>
      <div className="ens-anneau-texte-bloc">
        <strong>{surcharge ? 'Charge au-delà du seuil' : 'Charge dans la limite du seuil'}</strong>
        <span>
          {nombre(affectee)} h affectées pour un seuil d’alerte de {nombre(seuil)} h
          {surcharge && seuil != null && affectee != null ? ` — ${nombre(Math.round(affectee - seuil))} h de dépassement.` : '.'}
        </span>
      </div>
    </div>
  )
}

function Champ({ label, value, indisponible }) {
  return (
    <div className="ens-fiche-champ">
      <dt>{label}</dt>
      <dd className={indisponible ? 'ens-fiche-indisponible' : undefined}>{texte(value)}</dd>
    </div>
  )
}

/** Fiche pédagogique : aucune donnée de paie legacy ni agrégation académique côté React. */
export default function FormateurFicheModal({ formateur, onClose, onExport, exporting }) {
  const [fiche, setFiche] = useState(null)
  const [erreur, setErreur] = useState('')
  const [onglet, setOnglet] = useState('profil')
  const refModal = useRef(null)

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

  // Accessibilité : focus placé dans la fenêtre à l'ouverture, cycle de
  // tabulation borné au dialogue, et focus rendu à l'élément d'origine.
  useEffect(() => {
    const precedent = document.activeElement
    const focusables = () => Array.from(
      refModal.current?.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) || [],
    ).filter((el) => el.offsetParent !== null)
    focusables()[0]?.focus()
    const surTab = (e) => {
      if (e.key !== 'Tab') return
      const liste = focusables()
      if (!liste.length) return
      const premier = liste[0]
      const dernier = liste[liste.length - 1]
      if (e.shiftKey && document.activeElement === premier) { e.preventDefault(); dernier.focus() }
      else if (!e.shiftKey && document.activeElement === dernier) { e.preventDefault(); premier.focus() }
    }
    document.addEventListener('keydown', surTab)
    return () => {
      document.removeEventListener('keydown', surTab)
      if (precedent && typeof precedent.focus === 'function') precedent.focus()
    }
  }, [])

  useEffect(() => {
    const fermer = e => { if (e.key === 'Escape' && !exporting) onClose() }
    document.addEventListener('keydown', fermer)
    return () => document.removeEventListener('keydown', fermer)
  }, [onClose, exporting])

  const charge = fiche?.charge
  const nbAffectations = fiche?.affectations?.length ?? 0
  const libelleOnglet = (t) => (t.id === 'enseignements' && fiche ? `${t.label} (${nbAffectations})` : t.label)
  const totalRepartition = (fiche?.repartition || []).reduce((s, r) => s + (r.heures || 0), 0)

  return (
    <div className="px-modal-overlay" onClick={() => !exporting && onClose()}>
      <section className="px-modal ens-fiche-modal" role="dialog" aria-modal="true"
               aria-labelledby="ens-fiche-titre" aria-busy={!fiche && !erreur ? 'true' : 'false'}
               ref={refModal} onClick={e => e.stopPropagation()}>

        <div className="ens-fiche-grid">
          {/* Rail d'identité : l'enseignant reste identifiable quel que soit l'onglet. */}
          <aside className="ens-fiche-rail">
            <button type="button" className="px-modal-close" onClick={onClose} aria-label="Fermer la fiche"><i className="bi bi-x-lg" /></button>
            <span className="px-hero-eyebrow">Corps enseignant · {fiche?.annee_academique || 'Année courante'}</span>
            <span className="ens-avatar" aria-hidden="true">{initiales(formateur.nom, formateur.prenom)}</span>
            <h2 id="ens-fiche-titre">{formateur.nom} {formateur.prenom}</h2>
            <p className="ens-fiche-role">
              {texte(fiche?.grade_label ?? formateur.grade?.libelle)}
              {fiche?.specialite || formateur.specialite ? ` · ${fiche?.specialite || formateur.specialite}` : ''}
            </p>
            <div className="ens-fiche-hero-tags">
              {fiche?.numerobadge && <span className="ens-tag"><i className="bi bi-upc-scan" aria-hidden="true"></i>{fiche.numerobadge}</span>}
              {(fiche?.statut_enseignant || formateur.statut_enseignant) && <span className="ens-tag">{fiche?.statut_enseignant || formateur.statut_enseignant}</span>}
              {(fiche?.fonction || formateur.fonction) && <span className="ens-tag">{fiche?.fonction || formateur.fonction}</span>}
              {(fiche?.est_exemple ?? formateur.est_exemple) && <span className="badge-bg-warning" aria-label="Données d’exemple">[Exemple]</span>}
            </div>
            <ul className="ens-fiche-coordonnees">
              <li><i className="bi bi-envelope" aria-hidden="true"></i>{texte(fiche?.email ?? formateur.email)}</li>
              <li><i className="bi bi-telephone" aria-hidden="true"></i>{texte(fiche?.telephone ?? formateur.telephone)}</li>
              <li><i className="bi bi-buildings" aria-hidden="true"></i>{texte(fiche?.organisation ?? formateur.organisation)}</li>
            </ul>
            <p className="ens-fiche-source">
              Source : affectations pédagogiques {fiche?.annee_academique || 'de l’année en cours'}, hors affectations annulées.
              Aucune donnée de paie n’est affichée dans cette fiche.
            </p>
          </aside>

          <div className="ens-fiche-main">
            {erreur ? <div className="error-message m-3" role="alert">{erreur}</div> : !fiche ? (
              <div className="loading py-5" role="status"><div className="spinner" /><span>Chargement de la fiche…</span></div>
            ) : <>

              <div className="ens-fiche-kpis" aria-label="Chiffres clés de l’enseignant">
                <div><span>Formations LMD</span><strong>{nombre(fiche.nb_formations)}</strong></div>
                <div><span>ECUE distinctes</span><strong>{nombre(fiche.nb_ecue)}</strong></div>
                <div><span>Heures affectées</span><strong>{nombre(fiche.heures_affectees)} h</strong></div>
                <div><span>Heures effectuées</span><strong className="ens-fiche-indisponible">{NON_DISPONIBLE}</strong></div>
              </div>

              <AnneauCharge taux={fiche.taux_charge} surcharge={charge?.surcharge}
                            seuil={charge?.seuil} affectee={charge?.affectee} />

              <div className="px-tabs" role="tablist" aria-label="Rubriques de la fiche enseignant">
                {ONGLETS.map(t => (
                  <button key={t.id} type="button" role="tab" aria-selected={onglet === t.id}
                          className={`px-tab ${onglet === t.id ? 'active' : ''}`} onClick={() => setOnglet(t.id)}>
                    <i className={`bi ${t.icon}`} />{libelleOnglet(t)}
                  </button>
                ))}
              </div>

              <div className="ens-fiche-body" role="tabpanel">
                {onglet === 'profil' && <>
                  {/* Courriel, téléphone et organisation vivent dans le rail :
                      les répéter ici doublerait l'information à l'écran. */}
                  <dl className="ens-fiche-grille">
                    <Champ label="Identifiant" value={fiche.numerobadge} />
                    <Champ label="Grade académique" value={fiche.grade_label} />
                    <Champ label="Fonction" value={fiche.fonction} />
                    <Champ label="Statut" value={fiche.statut_enseignant} />
                    <Champ label="Spécialité" value={fiche.specialite} />
                    <Champ label="Année académique" value={fiche.annee_academique} />
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
                    <Champ label="Charge prévue (maquette)" indisponible={charge.prevue_disponible === false}
                           value={charge.prevue_disponible === false ? NON_DISPONIBLE : `${nombre(charge.prevue)} h`} />
                    <Champ label="Charge affectée" value={`${nombre(charge.affectee)} h`} />
                    <Champ label="Volume validé" value={`${nombre(charge.validee)} h`} />
                    <Champ label="Volume planifié" value={`${nombre(charge.planifiee)} h`} />
                    <Champ label="Volume au statut réalisé" value={`${nombre(charge.realisee)} h`} />
                    <Champ label="Seuil d’alerte" value={`${nombre(charge.seuil)} h`} />
                  </dl>
                  <h3>Répartition par nature d’enseignement</h3>
                  {fiche.repartition?.length ? (
                    <div className="ens-fiche-barres">
                      {fiche.repartition.map(r => (
                        <div className="ens-fiche-barre" key={r.libelle}>
                          <span className="ens-fiche-barre-libelle">{r.libelle}</span>
                          <span className="ens-fiche-barre-piste">
                            <i style={{ width: `${totalRepartition ? Math.max(2, (r.heures / totalRepartition) * 100) : 0}%` }} />
                          </span>
                          <b>{nombre(r.heures)} h</b>
                        </div>
                      ))}
                    </div>
                  ) : <p className="ens-fiche-observations">Répartition : {NON_DISPONIBLE}.</p>}
                  <p className={`ens-fiche-alerte ${charge.surcharge ? 'is-danger' : 'is-ok'}`}>
                    <i className={`bi ${charge.surcharge ? 'bi-exclamation-triangle-fill' : 'bi-check-circle-fill'}`} aria-hidden="true"></i>
                    {charge.surcharge
                      ? `Surcharge : ${nombre(charge.affectee)} h affectées pour un seuil de ${nombre(charge.seuil)} h.`
                      : `Charge dans la limite du seuil (${nombre(charge.seuil)} h).`}
                  </p>
                </> : <div className="finance-empty">Charge annuelle : {NON_DISPONIBLE}.</div>)}

                {onglet === 'evaluation' && <>
                  <dl className="ens-fiche-grille">
                    <Champ label="Heures effectuées" indisponible={fiche.heures_effectuees == null}
                           value={fiche.heures_effectuees == null ? NON_DISPONIBLE : fmtDuration(fiche.heures_effectuees * 60)} />
                    <Champ label="Présence de l’enseignant" indisponible={fiche.taux_presence == null}
                           value={fiche.taux_presence == null ? NON_DISPONIBLE : `${fiche.taux_presence} %`} />
                    <Champ label="Satisfaction étudiants" indisponible={fiche.satisfaction_etudiants == null}
                           value={fiche.satisfaction_etudiants == null ? NON_DISPONIBLE : fiche.satisfaction_etudiants} />
                  </dl>
                  <p className="ens-fiche-observations">{fiche.disponibilite_indicateurs}</p>
                </>}
              </div>
            </>}
          </div>
        </div>

        <footer className="px-modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>Fermer</button>
          <button type="button" className="btn btn-outline-success" disabled={!fiche || !!exporting} onClick={() => onExport(fiche, 'xlsx')}><i className="bi bi-file-earmark-spreadsheet me-1" />Export Excel</button>
          <button type="button" className="btn btn-dfrc" disabled={!fiche || !!exporting} onClick={() => onExport(fiche, 'pdf')}><i className="bi bi-file-earmark-pdf me-1" />{exporting ? 'Export…' : 'Export PDF'}</button>
        </footer>
      </section>
    </div>
  )
}
