import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import '../../styles/getInjsApp.css'

/**
 * GET INJS APP — page d'accueil du module de gestion des emplois du temps.
 *
 * Le moteur (génération déterministe, campagnes, import d'inscrits,
 * publication, exports) vit dans l'application backend ``edts`` et ses
 * écrans dédiés ; cette page est le point d'entrée visible du module :
 * elle présente ses fonctionnalités, ses compteurs réels et les séances
 * officiellement publiées prêtes pour le futur module Présences.
 * Aucun chiffre n'est inventé : un service injoignable affiche « — ».
 */

const FONCTIONNALITES = [
  {
    titre: 'Tableau des emplois du temps',
    description: 'Consulter, filtrer et ouvrir les emplois du temps par formation, groupe, enseignant ou salle.',
    chemin: '/edt', icone: 'bi-table',
  },
  {
    titre: 'Créer un emploi du temps',
    description: 'Composer manuellement un emploi du temps et ses séances.',
    chemin: '/edt/nouveau', icone: 'bi-plus-square',
  },
  {
    titre: 'Génération annuelle & import',
    description: 'Importer un fichier d’inscrits (CSV/XLSX) puis générer les emplois du temps de toute l’année.',
    chemin: '/edt/generation-annuelle', icone: 'bi-lightning-charge',
  },
  {
    titre: 'Campagnes de génération',
    description: 'Piloter les générations par campagnes tracées (périmètre, bilan, anomalies, durée).',
    chemin: '/edt/campagnes', icone: 'bi-collection-play',
  },
  {
    titre: 'Audit des données',
    description: 'Vérifier « puis-je générer ? » : contrôles des référentiels avant toute génération.',
    chemin: '/edt/audit', icone: 'bi-clipboard2-check',
  },
  {
    titre: 'Versions & publication',
    description: 'Valider puis publier officiellement les emplois du temps, par versions successives.',
    chemin: '/edt/versions', icone: 'bi-send-check',
  },
  {
    titre: 'Présences de séance',
    description: 'Séances du jour, effectifs attendus et émargement (QR & manuel).',
    chemin: '/edt/presences', icone: 'bi-qr-code-scan',
  },
  {
    titre: 'Cours (LMD)',
    description: 'Séances et cours rattachés aux maquettes LMD.',
    chemin: '/cours', icone: 'bi-journal-bookmark',
  },
  {
    titre: 'Salles & espaces',
    description: '166 salles et espaces de formation du référentiel INJS.',
    chemin: '/edt/salles-espaces', icone: 'bi-building',
  },
  {
    titre: 'Disponibilités',
    description: 'Indisponibilités et préférences des enseignants et des salles.',
    chemin: '/edt/disponibilites', icone: 'bi-calendar-heart',
  },
  {
    titre: 'Conflits & contraintes',
    description: 'Détecter et résoudre les conflits salle / enseignant / groupe.',
    chemin: '/edt/conflits', icone: 'bi-exclamation-triangle',
  },
  {
    titre: 'Export / Impression',
    description: 'Exporter les emplois du temps (CSV, XLSX, PDF) et les imprimer.',
    chemin: '/edt/export', icone: 'bi-printer',
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

const JOURS_SEMAINE = ['LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI', 'DIMANCHE']

function minutesDe(heure) {
  const [h, m] = String(heure || '').split(':').map(Number)
  return Number.isFinite(h) ? h * 60 + (m || 0) : null
}

/** Vue d'ensemble calculée des séances chargées — aucun chiffre inventé. */
function calculerVueEnsemble(seances) {
  // Semaine académique INJS : lundi à samedi toujours affichés ; le dimanche
  // n'apparaît que s'il porte effectivement des séances.
  const parJour = JOURS_SEMAINE.map((jour) => ({
    libelle: jour.charAt(0) + jour.slice(1).toLowerCase(),
    valeur: seances.filter((s) => s.placement?.jour === jour).length,
  })).filter((j, i) => i < 6 || j.valeur > 0)
  const types = {}
  let minutes = 0
  for (const s of seances) {
    const t = s.placement?.type_seance || 'AUTRE'
    types[t] = (types[t] || 0) + 1
    const d = minutesDe(s.placement?.heure_debut)
    const f = minutesDe(s.placement?.heure_fin)
    if (d !== null && f !== null && f > d) minutes += f - d
  }
  const parType = Object.entries(types)
    .map(([libelle, valeur]) => ({ libelle, valeur }))
    .sort((a, b) => b.valeur - a.valeur)
  return { parJour, parType, heures: Math.round((minutes / 60) * 10) / 10 }
}

function Barres({ donnees, accent }) {
  const max = Math.max(1, ...donnees.map((d) => d.valeur))
  return (
    <div className="giapp-barres">
      {donnees.map((d) => (
        <div className="giapp-barre" key={d.libelle}>
          <span className="giapp-barre-libelle">{d.libelle}</span>
          <span className="giapp-barre-piste">
            <span
              className={`giapp-barre-remplissage ${accent === 'ocre' ? 'is-ocre' : ''}`}
              style={{ width: `${Math.round((d.valeur / max) * 100)}%` }}
            ></span>
          </span>
          <span className="giapp-barre-valeur">{d.valeur}</span>
        </div>
      ))}
    </div>
  )
}

export default function GetInjsApp() {
  const { showToast } = useToast()
  const [compteurs, setCompteurs] = useState(null)
  const [seances, setSeances] = useState([])
  const [chargement, setChargement] = useState(true)
  const [telechargement, setTelechargement] = useState(false)

  useEffect(() => {
    let annule = false
    ;(async () => {
      const [emplois, emploisPub, publiees, evenements, conflits, sante] = await Promise.allSettled([
        api.get('/edts/emplois/'),
        // Compte exact des EDT publiés : la pagination ne doit pas le tronquer.
        api.get('/edts/emplois/', { params: { statut: 'PUBLIE', page_size: 1 } }),
        api.get('/edts/interop/seances-publiees/', { params: { page_size: 100 } }),
        api.get('/edts/interop/evenements/', { params: { non_consommes: 1 } }),
        api.get('/edts/conflits/'),
        api.get('/health/'),
      ])
      if (annule) return
      const listeEmplois = emplois.status === 'fulfilled' ? listeDe(emplois.value) : []
      const listeSeances = publiees.status === 'fulfilled' ? listeDe(publiees.value) : []
      setCompteurs({
        emploisTotal: emplois.status === 'fulfilled'
          ? compteDe(emplois.value, listeEmplois.length) : null,
        emploisPublies: emploisPub.status === 'fulfilled'
          ? compteDe(emploisPub.value,
              listeDe(emploisPub.value).filter((e) => e.statut === 'PUBLIE').length)
          : listeEmplois.filter((e) => e.statut === 'PUBLIE').length,
        seancesPubliees: publiees.status === 'fulfilled'
          ? compteDe(publiees.value, listeSeances.length) : null,
        evenements: evenements.status === 'fulfilled'
          ? (evenements.value.data?.count ?? null) : null,
        conflits: conflits.status === 'fulfilled'
          ? compteDe(conflits.value, listeDe(conflits.value).length) : null,
        apiOk: sante.status === 'fulfilled' && sante.value.data?.status === 'ok',
      })
      setSeances(listeSeances)
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

  const kpi = (valeur) => (chargement ? '…' : (valeur ?? '—'))
  const vue = calculerVueEnsemble(seances)

  return (
    <div className="giapp" data-testid="get-injs-app">
      {/* ── Bannière du module ─────────────────────────────────────────── */}
      <header className="giapp-hero">
        <div>
          <span className="giapp-hero-tag">INJS · Abidjan — Marcory</span>
          <h1 className="giapp-hero-title">GET INJS APP</h1>
          <p className="giapp-hero-sub">
            Gestion des Emplois du Temps — génération, import des inscrits,
            publication officielle et séances prêtes pour le module Présences.
          </p>
          <div className="giapp-hero-actions">
            <Link to="/edt/generation-annuelle" className="giapp-btn giapp-btn--or">
              <i className="bi bi-lightning-charge-fill"></i> Générer les emplois du temps
            </Link>
            <button
              type="button"
              className="giapp-btn giapp-btn--clair"
              onClick={telechargerConception}
              disabled={telechargement}
              data-testid="telecharger-conception"
            >
              <i className="bi bi-file-earmark-arrow-down"></i>
              {telechargement ? 'Téléchargement…' : 'Conception du module (TXT)'}
            </button>
          </div>
        </div>
        <div className="giapp-hero-etat" data-testid="etat-api">
          <span className={`giapp-pastille ${compteurs?.apiOk ? 'is-ok' : 'is-ko'}`}></span>
          {chargement ? 'Vérification des services…'
            : compteurs?.apiOk ? 'Services GET opérationnels' : 'Services GET injoignables'}
        </div>
      </header>

      {/* ── Compteurs réels ────────────────────────────────────────────── */}
      <section className="giapp-kpis" aria-label="Compteurs du module">
        <div className="giapp-kpi">
          <span className="giapp-kpi-valeur" data-testid="kpi-emplois">{kpi(compteurs?.emploisTotal)}</span>
          <span className="giapp-kpi-libelle">Emplois du temps</span>
        </div>
        <div className="giapp-kpi">
          <span className="giapp-kpi-valeur" data-testid="kpi-emplois-publies">{kpi(compteurs?.emploisPublies)}</span>
          <span className="giapp-kpi-libelle">EDT publiés</span>
        </div>
        <div className="giapp-kpi">
          <span className="giapp-kpi-valeur" data-testid="kpi-seances-publiees">{kpi(compteurs?.seancesPubliees)}</span>
          <span className="giapp-kpi-libelle">Séances publiées (prêtes pour Présences)</span>
        </div>
        <div className="giapp-kpi">
          <span className="giapp-kpi-valeur" data-testid="kpi-conflits">{kpi(compteurs?.conflits)}</span>
          <span className="giapp-kpi-libelle">Conflits actifs</span>
        </div>
        <div className="giapp-kpi">
          <span className="giapp-kpi-valeur" data-testid="kpi-evenements">{kpi(compteurs?.evenements)}</span>
          <span className="giapp-kpi-libelle">Événements de séance à consommer</span>
        </div>
      </section>

      {/* ── Vue d'ensemble dynamique des séances publiées ──────────────── */}
      {!chargement && seances.length > 0 && (
        <>
          <h2 className="giapp-titre-section">Vue d’ensemble des séances publiées</h2>
          <section className="giapp-graphs" data-testid="vue-ensemble">
            <div className="giapp-graph">
              <h3>Séances par jour de semaine</h3>
              <Barres donnees={vue.parJour} />
            </div>
            <div className="giapp-graph">
              <h3>Séances par nature d’enseignement</h3>
              <Barres donnees={vue.parType} accent="ocre" />
            </div>
            <div className="giapp-graph giapp-graph--chiffre">
              <h3>Volume horaire planifié</h3>
              <p className="giapp-gros-chiffre">{vue.heures} h</p>
              <p className="giapp-note">
                Calculé sur les {seances.length} séances publiées chargées
                (échantillon des 100 plus récentes) — le total officiel est le
                compteur « Séances publiées » ci-dessus.
              </p>
            </div>
          </section>
        </>
      )}

      {/* ── Fonctionnalités du module ──────────────────────────────────── */}
      <h2 className="giapp-titre-section">Fonctionnalités du module</h2>
      <section className="giapp-tuiles">
        {FONCTIONNALITES.map((f) => (
          <Link key={f.chemin} to={f.chemin} className="giapp-tuile">
            <span className="giapp-tuile-icone" aria-hidden="true"><i className={`bi ${f.icone}`}></i></span>
            <span className="giapp-tuile-titre">{f.titre}</span>
            <span className="giapp-tuile-desc">{f.description}</span>
            <span className="giapp-tuile-lien">Ouvrir <i className="bi bi-arrow-right"></i></span>
          </Link>
        ))}
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
