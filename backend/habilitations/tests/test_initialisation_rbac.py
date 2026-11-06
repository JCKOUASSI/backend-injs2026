"""Initialisation RBAC : prévisualisation, initialisation, mécanismes réels.

Couvre les quinze catégories attendues :

 1. création idempotente d'un compte RBAC
 2. liaison utilisateur ↔ compte
 3. préservation du superutilisateur existant
 4. absence d'attribution automatique (aucun rôle déduit de ``User.role``)
 5. absence d'élargissement de périmètre
 6. conflits de périmètre
 7. rôles sensibles (motif obligatoire, seconde signature)
 8. double validation et séparation demandeur / validateur
 9. révocation
10. suspension
11. expiration
12. MFA lorsque requis
13. incompatibilités entre rôles
14. journalisation
15. contrôles d'accès API et comportement des drapeaux

Règle de méthode : **on teste le mécanisme réel, pas la présence d'un champ**.
Lorsqu'une règle n'est pas appliquée effectivement (simple attribut de modèle),
le test constate le comportement observé et l'anomalie est documentée dans
``docs/curp/07-initialisation-rbac.md`` au lieu d'être masquée.

Les tests s'exécutent sur une base de test isolée ; aucune base de production
n'est touchée (aucune commande ne pointe vers elle).
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    DemandeAcces,
    DelegationHabilitation,
    JournalHabilitation,
    Perimetre,
    PermissionAttribuee,
    RoleMetier,
)
from habilitations.services.initialisation_rbac import (
    A_PERIMETRE_LOCAL,
    A_PERIMETRE_PLUS_LARGE,
    DRAPEAU_MODULE_UTILISATEURS,
    DRAPEAU_SOCLE,
    analyser_role,
    appliquer_rapport,
    comparer_catalogue_fichier,
    construire_rapport,
    ecriture_autorisee,
    etat_drapeaux,
)

from .helpers import (
    creer_attribution,
    creer_compte,
    creer_perimetre_secretariat,
    creer_permission,
    creer_role,
    creer_user,
)

User = get_user_model()

#: Application sans dépendre des drapeaux (fermés par défaut sous test).
APPLY = ['rbac_initialisation', '--apply', '--ignorer-drapeaux']


def appliquer(**kwargs):
    sortie = StringIO()
    options = {'stdout': sortie, 'stderr': StringIO(), **kwargs}
    call_command(*APPLY, **options)
    return sortie.getvalue()


class BaseRbac(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role_global = creer_role(
            code='ARCHIVISTE', libelle='Archiviste', niveau_defaut='L',
            perimetre_defaut=Perimetre.Type.INJS_ENTIER)
        cls.role_sensible = creer_role(
            code='ADMIN_SYSTEME', libelle='Administrateur système', niveau_defaut='E',
            perimetre_defaut=Perimetre.Type.INJS_ENTIER, sensible=True)
        cls.role_local = creer_role(
            code='SCOLARITE', libelle='Scolarité', niveau_defaut='L',
            perimetre_defaut=Perimetre.Type.SECRETARIAT)


# ══ 1. Création idempotente ═════════════════════════════════════════════════
class CreationIdempotenteTests(BaseRbac):
    def test_deux_applications_ne_creent_qu_un_compte(self):
        creer_user(username='idem-1', role_existant='ARCHIVE')
        appliquer()
        self.assertEqual(CompteUtilisateur.objects.count(), 1)
        appliquer()
        self.assertEqual(CompteUtilisateur.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1, 'aucun utilisateur dupliqué')

    def test_previsualisation_par_defaut_n_ecrit_rien(self):
        creer_user(username='idem-2', role_existant='ARCHIVE')
        call_command('rbac_initialisation', stdout=StringIO())
        self.assertEqual(CompteUtilisateur.objects.count(), 0)
        self.assertEqual(AttributionRole.objects.count(), 0)
        self.assertEqual(JournalHabilitation.objects.count(), 0)

    def test_echec_isole_ne_supprime_rien(self):
        """Une erreur sur un compte n'annule pas les autres (aucune suppression)."""
        creer_user(username='idem-ok', role_existant='ARCHIVE')
        creer_user(username='idem-ko', role_existant='ARCHIVE')
        rapport = construire_rapport()
        rapport.comptes['a_creer'] = ['idem-ok', 'fantome', 'idem-ko']
        appliquer_rapport(rapport, acteur=None)
        self.assertEqual(CompteUtilisateur.objects.count(), 2)
        self.assertTrue(any('fantome' in r for r in rapport.realise))


# ══ 2. Liaison utilisateur ↔ compte ═════════════════════════════════════════
class LiaisonCompteTests(BaseRbac):
    def test_profil_rattache_au_bon_utilisateur(self):
        user = creer_user(username='liaison-1', role_existant='ARCHIVE')
        appliquer()
        compte = CompteUtilisateur.objects.get(user=user)
        self.assertEqual(user.profil_habilitation.pk, compte.pk)
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)
        self.assertTrue(compte.motif_statut)


# ══ 3. Préservation du superutilisateur ═════════════════════════════════════
class SuperutilisateurTests(BaseRbac):
    def _superuser(self, nom='root-existant'):
        return User.objects.create_superuser(
            username=nom, password='Root#2026x', role='ADMIN')

    def test_superutilisateur_exclus_par_defaut(self):
        self._superuser()
        appliquer()
        self.assertFalse(
            CompteUtilisateur.objects.filter(user__username='root-existant').exists())

    def test_superutilisateur_inclus_sans_attribution(self):
        self._superuser()
        appliquer(inclure_superutilisateurs=True)
        compte = CompteUtilisateur.objects.get(user__username='root-existant')
        self.assertEqual(compte.attributions.count(), 0)

    def test_compte_django_du_superutilisateur_intact(self):
        su = self._superuser()
        avant = (su.is_superuser, su.role, su.password, su.is_active)
        appliquer(inclure_superutilisateurs=True)
        su.refresh_from_db()
        self.assertEqual((su.is_superuser, su.role, su.password, su.is_active), avant)

    def test_rapport_liste_le_superutilisateur(self):
        self._superuser()
        rapport = construire_rapport()
        self.assertIn('root-existant', rapport.utilisateurs['superutilisateurs'])


# ══ 4. Absence d'attribution automatique ════════════════════════════════════
class AbsenceAttributionAutoTests(BaseRbac):
    def test_aucune_attribution_apres_initialisation(self):
        for role in ('ADMIN', 'SECRETARIAT', 'FINANCE', 'ENCADRANT'):
            creer_user(username=f'auto-{role}', role_existant=role)
        appliquer()
        self.assertEqual(AttributionRole.objects.count(), 0,
                         'aucun rôle n’est déduit du champ historique User.role')

    def test_rapport_annonce_zero_attribution(self):
        creer_user(username='auto-2', role_existant='ADMIN')
        rapport = construire_rapport()
        self.assertTrue(any('Aucune attribution de rôle créée' in o
                            for o in rapport.operations))


# ══ 5. Absence d'élargissement de périmètre ═════════════════════════════════
class ElargissementPerimetreTests(TestCase):
    def test_initialisation_ne_cree_aucun_perimetre(self):
        creer_user(username='elarg-1', role_existant='ADMIN')
        appliquer()
        # Aucune attribution → aucun périmètre posé par l'initialisation.
        self.assertEqual(AttributionRole.objects.count(), 0)

    def test_perimetre_local_jamais_invente(self):
        role = creer_role(code='R_LOCAL', perimetre_defaut=Perimetre.Type.SECRETARIAT)
        analyse = analyser_role(role)
        self.assertTrue(any(A_PERIMETRE_LOCAL in a for a in analyse['anomalies']))
        self.assertNotIn(Perimetre.Type.INJS_ENTIER, analyse['plafonds_permissions']
                         + [analyse['perimetre_defaut']] or [])


# ══ 6. Conflits de périmètre ════════════════════════════════════════════════
class ConflitPerimetreTests(TestCase):
    def test_plafond_plus_etroit_est_signale(self):
        role = creer_role(code='R_LARGE', perimetre_defaut=Perimetre.Type.INJS_ENTIER)
        permission = creer_permission(code_module='scol', ressource='dossier',
                                      action='consulter')
        permission.portee_maximale = Perimetre.Type.SECRETARIAT
        permission.save(update_fields=['portee_maximale'])
        role.permissions.add(permission)
        analyse = analyser_role(role)
        self.assertTrue(any(A_PERIMETRE_PLUS_LARGE in a for a in analyse['anomalies']))

    def test_perimetre_declare_conserve_quand_le_plafond_est_plus_large(self):
        role = creer_role(code='R_ETROIT', perimetre_defaut=Perimetre.Type.SECRETARIAT)
        permission = creer_permission(code_module='scol', ressource='note',
                                      action='consulter')
        permission.portee_maximale = Perimetre.Type.INJS_ENTIER
        permission.save(update_fields=['portee_maximale'])
        role.permissions.add(permission)
        analyse = analyser_role(role)
        self.assertEqual(analyse['perimetre_defaut'], Perimetre.Type.SECRETARIAT)

    def test_attribution_sans_perimetre_secretariat_est_signalee(self):
        """Règle appliquée (``contraintes()``) et non simple attribut."""
        role = creer_role(code='R_SECR', perimetre_defaut=Perimetre.Type.SECRETARIAT)
        compte = creer_compte(user=creer_user(username='cp-1'))
        attribution = creer_attribution(compte, role)
        self.assertIn('PERIMETRE_SECRETARIAT_MANQUANT', attribution.contraintes())
        from .helpers import secretariat
        attribution.perimetres.add(creer_perimetre_secretariat(secretariat()))
        self.assertNotIn('PERIMETRE_SECRETARIAT_MANQUANT', attribution.contraintes())


# ══ 7. Rôles sensibles ══════════════════════════════════════════════════════
class RoleSensibleTests(BaseRbac):
    def test_role_sensible_actif_sans_signature_est_detecte(self):
        compte = creer_compte(user=creer_user(username='sens-1'))
        creer_attribution(compte, self.role_sensible)
        rapport = construire_rapport()
        self.assertEqual(
            rapport.attributions['sensibles_actives_sans_seconde_signature'],
            ['sens-1 → ADMIN_SYSTEME'])

    def test_motif_est_exige_par_les_serializeurs_de_decision(self):
        """Règle appliquée : motif court refusé par le validateur d'API."""
        from habilitations.api.serializers_admin import PropositionDecisionSerializer
        self.assertFalse(PropositionDecisionSerializer(data={'motif': 'court'}).is_valid())
        self.assertTrue(
            PropositionDecisionSerializer(data={'motif': 'Motif conforme 2026'}).is_valid())

    def test_le_modele_n_empeche_pas_un_motif_vide(self):
        """Constat documenté : ``motif`` n'est pas contraint au niveau base.

        La règle « motif obligatoire » est appliquée par les services et
        l'API, pas par une contrainte de schéma — d'où l'intérêt du test
        précédent plutôt que d'un simple ``assert`` sur le champ.
        """
        role = creer_role(code='R_MOTIF', perimetre_defaut=Perimetre.Type.INJS_ENTIER)
        compte = creer_compte(user=creer_user(username='motif-1'))
        attribution = AttributionRole.objects.create(
            compte=compte, role=role, niveau_effectif=role.niveau_defaut,
            statut=AttributionRole.Statut.ACTIVE, motif='')
        self.assertEqual(attribution.motif, '')


# ══ 8. Double validation et séparation des responsabilités ══════════════════
class DoubleValidationTests(BaseRbac):
    def test_un_demandeur_ne_valide_pas_sa_demande(self):
        from habilitations.services.demandes_acces import (
            appliquer_transition,
            creer_demande,
        )
        user = creer_user(username='dv-1', role_existant='ADMIN')
        compte = creer_compte(user=user)
        demande = creer_demande(
            user, type_demande=DemandeAcces.Type.ATTRIBUTION_ROLE,
            justification='Besoin métier documenté', compte_cible=compte,
            role=self.role_sensible)
        appliquer_transition(demande, DemandeAcces.Statut.SOUMISE, acteur=user,
                             motif_decision='Dépôt de la demande.')
        with self.assertRaises(ValueError):
            appliquer_transition(demande, DemandeAcces.Statut.APPROUVEE, acteur=user,
                                 motif_decision='Auto-approbation interdite.')

    def test_un_tiers_peut_approuver(self):
        from habilitations.services.demandes_acces import (
            appliquer_transition,
            creer_demande,
        )
        demandeur = creer_user(username='dv-dem', role_existant='ADMIN')
        validateur = creer_user(username='dv-val', role_existant='ADMIN')
        compte = creer_compte(user=demandeur)
        demande = creer_demande(
            demandeur, type_demande=DemandeAcces.Type.ATTRIBUTION_ROLE,
            justification='Besoin métier documenté', compte_cible=compte,
            role=self.role_sensible)
        appliquer_transition(demande, DemandeAcces.Statut.SOUMISE, acteur=demandeur,
                             motif_decision='Dépôt.')
        appliquer_transition(demande, DemandeAcces.Statut.APPROUVEE, acteur=validateur,
                             motif_decision='Validation par un tiers habilité.')
        demande.refresh_from_db()
        self.assertEqual(demande.statut, DemandeAcces.Statut.APPROUVEE)
        self.assertEqual(demande.approbateur, validateur)


# ══ 9 et 10. Révocation et suspension ═══════════════════════════════════════
class RevocationSuspensionTests(BaseRbac):
    def test_initialisation_ne_revoque_jamais(self):
        compte = creer_compte(user=creer_user(username='rev-1'))
        active = creer_attribution(compte, self.role_global)
        appliquer()
        active.refresh_from_db()
        self.assertEqual(active.statut, AttributionRole.Statut.ACTIVE)
        self.assertEqual(active.motif_revocation, '')

    def test_suspension_par_transition_legale(self):
        from habilitations.services.comptes_admin import changer_statut
        compte = creer_compte(user=creer_user(username='susp-1', role_existant='ARCHIVE'))
        changer_statut(compte, None, 'suspendre', 'Suspension de test.')
        compte.refresh_from_db()
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.SUSPENDU)
        self.assertFalse(compte.user.is_active)

    def test_transition_illegale_refusee(self):
        from habilitations.services.comptes_admin import ErreurConsole, changer_statut
        compte = creer_compte(user=creer_user(username='susp-2', role_existant='ARCHIVE'))
        changer_statut(compte, None, 'suspendre', 'Suspension.')
        with self.assertRaises(ErreurConsole):
            changer_statut(compte, None, 'suspendre', 'Seconde suspension illégale.')


# ══ 11. Expiration ══════════════════════════════════════════════════════════
class ExpirationTests(BaseRbac):
    def test_attribution_echue_n_est_plus_active(self):
        compte = creer_compte(user=creer_user(username='exp-1'))
        hier = timezone.localdate() - timezone.timedelta(days=1)
        attribution = creer_attribution(compte, self.role_global, date_fin=hier)
        self.assertFalse(attribution.est_active())

    def test_service_expirer_termes_traite_les_echeances(self):
        from habilitations.services.expirations import expirer_termes
        compte = creer_compte(user=creer_user(username='exp-2'))
        hier = timezone.localdate() - timezone.timedelta(days=1)
        attribution = creer_attribution(compte, self.role_global, date_fin=hier)
        expirer_termes()
        attribution.refresh_from_db()
        self.assertNotEqual(attribution.statut, AttributionRole.Statut.ACTIVE)


# ══ 12. MFA lorsque requis ══════════════════════════════════════════════════
class MfaTests(BaseRbac):
    def test_mfa_non_requis_tant_que_le_drapeau_est_ferme(self):
        from authentication.connexion_sure import etat_mfa
        compte = creer_compte(user=creer_user(username='mfa-1'))
        creer_attribution(compte, self.role_sensible)
        self.assertEqual(etat_mfa(compte.user), 'aucun')

    def test_mfa_obligatoire_sensible_suit_le_drapeau(self):
        from habilitations.services import drapeaux
        self.assertFalse(drapeaux.mfa_obligatoire_sensibles_active())
        self.assertFalse(drapeaux.mfa_active())


# ══ 13. Incompatibilités entre rôles ════════════════════════════════════════
class IncompatibiliteTests(TestCase):
    def test_incompatibilite_declaree_puis_detectee(self):
        from habilitations.services.validations import declarer_incompatibilite
        role_a = creer_role(code='R_INA', perimetre_defaut=Perimetre.Type.INJS_ENTIER)
        role_b = creer_role(code='R_INB', perimetre_defaut=Perimetre.Type.INJS_ENTIER)
        declarer_incompatibilite(role_a, role_b)
        compte = creer_compte(user=creer_user(username='inc-1'))
        creer_attribution(compte, role_a)
        seconde = creer_attribution(compte, role_b)
        self.assertIn('ROLES_INCOMPATIBLES', seconde.contraintes())


# ══ 14. Journalisation ══════════════════════════════════════════════════════
class JournalisationTests(BaseRbac):
    def test_chaque_compte_cree_est_journalise(self):
        creer_user(username='jrn-1', role_existant='ARCHIVE')
        creer_user(username='jrn-2', role_existant='ARCHIVE')
        appliquer()
        entrees = list(JournalHabilitation.objects.order_by('numero'))
        self.assertEqual(len(entrees), 2)
        self.assertEqual([e.numero for e in entrees], sorted(e.numero for e in entrees))
        self.assertTrue(all(e.empreinte for e in entrees))
        self.assertTrue(all(
            e.nouvelle_valeur.get('origine') == 'INITIALISATION_RBAC' for e in entrees))

    def test_journal_vide_en_previsualisation(self):
        creer_user(username='jrn-3', role_existant='ARCHIVE')
        call_command('rbac_initialisation', stdout=StringIO())
        self.assertEqual(JournalHabilitation.objects.count(), 0)


# ══ 15. Contrôles d'accès API et drapeaux ═══════════════════════════════════
class ControleAccesApiTests(TestCase):
    def test_endpoints_habilitations_proteges(self):
        for url in ('/api/habilitations/comptes/', '/api/habilitations/roles/',
                    '/api/habilitations/mes-acces/'):
            reponse = self.client.get(url)
            self.assertIn(reponse.status_code, (401, 403),
                          f'{url} doit refuser un anonyme (reçu {reponse.status_code})')

    def test_endpoints_authentication_toujours_servis(self):
        self.client.force_login(creer_user(username='api-1', role_existant='ADMIN'))
        for url in ('/api/auth/capabilities/', '/api/auth/users/'):
            self.assertNotEqual(self.client.get(url).status_code, 404,
                                f'{url} doit rester servi')


class DrapeauxTests(TestCase):
    def test_ecriture_refusee_sans_drapeaux(self):
        autorise, motifs = ecriture_autorisee()
        self.assertFalse(autorise)
        self.assertTrue(motifs)

    def test_contournement_explicite_autorise(self):
        autorise, _ = ecriture_autorisee(ignorer_drapeaux=True)
        self.assertTrue(autorise)

    def test_commande_echoue_sans_les_drapeaux(self):
        creer_user(username='flag-1', role_existant='ARCHIVE')
        with self.assertRaises(CommandError):
            call_command('rbac_initialisation', '--apply', stdout=StringIO())
        self.assertEqual(CompteUtilisateur.objects.count(), 0)

    def test_etat_des_deux_drapeaux(self):
        etats = etat_drapeaux()
        self.assertIn(DRAPEAU_SOCLE, etats)
        self.assertIn(DRAPEAU_MODULE_UTILISATEURS, etats)


# ══ Rapport : contenu de la prévisualisation ════════════════════════════════
class RapportPreviewTests(BaseRbac):
    def test_rapport_distingue_utilisateurs_comptes_attributions(self):
        creer_user(username='rap-1', role_existant='ARCHIVE')
        creer_user(username='rap-2', role_existant='ARCHIVE', is_active=False)
        compte = creer_compte(user=creer_user(username='rap-3'))
        creer_attribution(compte, self.role_global)
        rapport = construire_rapport()
        self.assertEqual(rapport.utilisateurs['total'], 3)
        self.assertEqual(rapport.utilisateurs['actifs'], 2)
        self.assertIn('rap-2', rapport.utilisateurs['inactifs'])
        self.assertEqual(rapport.comptes['existants'], 1)
        self.assertEqual(rapport.comptes['manquants'], 2)
        self.assertEqual(rapport.attributions['total'], 1)
        self.assertEqual(rapport.attributions['par_statut'].get('ACTIVE'), 1)

    def test_compte_desynchronise_signeale(self):
        user = creer_user(username='desync-1', role_existant='ARCHIVE', is_active=False)
        creer_compte(user=user, statut=CompteUtilisateur.Statut.ACTIF)
        rapport = construire_rapport()
        self.assertTrue(any('desync-1' in c for c in rapport.coherence))

    def test_catalogue_concordant_avec_le_fichier(self):
        # Règle R5 : la base de test n'est pas peuplée par la migration ; on
        # charge explicitement le référentiel (idempotent) pour prouver
        # l'équivalence fichier ↔ base.
        from habilitations.referentiel.chargement import charger_referentiel
        charger_referentiel()
        comparaison = comparer_catalogue_fichier()
        self.assertEqual(comparaison['codes_absents_de_la_base'],
                         comparaison['codes_absents_du_fichier'])
        self.assertEqual(comparaison['attributs_divergents'], [])
        self.assertEqual(comparaison['roles_fichier'], comparaison['roles_base'])
        self.assertEqual(comparaison['sensibles_fichier'], comparaison['sensibles_base'])

    def test_rapport_serialisable(self):
        creer_user(username='rap-json', role_existant='ARCHIVE')
        donnees = construire_rapport().vers_dict()
        self.assertEqual(donnees['comptes']['manquants'], 1)
        self.assertIn('utilisateurs', donnees)
        self.assertIn('operations', donnees)
