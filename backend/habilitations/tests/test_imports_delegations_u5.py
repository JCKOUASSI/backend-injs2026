"""Tests U5 (C3, L3/L4/L5) — imports en masse transactionnels/réversibles,
délégation bornée et contrôlée, endpoints API de la file et des notifications.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    DelegationHabilitation,
    ExecutionImport,
    JournalHabilitation,
    NotificationHabilitation,
    PermissionAttribuee,
    PermissionMetier,
    PropositionProvisionnement,
    RoleMetier,
)
from habilitations.services.comptes_admin import ErreurConsole
from habilitations.services.delegations_u5 import (
    activer_delegation,
    controler_delegation,
    journaliser_action_deleguee,
)
from habilitations.services.imports_masse import (
    annuler_import,
    executer_import,
)

from . import _u5_fixtures as fx

MDP = 'Essai#2026xx'
PREFIX = '/api/habilitations'


def ligne_etudiant(index):
    return {
        'username': f'etud{index:04d}', 'nom': 'Étudiant',
        'prenoms': f'Numéro {index}', 'email': f'etud{index:04d}@injs.ci',
        'mot_de_passe': MDP, 'roles': 'ETUDIANT',
    }


class ImportsMasseTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # Catalogue RBAC chargé une fois par classe (cf. test_cycle_vie_u5).
        fx.referentiel_charge()

    def setUp(self):
        self.admin = fx.admin()

    def test_27_execution_refusee_drapeau_ferme_mais_apercu_disponible(self):
        self.client.force_authenticate(self.admin)
        fx.positionner_flag(fx.F_UI, True)
        # L'aperçu U4 reste disponible…
        reponse = self.client.post(
            f'{PREFIX}/comptes/import-simuler/',
            {'lignes': [ligne_etudiant(1)]}, format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(reponse.data['ecriture'])
        # …mais l'exécution est 403 tant que le drapeau dédié est fermé.
        reponse = self.client.post(
            f'{PREFIX}/comptes/imports/',
            {'lignes': [ligne_etudiant(1)]}, format='json',
        )
        self.assertEqual(reponse.status_code, 403)
        self.assertEqual(reponse.data['code'], 'IMPORT_DESACTIVE')
        self.assertEqual(CompteUtilisateur.objects.count(), 0)

    def test_28_execution_cree_tous_les_comptes_et_rapporte(self):
        lignes = [ligne_etudiant(i) for i in range(1, 6)]
        execution = executer_import(self.admin, lignes, {}, 'lots.csv')
        self.assertEqual(execution.statut, ExecutionImport.Statut.TERMINE)
        self.assertTrue(execution.reference.startswith(
            f'IMP-{timezone.localdate().strftime("%Y%m%d")}-'))
        self.assertEqual(execution.crees, 5)
        self.assertEqual(CompteUtilisateur.objects.count(), 5)
        # Comptes mobiles (A6), liés à l'exécution, mot de passe imposé ?
        premier = CompteUtilisateur.objects.get(user__username='etud0001')
        self.assertEqual(premier.canal, 'MOBILE')
        self.assertEqual(premier.import_execution_id, execution.pk)
        self.assertEqual(premier.user.role, 'AUDITEUR')
        self.assertEqual(len(execution.rapport['lignes']), 5)
        self.assertTrue(JournalHabilitation.objects.filter(
            type_evenement=JournalHabilitation.TypeEvenement.IMPORT_EXECUTE).exists())

    def test_29_une_erreur_annule_tout_sans_ecriture(self):
        lignes = [ligne_etudiant(1), ligne_etudiant(2)]
        lignes[1]['roles'] = 'ROLE_FANTOME'
        with self.assertRaises(ErreurConsole) as ctx:
            executer_import(self.admin, lignes)
        self.assertEqual(ctx.exception.code, 'IMPORT_NON_VALIDE')
        self.assertEqual(CompteUtilisateur.objects.count(), 0)
        # Aucune exécution ne subsiste (la transaction englobante est annulée,
        # y compris l'enregistrement EN_COURS créé juste avant la boucle).
        self.assertFalse(
            ExecutionImport.objects.exclude(reference='TEMP').exists())

    def test_30_role_legacy_manquant_profil_admin_annule_tout(self):
        lignes = [ligne_etudiant(1)]
        lignes[0]['roles'] = 'AGENT_INSCRIPTIONS'
        with self.assertRaises(ErreurConsole) as ctx:
            executer_import(self.admin, lignes)
        self.assertEqual(ctx.exception.code, 'ROLE_LEGACY_REQUIS')
        self.assertEqual(CompteUtilisateur.objects.count(), 0)

    def test_31_rejeu_du_fichier_corrige(self):
        lignes = [ligne_etudiant(1)]
        lignes[0]['roles'] = 'ROLE_FANTOME'
        with self.assertRaises(ErreurConsole):
            executer_import(self.admin, lignes)
        lignes[0]['roles'] = 'ETUDIANT'
        execution = executer_import(self.admin, lignes)
        self.assertEqual(execution.crees, 1)

    def test_32_annulation_de_100_lignes_desactive_tout_sans_rien_supprimer(self):
        lignes = [ligne_etudiant(i) for i in range(1, 101)]
        execution = executer_import(self.admin, lignes, {}, 'rentree.csv')
        self.assertEqual(CompteUtilisateur.objects.count(), 100)
        self.assertEqual(
            CompteUtilisateur.objects.filter(
                statut=CompteUtilisateur.Statut.ACTIF).count(), 100)

        annulation = annuler_import(
            execution, self.admin, "Lot saisi en double : annulation complète.", {})
        self.assertEqual(annulation.statut, ExecutionImport.Statut.ANNULE)
        self.assertEqual(
            CompteUtilisateur.objects.filter(
                statut=CompteUtilisateur.Statut.DESACTIVE).count(), 100)
        # S5 : aucun compte supprimé physiquement ; miroir User.is_active faux.
        self.assertEqual(CompteUtilisateur.objects.count(), 100)
        self.assertEqual(
            CompteUtilisateur.objects.filter(user__is_active=False).count(), 100)
        self.assertEqual(len(annulation.rapport_annulation['comptes']), 100)
        self.assertTrue(JournalHabilitation.objects.filter(
            type_evenement=JournalHabilitation.TypeEvenement.IMPORTA_ANNULE,
            acteur=self.admin).exists())

    def test_33_annulation_double_refusee_et_motif_exige(self):
        execution = executer_import(self.admin, [ligne_etudiant(1)])
        annuler_import(execution, self.admin, 'Erreur de fichier.', {})
        execution.refresh_from_db()
        with self.assertRaises(ErreurConsole) as ctx:
            annuler_import(execution, self.admin, 'Encore.', {})
        self.assertEqual(ctx.exception.code, 'IMPORT_DEJA_ANNULE')
        with self.assertRaises(ErreurConsole):
            annuler_import(
                ExecutionImport.objects.get(pk=execution.pk),
                self.admin, '   ', {})

    def test_34_api_executer_puis_annuler_par_reference(self):
        fx.positionner_flag(fx.F_UI, True)
        fx.positionner_flag(fx.F_IMPORT, True)
        self.client.force_authenticate(self.admin)
        reponse = self.client.post(
            f'{PREFIX}/comptes/imports/',
            {'lignes': [ligne_etudiant(1), ligne_etudiant(2)],
             'nom_fichier': 'api.csv'}, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        reference = reponse.data['reference']

        detail = self.client.get(f'{PREFIX}/comptes/imports/{reference}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['crees'], 2)

        annulation = self.client.post(
            f'{PREFIX}/comptes/imports/{reference}/annuler/',
            {'motif': "Annulation démontrée via l'API."}, format='json')
        self.assertEqual(annulation.status_code, 200, annulation.data)
        self.assertEqual(annulation.data['statut'], ExecutionImport.Statut.ANNULE)

    def test_35_api_annulation_reference_inconnue_404(self):
        fx.positionner_flag(fx.F_UI, True)
        fx.positionner_flag(fx.F_IMPORT, True)
        self.client.force_authenticate(self.admin)
        reponse = self.client.post(
            f'{PREFIX}/comptes/imports/IMP-19000101-9999/annuler/',
            {'motif': "Test d'une référence inexistante."}, format='json')
        self.assertEqual(reponse.status_code, 404)


class DelegationsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        fx.referentiel_charge()

    def setUp(self):
        self.admin = fx.admin()
        self.role_rp = RoleMetier.objects.get(code='RESPONSABLE_PEDAGOGIQUE')
        self.role_agent = RoleMetier.objects.get(code='AGENT_INSCRIPTIONS')
        self.fin = timezone.localdate() + timedelta(days=30)

    def _delegant(self, username='chef1', role=None, date_fin=None):
        return fx.compte_curp(
            username, (role or self.role_rp.code), role_legacy='PERSONNEL',
            cree_par=self.admin)

    def test_36_on_ne_delegue_pas_ce_que_l_on_ne_detient_pas(self):
        delegant = fx.compte_curp('chef1', role_code=None, role_legacy='PERSONNEL')
        delegataire = fx.compte_curp('remp1', role_code=None, role_legacy='PERSONNEL')
        with self.assertRaises(ErreurConsole) as ctx:
            controler_delegation(
                delegant, delegataire, ['RESPONSABLE_PEDAGOGIQUE'], [],
                self.fin)
        self.assertEqual(ctx.exception.code, 'DROIT_NON_DETENU')

    def test_37_delegation_a_soi_memme_et_non_bornee_refusees(self):
        delegant = self._delegant()
        with self.assertRaises(ErreurConsole) as ctx:
            controler_delegation(delegant, delegant,
                                 ['RESPONSABLE_PEDAGOGIQUE'], [], self.fin)
        self.assertEqual(ctx.exception.code, 'DELEGATION_SOI_MEME')
        delegataire = fx.compte_curp('remp2', role_code=None, role_legacy='PERSONNEL')
        with self.assertRaises(ErreurConsole) as ctx:
            controler_delegation(
                delegant, delegataire, ['RESPONSABLE_PEDAGOGIQUE'], [], None)
        self.assertEqual(ctx.exception.code, 'DELEGATION_NON_BORNEE')

    def test_38_redelagation_interdite(self):
        # Le « délégant » ne détient le rôle QUE par délégation reçue.
        veritable_titulaire = self._delegant('titulaire')
        intermediaire = fx.compte_curp('inter', role_code=None, role_legacy='PERSONNEL')
        destinataire = fx.compte_curp('dest', role_code=None, role_legacy='PERSONNEL')
        delegation_recue = DelegationHabilitation.objects.create(
            delegant=veritable_titulaire, delegataire=intermediaire,
            date_fin=self.fin, motif='Délégation initiale.',
            statut=DelegationHabilitation.Statut.ACTIVE)
        delegation_recue.roles.set([self.role_rp])
        with self.assertRaises(ErreurConsole) as ctx:
            controler_delegation(
                intermediaire, destinataire, ['RESPONSABLE_PEDAGOGIQUE'], [],
                self.fin)
        self.assertEqual(ctx.exception.code, 'DROIT_NON_DETENU')
        self.assertIn('re-délégation', str(ctx.exception))

    def test_39_delegation_au_dela_du_terme_refusee(self):
        delegant = self._delegant()
        delegataire = fx.compte_curp('remp3', role_code=None, role_legacy='PERSONNEL')
        # L'attribution directe s'achève avant la fin demandée de la délégation.
        attribution = delegant.attributions.get(role=self.role_rp)
        attribution.date_fin = timezone.localdate() + timedelta(days=10)
        attribution.save()
        with self.assertRaises(ErreurConsole) as ctx:
            controler_delegation(
                delegant, delegataire, ['RESPONSABLE_PEDAGOGIQUE'], [],
                timezone.localdate() + timedelta(days=30))
        self.assertEqual(ctx.exception.code, 'DELEGATION_HORS_TERME')

    def test_40_activation_puis_action_deleguee_tracee_avec_delegant(self):
        delegant = self._delegant()
        delegataire = fx.compte_curp('remp4', role_code=None, role_legacy='PERSONNEL')
        delegation = DelegationHabilitation.objects.create(
            delegant=delegant, delegataire=delegataire,
            date_fin=self.fin, motif="Absence du responsable.",
            statut=DelegationHabilitation.Statut.PROPOSEE)
        delegation.roles.set([self.role_rp])
        activee = activer_delegation(delegation, self.admin,
                                     'Contrôle des droits fait.', {})
        self.assertEqual(activee.statut, DelegationHabilitation.Statut.ACTIVE)
        self.assertEqual(activee.valide_par, self.admin)
        self.assertTrue(JournalHabilitation.objects.filter(
            type_evenement=JournalHabilitation.TypeEvenement.DELEGATION_ACTIVEE).exists())

        entree = journaliser_action_deleguee(
            activee, delegataire.user, 'Validation d’une décision pédagogique',
            detail={'objet': 'décision 12'})
        self.assertEqual(entree.delegation_source_id, activee.pk)
        self.assertEqual(
            entree.nouvelle_valeur['delegant'], delegant.user.get_username())
        self.assertIn('par délégation', entree.nouvelle_valeur['mention'])

    def test_41_action_non_delegataire_ou_inactive_refusee(self):
        delegant = self._delegant()
        delegataire = fx.compte_curp('remp5', role_code=None, role_legacy='PERSONNEL')
        delegation = DelegationHabilitation.objects.create(
            delegant=delegant, delegataire=delegataire,
            date_fin=self.fin, motif='Test.',
            statut=DelegationHabilitation.Statut.PROPOSEE)
        delegation.roles.set([self.role_rp])
        # Délégation non activée : action refusée.
        with self.assertRaises(ErreurConsole) as ctx:
            journaliser_action_deleguee(delegation, delegataire.user, 'Agir')
        self.assertEqual(ctx.exception.code, 'DELEGATION_INACTIVE')
        # Quelqu'un d'autre que le délégataire ne peut pas journaliser.
        delegation.statut = DelegationHabilitation.Statut.ACTIVE
        delegation.save()
        with self.assertRaises(ErreurConsole) as ctx:
            journaliser_action_deleguee(delegation, self.admin, 'Agir')
        self.assertEqual(ctx.exception.code, 'PAS_LE_DELEGATAIRE')

    def test_42_api_creation_illegale_refusee_et_activation(self):
        fx.positionner_flag(fx.F_UI, True)
        self.client.force_authenticate(self.admin)
        # Création sans détenir le rôle : 409.
        pauvre = fx.compte_curp('pauvre', role_code=None, role_legacy='PERSONNEL')
        autre = fx.compte_curp('autre', role_code=None, role_legacy='PERSONNEL')
        reponse = self.client.post(f'{PREFIX}/delegations/', {
            'delegant': pauvre.pk, 'delegataire': autre.pk,
            'roles': ['RESPONSABLE_PEDAGOGIQUE'], 'permissions': [],
            'date_fin': self.fin.isoformat(),
            'motif': "Tentative de délégation d'un droit absent.",
        }, format='json')
        self.assertEqual(reponse.status_code, 409)
        self.assertEqual(reponse.data['code'], 'DROIT_NON_DETENU')

        # Création légale : PROPOSÉE, puis activation admin.
        chef = self._delegant('chef2')
        reponse = self.client.post(f'{PREFIX}/delegations/', {
            'delegant': chef.pk, 'delegataire': autre.pk,
            'roles': ['RESPONSABLE_PEDAGOGIQUE'], 'permissions': [],
            'date_fin': self.fin.isoformat(), 'motif': 'Intérim validé.',
        }, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertEqual(reponse.data['statut'], DelegationHabilitation.Statut.PROPOSEE)
        delegation_id = reponse.data['id']
        reponse = self.client.post(
            f'{PREFIX}/delegations/{delegation_id}/activer/',
            {'motif': 'Vérification faite.'}, format='json')
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(reponse.data['statut'], DelegationHabilitation.Statut.ACTIVE)

        # Le délégataire enregistre son action, tracée avec la délégation.
        self.client.force_authenticate(autre.user)
        reponse = self.client.post(
            f'{PREFIX}/delegations/{delegation_id}/action/',
            {'action': 'Décision pédagogique'}, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertTrue(JournalHabilitation.objects.filter(
            type_evenement=JournalHabilitation.TypeEvenement.ACTION_DELEGUEE,
            delegation_source_id=delegation_id).exists())


class ApiFileNotificationsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        fx.referentiel_charge()

    def setUp(self):
        self.admin = fx.admin()
        self.annee, self.formation, self.niveau, self.semestre = fx.cadre_academique()
        fx.positionner_flag(fx.F_UI, True)
        self.client.force_authenticate(self.admin)

    def _proposition_admission(self):
        fx.ouvrir(fx.F_MAITRE, fx.F_ADMISSION)
        fx.admission_admise(self.annee, self.formation, self.niveau)
        from habilitations.services.provisionnement import file as file_service
        file_service.scanner(acteur=self.admin)
        return PropositionProvisionnement.objects.get()

    def test_43_liste_file_et_compteurs(self):
        prop = self._proposition_admission()
        reponse = self.client.get(f'{PREFIX}/propositions/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['count'], 1)
        self.assertEqual(
            reponse.data['compteurs'][PropositionProvisionnement.Statut.EN_ATTENTE], 1)
        self.assertEqual(reponse.data['results'][0]['id'], prop.pk)

    def test_44_approbation_et_rejet_via_api(self):
        prop = self._proposition_admission()
        # Motif obligatoire.
        reponse = self.client.post(
            f'{PREFIX}/propositions/{prop.pk}/approuver/',
            {'motif': '  '}, format='json')
        self.assertEqual(reponse.status_code, 400)
        # Approbation complète.
        reponse = self.client.post(
            f'{PREFIX}/propositions/{prop.pk}/approuver/',
            {'motif': 'Admission vérifiée et conforme.'}, format='json')
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(reponse.data['statut'],
                         PropositionProvisionnement.Statut.APPLIQUEE)
        self.assertEqual(CompteUtilisateur.objects.count(), 1)

        # Une seconde admission est rejetée.
        fx.admission_admise(self.annee, self.formation, self.niveau,
                            matricule='CAND2')
        from habilitations.services.provisionnement import file as file_service
        file_service.scanner(acteur=self.admin)
        seconde = PropositionProvisionnement.objects.filter(
            statut=PropositionProvisionnement.Statut.EN_ATTENTE).first()
        reponse = self.client.post(
            f'{PREFIX}/propositions/{seconde.pk}/rejeter/',
            {'motif': 'Dossier incomplet à la vérification.'}, format='json')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['statut'],
                         PropositionProvisionnement.Statut.REJETEE)
        self.assertEqual(CompteUtilisateur.objects.count(), 1)

    def test_45_scan_endpoint_et_proposition_inconnue_404(self):
        reponse = self.client.post(
            f'{PREFIX}/provisions/scanner/', {}, format='json')
        self.assertEqual(reponse.status_code, 200)
        # Maître fermé : rien n'est lu.
        self.assertFalse(reponse.data['maitre_actif'])
        reponse = self.client.post(
            f'{PREFIX}/propositions/999999/approuver/',
            {'motif': 'Test introuvable.'}, format='json')
        self.assertEqual(reponse.status_code, 404)

    def test_46_notifications_liste_marquage(self):
        from habilitations.services.notifications import notifier
        notifier(self.admin, NotificationHabilitation.Categorie.AUTRE,
                 'À traiter', 'Message de test.')
        reponse = self.client.get(f'{PREFIX}/notifications/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['count'], 1)
        notification_id = reponse.data['results'][0]['id']
        reponse = self.client.post(
            f'{PREFIX}/notifications/{notification_id}/lire/')
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.data['lu'])
        # La notification d'autrui n'est pas accessible.
        notifier(fx.admin('admin5b'),
                 NotificationHabilitation.Categorie.AUTRE, 'Autre', '')
        etrangere = NotificationHabilitation.objects.exclude(
            destinataire=self.admin).first()
        reponse = self.client.post(
            f'{PREFIX}/notifications/{etrangere.pk}/lire/')
        self.assertEqual(reponse.status_code, 404)
