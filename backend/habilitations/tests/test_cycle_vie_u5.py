"""Tests U5 (C3, L1/L2) — machine à états A5, file de provisionnement,
sondes événementielles, approbation humaine, inactivité et expirations.

Principe constant : aucun automatisme n'écrit sans drapeau ouvert et sans
validation humaine tracée. Les drapeaux sont activés par test, jamais dans
les données livrées.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    JournalHabilitation,
    NotificationHabilitation,
    PolitiqueSecurite,
    PropositionProvisionnement,
)
from habilitations.services import drapeaux
from habilitations.services.comptes_admin import ErreurConsole, changer_statut
from habilitations.services.expirations import detecter_inactivite, expirer_termes
from habilitations.services.machine_etats import (
    TRANSITIONS,
    transition_legale,
    transitions_possibles,
)
from habilitations.services.provisionnement import approbation, file as file_service
from parametres.flags import invalidate_flags_cache

from . import _u5_fixtures as fx


class MachineEtatsTests(APITestCase):
    """L1 — graphe de l'annexe A5."""

    @classmethod
    def setUpTestData(cls):
        # Le référentiel RBAC est un CATALOGUE en lecture seule. Le charger
        # dans `setUp` le recréait (update_or_create sur 33 rôles + ~200
        # permissions) avant CHAQUE test : c'était la cause racine de la
        # lenteur de la suite globale. `setUpTestData` le charge une seule
        # fois par classe, dans une transaction annulée en fin de classe.
        fx.referentiel_charge()

    def setUp(self):
        self.admin = fx.admin()

    def _compte(self, statut, username, role_code='AGENT_INSCRIPTIONS'):
        return fx.compte_curp(
            username, role_code, statut=statut, role_legacy='SECRETARIAT',
            date_activation=timezone.now() if statut == 'ACTIF' else None,
        )

    def test_01_invitation_activee_premiere_connexion(self):
        compte = self._compte(CompteUtilisateur.Statut.INVITE, 'invite1')
        changer_statut(compte, self.admin, 'activer',
                       'Première connexion et changement de mot de passe.', {})
        compte.refresh_from_db()
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)
        self.assertTrue(compte.user.is_active)
        self.assertTrue(compte.journal.filter(
            type_evenement=JournalHabilitation.TypeEvenement.COMPTE_ACTIVE).exists())

    def test_02_invitation_expiree(self):
        compte = self._compte(CompteUtilisateur.Statut.INVITE, 'invite2')
        changer_statut(compte, self.admin, 'expirer', 'Invitation non acceptée.', {})
        compte.refresh_from_db()
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.EXPIRE)
        self.assertFalse(compte.user.is_active)

    def test_03_suspension_puis_reactivation_motivee(self):
        compte = self._compte(CompteUtilisateur.Statut.ACTIF, 'actif1')
        changer_statut(compte, self.admin, 'suspendre', 'Contrôle en cours.', {})
        compte.refresh_from_db()
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.SUSPENDU)
        self.assertFalse(compte.user.is_active)
        self.assertIsNotNone(compte.date_suspension)
        changer_statut(compte, self.admin, 'activer', 'Réactivation après contrôle.', {})
        compte.refresh_from_db()
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)
        self.assertTrue(compte.user.is_active)
        self.assertIsNone(compte.date_suspension)

    def test_04_verrouillage_puis_deverrouillage(self):
        compte = self._compte(CompteUtilisateur.Statut.ACTIF, 'actif2')
        changer_statut(compte, self.admin, 'verrouiller', 'Échecs répétés.', {})
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.VERROUILLE)
        changer_statut(compte, self.admin, 'deverrouiller', 'Déverrouillage admin.', {})
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)

    def test_05_desactivation_et_reactivation_exceptionnelle(self):
        compte = self._compte(CompteUtilisateur.Statut.ACTIF, 'actif3')
        changer_statut(compte, self.admin, 'desactiver', 'Fin de contrat.', {})
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.DESACTIVE)
        changer_statut(compte, self.admin, 'activer', 'Réactivation exceptionnelle motivée.', {})
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)

    def test_06_actif_expire_date_atteinte(self):
        compte = self._compte(CompteUtilisateur.Statut.ACTIF, 'actif4')
        changer_statut(compte, self.admin, 'expirer', "Date d'échéance atteinte.", {})
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.EXPIRE)

    def test_07_fleche_illegale_refusee_et_tracee(self):
        # SUSPENDU ne peut que redevenir ACTIF : désactiver directement est interdit.
        compte = self._compte(CompteUtilisateur.Statut.SUSPENDU, 'susp1')
        avant = JournalHabilitation.objects.count()
        with self.assertRaises(ErreurConsole) as ctx:
            changer_statut(compte, self.admin, 'desactiver', 'Tentative abusive.', {})
        self.assertEqual(ctx.exception.code, 'TRANSITION_ILLEGALE')
        compte.refresh_from_db()
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.SUSPENDU)
        self.assertTrue(JournalHabilitation.objects.filter(
            pk__gt=avant,
            type_evenement=JournalHabilitation.TypeEvenement.TRANSITION_REFUSEE).exists())

    def test_08_transition_inconnue_et_motif_obligatoire(self):
        compte = self._compte(CompteUtilisateur.Statut.ACTIF, 'actif5')
        with self.assertRaises(ErreurConsole) as ctx:
            changer_statut(compte, self.admin, 'supprimer', 'x', {})
        self.assertEqual(ctx.exception.code, 'TRANSITION_INCONNUE')
        with self.assertRaises(ErreurConsole) as ctx:
            changer_statut(compte, self.admin, 'suspendre', '   ', {})
        self.assertEqual(ctx.exception.code, 'MOTIF_REQUIS')

    def test_09_transitions_possibles_conformes_a5(self):
        self.assertIn('activer', transitions_possibles(CompteUtilisateur.Statut.INVITE))
        self.assertIn('expirer', transitions_possibles(CompteUtilisateur.Statut.INVITE))
        self.assertEqual(
            set(transitions_possibles(CompteUtilisateur.Statut.ACTIF)),
            {'suspendre', 'desactiver', 'verrouiller', 'expirer'},
        )
        self.assertEqual(transitions_possibles(CompteUtilisateur.Statut.EXPIRE), [])
        # Couverture statique du graphe : les six statuts sont atteints.
        cibles = {regle[0] for regle in TRANSITIONS.values()}
        self.assertEqual(len(cibles), 5) # ACTIF, SUSPENDU, VERROUILLE, DESACTIVE, EXPIRE
        self.assertTrue(transition_legale('VERROUILLE', 'deverrouiller'))
        self.assertFalse(transition_legale('EXPIRE', 'activer'))

    def test_09b_suspension_revoque_les_sessions_actives(self):
        from importlib import import_module
        from django.conf import settings
        from django.contrib.sessions.models import Session
        compte = self._compte(CompteUtilisateur.Statut.ACTIF, 'actifsess')
        moteur = import_module(settings.SESSION_ENGINE)
        session = moteur.SessionStore()
        session['_auth_user_id'] = str(compte.user_id)
        session.save()
        self.assertTrue(Session.objects.filter(
            session_key=session.session_key).exists())
        changer_statut(compte, self.admin, 'suspendre', 'Contrôle.', {})
        self.assertFalse(Session.objects.filter(
            session_key=session.session_key).exists())
        self.assertTrue(compte.journal.filter(
            type_evenement=JournalHabilitation.TypeEvenement.SESSION_REVOQUEE).exists())
        # Une réactivation ne lève pas d'erreur et rend l'accès de nouveau.
        changer_statut(compte, self.admin, 'activer', 'Contrôle terminé.', {})
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)


class FileSondesTests(APITestCase):
    """L2 — sondes, file idempotente et approbation humaine.

    Le cache des drapeaux (`parametres.flags`, 300 s) survit au rollback de
    la transaction de test : un test qui ouvre un drapeau laisse ce drapeau
    visible dans le cache pour les tests suivants de la classe. L'ordre
    d'exécution étant différent en `--parallel`, `test_10_scan_noop_
    drapeaux_fermes` pouvait lire un drapeau resté en cache et observer une
    sonde active alors que la base est revenue à son état initial. Le cache
    est donc invalidé avant chaque test : le contrôle porte bien sur l'état
    réel de la base, dans n'importe quel ordre d'exécution.
    """

    @classmethod
    def setUpTestData(cls):
        fx.referentiel_charge()

    def setUp(self):
        invalidate_flags_cache()
        self.admin = fx.admin()
        self.annee, self.formation, self.niveau, self.semestre = fx.cadre_academique()

    def test_10_scan_noop_drapeaux_fermes(self):
        fx.admission_admise(self.annee, self.formation, self.niveau)
        self.assertEqual(file_service.scanner(acteur=self.admin), {})
        self.assertEqual(PropositionProvisionnement.objects.count(), 0)

    def test_11_admission_propose_compte_et_idempotence(self):
        fx.ouvrir(fx.F_MAITRE, fx.F_ADMISSION)
        fx.admission_admise(self.annee, self.formation, self.niveau)
        bilan1 = file_service.scanner(acteur=self.admin)
        self.assertEqual(bilan1['ADMISSION'], 1)
        # Second scan le même jour : aucun doublon.
        self.assertEqual(file_service.scanner(acteur=self.admin)['ADMISSION'], 0)
        prop = PropositionProvisionnement.objects.get()
        self.assertEqual(prop.action_proposee,
                         PropositionProvisionnement.Action.CREER_COMPTE)
        self.assertEqual(prop.statut, PropositionProvisionnement.Statut.EN_ATTENTE)

    def test_12_approbation_cree_le_compte_etudiant(self):
        fx.ouvrir(fx.F_MAITRE, fx.F_ADMISSION)
        fx.admission_admise(self.annee, self.formation, self.niveau)
        file_service.scanner(acteur=self.admin)
        prop = PropositionProvisionnement.objects.get()
        prop = approbation.approuver(prop, self.admin, 'Admission vérifiée.', {})
        self.assertEqual(prop.statut, PropositionProvisionnement.Statut.APPLIQUEE)
        compte = prop.compte_cible
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)
        self.assertEqual(compte.canal, 'MOBILE')
        self.assertTrue(compte.user.must_change_password)
        self.assertTrue(JournalHabilitation.objects.filter(
            type_evenement=JournalHabilitation.TypeEvenement.PROPOSITION_APPROUVEE,
            acteur=self.admin).exists())

    def test_13_rejet_exige_motif_et_laisse_fil_vide_puis_redepot(self):
        fx.ouvrir(fx.F_MAITRE, fx.F_ADMISSION)
        fx.admission_admise(self.annee, self.formation, self.niveau)
        file_service.scanner(acteur=self.admin)
        prop = PropositionProvisionnement.objects.get()
        with self.assertRaises(ErreurConsole):
            approbation.rejeter(prop, self.admin, '  ', {})
        approbation.rejeter(prop, self.admin, 'Dossier incomplet.', {})
        self.assertEqual(CompteUtilisateur.objects.count(), 0)
        # Une proposition rejetée peut être redéposée (le fait métier persiste).
        self.assertEqual(file_service.scanner(acteur=self.admin)['ADMISSION'], 1)
        self.assertEqual(PropositionProvisionnement.objects.filter(
            statut=PropositionProvisionnement.Statut.REJETEE).count(), 1)

    def test_14_inscription_sans_compte_propose_creation(self):
        fx.ouvrir(fx.F_MAITRE, fx.F_INSCRIPTION)
        fx.inscription_validee(self.annee, self.formation, self.niveau)
        bilan = file_service.scanner(acteur=self.admin)
        self.assertEqual(bilan['INSCRIPTION'], 1)

    def test_15_inscription_compte_inactif_propose_activation(self):
        from habilitations.models import CanalAcces
        fx.ouvrir(fx.F_MAITRE, fx.F_INSCRIPTION)
        _ia, participant = fx.inscription_validee(
            self.annee, self.formation, self.niveau, avec_user=True)
        # Un profil CURP INVITÉ existe déjà sur le user porté par le participant.
        profil = CompteUtilisateur.objects.create(
            user=participant.user, statut=CompteUtilisateur.Statut.INVITE,
            canal=CanalAcces.MOBILE,
        )
        file_service.scanner(acteur=self.admin)
        prop = PropositionProvisionnement.objects.get()
        self.assertEqual(prop.action_proposee,
                         PropositionProvisionnement.Action.ACTIVER_COMPTE)
        approbation.approuver(prop, self.admin, 'IA validée.', {})
        profil.refresh_from_db()
        self.assertEqual(profil.statut, CompteUtilisateur.Statut.ACTIF)
        self.assertTrue(
            profil.attributions.filter(role__code='ETUDIANT').exists())

    def test_16_recrutement_role_a_completer_puis_ajustement(self):
        fx.ouvrir(fx.F_MAITRE, fx.F_RECRUTEMENT)
        fx.agent_actif(matricule='RH10')
        file_service.scanner(acteur=self.admin)
        prop = PropositionProvisionnement.objects.get()
        self.assertTrue(prop.proposition.get('role_a_completer'))
        # Approbation directe refusée : aucun droit d'accès deviné.
        with self.assertRaises(ErreurConsole) as ctx:
            approbation.approuver(prop, self.admin, 'OK.', {})
        self.assertEqual(ctx.exception.code, 'ROLE_A_COMPLETER')
        prop.refresh_from_db()
        prop = approbation.approuver(
            prop, self.admin, 'Affecté au service inscriptions.',
            ajustements={
                'identifiants': {'role_legacy': 'SECRETARIAT'},
                'roles': [{'role': 'AGENT_INSCRIPTIONS', 'niveau': 'N2'}],
            },
        )
        self.assertEqual(prop.compte_cible.user.role, 'SECRETARIAT')
        self.assertTrue(prop.compte_cible.attributions.filter(
            role__code='AGENT_INSCRIPTIONS').exists())

    def test_17_affectation_enseignant_propose_role(self):
        fx.ouvrir(fx.F_MAITRE, fx.F_AFFECTATION)
        fx.affectation_enseignant(
            self.annee, self.formation, self.niveau, self.semestre)
        bilan = file_service.scanner(acteur=self.admin)
        self.assertEqual(bilan['AFFECTATION_ENSEIGNANT'], 1)
        prop = PropositionProvisionnement.objects.get()
        self.assertEqual(prop.proposition['identifiants']['role_legacy'],
                         'FORMATEUR')
        self.assertEqual(prop.proposition['roles'][0]['role'], 'ENSEIGNANT')

    def test_18_fin_relation_agent_apres_grace_seulement(self):
        politique = PolitiqueSecurite.objet()
        politique.delai_grace_fin_relation_jours = 7
        politique.save()
        fx.ouvrir(fx.F_MAITRE, fx.F_FIN_RELATION)
        # Sorti depuis 3 jours : délai de grâce non écoulé, rien.
        fx.agent_actif(
            matricule='RH20', avec_compte=True, role_code='AGENT_INSCRIPTIONS',
            date_sortie=timezone.localdate() - timedelta(days=3),
            cree_par=self.admin)
        self.assertEqual(file_service.scanner(acteur=self.admin).get('FIN_RELATION', 0), 0)
        # Sorti depuis 10 jours : proposition de suspension.
        agent, user, compte = fx.agent_actif(
            matricule='RH21', avec_compte=True, role_code='AGENT_INSCRIPTIONS',
            date_sortie=timezone.localdate() - timedelta(days=10),
            cree_par=self.admin)
        bilan = file_service.scanner(acteur=self.admin)
        self.assertEqual(bilan['FIN_RELATION'], 1)
        prop = PropositionProvisionnement.objects.get()
        approbation.approuver(prop, self.admin, 'Contrat terminé.', {})
        compte.refresh_from_db()
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.SUSPENDU)

    def test_19_plafond_quotidien_bloque_et_alerte_une_fois(self):
        politique = PolitiqueSecurite.objet()
        politique.plafond_quotidien_propositions = 2
        politique.save()
        fx.ouvrir(fx.F_MAITRE, fx.F_ADMISSION)
        for i in range(3):
            # Des admissions distinctes (candidats distincts).
            fx.admission_admise(
                self.annee, self.formation, self.niveau, matricule=f'C{i}')
        bilan = file_service.scanner(acteur=self.admin)
        self.assertEqual(bilan['ADMISSION'], 2)
        self.assertEqual(PropositionProvisionnement.objects.count(), 2)
        alertes = NotificationHabilitation.objects.filter(
            categorie=NotificationHabilitation.Categorie.ALERTE_PLAFOND)
        self.assertGreaterEqual(alertes.count(), 1)
        # Un second scan ne crée pas de deuxième alerte.
        file_service.scanner(acteur=self.admin)
        self.assertEqual(
            NotificationHabilitation.objects.filter(
                categorie=NotificationHabilitation.Categorie.ALERTE_PLAFOND).count(),
            alertes.count(),
        )

    def test_20_maitre_ouvert_mais_sonde_fermee_rien_ne_passe(self):
        fx.ouvrir(fx.F_MAITRE)
        fx.admission_admise(self.annee, self.formation, self.niveau)
        self.assertFalse(drapeaux.sonde_active('ADMISSION'))
        self.assertEqual(file_service.scanner(acteur=self.admin), {})

    def test_21_jury_propose_role_avec_perimetre_formation(self):
        fx.ouvrir(fx.F_MAITRE, fx.F_JURY)
        fx.membre_jury(self.annee, self.formation, self.niveau,
                       avec_compte=True, role_code='ENSEIGNANT',
                       cree_par=self.admin)
        bilan = file_service.scanner(acteur=self.admin)
        self.assertEqual(bilan['JURY'], 1)
        prop = PropositionProvisionnement.objects.get()
        self.assertEqual(prop.declencheur, PropositionProvisionnement.Declencheur.JURY)
        self.assertEqual(prop.action_proposee,
                         PropositionProvisionnement.Action.ATTRIBUER_ROLE)
        self.assertEqual(prop.source_app, 'jurys')
        self.assertEqual(prop.source_modele, 'MembreJury')
        ligne = prop.proposition['roles'][0]
        self.assertEqual(ligne['role'], 'MEMBRE_JURY')
        perimetre = ligne['perimetres_generiques'][0]
        self.assertEqual(perimetre['type'], 'FORMATION')
        self.assertEqual(perimetre['objet_id'], self.formation.pk)
        # Second scan le même jour : aucun doublon (clé idempotente).
        self.assertEqual(file_service.scanner(acteur=self.admin)['JURY'], 0)

    def test_22_jury_membre_deja_role_rien_ne_passe(self):
        fx.ouvrir(fx.F_MAITRE, fx.F_JURY)
        fx.membre_jury(self.annee, self.formation, self.niveau,
                       avec_compte=True, role_code='MEMBRE_JURY',
                       cree_par=self.admin)
        self.assertEqual(file_service.scanner(acteur=self.admin), {'JURY': 0})
        self.assertEqual(PropositionProvisionnement.objects.count(), 0)

    def test_23_jury_sans_compte_curp_pas_de_fait(self):
        # L'utilisateur métier existe mais n'a pas encore de compte CURP :
        # la sonde ne dépose rien (la création passe par l'écran U4, jamais
        # de rôle d'accès deviné automatiquement).
        fx.ouvrir(fx.F_MAITRE, fx.F_JURY)
        fx.membre_jury(self.annee, self.formation, self.niveau)
        self.assertEqual(file_service.scanner(acteur=self.admin), {'JURY': 0})
        self.assertEqual(PropositionProvisionnement.objects.count(), 0)

    def test_24_jury_approbation_attribue_role_avec_perimetre(self):
        from habilitations.models import Perimetre
        fx.ouvrir(fx.F_MAITRE, fx.F_JURY)
        fx.membre_jury(self.annee, self.formation, self.niveau,
                       fonction='PRESIDENT', avec_compte=True,
                       role_code='ENSEIGNANT', cree_par=self.admin)
        file_service.scanner(acteur=self.admin)
        prop = PropositionProvisionnement.objects.get()
        self.assertIn('président', prop.proposition['motif'])
        prop = approbation.approuver(prop, self.admin, 'Désignation vérifiée.', {})
        self.assertEqual(prop.statut, PropositionProvisionnement.Statut.APPLIQUEE)
        compte = prop.compte_cible
        attribution = compte.attributions.get(role__code='MEMBRE_JURY')
        self.assertEqual(attribution.statut, AttributionRole.Statut.ACTIVE)
        perimetres = attribution.perimetres.all()
        self.assertEqual(perimetres.count(), 1)
        self.assertEqual(perimetres[0].type, Perimetre.Type.FORMATION)
        self.assertEqual(perimetres[0].object_id, self.formation.pk)
        # Le fait métier persiste : un nouveau scan ne redépose pas
        # (la proposition est déjà vivante).
        self.assertEqual(file_service.scanner(acteur=self.admin)['JURY'], 0)

    def test_25_jury_deux_sessions_meme_membre_deux_faits(self):
        fx.ouvrir(fx.F_MAITRE, fx.F_JURY)
        _, session_normale, user = fx.membre_jury(
            self.annee, self.formation, self.niveau,
            avec_compte=True, role_code='ENSEIGNANT', cree_par=self.admin)
        # Même membre, même académie : une session de rattrapage distincte
        # (maquette version suivante).
        fx.membre_jury(self.annee, self.formation, self.niveau, user=user,
                       type_session='RATTRAPAGE', version=2)
        bilan = file_service.scanner(acteur=self.admin)
        self.assertEqual(bilan['JURY'], 2)
        cles = set(
            PropositionProvisionnement.objects
            .values_list('cle_dedoublonnage', flat=True))
        self.assertEqual(len(cles), 2)
        # Rejet du premier fait : il peut être redéposé, le second n'est
        # pas touché (clé versionnée par session).
        premiere = PropositionProvisionnement.objects.first()
        approbation.rejeter(premiere, self.admin, 'Jury annulé.', {})
        self.assertEqual(file_service.scanner(acteur=self.admin)['JURY'], 1)


class InactiviteExpirationTests(APITestCase):
    """Suspension d'inactivité (préavis puis file) et expiration à terme."""

    @classmethod
    def setUpTestData(cls):
        fx.referentiel_charge()

    def setUp(self):
        self.admin = fx.admin()

    def test_21_attribution_expiree_et_preavis_j7(self):
        politique = PolitiqueSecurite.objet()
        politique.echeance_notification_jours = 7
        politique.save()
        compte = fx.compte_curp('exp1', 'AGENT_INSCRIPTIONS',
                                role_legacy='SECRETARIAT', cree_par=self.admin)
        attribution = compte.attributions.first()
        # Dans 7 jours exactement : une notification est émise.
        attribution.date_fin = timezone.localdate() + timedelta(days=7)
        attribution.save()
        bilan = expirer_termes()
        self.assertEqual(bilan['preavis'], 1)
        self.assertTrue(NotificationHabilitation.objects.filter(
            categorie=NotificationHabilitation.Categorie.ECHEANCE_ATTRIBUTION).exists())
        # Idempotent : pas de doublon de préavis.
        expirer_termes()
        self.assertEqual(NotificationHabilitation.objects.filter(
            categorie=NotificationHabilitation.Categorie.ECHEANCE_ATTRIBUTION).count(), 2)
        # Une fois la date passée, l'attribution expire.
        attribution.date_fin = timezone.localdate() - timedelta(days=1)
        attribution.notification_echeance_le = timezone.localdate() - timedelta(days=8)
        attribution.save()
        bilan = expirer_termes()
        self.assertEqual(bilan['attributions'], 1)
        attribution.refresh_from_db()
        self.assertEqual(attribution.statut, AttributionRole.Statut.EXPIREE)

    def test_22_delegation_terminee_a_echeance(self):
        from habilitations.models import DelegationHabilitation, RoleMetier
        delegant = fx.compte_curp('del1', 'RESPONSABLE_PEDAGOGIQUE',
                                  role_legacy='PERSONNEL')
        delegataire = fx.compte_curp('del2', role_code=None, role_legacy='PERSONNEL')
        delegation = DelegationHabilitation.objects.create(
            delegant=delegant, delegataire=delegataire,
            date_debut=timezone.localdate() - timedelta(days=20),
            date_fin=timezone.localdate() - timedelta(days=1),
            motif='Test borné.', statut=DelegationHabilitation.Statut.ACTIVE,
        )
        delegation.roles.set([RoleMetier.objects.get(code='RESPONSABLE_PEDAGOGIQUE')])
        bilan = expirer_termes()
        self.assertEqual(bilan['delegations'], 1)
        delegation.refresh_from_db()
        self.assertEqual(delegation.statut, DelegationHabilitation.Statut.TERMINEE)
        self.assertIn('Extinction automatique', delegation.raison_arret)

    def test_23_invitation_ancienne_expiree(self):
        compte = fx.compte_curp('invx', statut=CompteUtilisateur.Statut.INVITE,
                                role_legacy='PERSONNEL')
        CompteUtilisateur.objects.filter(pk=compte.pk).update(
            date_creation=timezone.now() - timedelta(days=40))
        bilan = expirer_termes()
        self.assertEqual(bilan['invitations'], 1)
        compte.refresh_from_db()
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.EXPIRE)
        self.assertTrue(NotificationHabilitation.objects.filter(
            categorie=NotificationHabilitation.Categorie.EXPIRATION_INVITATION).exists())

    def test_24_inactivite_preavis_puis_proposition_jamais_suspension_directe(self):
        politique = PolitiqueSecurite.objet()
        politique.inactivite_suspension_jours = 180
        politique.preavis_suspension_jours = 15
        politique.save()
        compte = fx.compte_curp('inact1', 'AGENT_INSCRIPTIONS',
                                role_legacy='SECRETARIAT', cree_par=self.admin)
        # Dernière activité il y a 170 jours : fenêtre de préavis.
        derniere = timezone.localdate() - timedelta(days=170)
        CompteUtilisateur.objects.filter(pk=compte.pk).update(
            date_activation=derniere, derniere_connexion=derniere)
        bilan = detecter_inactivite()
        self.assertEqual(bilan['preavis'], 1)
        self.assertEqual(bilan['propositions'], 0)
        # L'agent ET le responsable sont notifiés.
        self.assertEqual(NotificationHabilitation.objects.filter(
            categorie=NotificationHabilitation.Categorie.PREAVIS_SUSPENSION).count(), 2)
        # Le compte reste actif : aucune suspension silencieuse.
        compte.refresh_from_db()
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)

        # Au-delà du seuil, une proposition de suspension est mise en file.
        ancienne = timezone.localdate() - timedelta(days=181)
        CompteUtilisateur.objects.filter(pk=compte.pk).update(
            derniere_connexion=ancienne, date_activation=ancienne)
        bilan = detecter_inactivite()
        self.assertEqual(bilan['propositions'], 1)
        proposition = PropositionProvisionnement.objects.get(
            declencheur=PropositionProvisionnement.Declencheur.INACTIVITE)
        self.assertEqual(proposition.action_proposee,
                         PropositionProvisionnement.Action.SUSPENDRE_COMPTE)
        compte.refresh_from_db()
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)

    def test_25_exemption_inactivite_respectee(self):
        politique = PolitiqueSecurite.objet()
        politique.inactivite_suspension_jours = 180
        politique.preavis_suspension_jours = 15
        politique.save()
        compte = fx.compte_curp('cong1', 'AGENT_INSCRIPTIONS',
                                role_legacy='SECRETARIAT', exempt_inactivite=True)
        derniere = timezone.localdate() - timedelta(days=240)
        CompteUtilisateur.objects.filter(pk=compte.pk).update(
            date_activation=derniere, derniere_connexion=derniere)
        bilan = detecter_inactivite()
        self.assertEqual(bilan, {'preavis': 0, 'propositions': 0})

    def test_26_commandes_noop_quand_drapeaux_fermes(self):
        from django.core.management import call_command
        from io import StringIO
        sortie = StringIO()
        call_command('expirer_habilitations', stdout=sortie)
        call_command('detecter_inactivite', stdout=sortie)
        call_command('provisionnement_scanner', stdout=sortie)
        texte = sortie.getvalue()
        self.assertIn('no-op', texte)
        self.assertEqual(PropositionProvisionnement.objects.count(), 0)
