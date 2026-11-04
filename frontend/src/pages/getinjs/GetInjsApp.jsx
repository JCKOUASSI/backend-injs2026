import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import '../../styles/getInjsApp.css'

/**
 * GET INJS APP — tableau de bord d'accueil du module (miroir de la maquette
 * validée, couleurs INJS bleu foncé / bleu clair).
 *
 * Chaque chiffre provient d'un endpoint réel du module ou des référentiels :
 * aucun compteur n'est inventé — un service injoignable affiche « — » et un
 * bloc sans données affiche son état vide honnête.
 */

const SEMESTRES = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10']
const NIVEAUX = ['L1', 'L2', 'L3', 'M1', 'M2']

const ETAPES = [
  {
    titre: 'Référentiels INJS',
    description: 'Filières, formations, salles et enseignants du référentiel.',
    chemin: '/edt/salles-espaces',
  },
  {
    titre: 'Inscriptions / import',
    description: 'Fichier CSV ou XLSX des inscrits ; le parcours est créé automatiquement.',
    chemin: '/edt/generation-annuelle',
  },
  {
    titre: 'Parcours LMD',
    description: 'Maquettes pédagogiques, UE et ECUE des formations Licence & Master.',
    chemin: '/cours',
  },
  {
    titre: 'Génération',
    description: 'Moteur déterministe piloté par campagnes tracées (périmètre, bilan, anomalies).',
    chemin: '/edt/campagnes',
  },
  {
    titre: 'Consultation & export',
    description: 'Grilles hebdomadaires, exports CSV/XLSX/PDF et publication officielle.',
    chemin: '/edt',
  },
]

function listeDe(reponse) {
  const d = reponse?.data
  return Array.isArray(d) ? d : (d?.results ?? [])
}

function compteDe(reponse, repli) {
  const d = reponse?.data
  if (typeof d?.count === 'number') return d.count
  return repli
}

function formaterNombre(n) {
  return typeof n === 'number' ? n.toLocaleString('fr-FR') : '—'
}

function formaterDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('fr-FR')
}

function formaterDuree(ms) {
  if (typeof ms !== 'number') return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} s`
}

/** Répartition des séances publiées par semestre (S1 → S10), données exactes. */
function chargeParSemestre(seances) {
  const compteurs = Object.fromEntries(SEMESTRES.map((s) => [s, 0]))
  for (const s of seances) {
    const sem = s.placement?.semestre
    if (sem in compteurs) compteurs[sem] += 1
  }
  const max = Math.max(1, ...Object.values(compteurs))
  return SEMESTRES.map((sem) => ({
    libelle: sem, valeur: compteurs[sem],
    part: seances.length ? Math.round((compteurs[sem] / seances.length) * 100) : 0,
    largeur: Math.round((compteurs[sem] / max) * 100),
  }))
}

function BarreCharge({ ligne }) {
  return (
    <div className="giapp-barre">
      <span className="giapp-barre-libelle">{ligne.libelle}</span>
      <span className="giapp-barre-piste">
        <span className="giapp-barre-remplissage" style={{ width: `${ligne.largeur}%` }}></span>
      </span>
      <span className="giapp-barre-valeur">
        {ligne.valeur} <span className="giapp-barre-part">· {ligne.part} %</span>
      </span>
    </div>
  )
}

export default function GetInjsApp() {
  const { showToast } = useToast()
  const [chargement, setChargement] = useState(true)
  const [annee, setAnnee] = useState(null)
  const [compteurs, setCompteurs] = useState(null)
  const [seances, setSeances] = useState([])
  const [synthese, setSynthese] = useState(null)
  const [campagnes, setCampagnes] = useState([])
  const [journal, setJournal] = useState([])
  const [telechargement, setTelechargement] = useState(false)

  useEffect(() => {
    let annule = false
    ;(async () => {
      const [annees, emplois, emploisPub, publiees1, evenements, conflits, sante,
        campagnesR, enseignants, salles] = await Promise.allSettled([
        api.get('/scolarite/ref/annees/'),
        api.get('/edts/emplois/'),
        // Compte exact des EDT publiés : la pagination ne doit pas le tronquer.
        api.get('/edts/emplois/', { params: { statut: 'PUBLIE', page_size: 1 } }),
        api.get('/edts/interop/seances-publiees/', { params: { page_size: 100 } }),
        api.get('/edts/interop/evenements/', { params: { non_consommes: 1 } }),
        api.get('/edts/conflits/'),
        api.get('/health/'),
        api.get('/edts/campagnes/'),
        api.get('/edts/referentiel-enseignants/'),
        api.get('/scolarite/ref/salles/'),
      ])
      if (annule) return

      const listeAnnees = annees.status === 'fulfilled' ? listeDe(annees.value) : []
      const anneeCourante = listeAnnees.find((a) => a.courante) || listeAnnees[0] || null
      setAnnee(anneeCourante)

      // Séances publiées : pages suivantes pour des répartitions exactes.
      let toutesSeances = publiees1.status === 'fulfilled' ? listeDe(publiees1.value) : []
      const totalSeances = publiees1.status === 'fulfilled'
        ? compteDe(publiees1.value, toutesSeances.length) : toutesSeances.length
      if (publiees1.status === 'fulfilled' && totalSeances > toutesSeances.length) {
        const pages = Math.min(10, Math.ceil(totalSeances / 100))
        for (let p = 2; p <= pages && toutesSeances.length < totalSeances; p += 1) {
          try {
            const suite = await api.get('/edts/interop/seances-publiees/',
              { params: { page_size: 100, page: p } })
            toutesSeances = toutesSeances.concat(listeDe(suite))
          } catch { break }
          if (annule) return
        }
      }
      setSeances(toutesSeances)

      const listeEmplois = emplois.status === 'fulfilled' ? listeDe(emplois.value) : []
      setCompteurs({
        emploisTotal: emplois.status === 'fulfilled'
          ? compteDe(emplois.value, listeEmplois.length) : null,
        emploisPublies: emploisPub.status === 'fulfilled'
          ? compteDe(emploisPub.value,
              listeDe(emploisPub.value).filter((e) => e.statut === 'PUBLIE').length)
          : listeEmplois.filter((e) => e.statut === 'PUBLIE').length,
        seancesPubliees: publiees1.status === 'fulfilled' ? totalSeances : null,
        evenements: evenements.status === 'fulfilled'
          ? (evenements.value.data?.count ?? null) : null,
        conflits: conflits.status === 'fulfilled'
          ? compteDe(conflits.value, listeDe(conflits.value).length) : null,
        enseignants: enseignants.status === 'fulfilled'
          ? listeDe(enseignants.value).length : null,
        salles: salles.status === 'fulfilled' ? listeDe(salles.value).length : null,
        apiOk: sante.status === 'fulfilled' && sante.value.data?.status === 'ok',
      })
      setCampagnes(campagnesR.status === 'fulfilled' ? listeDe(campagnesR.value) : [])

      // Blocs rattachés à l'année courante : synthèse d'import et journal.
      if (anneeCourante?.id) {
        const [synth, journ] = await Promise.allSettled([
          api.get('/edts/lmd/import/inscrits/synthese/', { params: { annee: anneeCourante.id } }),
          api.get('/edts/lmd/import/inscrits/journal/', { params: { annee: anneeCourante.id } }),
        ])
        if (annule) return
        if (synth.status === 'fulfilled') setSynthese(synth.value.data)
        if (journ.status === 'fulfilled') setJournal(journ.value.data?.lots ?? [])
      }
      setChargement(false)
    })()
    return () => { annule = true }
  }, [])

  const telechargerConception = async () => {
    setTelechargement(true)
    try {
      const { blob, fileName } = await api.getBlob('/edts/lmd/conception/')
      const url = URL.createObjectURL(blob)
      const lien = document.createElement('a')
      lien.href = url
      lien.download = fileName || 'Conception-GET-INJS.txt'
      document.body.appendChild(lien)
      lien.click()
      lien.remove()
      URL.revokeObjectURL(url)
    } catch {
      showToast('Document de conception indisponible.', 'error')
    } finally {
      setTelechargement(false)
    }
  }

  const kpi = (v) => (chargement ? '…' : formaterNombre(v))
  const charge = chargeParSemestre(seances)
  const heuresPlanifiees = Math.round(
    seances.reduce((total, s) => total + (s.placement?.duree_prevue_minutes || 0), 0) / 60,
  )

  // Population gérée par le module pour la génération (inscrits importés).
  const cohortes = synthese?.cohortes ?? []
  const parFormation = Object.values(cohortes.reduce((acc, c) => {
    const cle = c.formation || '—'
    acc[cle] = acc[cle] || { libelle: cle, valeur: 0 }
    acc[cle].valeur += c.effectif || 0
    return acc
  }, {})).sort((a, b) => b.valeur - a.valeur)
  const maxFormation = Math.max(1, ...parFormation.map((f) => f.valeur))
  const parNiveau = NIVEAUX.map((n) => ({
    libelle: n,
    valeur: cohortes.filter((c) => c.niveau === n)
      .reduce((t, c) => t + (c.effectif || 0), 0),
  }))

  return (
    <div className="giapp" data-testid="get-injs-app">
      {/* ── En-tête du tableau de bord ─────────────────────────────────── */}
      <header className="giapp-hero">
        <div className="giapp-hero-main">
          <div className="giapp-pills">
            <Link to="/edt/audit" className="giapp-pill">
              <i className="bi bi-clipboard2-check"></i> Audit des données · Opérations
            </Link>
            <span className="giapp-pill">Licence • Master — Système LMD</span>
            <span className="giapp-pill">
              Année {annee?.libelle || '…'}
            </span>
          </div>
          <h1 className="giapp-hero-title">GET INJS APP</h1>
          <p className="giapp-hero-sub">
            GET INJS APP orchestre les filières, formations, groupes, vagues et
            enseignants de l’INJS d’Abidjan pour générer les emplois du temps de
            l’année — de l’import des inscrits (3 500 à 14 000 étudiants) à la
            publication officielle des séances, prêtes pour le module Présences.
          </p>
          <div className="giapp-hero-actions">
            <Link to="/edt/generation-annuelle" className="giapp-btn giapp-btn--accent">
              <i className="bi bi-lightning-charge-fill"></i> Générer un emploi du temps
            </Link>
            <Link to="/edt" className="giapp-hero-lien">
              Consulter les grilles <i className="bi bi-arrow-right"></i>
            </Link>
          </div>
        </div>
        <div className="giapp-hero-stats">
          <div className="giapp-hero-stat">
            <span className="giapp-hero-stat-libelle">Séances publiées</span>
            <span className="giapp-hero-stat-valeur">{kpi(compteurs?.seancesPubliees)}</span>
          </div>
          <div className="giapp-hero-stat">
            <span className="giapp-hero-stat-libelle">Heures planifiées</span>
            <span className="giapp-hero-stat-valeur">
              {chargement ? '…' : `${formaterNombre(heuresPlanifiees)} h`}
            </span>
          </div>
          <div className="giapp-hero-etat" data-testid="etat-api">
            <span className={`giapp-pastille ${compteurs?.apiOk ? 'is-ok' : 'is-ko'}`}></span>
            {chargement ? 'Vérification des services…'
              : compteurs?.apiOk ? 'Services GET opérationnels' : 'Services GET injoignables'}
          </div>
        </div>
      </header>

      {/* ── Indicateurs clés ───────────────────────────────────────────── */}
      <section className="giapp-kpis" aria-label="Indicateurs du module">
        <div className="giapp-kpi">
          <span className="giapp-kpi-libelle">Étudiants</span>
          <span className="giapp-kpi-valeur" data-testid="kpi-etudiants">{kpi(synthese?.effectif_total ?? null)}</span>
          <span className="giapp-kpi-detail">inscrits importés · année {annee?.libelle || '—'}</span>
        </div>
        <div className="giapp-kpi">
          <span className="giapp-kpi-libelle">Cohortes</span>
          <span className="giapp-kpi-valeur" data-testid="kpi-cohortes">{kpi(synthese?.nb_cohortes ?? null)}</span>
          <span className="giapp-kpi-detail">formation · niveau · groupe · vague</span>
        </div>
        <div className="giapp-kpi">
          <span className="giapp-kpi-libelle">Salles</span>
          <span className="giapp-kpi-valeur" data-testid="kpi-salles">{kpi(compteurs?.salles)}</span>
          <span className="giapp-kpi-detail">salles & espaces du référentiel</span>
        </div>
        <div className="giapp-kpi">
          <span className="giapp-kpi-libelle">Enseignants</span>
          <span className="giapp-kpi-valeur" data-testid="kpi-enseignants">{kpi(compteurs?.enseignants)}</span>
          <span className="giapp-kpi-detail">référentiel des enseignants</span>
        </div>
        <div className="giapp-kpi">
          <span className="giapp-kpi-libelle">EDT publiés</span>
          <span className="giapp-kpi-valeur" data-testid="kpi-edt-publies">{kpi(compteurs?.emploisPublies)}</span>
          <span className="giapp-kpi-detail">sur {kpi(compteurs?.emploisTotal)} emplois du temps</span>
        </div>
        <div className="giapp-kpi">
          <span className="giapp-kpi-libelle">Séances</span>
          <span className="giapp-kpi-valeur" data-testid="kpi-seances-publiees">{kpi(compteurs?.seancesPubliees)}</span>
          <span className="giapp-kpi-detail">publiées · prêtes pour Présences</span>
        </div>
      </section>

      {/* ── Charge par semestre · Population par filière ───────────────── */}
      <section className="giapp-grid-2">
        <div className="giapp-card">
          <div className="giapp-card-entete">
            <h2>Charge par semestre</h2>
            <span className="giapp-badge">{kpi(compteurs?.seancesPubliees)} séances</span>
          </div>
          <p className="giapp-card-sous">Séances officielles publiées, par semestre académique</p>
          {chargement ? <p className="giapp-vide">Chargement…</p>
            : seances.length === 0 ? (
              <p className="giapp-vide">Aucune séance publiée pour le moment.</p>
            ) : (
              <div className="giapp-barres" data-testid="charge-semestres">
                {charge.map((ligne) => <BarreCharge key={ligne.libelle} ligne={ligne} />)}
              </div>
            )}
        </div>

        <div className="giapp-card">
          <div className="giapp-card-entete">
            <h2>Population par filière</h2>
            <span className="giapp-badge">{kpi(synthese?.effectif_total ?? null)} étudiants</span>
          </div>
          <p className="giapp-card-sous">Étudiants importés rattachés à leurs cohortes de génération</p>
          {chargement ? <p className="giapp-vide">Chargement…</p>
            : parFormation.length === 0 ? (
              <p className="giapp-vide">
                Aucun inscrit importé pour l’année {annee?.libelle || 'courante'} :
                importez le fichier des inscrits pour alimenter la génération.
              </p>
            ) : (
              <>
                <div className="giapp-barres" data-testid="population-filieres">
                  {parFormation.slice(0, 5).map((f) => (
                    <div className="giapp-barre" key={f.libelle}>
                      <span className="giapp-barre-libelle giapp-barre-libelle--long">{f.libelle}</span>
                      <span className="giapp-barre-piste">
                        <span className="giapp-barre-remplissage is-clair"
                          style={{ width: `${Math.round((f.valeur / maxFormation) * 100)}%` }}></span>
                      </span>
                      <span className="giapp-barre-valeur">{formaterNombre(f.valeur)}</span>
                    </div>
                  ))}
                </div>
                <div className="giapp-niveaux">
                  {parNiveau.map((n) => (
                    <div className="giapp-niveau" key={n.libelle}>
                      <span className="giapp-niveau-code">{n.libelle}</span>
                      <span className="giapp-niveau-valeur">{formaterNombre(n.valeur)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
        </div>
      </section>

      {/* ── Dernières générations · Étapes du processus ────────────────── */}
      <section className="giapp-grid-2">
        <div className="giapp-card">
          <div className="giapp-card-entete">
            <h2>Dernières générations</h2>
            <Link to="/edt/campagnes" className="giapp-btn giapp-btn--petit">Ouvrir le moteur</Link>
          </div>
          <p className="giapp-card-sous">Campagnes de génération tracées du module</p>
          {chargement ? <p className="giapp-vide">Chargement…</p>
            : campagnes.length === 0 ? (
              <p className="giapp-vide">Aucune campagne de génération pour le moment.</p>
            ) : (
              <ul className="giapp-generations" data-testid="dernieres-generations">
                {campagnes.slice(0, 4).map((c) => {
                  const stats = { ...(c.totaux || {}), ...(c.statistiques || {}) }
                  const placees = stats.seances_placees
                  const nonPlacees = stats.seances_non_placees
                  const couverture = (typeof placees === 'number' && typeof nonPlacees === 'number'
                    && (placees + nonPlacees) > 0)
                    ? `${((placees / (placees + nonPlacees)) * 100).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`
                    : '—'
                  return (
                    <li key={c.id} className="giapp-generation">
                      <div className="giapp-generation-ligne">
                        <span className="giapp-generation-date">{formaterDate(c.created_at)}</span>
                        <span className="giapp-badge">{c.statut_libelle || c.statut}</span>
                      </div>
                      <p className="giapp-generation-titre">{c.libelle}</p>
                      <p className="giapp-generation-stats">
                        Séances <strong>{formaterNombre(placees ?? null)}</strong> · Couverture{' '}
                        <strong>{couverture}</strong> · Durée{' '}
                        <strong>{formaterDuree(stats.duree_ms)}</strong>
                      </p>
                    </li>
                  )
                })}
              </ul>
            )}
        </div>

        <div className="giapp-card">
          <div className="giapp-card-entete">
            <h2>Les 5 étapes du processus</h2>
          </div>
          <p className="giapp-card-sous">De l’inscription à la publication officielle</p>
          <ol className="giapp-etapes">
            {ETAPES.map((etape, i) => (
              <li key={etape.titre}>
                <Link to={etape.chemin} className="giapp-etape">
                  <span className="giapp-etape-numero">{i + 1}</span>
                  <span>
                    <span className="giapp-etape-titre">{etape.titre}</span>
                    <span className="giapp-etape-desc">{etape.description}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ── Journal des imports ────────────────────────────────────────── */}
      <section className="giapp-card">
        <div className="giapp-card-entete">
          <h2>Journal des imports</h2>
          <Link to="/edt/generation-annuelle" className="giapp-btn giapp-btn--petit">
            <i className="bi bi-upload"></i> Importer
          </Link>
        </div>
        <p className="giapp-card-sous">
          Traçabilité des fichiers d’inscrits reçus pour l’année {annee?.libelle || 'courante'}
        </p>
        {chargement ? <p className="giapp-vide">Chargement…</p>
          : journal.length === 0 ? (
            <p className="giapp-vide">Aucun import enregistré pour cette année.</p>
          ) : (
            <div className="giapp-table-wrap">
              <table className="giapp-table" data-testid="journal-imports">
                <thead>
                  <tr>
                    <th>Fichier</th><th>Reçu le</th><th>Lignes rattachées</th>
                    <th>Étudiants inscrits</th><th>Empreinte du lot</th>
                  </tr>
                </thead>
                <tbody>
                  {journal.map((lot, i) => (
                    <tr key={`${lot.empreinte}-${i}`}>
                      <td>{lot.fichier}</td>
                      <td>{formaterDate(lot.recu_le)}</td>
                      <td>{formaterNombre(lot.lignes)}</td>
                      <td>{formaterNombre(lot.inscrits)}</td>
                      <td><code className="giapp-uuid">{lot.empreinte || '—'}</code></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </section>

      {/* ── Accès rapides ──────────────────────────────────────────────── */}
      <section className="giapp-minis">
        <Link to="/edt" className="giapp-mini">
          <span className="giapp-mini-libelle">Emplois du temps</span>
          <span className="giapp-mini-valeur">{kpi(compteurs?.emploisTotal)}</span>
          <span className="giapp-mini-titre">Grille hebdomadaire</span>
          <span className="giapp-mini-lien">Accéder <i className="bi bi-arrow-right"></i></span>
        </Link>
        <Link to="/edt/conflits" className="giapp-mini">
          <span className="giapp-mini-libelle">Moteur LMD</span>
          <span className="giapp-mini-valeur">{kpi(compteurs?.conflits)}</span>
          <span className="giapp-mini-titre">Conflit(s) actif(s)</span>
          <span className="giapp-mini-lien">Accéder <i className="bi bi-arrow-right"></i></span>
        </Link>
        <Link to="/edt/generation-annuelle" className="giapp-mini">
          <span className="giapp-mini-libelle">Import annuel</span>
          <span className="giapp-mini-valeur">{kpi(synthese?.effectif_total ?? null)}</span>
          <span className="giapp-mini-titre">Étudiants importés</span>
          <span className="giapp-mini-lien">Accéder <i className="bi bi-arrow-right"></i></span>
        </Link>
        <button type="button" className="giapp-mini giapp-mini--bouton"
          onClick={telechargerConception} disabled={telechargement}
          data-testid="telecharger-conception">
          <span className="giapp-mini-libelle">Document</span>
          <span className="giapp-mini-valeur"><i className="bi bi-file-earmark-text"></i></span>
          <span className="giapp-mini-titre">Conception du module</span>
          <span className="giapp-mini-lien">
            {telechargement ? 'Téléchargement…' : 'Télécharger'} <i className="bi bi-arrow-right"></i>
          </span>
        </button>
      </section>

      {/* ── Séances officielles publiées ───────────────────────────────── */}
      <h2 className="giapp-titre-section">Séances officielles publiées — prêtes pour le module Présences</h2>
      <section className="giapp-panneau">
        {chargement ? (
          <p className="giapp-vide">Chargement des séances publiées…</p>
        ) : seances.length === 0 ? (
          <p className="giapp-vide">
            Aucune séance publiée pour le moment. Générez puis publiez un emploi
            du temps : ses séances apparaîtront ici avec leur identifiant
            permanent, prêtes à ouvrir des sessions de présence.
          </p>
        ) : (
          <div className="giapp-table-wrap">
            <table className="giapp-table">
              <thead>
                <tr>
                  <th>Identifiant permanent</th>
                  <th>Formation</th>
                  <th>UE / ECUE</th>
                  <th>Jour & horaire</th>
                  <th>Enseignant</th>
                  <th>Statut</th>
                  <th>Session de présence</th>
                </tr>
              </thead>
              <tbody>
                {seances.slice(0, 10).map((s) => (
                  <tr key={s.seance_uuid}>
                    <td><code className="giapp-uuid">{String(s.seance_uuid).slice(0, 8)}…</code></td>
                    <td>{s.placement?.formation || '—'}</td>
                    <td>{[s.placement?.ue, s.placement?.ecue].filter(Boolean).join(' · ') || '—'}</td>
                    <td>{[s.placement?.jour, s.placement?.heure_debut, s.placement?.heure_fin].filter(Boolean).join(' ') || '—'}</td>
                    <td>{s.placement?.enseignant || '—'}</td>
                    <td><span className="giapp-badge">{s.statut}</span></td>
                    <td>
                      {s.peut_ouvrir_session_presence
                        ? <span className="giapp-badge giapp-badge--ok">Ouvrable</span>
                        : <span className="giapp-badge giapp-badge--ko">Non ouvrable</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="giapp-note">
          Chaque séance publiée possède un identifiant unique permanent (UUID) :
          c’est la référence que le futur module de présence (QR Code, pointage
          manuel, géolocalisation) utilisera, indépendamment de l’horaire, de
          la salle ou de l’enseignant.
        </p>
      </section>
    </div>
  )
}
