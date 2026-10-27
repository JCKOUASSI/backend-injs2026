/** Dashboard habilitations — vue d'ensemble (couche IMPACT, additive).
 *
 * Tous les indicateurs proviennent de l'endpoint /api/habilitations/dashboard/
 * (calculés côté Django depuis les données CURP réelles) : rien n'est inventé
 * ni recalculé côté frontend. Les tuiles ne cliquent QUE vers les routes
 * qui existent déjà dans la console.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { dashboardHabilitations, messageErreur } from '@/services/habilitations'
import { EnChargement } from './partages'
import './habilitations.css'

function Tuile({ libelle, valeur, vers, testid }) {
  const corps = (
    <div className="hab-carte text-center h-100" data-testid={testid}>
      <div className="hab-tuile-valeur">{valeur}</div>
      <div className="hab-muted">{libelle}</div>
    </div>
  )
  return vers
    ? <Link to={vers} className="hab-lien-tuile">{corps}</Link>
    : corps
}

export default function Dashboard() {
  const [donnees, setDonnees] = useState(null)
  const [erreur, setErreur] = useState('')

  useEffect(() => {
    dashboardHabilitations()
      .then(setDonnees)
      .catch((e) => setErreur(messageErreur(e, 'Dashboard indisponible.')))
  }, [])

  if (erreur) {
    return (
      <section data-testid="ecran-dashboard-hab">
        <div className="hab-carte hab-avertissement" data-testid="dashboard-erreur">
          {erreur}
        </div>
      </section>
    )
  }
  if (!donnees) {
    return (
      <section data-testid="ecran-dashboard-hab">
        <EnChargement message="Chargement du dashboard…" />
      </section>
    )
  }

  const lignesModule = donnees.permissions.par_module
  const maxModule = Math.max(1, ...lignesModule.map((l) => l.total))

  // Lot A — « Alertes et actions prioritaires » : dérivées des données du
  // backend uniquement (clé `alertes`, absente des anciens mocks → repli 0).
  const a = donnees.alertes || {}
  const alertes = []
  if ((a.comptes_inactifs?.total ?? 0) > 0) {
    alertes.push({
      cle: 'comptes-inactifs',
      titre: `${a.comptes_inactifs.total} compte(s) sans activité depuis ${a.comptes_inactifs.seuil_jours} jours ou plus`,
      gravite: 'attention',
      icone: 'bi-hourglass-split',
      vers: '/administration/comptes',
    })
  }
  if ((a.comptes_prileges ?? 0) > 0) {
    alertes.push({
      cle: 'comptes-prileges',
      titre: `${a.comptes_prileges} compte(s) à privilèges élevés — à surveiller`,
      gravite: 'attention',
      icone: 'bi-shield-lock',
    })
  }
  if ((a.roles_sensibles_recemment_modifies?.total ?? 0) > 0) {
    const codes = a.roles_sensibles_recemment_modifies.codes || []
    const suffixe = codes.length > 0 ? ` (${codes.join(', ')})` : ''
    alertes.push({
      cle: 'roles-sensibles-modifies',
      titre: `${a.roles_sensibles_recemment_modifies.total} rôle(s) sensible(s) récemment modifié(s)${suffixe}`,
      gravite: 'attention',
      icone: 'bi-pencil-square',
      vers: '/administration/comptes/roles',
    })
  }
  if ((a.conflits_separation_taches?.total ?? 0) > 0) {
    const exemples = a.conflits_separation_taches.exemples || []
    const detail = exemples.length > 0
      ? ` — ex. : ${exemples.map((e) => e.roles.join(' + ')).join(' ; ')}`
      : ''
    alertes.push({
      cle: 'conflits-separation-taches',
      titre: `${a.conflits_separation_taches.total} conflit(s) de séparation des tâches détecté(s)${detail}`,
      gravite: 'critique',
      icone: 'bi-exclamation-octagon',
    })
  }
  if ((a.habilitations_echues ?? 0) > 0) {
    alertes.push({
      cle: 'habilitations-echues',
      titre: `${a.habilitations_echues} habilitation(s) expirée(s) encore marquée(s) active(s)`,
      gravite: 'critique',
      icone: 'bi-calendar-x',
      vers: '/administration/comptes/revue',
    })
  }
  if ((a.habilitations_expirantes ?? 0) > 0) {
    alertes.push({
      cle: 'habilitations-expirantes',
      titre: `${a.habilitations_expirantes} habilitation(s) arrivant à expiration dans 30 jours ou moins`,
      gravite: 'attention',
      icone: 'bi-calendar-event',
      vers: '/administration/comptes/revue',
    })
  }
  if ((a.provisionnement_en_attente ?? 0) > 0) {
    alertes.push({
      cle: 'provisionnement-attente',
      titre: `${a.provisionnement_en_attente} demande(s) de provisionnement en attente`,
      gravite: 'info',
      icone: 'bi-inbox',
      vers: '/administration/comptes/provisionnement',
    })
  }
  if ((a.demandes_acces_en_attente ?? 0) > 0) {
    alertes.push({
      cle: 'demandes-acces-attente',
      titre: `${a.demandes_acces_en_attente} demande(s) d'accès à décider`,
      gravite: 'attention',
      icone: 'bi-clipboard2-check',
      vers: '/administration/comptes/demandes',
    })
  }

  return (
    <section data-testid="ecran-dashboard-hab">
      <div className="hab-carte">
        <h2 className="h5">
          <i className="bi bi-speedometer2 me-2" />Dashboard des habilitations
        </h2>
        <p className="hab-muted mb-0">
          Vue d'ensemble dérivée des données CURP réelles. Date de référence :{' '}
          {donnees.date_reference}.
        </p>
      </div>

      <div className="hab-grille">
        <Tuile libelle="Comptes" valeur={donnees.comptes.total} vers="/administration/comptes" testid="dash-comptes" />
        <Tuile libelle="Comptes actifs" valeur={donnees.comptes.actifs} testid="dash-comptes-actifs" />
        <Tuile libelle="Comptes suspendus" valeur={donnees.comptes.par_statut?.SUSPENDU ?? 0} testid="dash-comptes-suspendus" />
        <Tuile libelle="Comptes verrouillés" valeur={donnees.comptes.par_statut?.VERROUILLE ?? 0} testid="dash-comptes-verrouilles" />
        <Tuile libelle="En attente d'activation" valeur={donnees.comptes.par_statut?.INVITE ?? 0} testid="dash-comptes-attente" />
        <Tuile libelle="Rôles" valeur={donnees.roles.total} vers="/administration/comptes/roles" testid="dash-roles" />
        <Tuile libelle="Rôles sensibles" valeur={donnees.roles.sensibles} vers="/administration/comptes/roles" testid="dash-roles-sensibles" />
        <Tuile libelle="Permissions" valeur={donnees.permissions.total} vers="/administration/comptes/permissions" testid="dash-permissions" />
        <Tuile libelle="Permissions sensibles" valeur={donnees.permissions.sensibles} vers="/administration/comptes/permissions" testid="dash-permissions-sensibles" />
        <Tuile libelle="Comptes privilégiés" valeur={donnees.comptes_privileges} testid="dash-privileges" />
        <Tuile libelle="Habilitations actives" valeur={donnees.habilitations?.actives ?? 0} testid="dash-hab-actives" />
        <Tuile libelle="Habilitations expirant ≤ 30 j" valeur={donnees.habilitations?.expirant_prochainement ?? 0} testid="dash-hab-expirantes" />
        <Tuile libelle="Dérogations actives" valeur={donnees.derogations.octrois + donnees.derogations.retraits} vers="/administration/comptes/derogations" testid="dash-derogations" />
        <Tuile libelle="Demandes d'accès en attente" valeur={donnees.demandes_acces?.en_attente ?? 0} vers="/administration/comptes/demandes" testid="dash-demandes" />
        <Tuile libelle="Délégations actives" valeur={donnees.delegations.actives} vers="/administration/comptes/delegations" testid="dash-delegations" />
        <Tuile libelle="Provisionnement en attente" valeur={donnees.provisionnement.propositions_en_attente} vers="/administration/comptes/provisionnement" testid="dash-provisionnement" />
      </div>

      <div className="hab-carte" data-testid="dash-alertes">
        <h4 className="h6">
          <i className="bi bi-exclamation-triangle me-2" />Alertes et actions prioritaires
        </h4>
        {alertes.length === 0 ? (
          <p className="hab-muted mb-0" data-testid="dash-alertes-vide">
            Aucune alerte prioritaire.
          </p>
        ) : (
          <ul className="hab-alerte-liste mb-0">
            {alertes.map((alerte) => (
              <li
                key={alerte.cle}
                className={`hab-alerte-item hab-alerte-${alerte.gravite}`}
                data-testid={`dash-alerte-${alerte.cle}`}
              >
                <i className={`bi ${alerte.icone} me-2`} aria-hidden="true" />
                <span>{alerte.titre}</span>
                {alerte.vers && (
                  <Link to={alerte.vers} className="hab-lien-impact ms-2">
                    <i className="bi bi-box-arrow-up-right" aria-hidden="true" /> voir
                  </Link>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="hab-carte">
        <h4 className="h6">Répartition des permissions par module</h4>
        <div data-testid="dash-par-module">
          {lignesModule.map((ligne) => (
            <div key={ligne.module} className="hab-barre-ligne">
              <span className="hab-barre-libelle">{ligne.module}</span>
              <span className="hab-barre-piste">
                <span
                  className="hab-barre"
                  style={{ width: `${Math.round((ligne.total / maxModule) * 100)}%` }}
                />
              </span>
              <span className="hab-barre-total">{ligne.total}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="hab-carte">
        <h4 className="h6">Dernières actions d'administration</h4>
        {donnees.dernieres_actions.length === 0 ? (
          <p className="hab-muted" data-testid="dash-journal-vide">
            Aucune action enregistrée.
          </p>
        ) : (
          <table className="hab-table" data-testid="dash-journal">
            <thead>
              <tr><th>#</th><th>Date</th><th>Action</th><th>Acteur</th><th>Objet</th></tr>
            </thead>
            <tbody>
              {donnees.dernieres_actions.map((e) => (
                <tr key={e.numero}>
                  <td>{e.numero}</td>
                  <td>{e.horodatage.replace('T', ' ').slice(0, 19)}</td>
                  <td>{e.type_libelle}</td>
                  <td>{e.acteur || '—'}</td>
                  <td>{e.objet_libelle || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}
