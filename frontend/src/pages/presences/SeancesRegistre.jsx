import React, { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api from '../../services/api'
import { formatHeure, identifiantPermanent, messageErreur } from './commun'

export { identifiantPermanent } from './commun'
import '../../styles/presences.css'

/**
 * Module « Séances » du hub Présences QR — registre des séances.
 *
 * Refonte alignée sur le registre de référence : filtres **côté serveur**
 * (date + statut, synchronisés dans l'URL), identifiant permanent
 * `INJS-S-######`, chaîne ECUE → UE, parcours/niveau, enseignant et
 * encadrants habilités, attendus/présents/manuels/anomalies, statut.
 * Source unique : `GET /api/presences/seances-edt/supervision/`
 * (statuts réels du dépôt : EN_COURS, A_VENIR, TERMINEE, ANNULEE).
 * Le détail d'une séance (QR, émargement, présences) s'ouvre dans
 * l'écran « Présences » du hub.
 */

const FILTRES = [
  { valeur: '', libelle: 'Toutes' },
  { valeur: 'EN_COURS', libelle: 'En cours' },
  { valeur: 'A_VENIR', libelle: 'À venir' },
  { valeur: 'TERMINEE', libelle: 'Terminées' },
  { valeur: 'ANNULEE', libelle: 'Annulées' },
]

const TON_STATUT = {
  EN_COURS: 'text-bg-success', TERMINEE: 'text-bg-secondary', CLOTUREE: 'text-bg-secondary',
  A_VENIR: 'text-bg-info', PLANIFIEE: 'text-bg-info', ANNULEE: 'text-bg-danger',
  PUBLIEE: 'text-bg-primary',
}

function libelleDateLongue(iso) {
  if (!iso) return 'Date inconnue'
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  const texte = d.toLocaleDateString('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  })
  return texte.charAt(0).toUpperCase() + texte.slice(1)
}

function anomaliesSeance(s) {
  const horsPerimetre = s.presences?.presences_hors_perimetre || 0
  const sansGroupe = s.effectif_attendu === null || s.effectif_attendu === undefined ? 1 : 0
  return horsPerimetre + sansGroupe
}

export default function SeancesRegistre() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [date, setDate] = useState(() => searchParams.get('date') || new Date().toLocaleDateString('en-CA'))
  const [statut, setStatut] = useState(() => searchParams.get('statut') || '')
  // Chargement explicite de 200 séances appliqué dès l'ouverture ;
  // un jour précis demandé dans l'URL (?date= ou ?mode=jour) conserve
  // le mode « Par jour » historique.
  const [mode, setMode] = useState(() => {
    if (searchParams.get('mode') === 'jour') return 'jour'
    if (searchParams.get('mode') === '200') return 'plage'
    return searchParams.get('date') ? 'jour' : 'plage'
  })
  const [donnees, setDonnees] = useState(null)
  const [auto, setAuto] = useState(false)
  const [charge, setCharge] = useState(true)
  const [erreur, setErreur] = useState('')

  const charger = useCallback(async () => {
    setCharge(true)
    setErreur('')
    setPage(1)
    try {
      const params = new URLSearchParams({ date })
      if (mode === 'plage') {
        // Chargement explicite : 200 séances les plus proches de la
        // date repère (jours candidats explorés par proximité, ±120 j).
        params.set('limite', '200')
        params.set('horizon', '120')
      }
      if (statut) params.set('statut', statut)
      const res = await api.get(`/presences/seances-edt/supervision/?${params.toString()}`)
      setDonnees(res.data)
    } catch (err) {
      setErreur(messageErreur(err, 'Registre des séances indisponible.'))
    } finally {
      setCharge(false)
    }
  }, [date, statut, mode])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    if (!auto) return undefined
    const t = window.setInterval(charger, 30000)
    return () => window.clearInterval(t)
  }, [auto, charger])

  useEffect(() => {
    const sp = new URLSearchParams()
    sp.set('date', date)
    if (statut) sp.set('statut', statut)
    sp.set('mode', mode === 'plage' ? '200' : 'jour')
    setSearchParams(sp, { replace: true })
  }, [date, statut, mode, setSearchParams])

  const [recherche, setRecherche] = useState('')
  const [page, setPage] = useState(1)

  const lignes = donnees?.seances || []
  const resume = donnees?.resume || {}

  // Présentation : recherche instantanée sur la sélection chargée,
  // regroupement par date et pagination par 15 (la sélection complète
  // reste celle du serveur : aucun filtrage métier côté navigateur).
  const PAR_PAGE = 15
  const texte = recherche.trim().toLowerCase()
  const lignesFiltrees = texte
    ? lignes.filter((x) => [x.ecue_code, x.ecue_libelle, x.ue_code, x.intitule,
        x.libelle, x.groupe_libelle, x.salle_libelle, x.formation_libelle]
        .filter(Boolean).join(' ').toLowerCase().includes(texte))
    : lignes
  const totalParDate = lignesFiltrees.reduce((acc, x) => {
    const d = x.date || date
    acc[d] = (acc[d] || 0) + 1
    return acc
  }, {})
  const pagesTotal = Math.max(1, Math.ceil(lignesFiltrees.length / PAR_PAGE))
  const pageSure = Math.min(page, pagesTotal)
  const debutPage = (pageSure - 1) * PAR_PAGE
  const visibles = lignesFiltrees.slice(debutPage, debutPage + PAR_PAGE)
  const groupesVisibles = []
  for (const x of visibles) {
    const d = x.date || date
    const dernier = groupesVisibles[groupesVisibles.length - 1]
    if (dernier && dernier.date === d) dernier.lignes.push(x)
    else groupesVisibles.push({ date: d, lignes: [x] })
  }

  return (
    <div>
      <div className="pqr-hero">
        <div>
          <span className="pqr-hero-badge"><i className="bi bi-journal-bookmark me-1"></i>EMPLOIS DU TEMPS · SÉANCES PÉDAGOGIQUES</span>
          <h1 className="pqr-hero-title">Registre des séances</h1>
          <p className="pqr-hero-intro">
            Séances LMD publiées par GET INJS APP et leurs présences rattachées :
            identifiant permanent, ECUE → UE, enseignant, encadrants habilités,
            attendus, présents, émargements manuels et anomalies.
          </p>
          <div className="d-flex flex-wrap gap-2 mt-3">
            <span className="badge text-bg-light">{lignes.length} séance(s)</span>
            <span className="badge text-bg-light">{resume.participants_presents ?? 0} présent(s)</span>
            <span className="badge text-bg-light">{resume.sessions_qr_ouvertes ?? 0} session(s) QR ouverte(s)</span>
            <span className="badge text-bg-light">{resume.emargements_manuels ?? 0} émargement(s) manuel(s)</span>
            {mode === 'plage' && (
              <span className="badge text-bg-warning">
                <i className="bi bi-cloud-download me-1"></i>Chargement explicite : 200 séances
              </span>
            )}
          </div>
        </div>
        <div className="pqr-hero-actions">
          <div>
            <label className="form-label text-white-50 mb-1">Chargement</label>
            <div className="pqr-segmente" role="group" aria-label="Mode de chargement des séances">
              <button type="button" className={mode === 'jour' ? 'actif' : ''}
                      onClick={() => setMode('jour')}>Par jour</button>
              <button type="button" className={mode === 'plage' ? 'actif' : ''}
                      onClick={() => setMode('plage')}>200 séances</button>
            </div>
          </div>
          <div>
            <label className="form-label text-white-50 mb-1" htmlFor="pqr-seances-date">{mode === 'plage' ? 'Autour du' : 'Date'}</label>
            <input id="pqr-seances-date" type="date" className="input" value={date}
                   onChange={(e) => setDate(e.target.value)} />
          </div>
          <div>
            <label className="form-label text-white-50 mb-1" htmlFor="pqr-seances-statut">Statut</label>
            <select id="pqr-seances-statut" className="input" value={statut}
                    onChange={(e) => setStatut(e.target.value)}>
              {FILTRES.map((f) => (
                <option key={f.valeur} value={f.valeur}>{f.libelle}</option>
              ))}
            </select>
          </div>
          <button className="btn btn-outline-light" onClick={charger}>
            <i className="bi bi-funnel me-1"></i>Filtrer
          </button>
          <div className="form-check text-white-50">
            <input id="pqr-seances-auto" type="checkbox" className="form-check-input"
                   checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            <label className="form-check-label" htmlFor="pqr-seances-auto">Direct (30 s)</label>
          </div>
        </div>
      </div>

      {erreur && <div className="error-message">{erreur}</div>}

      <div className="pqr-panel">
        {mode === 'plage' && (
          <>
            <div className="pqr-panel-tete">
              <span>
                <i className="bi bi-cloud-download me-2"></i>
                Chargement explicite : 200 séances autour du {date}
                {donnees?.periode ? ` — fenêtre explorée du ${donnees.periode.date_debut} au ${donnees.periode.date_fin}` : ''}
              </span>
              <span className="badge text-bg-primary">{lignes.length} chargée(s)</span>
            </div>
            {donnees?.periode?.tronque && (
              <p className="pqr-audit-limite">
                Plafond de 200 séances atteint — resserrez la date repère
                ou le statut pour explorer la suite.
              </p>
            )}
          </>
        )}
        <div className="pqr-seances-outils">
          <input
            type="search"
            className="input"
            aria-label="Rechercher dans les séances chargées"
            placeholder="Rechercher (ECUE, UE, enseignant, groupe, salle…)"
            value={recherche}
            onChange={(e) => { setRecherche(e.target.value); setPage(1) }}
          />
          <span className="pqr-seances-compteur">
            {lignesFiltrees.length} séance(s)
            {pagesTotal > 1 ? ` · ${debutPage + 1} à ${debutPage + visibles.length} affichée(s)` : ''}
          </span>
        </div>
        <div className="table-container pqr-seances-scroll">
          <table className="table edt-table pqr-table-seances mb-0">
            <thead>
              <tr>
                <th>Identifiant</th><th>Date</th><th>Horaire</th><th>ECUE → UE</th>
                <th>Parcours / niveau</th><th>Groupe</th><th>Enseignant</th><th>Salle</th>
                <th className="text-end">Attendus</th><th className="text-end">Présents</th>
                <th className="text-end">Manuels</th><th className="text-end">Anom.</th><th>Statut</th>
              </tr>
            </thead>
            <tbody>
              {groupesVisibles.map((g) => (
                <React.Fragment key={g.date}>
                  <tr className="pqr-seances-groupe">
                    <td colSpan={13}>
                      <i className="bi bi-calendar3 me-2"></i>{libelleDateLongue(g.date)}
                      <span className="pqr-seances-groupe-nb">{totalParDate[g.date]} séance(s)</span>
                    </td>
                  </tr>
                  {g.lignes.map((s) => {
                    const anom = anomaliesSeance(s)
                    return (
                  <tr key={s.id}>
                    <td><code>{identifiantPermanent(s.id)}</code></td>
                    <td><code>{s.date || date}</code></td>
                    <td><code>{formatHeure(s.debut)}–{formatHeure(s.fin)}</code></td>
                    <td>
                      <Link className="fw-semibold text-decoration-none"
                            to={`/edt/presences?seance=${s.id}&date=${s.date || date}`}>
                        {s.ecue_code ? `${s.ecue_code} · ` : ''}{s.ecue_libelle || s.intitule || 'Séance'}
                      </Link>
                      <div className="caps text-muted" style={{ fontSize: '.72rem' }}>
                        {[s.ue_code, s.nature_libelle].filter(Boolean).join(' · ') || 'UE non renseignée'}
                      </div>
                    </td>
                    <td>
                      {[s.parcours_libelle, s.niveau_libelle, s.semestre_libelle].filter(Boolean).join(' · ') || '—'}
                      <div className="caps text-muted" style={{ fontSize: '.72rem' }}>
                        {s.formation_libelle || ''}
                      </div>
                    </td>
                    <td><code>{s.groupe_libelle || '—'}</code></td>
                    <td>
                      {s.libelle || '—'}
                      {(s.encadrants || []).map((nom) => (
                        <div key={nom} className="caps text-muted" style={{ fontSize: '.72rem' }}>
                          Enc. {nom}
                        </div>
                      ))}
                    </td>
                    <td>{s.salle_libelle || '—'}</td>
                    <td className="text-end">{s.effectif_attendu ?? '—'}</td>
                    <td className="text-end">
                      <strong className="text-success">{s.presences?.presents || 0}</strong>
                    </td>
                    <td className="text-end">{s.presences?.source_manuelle || 0}</td>
                    <td className="text-end">
                      {anom > 0
                        ? <strong className="text-danger" title="Présences hors périmètre et/ou séance sans groupe rattaché">{anom}</strong>
                        : <span className="text-muted">0</span>}
                    </td>
                    <td>
                      <span className={`badge ${TON_STATUT[s.statut] || 'text-bg-secondary'}`}>
                        {s.statut_libelle || s.statut}
                      </span>
                      {s.session_qr_ouverte && (
                        <span className="badge text-bg-primary ms-1" title="Session QR ouverte">QR</span>
                      )}
                      {s.statut === 'ANNULEE' && (
                        <div className="text-danger" style={{ fontSize: '.72rem', maxWidth: '22ch' }}>
                          Annulation logique tracée dans l’EDT
                        </div>
                      )}
                    </td>
                  </tr>
                    )
                  })}
                </React.Fragment>
              ))}
              {!charge && lignesFiltrees.length === 0 && (
                <tr><td colSpan={13} className="text-center text-muted py-5">
                  {lignes.length === 0
                    ? 'Aucune séance ne correspond à ces critères.'
                    : <>Aucune séance ne correspond à la recherche « {recherche} ».
                        <button type="button" className="btn btn-link btn-sm"
                                onClick={() => setRecherche('')}>Effacer la recherche</button></>}
                </td></tr>
              )}
              {charge && (
                <tr><td colSpan={13} className="text-center py-5">
                  <div className="loading"><div className="spinner"></div></div>
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
        {pagesTotal > 1 && (
          <nav className="pqr-pagination" aria-label="Pagination des séances">
            <button type="button" className="btn btn-outline-secondary btn-sm"
                    disabled={pageSure <= 1} onClick={() => setPage(pageSure - 1)}>
              <i className="bi bi-chevron-left me-1"></i>Précédent
            </button>
            <span className="pqr-pagination-info">Page {pageSure} sur {pagesTotal}</span>
            <button type="button" className="btn btn-outline-secondary btn-sm"
                    disabled={pageSure >= pagesTotal} onClick={() => setPage(pageSure + 1)}>
              Suivant<i className="bi bi-chevron-right ms-1"></i>
            </button>
          </nav>
        )}
        <div className="pqr-panel-corps pt-0">
          <p className="pqr-legende">
            L’identifiant permanent (<code>INJS-S-######</code>) est stable : une modification
            d’horaire, de salle ou d’enseignant conserve l’identité de la séance. Une annulation
            est logique et tracée dans l’EDT (jamais de suppression physique) ; une
            reprogrammation crée une nouvelle séance, avec son propre identifiant.
          </p>
        </div>
      </div>
    </div>
  )
}
