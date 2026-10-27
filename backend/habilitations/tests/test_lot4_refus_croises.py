"""Tests du LOT 4 — refus d'accès croisés du prompt §34, moteur en APPLICATION.

Le LOT 4 lève l'attente signalée par l'audit du 2026-09-14 (§11) : *« pas
encore de tests de refus sur le moteur CURP en mode APPLICATION »*. Ces tests
font donc tourner le moteur **en mode APPLICATION sur la base de test
uniquement** (``override_settings``) : le défaut livré (OFF) n'est jamais
modifié, aucune vue métier n'est branchée (cela reste le LOT 5 / U8, sur feu
vert séparé).

Cinq familles de refus croisés sont verrouillées, dans l'ordre du §34 :

1. **enseignant A ≠ enseignant B** — un enseignant n'agit que sur les modules
   de son périmètre, jamais sur ceux d'un collègue, et n'administre aucune
   fiche enseignant ;
2. **chef de département A ≠ B** — un chef de département n'agit que dans sa
   direction/département, jamais dans un autre ;
3. **étudiant A ≠ étudiant B** — un étudiant ne lit que son propre dossier,
   jamais celui d'un autre, et ne force aucun émargement ;
4. **agent scolarité ≠ administration des rôles** — un agent de scolarité ne
   crée, ne modifie ni ne valide aucun rôle/attribution (console CURP 403) ;
5. **admin SI ≠ permissions métier sensibles** — les rôles techniques (SI) ne
   portent aucun acte métier sensible ; l'administrateur système reste un rôle
   sensible à seconde signature (et l'écart J2 de sa ligne A2 est caractérisé).

Une sixième classe **verrouille le correctif L4-01** (résolution des cibles
« objet métier », posé au LOT 5) ; elle était née pour caractériser
l'écart : voir :doc:`/docs/audit/permissions` §5.

Deux garde-fous transverses ferment le fichier : l'**abstention** d'un compte
non gouverné n'est pas un refus, et le mode **OFF** livré reste un *no-op*.

Contrat de cible rappelé (``est_autorise``) : la cible nommée est un **dict**
``{'type': <type de périmètre>, 'object_id': <pk>}`` — c'est aussi le format
accepté par ``POST /api/habilitations/evaluer/``. La résolution d'un objet
métier passé directement (``has_object_permission``) est résolue depuis le
correctif L4-01 (LOT 5) : voir la classe ``CouvertureObjetEcartTests``.
"""
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from administrations.models import Departement, Direction
from formations.models import Formation, Module
from habilitations.models import (
    AttributionRole,
    CanalAcces,
    CompteUtilisateur,
    JournalHabilitation,
    PermissionMetier,
    Perimetre,
    Personne,
    RoleMetier,
)
from habilitations.permissions import ExigePermission
from habilitations.referentiel.catalogue_modules import PERMISSIONS_CRITIQUES
from habilitations.referentiel.chargement import charger_referentiel
from habilitations.services import observation
from habilitations.services.identite import generer_matricule_personne
from habilitations.services.journalisation import verifier_chaine
from habilitations.services.moteur import est_autorise
from parametres.flags import invalidate_flags_cache
from parametres.models import Parametre
from scolarite.models import DossierEtudiant

User = get_user_model()

#: Mode APPLICATION (jamais activé hors base de test : règle R3).
APPLICATION = dict(HABILITATIONS_OBSERVATION=True, HABILITATIONS_APPLICATION=True)
#: Mode OFF : le défaut livré durci (rappel explicite pour les garde-fous).
TOUT_OFF = dict(HABILITATIONS_OBSERVATION=False, HABILITATIONS_APPLICATION=False)

MOT_DE_PASSE = 'Lot4!2026curp'
FLAG_CONSOLE = 'flag.curp_ui_admin'

#: Rôles techniques « administration SI » du catalogue cible (domaine TECHNIQUE).
ROLES_SI = (
    'SUPPORT_IT', 'SYSADMIN', 'NETWORK_ADMIN', 'DB_ADMIN', 'SECURITY_ADMIN',
    'API_MANAGER',
)

#: Modules du dispositif lui-même (leurs actes critiques sont légitimes pour
#: l'administration du SI et des habilitations).
MODULES_DISPOSITIF = {'administration', 'parametres', 'exports', 'referentiels'}

#: Actes métier sensibles (§34, 5e tiret) : permissions critiques du catalogue
#: hors modules du dispositif.
ACTES_METIER_SENSIBLES = sorted(
    code for code in PERMISSIONS_CRITIQUES
    if code.split('.')[0] not in MODULES_DISPOSITIF
)


# ---------------------------------------------------------------------------
# Fabriques du LOT 4 (additives : rien ici n'est partagé avec les unités U1–U5)
# ---------------------------------------------------------------------------
def _perimetre(type_perimetre, objet=None, reference='', libelle=''):
    """Périmètre CURP typé, pointant sur un objet métier réel si fourni."""
    valeurs = {'type': type_perimetre, 'reference_lisible': reference,
               'libelle': libelle}
    if objet is not None:
        valeurs['content_type'] = ContentType.objects.get_for_model(objet.__class__)
        valeurs['object_id'] = objet.pk
    return Perimetre.objects.create(**valeurs)


def _cible(type_perimetre, objet):
    """Cible nommée au format du contrat d'API (dict type/object_id)."""
    return {'type': type_perimetre, 'object_id': objet.pk}


def _compte(username, role_code, *, niveau=None, perimetres=(),
            canal=CanalAcces.LES_DEUX, role_legacy='SECRETARIAT',
            mfa_actif=False, seconde_signature=False, nom=None, prenoms='Lot4'):
    """User + Personne + CompteUtilisateur + une attribution ACTIVE du rôle.

    ``seconde_signature`` arme ``valide_par`` (exigée par les rôles sensibles),
    ``mfa_actif`` arme la 2FA (exigée par le contrôle 6 du moteur).
    """
    user = User.objects.create_user(
        username=username, password=MOT_DE_PASSE, role=role_legacy,
        email=f'{username}@injs.ci',
    )
    personne = Personne.objects.create(
        matricule=generer_matricule_personne(),
        nom=nom or username.upper(), prenoms=prenoms,
    )
    compte = CompteUtilisateur.objects.create(
        user=user, personne=personne, statut=CompteUtilisateur.Statut.ACTIF,
        canal=canal, mfa_actif=mfa_actif,
        motif_statut='Compte de test LOT 4 (refus croisés §34).',
    )
    if role_code:
        role = RoleMetier.objects.get(code=role_code)
        attribution = AttributionRole.objects.create(
            compte=compte, role=role,
            niveau_effectif=niveau or role.niveau_defaut,
            statut=AttributionRole.Statut.ACTIVE,
            valide_par=user if seconde_signature else None,
            motif='Attribution de test LOT 4.',
        )
        if perimetres:
            attribution.perimetres.set(list(perimetres))
    return user, compte


def _requete(user, methode='get'):
    """Requête DRF forcée (même fabrique que les tests U2 du mode observation)."""
    fabrique = APIRequestFactory()
    url = '/api/lot4/sonde/'
    brute = (fabrique.get(url) if methode == 'get'
             else fabrique.post(url, {}, format='json'))
    force_authenticate(brute, user=user)
    return Request(brute)


def _drapeau_console(actif=True):
    Parametre.objects.update_or_create(
        cle=FLAG_CONSOLE,
        defaults={
            'libelle': 'Console CURP', 'categorie': 'flags', 'type': 'bool',
            'valeur': 'true' if actif else 'false',
            'valeur_defaut': 'false', 'actif': True,
        },
    )
    invalidate_flags_cache()


def _refus_journalises(compte=None):
    qs = JournalHabilitation.objects.filter(
        type_evenement=JournalHabilitation.TypeEvenement.ACCES_REFUSE)
    return qs.filter(compte_concerne=compte) if compte else qs


@override_settings(**APPLICATION)
class SocleLot4(APITestCase):
    """Référentiel chargé (81 rôles / 1 155 permissions) + compteurs à zéro."""

    @classmethod
    def setUpTestData(cls):
        charger_referentiel()

    def setUp(self):
        # LocMem : les compteurs d'observation et le cache de drapeaux
        # survivent au savepoint de test — remis à zéro systématiquement.
        from django.core.cache import cache
        cache.clear()
        observation.remettre_a_zero()
        invalidate_flags_cache()

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()
        observation.remettre_a_zero()
        super().tearDown()

    def assertAutorise(self, decision):
        self.assertTrue(decision.autorise, f'motifs inattendus : {decision.motifs}')

    def assertRefuse(self, decision, motif=None):
        self.assertFalse(decision.autorise)
        self.assertTrue(decision.gouverne)
        if motif:
            self.assertIn(motif, decision.motifs)


# ===========================================================================
# §34.1 — enseignant A ≠ enseignant B
# ===========================================================================
@override_settings(**APPLICATION)
class EnseignantCroiseTests(SocleLot4):
    """Deux enseignants, deux modules : chacun reste dans son périmètre."""

    def setUp(self):
        super().setUp()
        formation = Formation.objects.create(formation='FAB — Administration de base')
        self.module_a = Module.objects.create(
            formation=formation, intitule='Déontologie de la fonction publique')
        self.module_b = Module.objects.create(
            formation=formation, intitule='Management des organisations sportives')
        perimetre_a = _perimetre(
            Perimetre.Type.MODULE_ECUE, self.module_a,
            reference=f'MOD-{self.module_a.pk}', libelle=self.module_a.intitule)
        perimetre_b = _perimetre(
            Perimetre.Type.MODULE_ECUE, self.module_b,
            reference=f'MOD-{self.module_b.pk}', libelle=self.module_b.intitule)
        self.cible_a = _cible(Perimetre.Type.MODULE_ECUE, self.module_a)
        self.cible_b = _cible(Perimetre.Type.MODULE_ECUE, self.module_b)
        self.user_a, self.compte_a = _compte(
            'ens_a', 'ENSEIGNANT', perimetres=[perimetre_a],
            role_legacy='ENCADRANT', nom='KOUASSI')
        self.user_b, self.compte_b = _compte(
            'ens_b', 'ENSEIGNANT', perimetres=[perimetre_b],
            role_legacy='ENCADRANT', nom='DIALLO')

    def test_01_enseignant_autorise_sur_son_propre_module(self):
        decision = est_autorise(
            self.user_a, 'evaluations.note.saisir',
            canal='MOBILE', cible=self.cible_a)
        self.assertAutorise(decision)
        self.assertEqual(decision.octrois[0].role_code, 'ENSEIGNANT')
        self.assertEqual(decision.octrois[0].perimetres[0]['type'], 'MODULE_ECUE')

    def test_02_enseignant_A_refuse_sur_le_module_de_B(self):
        decision = est_autorise(
            self.user_a, 'evaluations.note.saisir',
            canal='MOBILE', cible=self.cible_b)
        self.assertRefuse(decision, 'CIBLE_HORS_PERIMETRE')

    def test_03_symetrie_le_refus_vaut_aussi_pour_B(self):
        decision = est_autorise(
            self.user_b, 'evaluations.note.saisir',
            canal='MOBILE', cible=self.cible_a)
        self.assertRefuse(decision, 'CIBLE_HORS_PERIMETRE')

    def test_04_enseignant_n_administre_pas_la_fiche_d_un_collegue(self):
        # Colonne A2 « enseignants » = N1 : lecture seule, jamais de gestion.
        self.assertRefuse(
            est_autorise(
                self.user_a, 'enseignants.enseignant.modifier', canal='MOBILE'),
            'AUCUNE_ATTRIBUTION_PERMETTANTE')

    def test_05_enseignant_ne_valide_pas_les_notes(self):
        # N2 en évaluations : saisie oui, validation non (verbe de niveau N3).
        self.assertRefuse(
            est_autorise(self.user_a, 'evaluations.note.valider', canal='MOBILE'),
            'AUCUNE_ATTRIBUTION_PERMETTANTE')

    def test_06_canal_impose_par_le_role_mobile(self):
        """Le rôle ENSEIGNANT impose le canal mobile : une demande web refuse."""
        decision = est_autorise(
            self.user_a, 'evaluations.note.saisir',
            canal='WEB', cible=self.cible_a)
        self.assertRefuse(decision, 'CANAL_IMPOSE_PAR_ROLE')

    def test_07_refus_fonctionnel_trace_au_journal_en_mode_application(self):
        """En APPLICATION, ``ExigePermission`` refuse ET journalise le refus."""
        permission = ExigePermission('evaluations.note.valider', canal='MOBILE')
        requete = _requete(self.user_a)
        self.assertFalse(permission.has_permission(requete, None))
        refus = _refus_journalises(self.compte_a)
        self.assertEqual(refus.count(), 1)
        entree = refus.first()
        self.assertEqual(entree.nouvelle_valeur['permission'], 'evaluations.note.valider')
        self.assertIn('AUCUNE_ATTRIBUTION_PERMETTANTE', entree.nouvelle_valeur['motifs'])
        self.assertEqual(entree.nouvelle_valeur['canal'], 'MOBILE')
        self.assertEqual(verifier_chaine(), [])

    def test_08_acces_autorise_ne_produit_aucun_refus_journalise(self):
        permission = ExigePermission('evaluations.note.saisir', canal='MOBILE')
        self.assertTrue(permission.has_permission(_requete(self.user_a), None))
        self.assertEqual(_refus_journalises().count(), 0)


# ===========================================================================
# §34.2 — chef de département A ≠ chef de département B
# ===========================================================================
def couverture_direction(perimetre, cible):
    """Sonde de résolveur hiérarchique Direction → Département (LOT 4).

    Le moteur accepte une fonction de couverture par le contexte (contrôle 9).
    Depuis le LOT 5, un résolveur hiérarchique est **livré par défaut**
    (``services/resolveurs.py``) ; cette sonde reste la preuve que la voie
    d'injection est utilisable et prioritaire, sans fork du moteur.
    """
    if perimetre.type != Perimetre.Type.DIRECTION or perimetre.object_id is None:
        return False
    if isinstance(cible, Departement):
        return cible.direction_id == perimetre.object_id
    if isinstance(cible, Direction):
        return cible.pk == perimetre.object_id
    if isinstance(cible, dict):
        return (cible.get('type') == Perimetre.Type.DIRECTION
                and str(cible.get('object_id')) == str(perimetre.object_id))
    return False


@override_settings(**APPLICATION)
class ChefDepartementCroiseTests(SocleLot4):
    """Deux directions, deux départements, deux chefs : cloisonnement."""

    def setUp(self):
        super().setUp()
        self.direction_a = Direction.objects.create(
            code='DG', libelle='Direction générale', ordre=1)
        self.direction_b = Direction.objects.create(
            code='DAE', libelle='Direction des études', ordre=2)
        self.departement_a = Departement.objects.create(
            code='DEPT-SPORT', libelle='Département sports',
            direction=self.direction_a)
        self.departement_b = Departement.objects.create(
            code='DEPT-ADMIN', libelle='Département administration',
            direction=self.direction_b)
        perimetre_a = _perimetre(
            Perimetre.Type.DIRECTION, self.direction_a,
            reference=self.direction_a.code, libelle=self.direction_a.libelle)
        perimetre_b = _perimetre(
            Perimetre.Type.DIRECTION, self.direction_b,
            reference=self.direction_b.code, libelle=self.direction_b.libelle)
        self.cible_a = _cible(Perimetre.Type.DIRECTION, self.direction_a)
        self.cible_b = _cible(Perimetre.Type.DIRECTION, self.direction_b)
        self.user_a, self.compte_a = _compte(
            'chef_a', 'CHEF_DEPARTEMENT', perimetres=[perimetre_a],
            role_legacy='CHEF_SECRETARIAT', nom='TRAORE')
        self.user_b, self.compte_b = _compte(
            'chef_b', 'CHEF_DEPARTEMENT', perimetres=[perimetre_b],
            role_legacy='CHEF_SECRETARIAT', nom='SOW')

    def test_01_chef_A_autorise_dans_sa_direction(self):
        self.assertAutorise(est_autorise(
            self.user_a, 'scolarite.groupe.modifier', cible=self.cible_a))

    def test_02_chef_A_refuse_dans_la_direction_de_B(self):
        self.assertRefuse(
            est_autorise(
                self.user_a, 'scolarite.groupe.modifier', cible=self.cible_b),
            'CIBLE_HORS_PERIMETRE')

    def test_03_chef_A_refuse_sur_le_departement_d_une_autre_direction(self):
        self.assertRefuse(
            est_autorise(
                self.user_a, 'pedagogie.maquette.consulter',
                cible=_cible(Perimetre.Type.DIRECTION, self.direction_b)),
            'CIBLE_HORS_PERIMETRE')

    def test_04_symetrie_pour_le_chef_B(self):
        self.assertRefuse(
            est_autorise(
                self.user_b, 'scolarite.groupe.modifier', cible=self.cible_a),
            'CIBLE_HORS_PERIMETRE')

    def test_05_sonde_hierarchique_couvre_le_departement_rattache(self):
        """Résolveur de couverture injecté : oui chez soi, non chez l'autre."""
        contexte = {'couverture': couverture_direction}
        self.assertAutorise(est_autorise(
            self.user_a, 'scolarite.groupe.modifier',
            cible=self.departement_a, contexte=contexte))
        self.assertRefuse(
            est_autorise(
                self.user_a, 'scolarite.groupe.modifier',
                cible=self.departement_b, contexte=contexte),
            'CIBLE_HORS_PERIMETRE')

    def test_06_chef_de_departement_ne_valide_pas_un_jury(self):
        # Rôle cible J2 : aucune colonne « jurys » dans sa matrice.
        self.assertRefuse(
            est_autorise(self.user_a, 'jurys.pv.signer'),
            'AUCUNE_ATTRIBUTION_PERMETTANTE')

    def test_07_chef_de_departement_ne_cree_pas_de_role(self):
        # Colonne « administration » N2 (J2) : créer oui, administrer/supprimer non.
        self.assertAutorise(
            est_autorise(self.user_a, 'administration.compte.consulter'))
        self.assertRefuse(
            est_autorise(self.user_a, 'administration.role.supprimer'),
            'AUCUNE_ATTRIBUTION_PERMETTANTE')

    def test_08_refus_trace_au_journal_pour_le_compte_concerne(self):
        permission = ExigePermission('administration.role.supprimer')
        self.assertFalse(permission.has_permission(_requete(self.user_a), None))
        refus = _refus_journalises(self.compte_a)
        self.assertEqual(refus.count(), 1)
        self.assertEqual(verifier_chaine(), [])


# ===========================================================================
# §34.3 — étudiant A ≠ étudiant B
# ===========================================================================
@override_settings(**APPLICATION)
class EtudiantCroiseTests(SocleLot4):
    """Deux dossiers étudiants : chacun n'accède qu'au sien (PROPRE_COMPTE)."""

    def setUp(self):
        super().setUp()
        self.dossier_a = self._dossier('ETU-L4-A', 'KOUAME', 'Aya')
        self.dossier_b = self._dossier('ETU-L4-B', 'BAMBA', 'Moussa')
        perimetre_a = _perimetre(
            Perimetre.Type.ETUDIANT, self.dossier_a,
            reference='ETU-L4-A', libelle='Dossier Aya KOUAME')
        self.cible_a = _cible(Perimetre.Type.ETUDIANT, self.dossier_a)
        self.cible_b = _cible(Perimetre.Type.ETUDIANT, self.dossier_b)
        self.user_a, self.compte_a = _compte(
            'etu_a', 'ETUDIANT', perimetres=[perimetre_a],
            role_legacy='AUDITEUR', nom='KOUAME', prenoms='Aya')
        self.user_b, self.compte_b = _compte(
            'etu_b', 'ETUDIANT', role_legacy='AUDITEUR',
            nom='BAMBA', prenoms='Moussa')

    @staticmethod
    def _dossier(matricule, nom, prenom):
        from formations.models import Participant
        participant = Participant.objects.create(
            matricule=matricule, nom=nom, prenom=prenom,
            email=f'{matricule.lower()}@injs.ci')
        return DossierEtudiant.objects.create(participant=participant)

    def test_01_etudiant_consulte_son_propre_dossier(self):
        decision = est_autorise(
            self.user_a, 'scolarite.dossier_etudiant.consulter',
            canal='MOBILE', cible=self.cible_a)
        self.assertAutorise(decision)

    def test_02_etudiant_A_ne_consulte_pas_le_dossier_de_B(self):
        self.assertRefuse(
            est_autorise(
                self.user_a, 'scolarite.dossier_etudiant.consulter',
                canal='MOBILE', cible=self.cible_b),
            'CIBLE_HORS_PERIMETRE')

    def test_03_symetrie_pour_l_etudiant_B(self):
        self.assertRefuse(
            est_autorise(
                self.user_b, 'scolarite.dossier_etudiant.consulter',
                canal='MOBILE', cible=self.cible_a),
            'CIBLE_HORS_PERIMETRE')

    def test_04_etudiant_ne_modifie_pas_son_dossier(self):
        # N1 : lecture et auto-démarche seulement, jamais la modification.
        self.assertRefuse(
            est_autorise(
                self.user_a, 'scolarite.dossier_etudiant.modifier',
                canal='MOBILE', cible=self.cible_a),
            'AUCUNE_ATTRIBUTION_PERMETTANTE')

    def test_05_etudiant_ne_force_aucun_emargement(self):
        self.assertRefuse(
            est_autorise(self.user_a, 'presences.emargement.forcer', canal='MOBILE'),
            'AUCUNE_ATTRIBUTION_PERMETTANTE')

    def test_06_etudiant_depose_un_justificatif_sur_son_compte(self):
        # Acte d'auto-démarche (PERMISSIONS_USAGERS) malgré le niveau N1.
        self.assertAutorise(est_autorise(
            self.user_a, 'presences.justificatif.deposer', canal='MOBILE'))

    def test_07_perimetre_propre_compte_seul_ne_couvre_pas_une_cible(self):
        """PROPRE_COMPTE est global : sans périmètre nommé, aucune cible."""
        self.assertRefuse(
            est_autorise(
                self.user_b, 'scolarite.dossier_etudiant.consulter',
                canal='MOBILE', cible=self.cible_b),
            'CIBLE_HORS_PERIMETRE')

    def test_08_canal_web_refuse_a_un_compte_mobile(self):
        compte = CompteUtilisateur.objects.get(pk=self.compte_a.pk)
        compte.canal = CanalAcces.MOBILE
        compte.save(update_fields=['canal'])
        self.assertRefuse(
            est_autorise(
                self.user_a, 'scolarite.dossier_etudiant.consulter', canal='WEB'),
            'CANAL_NON_AUTORISE')


# ===========================================================================
# §34.4 — agent scolarité ≠ administration des rôles
# ===========================================================================
@override_settings(**APPLICATION)
class AgentScolariteTests(SocleLot4):
    """Un agent de scolarité n'administre ni les rôles ni les attributions."""

    def setUp(self):
        super().setUp()
        from formations.models import Secretariat
        self.secretariat = Secretariat.objects.create(
            numero='SECR-L4-A', nom='Secrétariat LOT 4')
        perimetre = _perimetre(
            Perimetre.Type.SECRETARIAT, self.secretariat,
            reference=self.secretariat.numero, libelle=self.secretariat.nom)
        self.cible_secretariat = _cible(
            Perimetre.Type.SECRETARIAT, self.secretariat)
        self.user, self.compte = _compte(
            'agent_scol', 'SCOLARITE', perimetres=[perimetre],
            role_legacy='SECRETARIAT', nom='CONDE')
        self.admin = User.objects.create_user(
            username='adm_l4', password=MOT_DE_PASSE, role='ADMIN', is_staff=True)

    def test_01_agent_ne_cree_pas_de_role(self):
        self.assertRefuse(
            est_autorise(self.user, 'administration.role.creer'),
            'AUCUNE_ATTRIBUTION_PERMETTANTE')

    def test_02_agent_ne_valide_pas_une_attribution(self):
        self.assertRefuse(
            est_autorise(self.user, 'administration.attribution.valider'),
            'AUCUNE_ATTRIBUTION_PERMETTANTE')

    def test_03_agent_n_administre_pas_la_politique_de_securite(self):
        self.assertRefuse(
            est_autorise(self.user, 'administration.politique.administrer'),
            'AUCUNE_ATTRIBUTION_PERMETTANTE')

    def test_04_frontiere_lecture_seule_du_module_administration(self):
        # Colonne A2 « administration » = N1 pour SCOLARITE : lecture admise,
        # écriture refusée (le refus ci-dessus est bien un refus de niveau).
        self.assertAutorise(
            est_autorise(self.user, 'administration.compte.consulter'))

    def test_05_agent_garde_son_perimetre_de_scolarite(self):
        self.assertAutorise(est_autorise(
            self.user, 'scolarite.inscription_administrative.creer',
            cible=self.cible_secretariat))

    def test_06_agent_hors_de_son_secretariat_est_refuse(self):
        from formations.models import Secretariat
        autre = Secretariat.objects.create(numero='SECR-L4-B', nom='Autre secrétariat')
        self.assertRefuse(
            est_autorise(
                self.user, 'scolarite.inscription_administrative.creer',
                cible=_cible(Perimetre.Type.SECRETARIAT, autre)),
            'CIBLE_HORS_PERIMETRE')

    def test_07_console_des_comptes_refusee_meme_drapeau_ouvert(self):
        _drapeau_console(True)
        self.client.force_authenticate(self.user)
        self.assertEqual(
            self.client.get('/api/habilitations/comptes/').status_code, 403)
        self.assertEqual(
            self.client.post(
                '/api/habilitations/comptes/',
                {'identifiants': {'username': 'x', 'mot_de_passe': 'Essai#2026',
                                  'role_legacy': 'SECRETARIAT'},
                 'motif': 'Tentative hors périmètre.'},
                format='json').status_code, 403)

    def test_08_admin_accede_a_la_console_dans_le_meme_contexte(self):
        _drapeau_console(True)
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.get('/api/habilitations/comptes/').status_code, 200)

    def test_09_refus_par_la_permission_drf_sur_un_acte_administration(self):
        permission = ExigePermission('administration.role.creer')
        self.assertFalse(permission.has_permission(_requete(self.user), None))
        self.assertEqual(_refus_journalises(self.compte).count(), 1)
        self.assertEqual(verifier_chaine(), [])


# ===========================================================================
# §34.5 — admin SI ≠ permissions métier sensibles
# ===========================================================================
@override_settings(**APPLICATION)
class AdminSiTests(SocleLot4):
    """Les rôles techniques gouvernent la plateforme, pas les actes métier."""

    def test_01_roles_si_sans_acte_metier_sensible_au_catalogue(self):
        for code in ROLES_SI:
            role = RoleMetier.objects.get(code=code)
            porte = set(role.permissions.values_list('code', flat=True))
            sensibles = sorted(porte & set(ACTES_METIER_SENSIBLES))
            self.assertEqual(
                sensibles, [],
                f'{code} porte des actes métier sensibles : {sensibles}')

    def test_02_roles_si_hors_modules_metier(self):
        # Aucun module métier dans la matrice des rôles SI (parametres, plus
        # statistiques/exports pour SECURITY_ADMIN, référentiels dérivé).
        for code in ROLES_SI:
            role = RoleMetier.objects.get(code=code)
            modules = set(role.permissions.values_list('module', flat=True))
            interdits = modules & {
                'jurys', 'diplomation', 'finances_etud', 'evaluations',
                'scolarite', 'presences',
            }
            self.assertEqual(interdits, set(), f'{code} déborde sur {interdits}')

    def test_03_sysadmin_refuse_sur_un_paiement(self):
        user, _ = _compte(
            'sysadmin_l4', 'SYSADMIN', role_legacy='ADMIN',
            mfa_actif=True, seconde_signature=True, nom='KOFFI')
        self.assertRefuse(
            est_autorise(user, 'finances_etud.paiement.valider'),
            'AUCUNE_ATTRIBUTION_PERMETTANTE')

    def test_04_sysadmin_garde_la_main_sur_les_parametres(self):
        user, _ = _compte(
            'sysadmin_l4b', 'SYSADMIN', role_legacy='ADMIN',
            mfa_actif=True, seconde_signature=True, nom='KOFFI')
        self.assertAutorise(
            est_autorise(user, 'parametres.parametre.administrer'))

    def test_05_role_sensible_exige_la_seconde_signature(self):
        """SYSADMIN sans seconde signature : refus motivé (contrôle 7)."""
        user, _ = _compte(
            'sysadmin_l4c', 'SYSADMIN', role_legacy='ADMIN',
            mfa_actif=True, seconde_signature=False, nom='KOFFI')
        self.assertRefuse(
            est_autorise(user, 'parametres.parametre.administrer'),
            'ROLE_SENSIBLE_SANS_SECONDE_SIGNATURE')

    def test_06_role_sensible_exige_le_mfa_actif(self):
        user, _ = _compte(
            'sysadmin_l4d', 'SYSADMIN', role_legacy='ADMIN',
            mfa_actif=False, seconde_signature=True, nom='KOFFI')
        self.assertRefuse(
            est_autorise(user, 'parametres.parametre.administrer'),
            'MFA_REQUIS_NON_ACTIF')

    def test_07_db_admin_ne_touche_pas_aux_dossiers_etudiants(self):
        user, compte = _compte(
            'dba_l4', 'DB_ADMIN', role_legacy='ADMIN',
            mfa_actif=True, seconde_signature=True, nom='SANOGO')
        self.assertRefuse(
            est_autorise(user, 'scolarite.dossier_etudiant.modifier'),
            'AUCUNE_ATTRIBUTION_PERMETTANTE')
        self.assertEqual(
            AttributionRole.objects.filter(compte=compte).count(), 1)

    def test_08_ecart_j2_ligne_a2_de_admin_systeme_a_arbitrer(self):
        """Caractérisation d'un écart de données, PAS une cible validée.

        La ligne A2 d'``ADMIN_SYSTEME`` est ``{module: N4}`` sur les quinze
        modules de la matrice : ce rôle porte donc aussi les actes métier
        critiques (signature de PV, validation de diplôme, validation de
        paiement), alors que sa description catalogue dit l'inverse
        (« sans intervenir sur les décisions métier »). L'audit du 2026-09-14
        (§12, ligne 17) renvoie cette contradiction à l'atelier J2 : la règle
        « ne pas contourner les validations métier » reste à formaliser.
        Ce test verrouille l'état livré pour qu'aucune décision implicite ne
        le modifie ; si l'atelier restreint la ligne A2, il doit échouer et
        être mis à jour avec la documentation (docs/security/RBAC.md §6).
        """
        user, _ = _compte(
            'adm_sys_l4', 'ADMIN_SYSTEME', role_legacy='ADMIN',
            mfa_actif=True, seconde_signature=True, nom='ADMIN')
        # Son domaine légitime : l'administration du dispositif.
        self.assertAutorise(est_autorise(user, 'administration.role.creer'))
        # Écart caractérisé : les actes métier critiques sont aujourd'hui
        # couverts par la ligne A2 N4 globale (double validation requise).
        for code in ('jurys.pv.signer', 'diplomation.diplome.valider',
                     'finances_etud.paiement.valider'):
            self.assertAutorise(est_autorise(user, code))
            self.assertTrue(
                PermissionMetier.objects.get(code=code).necessite_double_validation)
        self.assertIn(code, ACTES_METIER_SENSIBLES)


# ===========================================================================
# Écart L4-01 corrigé au LOT 5 — résolution des cibles « objet métier » verrouillée
# ===========================================================================
@override_settings(**APPLICATION)
class CouvertureObjetEcartTests(SocleLot4):
    """Verrouille le correctif L4-01 (classe née caractérisation, inversée au LOT 5).

    ``est_autorise`` accepte deux formes de cible : le dict du contrat d'API
    ``{'type', 'object_id'}`` et l'objet métier lui-même (celui que DRF
    transmet à ``has_object_permission``). Les **deux formes sont résolues**
    depuis le LOT 5 : ``moteur._decrire_perimetre`` expose ``content_type_id``
    et ``id`` et le contrôle 9 rapproche alors les périmètres sérialisés des
    objets, par type+pk exacts d'abord, règle générique ``SECRETARIAT``
    ensuite, ancêtres hiérarchiques enfin (``services/resolveurs.py``).

    Cette classe affirmait l'inverse pour rendre l'écart visible (écarts
    numérotés, ``docs/audit/permissions.md`` §5) ; elle garantit désormais sa
    non-régression. La voie du résolveur injecté reste l'extension prévue du
    moteur, sans fork.
    """

    def setUp(self):
        super().setUp()
        from formations.models import Secretariat
        self.secretariat = Secretariat.objects.create(
            numero='SECR-L4-EC', nom='Secrétariat écart')
        self.hors_perimetre = Secretariat.objects.create(
            numero='SECR-L4-HS', nom='Secrétariat voisin')
        perimetre = _perimetre(
            Perimetre.Type.SECRETARIAT, self.secretariat,
            reference=self.secretariat.numero)
        self.user, self.compte = _compte(
            'agent_ecart', 'SCOLARITE', perimetres=[perimetre],
            role_legacy='SECRETARIAT', nom='OUATTARA')
        self.permission = 'scolarite.inscription_administrative.creer'

    def test_01_cible_dict_et_cible_objet_toutes_deux_couvertes(self):
        en_dict = est_autorise(
            self.user, self.permission,
            cible=_cible(Perimetre.Type.SECRETARIAT, self.secretariat))
        self.assertAutorise(en_dict)
        en_objet = est_autorise(
            self.user, self.permission, cible=self.secretariat)
        self.assertAutorise(en_objet)

    def test_02_objet_hors_perimetre_toujours_refuse(self):
        """Le correctif n'élargit rien hors des ancêtres connus : pas d'accord, pas d'accès."""
        decision = est_autorise(
            self.user, self.permission, cible=self.hors_perimetre)
        self.assertRefuse(decision, 'CIBLE_HORS_PERIMETRE')

    def test_03_la_description_du_perimetre_porte_le_content_type(self):
        """Trace du correctif : ``content_type_id`` et ``id`` sont exposés."""
        from habilitations.services.moteur import _decrire_perimetre
        decrit = _decrire_perimetre(
            self.compte.attributions.first().perimetres.first())
        self.assertEqual(decrit['type'], Perimetre.Type.SECRETARIAT)
        self.assertEqual(decrit['object_id'], self.secretariat.pk)
        self.assertEqual(
            decrit['content_type_id'],
            ContentType.objects.get_for_model(self.secretariat).pk)
        self.assertIsNotNone(decrit['id'])

    def test_04_has_object_permission_accorde_puis_refuse_en_le_journalisant(self):
        """La voie DRF est opérationnelle : couvert → oui ; hors → refus tracé."""
        permission = ExigePermission(self.permission)
        self.assertTrue(
            permission.has_object_permission(
                _requete(self.user), None, self.secretariat))
        self.assertEqual(_refus_journalises(self.compte).count(), 0)
        self.assertFalse(
            permission.has_object_permission(
                _requete(self.user), None, self.hors_perimetre))
        refus = _refus_journalises(self.compte)
        self.assertEqual(refus.count(), 1)
        entree = refus.first()
        self.assertEqual(entree.objet_type, 'formations.secretariat')
        self.assertEqual(entree.object_id, str(self.hors_perimetre.pk))
        self.assertEqual(verifier_chaine(), [])

    def test_05_un_resolveur_injecte_reste_la_voie_d_extensibilite(self):
        """Une couverture maison injectée a toujours priorité sur le défaut."""
        def couverture(perimetre, cible):
            return (perimetre.type == Perimetre.Type.SECRETARIAT
                    and str(perimetre.object_id) == str(getattr(cible, 'pk', '')))

        self.assertAutorise(est_autorise(
            self.user, self.permission, cible=self.secretariat,
            contexte={'couverture': couverture}))


# ===========================================================================
# Garde-fous transverses (R3 : le dispositif livré reste inerte)
# ===========================================================================
@override_settings(**APPLICATION)
class GardeFousLot4Tests(SocleLot4):
    def test_01_compte_non_gouverne_s_abstient_et_n_est_pas_refuse(self):
        """Sans profil CURP, le moteur s'abstient : le legacy décide seul."""
        user = User.objects.create_user(
            username='legacy_l4', password=MOT_DE_PASSE, role='SECRETARIAT')
        decision = est_autorise(user, 'administration.role.creer')
        self.assertFalse(decision.gouverne)
        self.assertFalse(decision.autorise)
        self.assertTrue(
            ExigePermission('administration.role.creer').has_permission(
                _requete(user), None))
        self.assertEqual(_refus_journalises().count(), 0)

    def test_02_compte_suspendu_est_refuse(self):
        user, compte = _compte(
            'sus_l4', 'CHEF_DEPARTEMENT', role_legacy='CHEF_SECRETARIAT')
        compte.statut = CompteUtilisateur.Statut.SUSPENDU
        compte.save(update_fields=['statut'])
        self.assertRefuse(
            est_autorise(user, 'scolarite.groupe.modifier'), 'COMPTE_SUSPENDU')

    def test_03_anonyme_est_refuse(self):
        from django.contrib.auth.models import AnonymousUser
        decision = est_autorise(AnonymousUser(), 'scolarite.groupe.modifier')
        self.assertFalse(decision.autorise)
        self.assertFalse(decision.gouverne)
        self.assertIn('NON_AUTHENTIFIE', decision.motifs)

    @override_settings(**TOUT_OFF)
    def test_04_mode_off_reste_un_noop_total(self):
        """Aucun refus ne peut être produit tant que le défaut livré tient."""
        user, _ = _compte('off_l4', 'ETUDIANT', role_legacy='AUDITEUR')
        permission = ExigePermission('administration.role.creer')
        self.assertTrue(permission.has_permission(_requete(user), None))
        self.assertTrue(
            permission.has_object_permission(_requete(user), None, object()))
        self.assertEqual(_refus_journalises().count(), 0)

    def test_05_les_refus_ci_dessus_sont_bien_produits_en_mode_application(self):
        """Le mode lu pendant ces tests est APPLICATION (jamais le défaut)."""
        from habilitations.services.codes import MODE_APPLICATION
        from habilitations.services.moteur import mode_moteur
        self.assertEqual(mode_moteur(), MODE_APPLICATION)

    def test_06_le_defaut_livre_est_inerte(self):
        """R3 : le dépôt livre ``HABILITATIONS_APPLICATION=false``.

        La valeur lue ici est celle du **module** ``config.settings``
        (calculée à l'import depuis l'environnement) : ``override_settings``
        ne la modifie pas, c'est donc bien le défaut livré qui est vérifié.
        """
        import config.settings as module_reglages
        self.assertFalse(module_reglages.HABILITATIONS_APPLICATION)
