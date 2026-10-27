"""Test de CONTRAT P00-06 — GET /api/auth/capabilities/.

L'endpoint est la projection des permissions EXISTANTES (constantes de
``authentication.role_groups``, permissions ``authentication.*`` dérivées de
``ROLE_POLICY``, classes DRF) pour l'affichage de l'interface.

La matrice attendue pour les 12 rôles est écrite ci-dessous (donc exécutable) :
toute dérive de la politique de rôles casse ce test.
"""
import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APITestCase

from formations.models import (
    Formation,
    Module,
    ModuleParticipant,
    Participant,
    RefFormation,
    RefModule,
    Secretariat,
)
from authentication.capabilities import CAPACITES_DESCRIPTEURS
from authentication.role_groups import ROLE_GROUP_NAMES, ensure_role_groups
from scolarite.models import AnneeAcademique, Groupe, Niveau

User = get_user_model()

# ---------------------------------------------------------------------------
# Matrice de contrat : module -> actions par rôle (forme réduite aux rôles).
# Les rôles non cités pour un module n'obtiennent aucune action sur ce module.
# ---------------------------------------------------------------------------
TOUS_MODULES = tuple(CAPACITES_DESCRIPTEURS.keys())

ADMIN_TRIO = ('ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN')
SECRETARIATS = ('CHEF_SECRETARIAT', 'SECRETARIAT')

MATRICE = {
    role: {module: [] for module in TOUS_MODULES}
    for role in User.Role.values
}

# --- ADMIN, CHEF_INJS_ADMIN, INJS_ADMIN (matrice identique) --------------
for _role in ADMIN_TRIO:
    MATRICE[_role].update({
        'web': ['acceder', 'operationnel'],
        'utilisateurs': ['gerer', 'voir'],
        'participants': ['creer', 'gerer', 'lister'],
        'modules': ['archiver'],
        'presences': ['agir', 'superviser', 'voir'],
        'finance': [],
        'statistiques': ['voir', 'voir_globales'],
        'evaluations': ['consulter', 'gerer_questionnaires'],
        'notes': ['gerer', 'valider_decisions'],
        'scolarite': ['agir', 'voir'],
        'exports': ['liste_classe'],
        'dashboard': ['filtrer_secretariat'],
    })

# --- DIRECTION --------------------------------------------------------------
MATRICE['DIRECTION'].update({
    'web': ['acceder', 'operationnel'],
    'utilisateurs': ['voir'],
    'participants': ['lister'],
    'modules': ['archiver'],
    'presences': ['voir'],
    'finance': ['exporter', 'parametrer', 'voir'],
    'statistiques': ['voir', 'voir_globales'],
    'evaluations': ['consulter'],
    'notes': ['gerer', 'valider_decisions'],
    'scolarite': ['voir'],
    'exports': ['liste_classe'],
    'dashboard': ['filtrer_secretariat'],
})

# --- CHEF_SECRETARIAT / SECRETARIAT ----------------------------------------
for _role in SECRETARIATS:
    MATRICE[_role].update({
        'web': ['acceder', 'operationnel'],
        'utilisateurs': ['gerer', 'voir'],
        'participants': ['gerer', 'lister'],
        'modules': ['archiver'],
        'presences': ['agir', 'superviser', 'voir'],
        'statistiques': ['voir'],
        'evaluations': ['consulter', 'gerer_questionnaires'],
        'notes': ['gerer', 'valider_decisions'],
        'scolarite': ['agir', 'voir'],
        'exports': ['liste_classe'],
    })

# --- FINANCE ----------------------------------------------------------------
MATRICE['FINANCE'].update({
    'web': ['acceder'],
    'finance': ['exporter', 'parametrer', 'voir'],
    'statistiques': ['voir', 'voir_globales'],
    'evaluations': ['consulter'],
    'scolarite': ['voir'],
})

# --- ARCHIVE ----------------------------------------------------------------
MATRICE['ARCHIVE'].update({
    'web': ['acceder', 'operationnel'],
    'participants': ['lister'],
    'presences': ['voir'],
    'finance': ['exporter', 'voir'],
    'statistiques': ['voir', 'voir_globales'],
    'evaluations': ['consulter'],
    'scolarite': ['voir'],
    'exports': ['liste_classe'],
    'dashboard': ['filtrer_secretariat'],
})

# --- ENCADRANT --------------------------------------------------------------
MATRICE['ENCADRANT'].update({
    'web': ['acceder', 'operationnel'],
    'participants': ['lister'],
    'presences': ['agir', 'superviser', 'voir'],
    'statistiques': ['voir'],
    'evaluations': ['consulter', 'gerer_questionnaires'],
    'notes': ['gerer', 'valider_decisions'],
    'scolarite': ['voir'],
    'exports': ['liste_classe'],
})

# --- SUPERVISEUR ------------------------------------------------------------
MATRICE['SUPERVISEUR'].update({
    'web': ['acceder', 'operationnel'],
    'evaluations': ['consulter', 'gerer_questionnaires'],
    'notes': ['gerer', 'valider_decisions'],
})
# FORMATEUR et AUDITEUR : aucune capacité (comptes réservés au mobile).

NIVEAU_ATTENDU = {
    'ADMIN': 'N4', 'DIRECTION': 'N4', 'CHEF_INJS_ADMIN': 'N4', 'INJS_ADMIN': 'N4',
    'CHEF_SECRETARIAT': 'N3', 'FINANCE': 'N3',
    'SECRETARIAT': 'N2', 'ENCADRANT': 'N2', 'SUPERVISEUR': 'N2', 'FORMATEUR': 'N2',
    'ARCHIVE': 'N1', 'AUDITEUR': 'N1',
}

# Cohérence capacités ↔ permissions personnalisées Django (ROLE_POLICY).
EQUIVALENCE_PERMS = {
    ('web', 'acceder'): 'authentication.access_web',
    ('web', 'operationnel'): 'authentication.operational_web',
    ('participants', 'lister'): 'authentication.list_participants',
    ('utilisateurs', 'gerer'): 'authentication.mutate_users',
    ('evaluations', 'gerer_questionnaires'): 'authentication.manage_questionnaires',
    ('evaluations', 'consulter'): 'authentication.consult_evaluation',
    ('notes', 'gerer'): 'authentication.manage_notes',
    ('notes', 'valider_decisions'): 'authentication.validate_decisions',
}


class CapabilitiesContractTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # Les groupes ROLE_* sont normalement créés par les signaux post-migrate ;
        # on force l'alignement complet de ROLE_POLICY pour la stabilité du contrat.
        ensure_role_groups(force_reset=True)
        cls.users = {}
        for role in User.Role.values:
            cls.users[role] = User.objects.create_user(
                username=f'caps_{role}', password='Caps!2026x', role=role,
            )

    def _get(self, user):
        self.client.force_authenticate(user)
        res = self.client.get('/api/auth/capabilities/')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.content)
        return res.json()

    def test_anonyme_refuse(self):
        res = self.client.get('/api/auth/capabilities/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_les_douze_roles_suivent_la_matrice_de_contrat(self):
        for role in User.Role.values:
            with self.subTest(role=role):
                data = self._get(self.users[role])
                # Tous les modules sont présents (les droits vides sont explicites).
                self.assertEqual(set(data['capacites'].keys()), set(TOUS_MODULES))
                for module in TOUS_MODULES:
                    self.assertEqual(
                        sorted(data['capacites'][module]),
                        sorted(MATRICE[role][module]),
                        f'{role} / {module}',
                    )
                self.assertEqual(data['niveau'], NIVEAU_ATTENDU[role])
                self.assertTrue(data['niveau_provisoire'])
                self.assertIn(role, data['roles'])

    def test_coherence_permissions_django_pour_les_douze_roles(self):
        """Test croisé : capacité custom ⇔ permission de groupe effective."""
        for role in User.Role.values:
            user = self.users[role]
            data = self._get(user)
            with self.subTest(role=role):
                for (module, action), codename in EQUIVALENCE_PERMS.items():
                    depuis_caps = action in data['capacites'][module]
                    depuis_perm = user.has_perm(codename)
                    self.assertEqual(
                        depuis_caps, depuis_perm,
                        f'{role} {module}.{action} ({codename}) : '
                        f'capacités={depuis_caps} permission={depuis_perm}',
                    )

    def test_superutilisateur_obtient_toutes_les_actions(self):
        root = User.objects.create_superuser(
            username='caps_root', password='Root!2026x', email='root@injs.test',
        )
        data = self._get(root)
        for module, actions in CAPACITES_DESCRIPTEURS.items():
            self.assertEqual(sorted(data['capacites'][module]), sorted(actions.keys()))
        self.assertEqual(data['perimetres']['secretariats'], '*')
        self.assertEqual(data['perimetres']['formations'], '*')

    def test_perimetre_global_pour_roles_globaux(self):
        for role in ('ADMIN', 'DIRECTION', 'ARCHIVE'):
            with self.subTest(role=role):
                data = self._get(self.users[role])
                self.assertEqual(data['perimetres']['niveaux'], ['INJS_ENTIER'])
                self.assertEqual(data['perimetres']['secretariats'], '*')
                self.assertEqual(data['perimetres']['formations'], '*')
                self.assertEqual(data['perimetres']['groupes'], '*')

    def test_perimetre_secretariat_avec_identifiants_concrets(self):
        secretariat = Secretariat.objects.create(nom='Sec contrat')
        formation = Formation.objects.create(formation='Formation secrétariat')
        Module.objects.create(
            formation=formation, intitule='Module sec',
            statut='PLANIFIE', secretariat=secretariat,
        )
        user = self.users['SECRETARIAT']
        User.objects.filter(pk=user.pk).update(secretariat=secretariat)
        user.refresh_from_db()

        data = self._get(user)
        self.assertEqual(data['perimetres']['niveaux'], ['SERVICE'])
        self.assertEqual(data['perimetres']['secretariats'], [secretariat.id])
        self.assertEqual(data['perimetres']['formations'], [formation.id])

    def test_perimetre_encadrant_via_modules_supervises(self):
        formation = Formation.objects.create(formation='Formation encadrant')
        Module.objects.create(
            formation=formation, intitule='Module encadré',
            statut='PLANIFIE', superviseur=self.users['ENCADRANT'],
        )
        data = self._get(self.users['ENCADRANT'])
        self.assertEqual(
            data['perimetres']['niveaux'], ['FORMATION', 'GROUPE', 'MODULE'],
        )
        self.assertEqual(data['perimetres']['formations'], [formation.id])

    def test_perimetre_auditeur_via_inscription(self):
        formation = Formation.objects.create(formation="Formation étudiant")
        module = Module.objects.create(
            formation=formation, intitule='Module auditeur', statut='PLANIFIE',
        )
        # Le participant peut être créé automatiquement par le câblage de
        # profil (signaux authentication) : on le réutilise si présent.
        participant = Participant.objects.filter(user=self.users['AUDITEUR']).first()
        if participant is None:
            participant = Participant.objects.create(
                matricule='CAPS-AUD-001', nom='Étudiant', prenom='Contrat',
                user=self.users['AUDITEUR'],
            )
        ModuleParticipant.objects.create(module=module, participant=participant)
        data = self._get(self.users['AUDITEUR'])
        self.assertEqual(data['perimetres']['niveaux'], ['ETUDIANT', 'PROPRE_COMPTE'])
        self.assertEqual(data['perimetres']['formations'], [formation.id])

    def test_finance_pas_de_modules_de_formation_mais_secretariats_globaux(self):
        data = self._get(self.users['FINANCE'])
        self.assertEqual(data['perimetres']['formations'], [])
        self.assertEqual(data['perimetres']['secretariats'], '*')
        self.assertIn('INJS_ENTIER', data['perimetres']['niveaux'])

    def test_groupes_concrets_du_perimetre_secretariat(self):
        secretariat = Secretariat.objects.create(nom='Sec groupes')
        user = self.users['SECRETARIAT']
        User.objects.filter(pk=user.pk).update(secretariat=secretariat)
        user.refresh_from_db()

        annee = AnneeAcademique.objects.create(
            libelle='2026-2027',
            date_debut=datetime.date(2026, 10, 1),
            date_fin=datetime.date(2027, 7, 31),
        )
        ref_formation = RefFormation.objects.create(intitule='STAPS contrat')
        ref_module = RefModule.objects.create(intitule='MODULE CONTRAT')
        ref_module.formations.add(ref_formation)
        niveau = Niveau.objects.create(code='L1C', libelle='L1 Contrat', ordre=1)
        formation = Formation.objects.create(formation='Formation groupes')
        Module.objects.create(
            formation=formation, intitule='Module groupes',
            statut='PLANIFIE', secretariat=secretariat,
            ref_module=ref_module,
        )
        groupe = Groupe.objects.create(
            annee_academique=annee, ref_formation=ref_formation,
            niveau=niveau, nom='L1-GCAPS',
        )
        data = self._get(user)
        self.assertIn(formation.id, data['perimetres']['formations'])
        self.assertEqual(data['perimetres']['groupes'], [groupe.id])

    def test_union_des_droites_en_combinaison_multi_role(self):
        # SUPERVISEUR + ENCADRANT (combinaison autorisée) : l'encadrant apporte
        # la liste des participants et les actions de présence.
        user = self.users['SUPERVISEUR']
        user.groups.add(Group.objects.get(name=ROLE_GROUP_NAMES['ENCADRANT']))
        for attr in ('_role_groups_cache',):
            if hasattr(user, attr):
                delattr(user, attr)
        data = self._get(user)
        self.assertIn('lister', data['capacites']['participants'])
        self.assertIn('agir', data['capacites']['presences'])
        self.assertEqual(sorted(data['roles']), ['ENCADRANT', 'SUPERVISEUR'])
        # Le niveau reste N2 (pas de surélévation).
        self.assertEqual(data['niveau'], 'N2')

    def test_role_context_est_inclut_pour_source_unique(self):
        data = self._get(self.users['ADMIN'])
        self.assertIn('role_context', data)
        self.assertTrue(data['role_context']['can_mutate_users'])

    def test_endpoint_documente_dans_openapi(self):
        self.client.force_authenticate(self.users['ADMIN'])
        res = self.client.get('/api/schema/?format=json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('/api/auth/capabilities/', res.json()['paths'])
