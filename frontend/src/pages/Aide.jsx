import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useMenuAutorise } from '../hooks/useMenuAutorise'
import { getUserRoles } from '../utils/roles'
import { LIBELLES_ROLES } from '../menu/arborescence'

/**
 * Aide en ligne — écran **réel** (aucune donnée fictive) : il décrit la
 * navigation, l'origine des droits affichés pour le compte connecté et renvoie
 * vers la documentation du dépôt (`docs/`).
 *
 * Le bloc « Mes droits » rend visible la règle structurante du produit :
 * l'interface n'accorde rien, elle projette ce que le backend a décidé
 * (règle S3). La source affichée (`CURP` ou capacités projetées) est celle qui
 * pilote réellement le filtrage du menu.
 */
export default function Aide() {
  const { user } = useAuth()
  const { gouverne, nombreCodes, sections, attributions } = useMenuAutorise()

  const roles = getUserRoles(user).map((r) => LIBELLES_ROLES[r] || r).join(', ') || user?.role || '—'
  const totalEntrees = sections.reduce((n, s) => n + (s.enfants ? s.enfants.length : 1), 0)

  return (
    <div>
      <h4 className="mb-3"><i className="bi bi-question-circle me-2 text-primary"></i>Aide</h4>

      <div className="row g-3">
        <div className="col-lg-6">
          <div className="card h-100">
            <div className="card-header"><strong>Se repérer</strong></div>
            <div className="card-body">
              <ul className="mb-0 ps-3">
                <li>La barre latérale est organisée en <strong>domaines</strong> (Scolarité, Formations, GET-INJS, Évaluations, Jurys, Diplômation, Finances, Stages, Personnel, Administration, Utilisateurs &amp; Accès, Statistiques, Référentiels, Audit).</li>
                <li>Cliquez sur un domaine pour <strong>déplier</strong> ses sous-menus ; le domaine contenant l'écran affiché reste ouvert.</li>
                <li>Votre état (domaines ouverts) est <strong>mémorisé</strong> sur ce navigateur.</li>
                <li>Le bouton <i className="bi bi-layout-sidebar"></i> en haut de page replie ou déplie la barre ; sur mobile, elle s'ouvre en panneau.</li>
              </ul>
            </div>
          </div>
        </div>

        <div className="col-lg-6">
          <div className="card h-100" data-testid="aide-mes-droits">
            <div className="card-header"><strong>Mes droits</strong></div>
            <div className="card-body">
              <dl className="row mb-0 small">
                <dt className="col-6">Compte</dt>
                <dd className="col-6">{user?.username || '—'}</dd>
                <dt className="col-6">Rôle affiché</dt>
                <dd className="col-6">{roles}</dd>
                <dt className="col-6">Source des droits du menu</dt>
                <dd className="col-6">
                  {gouverne
                    ? <span className="badge text-bg-success">Permissions effectives CURP ({nombreCodes})</span>
                    : <span className="badge text-bg-secondary">Capacités projetées (legacy)</span>}
                </dd>
                <dt className="col-6">Entrées affichées</dt>
                <dd className="col-6">{totalEntrees} sur {sections.length} domaine(s)</dd>
                {attributions.length > 0 && (
                  <>
                    <dt className="col-6">Attributions CURP actives</dt>
                    <dd className="col-6">
                      {attributions.map((a) => a.role?.libelle || a.role?.code || a.role_code || '—').join(', ')}
                    </dd>
                  </>
                )}
              </dl>
              <p className="text-muted small mt-3 mb-0">
                <i className="bi bi-info-circle me-1"></i>
                Le menu <strong>masque</strong> ce que vous ne détenez pas ; il
                n'accorde jamais rien. Chaque action repasse par le serveur, qui
                applique ses propres contrôles et journalise les gestes sensibles.
              </p>
            </div>
          </div>
        </div>

        <div className="col-lg-6">
          <div className="card h-100">
            <div className="card-header"><strong>Accès rapides</strong></div>
            <div className="card-body">
              <div className="d-flex flex-wrap gap-2">
                <Link className="btn btn-sm btn-outline-primary" to="/profile">
                  <i className="bi bi-person-circle me-1"></i>Mon profil
                </Link>
                <Link className="btn btn-sm btn-outline-primary" to="/dashboard">
                  <i className="bi bi-speedometer2 me-1"></i>Tableau de bord
                </Link>
                <Link className="btn btn-sm btn-outline-primary" to="/statistiques">
                  <i className="bi bi-bar-chart-line me-1"></i>Statistiques
                </Link>
                <Link className="btn btn-sm btn-outline-primary" to="/audit/journal">
                  <i className="bi bi-journal-text me-1"></i>Journal d'audit
                </Link>
                <Link className="btn btn-sm btn-outline-secondary" to="/administration/comptes">
                  <i className="bi bi-shield-lock me-1"></i>Console des comptes
                </Link>
              </div>
            </div>
          </div>
        </div>

        <div className="col-lg-6">
          <div className="card h-100">
            <div className="card-header"><strong>Documentation du produit</strong></div>
            <div className="card-body small">
              <ul className="mb-2 ps-3">
                <li><code>docs/architecture/IAM.md</code> — identité, comptes et contrôle d'accès</li>
                <li><code>docs/security/RBAC.md</code> — rôles, niveaux N0–N4, permissions, périmètres</li>
                <li><code>docs/administration/utilisateurs.md</code> — guide d'exploitation des comptes</li>
                <li><code>docs/audit/permissions.md</code> — audit des droits et écarts connus</li>
                <li><code>docs/API_ENDPOINTS.md</code> — référence des endpoints REST</li>
              </ul>
              <p className="text-muted mb-0">
                Schéma d'API vivant : <code>/api/schema/</code> (OpenAPI) et
                <code> /api/docs/</code> (Swagger UI).
              </p>
            </div>
          </div>
        </div>

        <div className="col-12">
          <div className="card">
            <div className="card-header"><strong>En cas de difficulté</strong></div>
            <div className="card-body small mb-0">
              <ul className="mb-0 ps-3">
                <li><strong>Un menu attendu n'apparaît pas</strong> : le droit correspondant n'est pas attribué. Un administrateur d'habilitation peut l'ajouter (console <Link to="/administration/comptes">Comptes utilisateurs</Link>), avec motif et, pour un rôle sensible, seconde signature.</li>
                <li><strong>« Accès non autorisé » sur un écran</strong> : même cause — l'URL a été saisie directement. Le serveur aurait refusé l'appel de toute façon.</li>
                <li><strong>« Données indisponibles »</strong> : l'écran affiche le message renvoyé par le serveur et l'endpoint appelé, ce qui permet un diagnostic immédiat.</li>
                <li><strong>Compte bloqué après plusieurs échecs</strong> : verrouillage temporaire (5 échecs / 15 minutes) ; attendez l'échéance ou demandez un déverrouillage.</li>
                <li><strong>Double authentification</strong> : armement puis confirmation depuis <Link to="/profile">Mon profil</Link> ; obligatoire pour les rôles sensibles si la politique l'impose.</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
