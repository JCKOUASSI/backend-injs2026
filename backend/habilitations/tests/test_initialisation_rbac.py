"""Initialisation RBAC contrôlée — prévisualisation, idempotence, garde-fous.

Couvre les dix points exigés par la préparation à la mise en service :
création idempotente, liaison utilisateur ↔ compte, préservation du
superutilisateur, absence d'attribution automatique non autorisée, conflits
de périmètre, rôles sensibles, double validation, révocations, journalisation
et contrôles d'accès API.

Aucun test n'écrit dans une base de production : tout se joue dans la base de
test Django, créée et détruite par le lanceur de tests.
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    JournalHabilitation,
    Perimetre,
    RoleMetier,
)
from habilitations.services.initialisation_rbac import (
    A_PERIMETRE_LOCAL,
    A_ROLE_SENSIBLE,
    A_SUPERUTILISATEUR,
    DRAPEAU_MODULE_UTILISATEURS,
    DRAPEAU_SOCLE,
    analyser_role,
    appliquer_plan,
    construire_plan,
    ecriture_autorisee,
    etat_drapeaux,
)

from .helpers import creer_attribution, creer_compte, creer_permission, creer_role, creer_user

User = get_user_model()

#: Applique sans dépendre des drapeaux (fermés par défaut dans les tests).
APPLIQUER = {'appliquer': True, 'ignorer_drapeaux': True}


class BaseInitialisation(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Deux rôles posables seuls (périmètre global), un sensible, un local.
        cls.role_global = creer_role(
            code='ARCHIVISTE', libelle='Archiviste',
            niveau_defaut='L', perimetre_defaut=Perimetre.Type.INJS_ENTIER,
        )
        cls.role_sensible = creer_role(
            code='ADMIN_SYSTEME', libelle='Administrateur système',
            niveau_defaut='E', perimetre_defaut=Perimetre.Type.INJS_ENTIER,
            sensible=True,
        )
        cls.role_local = creer_role(
            code='AGENT_INSCRIPTIONS', libelle='Agent inscriptions',
            niveau_defaut='L', perimetre_defaut=Perimetre.Type.SECRETARIAT,
        )


# ── 1. Création idempotente ─────────────────────────────────────────────────
class CreationIdempotenteTests(BaseInitialisation):
    def test_deux_passages_ne_creent_qu_un_compte(self):
        creer_user(username='idem-1', role_existant='ARCHIVE')
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        self.assertEqual(CompteUtilisateur.objects.count(), 1)
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        self.assertEqual(CompteUtilisateur.objects.count(), 1)
        self.assertEqual(
            AttributionRole.objects.filter(statut=AttributionRole.Statut.ACTIVE).count(), 1,
            "le second passage ne doit pas dupliquer l'attribution",
        )

    def test_simulation_n_ecrit_rien(self):
        creer_user(username='idem-2', role_existant='ARCHIVE')
        call_command('initialiser_rbac', stdout=StringIO())  # sans --appliquer
        self.assertEqual(CompteUtilisateur.objects.count(), 0)
        self.assertEqual(AttributionRole.objects.count(), 0)

    def test_previsualisation_n_ecrit_jamais(self):
        creer_user(username='idem-3', role_existant='ARCHIVE')
        call_command('previsualiser_initialisation_rbac', stdout=StringIO())
        self.assertEqual(CompteUtilisateur.objects.count(), 0)
        self.assertEqual(JournalHabilitation.objects.count(), 0)


# ── 2. Liaison utilisateur ↔ compte ─────────────────────────────────────────
class LiaisonCompteTests(BaseInitialisation):
    def test_profil_rattache_au_bon_utilisateur(self):
        user = creer_user(username='liaison-1', role_existant='ARCHIVE')
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        compte = CompteUtilisateur.objects.get(user=user)
        self.assertEqual(user.profil_habilitation, compte)
        attribution = compte.attributions.get(role=self.role_global)
        self.assertEqual(attribution.statut, AttributionRole.Statut.ACTIVE)
        # Périmètre posé et borné au périmètre déclaré du rôle.
        self.assertEqual(
            list(attribution.perimetres.values_list('type', flat=True)),
            [Perimetre.Type.INJS_ENTIER],
        )

    def test_attribution_porte_le_niveau_du_role(self):
        user = creer_user(username='liaison-2', role_existant='ARCHIVE')
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        attribution = AttributionRole.objects.get(compte__user=user)
        self.assertEqual(attribution.niveau_effectif, self.role_global.niveau_defaut)
        self.assertTrue(attribution.motif, "le motif d'attribution est obligatoire")


# ── 3. Préservation du superutilisateur ─────────────────────────────────────
class SuperutilisateurTests(BaseInitialisation):
    def _superuser(self):
        return User.objects.create_superuser(
            username='root-existant', password='Root#2026x', role='ADMIN',
        )

    def test_superutilisateur_exclus_du_plan(self):
        self._superuser()
        plan = construire_plan()
        self.assertEqual(plan.lignes, [])
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        self.assertFalse(
            CompteUtilisateur.objects.filter(user__username='root-existant').exists())

    def test_superutilisateur_inclus_sans_attribution(self):
        self._superuser()
        call_command('initialiser_rbac', **APPLIQUER,
                     inclure_superutilisateurs=True, stdout=StringIO())
        compte = CompteUtilisateur.objects.get(user__username='root-existant')
        self.assertEqual(compte.attributions.count(), 0,
                         "aucune auto-élévation d'un superutilisateur")
        self.assertTrue(compte.user.is_superuser)

    def test_compte_django_du_superutilisateur_est_intact(self):
        su = self._superuser()
        avant = (su.is_superuser, su.role, su.password, su.is_active)
        call_command('initialiser_rbac', **APPLIQUER,
                     inclure_superutilisateurs=True, stdout=StringIO())
        su.refresh_from_db()
        self.assertEqual((su.is_superuser, su.role, su.password, su.is_active), avant)

    def test_anomalie_superutilisateur_signalee(self):
        self._superuser()
        plan = construire_plan(inclure_superutilisateurs=True)
        self.assertTrue(any(
            A_SUPERUTILISATEUR in a for a in plan.lignes[0].anomalies))


# ── 4. Absence d'attribution automatique non autorisée ──────────────────────
class AbsenceAttributionAutoTests(BaseInitialisation):
    def test_role_sensible_jamais_active(self):
        creer_user(username='sensible-1', role_existant='ADMIN')
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        attribution = AttributionRole.objects.get(role=self.role_sensible)
        self.assertEqual(attribution.statut, AttributionRole.Statut.PROPOSEE)
        self.assertIsNone(attribution.valide_par,
                          "l'initialisation ne pose jamais la seconde signature")
        self.assertIsNone(attribution.date_validation)

    def test_role_a_perimetre_local_non_cree(self):
        creer_user(username='local-1', role_existant='SECRETARIAT')
        plan = construire_plan()
        self.assertTrue(any(
            A_PERIMETRE_LOCAL in a
            for ligne in plan.lignes for prevu in ligne.roles for a in prevu.anomalies))
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        self.assertFalse(
            AttributionRole.objects.filter(role=self.role_local).exists(),
            "un périmètre local ne peut pas être inventé par l'initialisation",
        )



# ── 5. Conflits de périmètre ────────────────────────────────────────────────
class ConflitPerimetreTests(TestCase):
    def test_perimetre_local_bloque_et_signale(self):
        role = creer_role(code='R_LOCAL', perimetre_defaut=Perimetre.Type.FORMATION)
        prevu = analyser_role(role)
        self.assertFalse(prevu.perimetre_posable)
        self.assertTrue(any(A_PERIMETRE_LOCAL in a for a in prevu.anomalies))

    def test_perimetre_global_posable(self):
        role = creer_role(code='R_GLOBAL', perimetre_defaut=Perimetre.Type.INJS_ENTIER)
        prevu = analyser_role(role)
        self.assertTrue(prevu.perimetre_posable)

    def test_perimetre_declare_plus_large_que_le_plafond_est_ramene(self):
        role = creer_role(code='R_LARGE', perimetre_defaut=Perimetre.Type.INJS_ENTIER)
        permission = creer_permission(
            code_module='scol', ressource='dossier', action='consulter')
        permission.portee_maximale = Perimetre.Type.SECRETARIAT
        permission.save(update_fields=['portee_maximale'])
        role.permissions.add(permission)
        prevu = analyser_role(role)
        self.assertFalse(prevu.perimetre_posable,
                         "le périmètre est ramené au plafond (SECRETARIAT) → local")
        self.assertTrue(any('PERIMETRE_DEFAUT_PLUS_LARGE' in a for a in prevu.anomalies))

    def test_aucun_elargissement_du_perimetre_du_role(self):
        role = creer_role(code='R_ETROIT', perimetre_defaut=Perimetre.Type.SECRETARIAT)
        permission = creer_permission(
            code_module='scol', ressource='note', action='consulter')
        permission.portee_maximale = Perimetre.Type.INJS_ENTIER
        permission.save(update_fields=['portee_maximale'])
        role.permissions.add(permission)
        prevu = analyser_role(role)
        self.assertEqual(
            prevu.perimetre_defaut, Perimetre.Type.SECRETARIAT,
            "un plafond plus large n'autorise pas à élargir le périmètre déclaré",
        )


# ── 6. Rôles sensibles : motif, signature, journal ──────────────────────────
class RoleSensibleTests(BaseInitialisation):
    def test_proposition_sensible_tracée_et_motivee(self):
        creer_user(username='sens-2', role_existant='ADMIN')
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        attribution = AttributionRole.objects.get(role=self.role_sensible)
        self.assertTrue(attribution.motif)
        self.assertIn('seconde signature', attribution.motif.lower())
        entree = JournalHabilitation.objects.filter(
            type_evenement=JournalHabilitation.TypeEvenement.PROPOSITION_DEPOSEE,
        ).first()
        self.assertIsNotNone(entree)
        self.assertEqual(entree.compte_concerne, attribution.compte)

    def test_role_sensible_detecte_dans_le_plan(self):
        creer_user(username='sens-3', role_existant='ADMIN')
        plan = construire_plan()
        prevus = [r for ligne in plan.lignes for r in ligne.roles]
        self.assertTrue(any(p.sensible for p in prevus))
        self.assertTrue(any(
            A_ROLE_SENSIBLE in a for p in prevus if p.sensible for a in p.anomalies))


# ── 7. Double validation et séparation demandeur / validateur ───────────────
class DoubleValidationTests(BaseInitialisation):
    def test_le_demandeur_ne_peut_pas_valider_sa_demande(self):
        """Séparation demandeur / approbateur : jamais soi-même."""
        from habilitations.models import DemandeAcces
        from habilitations.services.demandes_acces import (
            appliquer_transition,
            creer_demande,
        )
        user = creer_user(username='dv-1', role_existant='ADMIN')
        compte = creer_compte(user=user)
        demande = creer_demande(
            user, type_demande=DemandeAcces.Type.ATTRIBUTION_ROLE,
            justification='Besoin métier', compte_cible=compte,
            role=self.role_sensible,
        )
        appliquer_transition(demande, DemandeAcces.Statut.SOUMISE,
                             acteur=user, motif_decision='Demande déposée.')
        with self.assertRaises(ValueError):
            appliquer_transition(
                demande, DemandeAcces.Statut.APPROUVEE, acteur=user,
                motif_decision='Auto-approbation interdite.',
            )

    def test_initialisation_ne_remplace_pas_la_double_validation(self):
        creer_user(username='dv-2', role_existant='ADMIN')
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        self.assertFalse(
            AttributionRole.objects.filter(
                role__sensible=True, statut=AttributionRole.Statut.ACTIVE).exists())
        self.assertTrue(
            AttributionRole.objects.filter(
                role__sensible=True, statut=AttributionRole.Statut.PROPOSEE).exists())


# ── 8. Révocations ──────────────────────────────────────────────────────────
class RevocationTests(BaseInitialisation):
    def test_attribution_revoquee_n_est_pas_resuscitee(self):
        user = creer_user(username='rev-1', role_existant='ARCHIVE')
        compte = creer_compte(user=user)
        revoquee = creer_attribution(
            compte, self.role_global, statut=AttributionRole.Statut.REVOQUEE)
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        revoquee.refresh_from_db()
        self.assertEqual(revoquee.statut, AttributionRole.Statut.REVOQUEE)

    def test_initialisation_ne_revoque_jamais_une_attribution_active(self):
        user = creer_user(username='rev-2', role_existant='ARCHIVE')
        compte = creer_compte(user=user)
        active = creer_attribution(compte, self.role_global)
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        active.refresh_from_db()
        self.assertEqual(active.statut, AttributionRole.Statut.ACTIVE)
        self.assertEqual(active.motif_revocation, '')


# ── 9. Journalisation ───────────────────────────────────────────────────────
class JournalisationTests(BaseInitialisation):
    def test_chaque_ecriture_est_journalisee_et_chainee(self):
        creer_user(username='jrn-1', role_existant='ARCHIVE')
        creer_user(username='jrn-2', role_existant='ADMIN')
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        entrees = list(JournalHabilitation.objects.order_by('numero'))
        self.assertGreaterEqual(len(entrees), 4)
        numeros = [e.numero for e in entrees]
        self.assertEqual(numeros, sorted(numeros))
        self.assertEqual(len(set(numeros)), len(numeros), "numéros de journal uniques")
        self.assertTrue(all(e.empreinte for e in entrees))
        types = {e.type_evenement for e in entrees}
        self.assertIn(JournalHabilitation.TypeEvenement.COMPTE_CREE, types)
        self.assertIn(JournalHabilitation.TypeEvenement.ROLE_ATTRIBUE, types)
        self.assertIn(JournalHabilitation.TypeEvenement.PROPOSITION_DEPOSEE, types)


# ── 10. Contrôles d'accès API ───────────────────────────────────────────────
class ControleAccesApiTests(TestCase):
    def test_endpoints_habilitations_proteges(self):
        for url in ('/api/habilitations/comptes/', '/api/habilitations/roles/',
                    '/api/habilitations/mes-acces/'):
            reponse = self.client.get(url)
            self.assertIn(
                reponse.status_code, (401, 403),
                f'{url} doit refuser un appelant anonyme (reçu {reponse.status_code})',
            )

    def test_endpoints_authentication_toujours_servis(self):
        user = creer_user(username='api-1', role_existant='ADMIN')
        self.client.force_login(user)
        for url in ('/api/auth/capabilities/', '/api/auth/users/'):
            reponse = self.client.get(url)
            self.assertNotEqual(
                reponse.status_code, 404,
                f'{url} doit rester servi (contrat d’authentification préservé)',
            )


# ── Garde-fous : drapeaux ───────────────────────────────────────────────────
class DrapeauxTests(TestCase):
    def test_ecriture_refusee_sans_les_drapeaux(self):
        autorise, motifs = ecriture_autorisee()
        self.assertFalse(autorise)
        self.assertTrue(motifs)

    def test_ecriture_autorisee_avec_contournement_explicite(self):
        autorise, _ = ecriture_autorisee(ignorer_drapeaux=True)
        self.assertTrue(autorise)

    def test_commande_echoue_sans_appliquer_les_drapeaux(self):
        creer_user(username='flag-1', role_existant='ARCHIVE')
        with self.assertRaises(CommandError):
            call_command('initialiser_rbac', '--appliquer', stdout=StringIO())
        self.assertEqual(CompteUtilisateur.objects.count(), 0)

    def test_etat_des_drapeaux_expose_les_deux_cles(self):
        etats = etat_drapeaux()
        self.assertIn(DRAPEAU_SOCLE, etats)
        self.assertIn(DRAPEAU_MODULE_UTILISATEURS, etats)
        for etat in etats.values():
            self.assertIn('present', etat)
            self.assertIn('actif', etat)


# ── Plan : structure du rapport ─────────────────────────────────────────────
class PlanInitialisationTests(BaseInitialisation):
    def test_rapport_est_serialisable(self):
        creer_user(username='plan-1', role_existant='ARCHIVE')
        plan = construire_plan()
        donnees = plan.vers_dict()
        self.assertEqual(donnees['totaux']['utilisateurs_analyses'], 1)
        self.assertEqual(donnees['totaux']['comptes_a_creer'], 1)
        self.assertEqual(donnees['lignes'][0]['username'], 'plan-1')

    def test_appliquer_plan_est_idempotent(self):
        creer_user(username='plan-2', role_existant='ARCHIVE')
        premier = appliquer_plan(construire_plan(), acteur=None)
        total_attributions = AttributionRole.objects.count()
        self.assertTrue(premier.lignes[0].applique)
        # Second passage : le compte est désormais rattaché, il n'y a plus rien
        # à traiter — aucune création, aucune modification.
        second_plan = construire_plan()
        self.assertEqual(second_plan.lignes, [], 'plus aucun compte sans profil')
        second = appliquer_plan(second_plan, acteur=None)
        self.assertEqual(AttributionRole.objects.count(), total_attributions)
        self.assertEqual(CompteUtilisateur.objects.count(), 1)

    def test_aucun_utilisateur_django_modifie(self):
        user = creer_user(username='plan-3', role_existant='ARCHIVE')
        avant = (user.role, user.is_active, user.is_superuser, user.password)
        call_command('initialiser_rbac', **APPLIQUER, stdout=StringIO())
        user.refresh_from_db()
        self.assertEqual((user.role, user.is_active, user.is_superuser, user.password), avant)

    def test_catalogue_roles_reference_present(self):
        """Le catalogue de référence est intact (aucune création parasite)."""
        self.assertGreaterEqual(RoleMetier.objects.count(), 1)
