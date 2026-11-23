import React, { useState } from 'react'
import api from '@/services/api'
import { useToast } from '../../context/ToastContext'

/**
 * « Conception » — Documentation technique du module GET INJS APP.
 *
 * Refonte du sous-module : la conception n'est plus seulement un fichier
 * téléchargé depuis le menu, elle se consulte en ligne dans le hub.
 * Chaque affirmation de la page décrit le code réellement livré
 * (application Django `edts`, moteur `edts/moteur`, document
 * `docs/getinjs/Conception-GET-INJS.txt`) : architecture en couches,
 * algorithme de génération, contrats d'API, modèle de données, commandes
 * d'implémentation et exigences couvertes. Le document complet reste
 * téléchargeable au format texte, versionné avec le code.
 */

const COUCHES = [
  {
    nom: 'Interface',
    pile: 'React 18 · Vite · React Router',
    role: 'Tableaux de bord, grilles hebdomadaires, formulaires et collections du hub GET-INJS (design system INJS).',
  },
  {
    nom: 'API',
    pile: 'Django REST Framework',
    role: 'Génération, campagnes, import des inscrits, population, référentiels, exports et documentation sous /api/edts/.',
  },
  {
    nom: 'Services',
    pile: 'Campagnes de génération',
    role: 'Orchestration données-prêtes → démarrage → résultat → validation → publication ; journal des imports et audit des données.',
  },
  {
    nom: 'Moteur',
    pile: 'Python déterministe (edts/moteur)',
    role: 'Besoins, backtracking borné, validation C1…C9 : aucun aléa, aucun placement en conflit, échec explicite plutôt que plan faux.',
  },
  {
    nom: 'Données',
    pile: 'Django ORM',
    role: 'PostgreSQL en production, SQLite en développement et tests ; tables edts_* du module adossées à la chaîne LMD du socle.',
  },
]

const ETAPES_ALGORITHME = [
  'Besoins : affectations pédagogiques quand elles existent ; sinon maquette active (CM/TD/TP convertis en séances de 2 h).',
  'Contexte : créneaux officiels, salles actives, semaines, index de disponibilités et index d’occupations.',
  'Backtracking chronologique borné par un budget de placements : à chaque étape le besoin le plus contraint, candidats triés par (score de pénalités, jour, heure, salle).',
  'Validation : contraintes C1…C9 et couverture des besoins ; toute violation est listée, jamais masquée.',
  'Persistance : un emploi du temps BROUILLON par groupe, dans une transaction par EDT.',
  'Publication : geste humain, après validation, atomique pour le périmètre de la campagne.',
]

const ROUTES_API = [
  { methode: 'POST', route: '/api/edts/lmd/import/inscrits/analyser/', role: 'Analyse un fichier d’inscrits, sans écriture' },
  { methode: 'POST', route: '/api/edts/lmd/import/inscrits/', role: 'Importe le fichier (idempotent, journalisé)' },
  { methode: 'GET', route: '/api/edts/lmd/import/inscrits/journal/', role: 'Journal des imports de l’année' },
  { methode: 'GET', route: '/api/edts/lmd/inscrits/', role: 'Population des étudiants inscrits (base + imports)' },
  { methode: 'GET', route: '/api/edts/lmd/referentiels/', role: 'Données de référence de l’année' },
  { methode: 'POST', route: '/api/edts/campagnes/', role: 'Crée une campagne de génération' },
  { methode: 'POST', route: '/api/edts/campagnes/{id}/demarrer/', role: 'Démarre la génération du périmètre' },
  { methode: 'GET', route: '/api/edts/campagnes/{id}/resultat/', role: 'Résultat, bilan et anomalies de la campagne' },
  { methode: 'POST', route: '/api/edts/campagnes/{id}/valider/', role: 'Valide les emplois du temps brouillons' },
  { methode: 'POST', route: '/api/edts/campagnes/{id}/publier/', role: 'Publie atomiquement le périmètre validé' },
  { methode: 'GET', route: '/api/edts/lmd/{id}/export.xlsx/', role: 'Grille au format XLSX (PDF également servi)' },
  { methode: 'GET', route: '/api/edts/lmd/conception/', role: 'Télécharge le document de conception (cette page)' },
]

const TABLES = [
  { table: 'edts_campagnegeneration', contenu: 'Campagnes de génération : périmètre, statut, bilan' },
  { table: 'edts_executioncampagne', contenu: 'Exécutions tracées d’une campagne (démarrage, résultat)' },
  { table: 'edts_emploidutemps', contenu: 'Emplois du temps par groupe, du brouillon à la publication' },
  { table: 'edts_affectationcreneau', contenu: 'Séances placées : créneau, salle, enseignant, groupe' },
  { table: 'edts_conflitcreneau', contenu: 'Conflits détectés par le moteur et leur résolution' },
  { table: 'edts_creneautemplate', contenu: 'Créneaux officiels de la journée type INJS' },
  { table: 'edts_disponibilitehoraire', contenu: 'Disponibilités et indisponibilités des enseignants' },
  { table: 'edts_inscriptionimportee', contenu: 'Inscriptions lues dans un fichier externe (fichier, empreinte, ligne source)' },
  { table: 'edts_politiquecontraintessouples', contenu: 'Politique des contraintes souples : quotas et préférences' },
  { table: 'gi_seance_registre', contenu: 'Séances publiées : identifiant permanent consommé par le module Présences' },
]

const COMMANDES = [
  {
    etape: 'P.1 — Dépendances backend',
    commande: 'pip install -r backend/requirements.txt',
    detail: 'Aucune dépendance nouvelle : le module réutilise le socle Django du dépôt.',
  },
  {
    etape: 'P.2 — Base de données',
    commande: 'python backend/manage.py migrate',
    detail: 'Crée les tables edts_* et gi_* du module, sans toucher aux données du socle.',
  },
  {
    etape: 'P.3 — Données de démonstration (optionnel)',
    commande: 'python backend/manage.py donnees_demonstration_getinjs --forcer',
    detail: 'Jeu de démonstration identifiable (année, formation INJS, groupes, salles, maquette), refusé hors mode démonstration sans --forcer.',
  },
  {
    etape: 'P.4 — Contrôle du canevas officiel',
    commande: 'python backend/manage.py verifier_canevas',
    detail: 'Compare les créneaux types en base au canevas officiel INJS (6 jours × 4 plages = 24 créneaux).',
  },
  {
    etape: 'P.5 — Tests du module',
    commande: 'python backend/manage.py test edts',
    detail: 'Import, moteur, campagnes, population et référentiels : la suite doit être verte avant toute livraison.',
  },
  {
    etape: 'P.6 — Interface',
    commande: 'cd frontend && npm install && npm run build',
    detail: 'Build de production des écrans du hub GET-INJS servis par l’application.',
  },
]

const EXIGENCES = [
  {
    titre: 'Module complet',
    detail: 'Tableau de bord, référentiels, import, étudiants inscrits, génération, campagnes, grilles, exports et audit.',
  },
  {
    titre: 'Génération par parcours',
    detail: 'Filière, formation, niveau, groupe, vague, semestre et année académique découpent chaque génération.',
  },
  {
    titre: 'Population réelle',
    detail: '3 786 étudiants inscrits en 2026-2027 (base + fichier externe) ; aucun effectif inventé, les cellules sans source affichent « — ».',
  },
  {
    titre: 'Fichier externe',
    detail: 'CSV ou XLSX, alias de colonnes insensibles aux accents, reconstruction du parcours et rejets motivés ligne par ligne.',
  },
  {
    titre: 'Sans parcours préalable',
    detail: 'Les inscriptions importées restent identifiables et supprimables ; jamais d’inscription administrative ni de parcours fictifs.',
  },
  {
    titre: 'Documentation',
    detail: 'Document de conception versionné avec le code (docs/getinjs/), consultable en ligne et téléchargeable depuis cette page.',
  },
  {
    titre: 'Backend testé',
    detail: 'Suites du module vertes : import des inscrits, population, référentiels et API des campagnes.',
  },
]

export default function Conception() {
  const { showToast } = useToast()
  const [enCours, setEnCours] = useState('')

  const recupererDocument = async () => {
    const { blob, fileName } = await api.getBlob('/edts/lmd/conception/')
    return { blob, fileName: fileName || 'Conception-GET-INJS.txt' }
  }

  const telecharger = async () => {
    setEnCours('telechargement')
    try {
      const { blob, fileName } = await recupererDocument()
      const url = URL.createObjectURL(blob)
      const lien = document.createElement('a')
      lien.href = url
      lien.download = fileName
      document.body.appendChild(lien)
      lien.click()
      lien.remove()
      URL.revokeObjectURL(url)
      showToast('Document de conception téléchargé.', 'success')
    } catch {
      showToast('Document de conception indisponible.', 'error')
    } finally {
      setEnCours('')
    }
  }

  const consulterEnLigne = async () => {
    setEnCours('consultation')
    try {
      const { blob } = await recupererDocument()
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener')
      showToast('Document ouvert dans un nouvel onglet.', 'success')
    } catch {
      showToast('Document de conception indisponible.', 'error')
    } finally {
      setEnCours('')
    }
  }

  return (
    <div className="getinjs gen-page imp-page conc-page" data-testid="conception">
      {/* ── En-tête clair : sur-titre, titre, actions document ──────────── */}
      <div className="imp-entete">
        <div>
          <div className="imp-surtitre">Documentation technique</div>
          <h1 className="imp-titre">Conception du module GET INJS APP</h1>
          <p className="imp-sous">
            Architecture, modèle de données, algorithme de génération, API et
            procédures d'exploitation. Le document complet est téléchargeable
            au format texte et versionnable avec le code.
          </p>
        </div>
        <div className="imp-actions">
          <button
            type="button"
            className="btn btn-dark gen-btn-lancer"
            onClick={telecharger}
            disabled={enCours !== ''}
          >
            {enCours === 'telechargement'
              ? 'Téléchargement…'
              : 'Télécharger Conception-GET-INJS.txt'}
          </button>
          <button
            type="button"
            className="btn btn-outline-primary"
            onClick={consulterEnLigne}
            disabled={enCours !== ''}
          >
            Consulter en ligne
          </button>
        </div>
      </div>

      <div className="row g-3">
        {/* ── Architecture en couches ─────────────────────────────────── */}
        <div className="col-lg-6">
          <div className="card h-100">
            <div className="card-body">
              <div className="imp-card-titre">Architecture en couches</div>
              <p className="imp-card-sous">Intégration au socle INJS2026</p>
              <div>
                {COUCHES.map((c) => (
                  <div className="conc-couche" key={c.nom}>
                    <div className="conc-couche-nom">{c.nom}</div>
                    <div>
                      <div className="conc-couche-pile">{c.pile}</div>
                      <div className="conc-couche-role">{c.role}</div>
                    </div>
                  </div>
                ))}
              </div>
              <p className="conc-note">
                Le module est intégré à l'application Django existante (app
                edts), sans second backend ni dépendance nouvelle ; le
                document de conception est versionné avec le code dans
                docs/getinjs/.
              </p>
            </div>
          </div>
        </div>

        {/* ── Algorithme de génération ────────────────────────────────── */}
        <div className="col-lg-6">
          <div className="card h-100">
            <div className="card-body">
              <div className="imp-card-titre">Algorithme de génération</div>
              <p className="imp-card-sous">Déterministe, sans randomisation</p>
              <ol className="conc-etapes">
                {ETAPES_ALGORITHME.map((etape, i) => (
                  <li key={i}>
                    <span className="conc-etape-num">{i + 1}</span>
                    <span>{etape}</span>
                  </li>
                ))}
              </ol>
              <p className="conc-note">
                Déterministe à paramètres égaux (tri stable) : aucune séance
                inventée, aucun placement en conflit — échec explicite plutôt
                que plan faux.
              </p>
            </div>
          </div>
        </div>

        {/* ── API du module ───────────────────────────────────────────── */}
        <div className="col-lg-6">
          <div className="card h-100">
            <div className="card-body pb-0">
              <div className="imp-card-titre">API du module</div>
              <p className="imp-card-sous">
                Contrats d'échange utilisés par l'interface
              </p>
            </div>
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0 imp-journal-table">
                <thead>
                  <tr><th>Méthode</th><th>Route</th><th>Rôle</th></tr>
                </thead>
                <tbody>
                  {ROUTES_API.map((r) => (
                    <tr key={r.route}>
                      <td>
                        <span className={
                          r.methode === 'GET' ? 'conc-methode conc-methode-get'
                            : 'conc-methode conc-methode-post'
                        }
                        >
                          {r.methode}
                        </span>
                      </td>
                      <td className="conc-route">{r.route}</td>
                      <td>{r.role}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* ── Modèle de données ───────────────────────────────────────── */}
        <div className="col-lg-6">
          <div className="card h-100">
            <div className="card-body pb-0">
              <div className="imp-card-titre">Modèle de données</div>
              <p className="imp-card-sous">Tables et responsabilités</p>
            </div>
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0 imp-journal-table">
                <thead>
                  <tr><th>Table</th><th>Contenu</th></tr>
                </thead>
                <tbody>
                  {TABLES.map((t) => (
                    <tr key={t.table}>
                      <td className="conc-route">{t.table}</td>
                      <td>{t.contenu}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* ── Commandes d'implémentation ──────────────────────────────── */}
        <div className="col-lg-6">
          <div className="card h-100">
            <div className="card-body">
              <div className="imp-card-titre">Commandes d'implémentation</div>
              <p className="imp-card-sous">Séquence exécutable de bout en bout</p>
              {COMMANDES.map((c) => (
                <div className="conc-commande" key={c.etape}>
                  <div className="conc-commande-etape">{c.etape}</div>
                  <code className="conc-commande-code">{c.commande}</code>
                  <div className="conc-commande-detail">{c.detail}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Exigences couvertes ─────────────────────────────────────── */}
        <div className="col-lg-6">
          <div className="card h-100">
            <div className="card-body">
              <div className="imp-card-titre">Exigences couvertes</div>
              <p className="imp-card-sous">Traçabilité de la demande</p>
              <ul className="conc-exigences">
                {EXIGENCES.map((e) => (
                  <li key={e.titre}>
                    <span className="conc-coche" aria-hidden="true">✓</span>
                    <span>
                      <strong>{e.titre}</strong> — {e.detail}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>

      <p className="imp-pied">
        GET INJS APP · module intégré à INJS2026 · Institut National de la
        Jeunesse et des Sports (INJS) - Marcory · Moteur LMD déterministe
      </p>
    </div>
  )
}
