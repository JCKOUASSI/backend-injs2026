"""Jeux de données réutilisables pour les tests U5 (non découvert comme test).

Centralise le chargement du référentiel U3, la gestion des drapeaux et la
création des comptes/objets métier minimaux utilisés par les sondes.
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from habilitations.models import (
    CanalAcces,
    AttributionRole,
    CompteUtilisateur,
    RoleMetier,
)
from parametres.flags import invalidate_flags_cache
from parametres.models import Parametre

User = get_user_model()

#: Drapeaux du dispositif U5 (livrés éteints).
F_MAITRE = 'flag.curp_provisionnement_auto'
F_ADMISSION = 'flag.curp_declencheur_admission'
F_INSCRIPTION = 'flag.curp_declencheur_inscription'
F_RECRUTEMENT = 'flag.curp_declencheur_recrutement'
F_AFFECTATION = 'flag.curp_declencheur_affectation_enseignant'
F_FIN_RELATION = 'flag.curp_declencheur_fin_relation'
F_JURY = 'flag.curp_declencheur_jury'
F_INACTIVITE = 'flag.curp_suspension_inactivite'
F_EXPIRATION = 'flag.curp_expiration_auto'
F_IMPORT = 'flag.curp_import_masse'
F_UI = 'flag.curp_ui_admin'
TOUS_F_SONDES = [F_MAITRE, F_ADMISSION, F_INSCRIPTION, F_RECRUTEMENT,
                 F_AFFECTATION, F_FIN_RELATION, F_JURY]


def referentiel_charge():
    from habilitations.referentiel.chargement import charger_referentiel
    charger_referentiel()


def admin(username='admin5', role='ADMIN'):
    """Administrateur de test, idempotent.

    Le `username` est la contrainte d'unicité de la table utilisateur : deux
    creations successives du MÊME nom dans une même transaction de test
    levaient une `IntegrityError`. La fixture est donc réutilisée si elle
    existe déjà (un test peut légitimement appeler `fx.admin()` plusieurs fois,
    ou une seconde fois depuis un `setUp` qui l'a déjà appelée).
    """
    user, cree = User.objects.get_or_create(
        username=username,
        defaults={
            'role': role, 'is_staff': True,
        },
    )
    if cree:
        user.set_password('Mot#2026x')
        user.save(update_fields=['password'])
    return user


#: Rôle RBAC utilisé quand une fixture demande l'ancien pseudo-rôle métier
#: `PERSONNEL`, qui n'appartient pas aux 12 rôles canoniques INJS-LMD.
ROLE_RBAC_DEFAUT = User.Role.SECRETARIAT


def positionner_flag(cle, actif):
    Parametre.objects.update_or_create(
        cle=cle,
        defaults={
            'libelle': cle, 'categorie': 'flags', 'type': 'bool',
            'valeur': 'true' if actif else 'false',
            'valeur_defaut': 'false', 'actif': True,
        },
    )
    invalidate_flags_cache()


def ouvrir(*cles):
    for cle in cles:
        positionner_flag(cle, True)


def compte_curp(username, role_code=None, statut=CompteUtilisateur.Statut.ACTIF,
                role_legacy='PERSONNEL', cree_par=None, niveau='N2',
                canal=CanalAcces.WEB, **champs):
    """Crée un User + profil CURP direct (pour les tests de services).

    `role_legacy` alimente `User.role`, qui n'accepte que les 12 rôles RBAC
    INJS-LMD (contrainte `auth_user_role_canonique_l4b`, lot L4b). La valeur
    historique `PERSONNEL` était un rôle métier CURP, jamais un rôle RBAC :
    elle est désormais mappée sur `SECRETARIAT`, qui joue exactement le même
    rôle de « compte opérationnel » dans ces tests. Le rôle métier reste porté
    par `role_code` / `AttributionRole`, comme dans le modèle cible.
    """
    role_rbac = ROLE_RBAC_DEFAUT if role_legacy == 'PERSONNEL' else role_legacy
    user = User.objects.create_user(
        username=username, password='Mot#2026x', role=role_rbac,
        is_active=statut == CompteUtilisateur.Statut.ACTIF,
    )
    compte = CompteUtilisateur.objects.create(
        user=user, statut=statut, canal=canal, cree_par=cree_par, **champs,
    )
    if role_code:
        role = RoleMetier.objects.get(code=role_code)
        AttributionRole.objects.create(
            compte=compte, role=role, niveau_effectif=niveau,
            motif='Attribution de jeu de test U5.',
            statut=AttributionRole.Statut.ACTIVE,
            date_debut=timezone.localdate(),
        )
    return compte


def cadre_academique():
    """Année, formation, niveau et semestre minimaux."""
    from formations.models import RefFormation
    from scolarite.models import AnneeAcademique, Niveau, Semestre
    annee = AnneeAcademique.objects.create(
        libelle='2025-2026',
        date_debut=date(2025, 10, 1), date_fin=date(2026, 7, 31),
    )
    formation = RefFormation.objects.create(intitule='Licence Sciences de l’éducation')
    niveau = Niveau.objects.create(code='L1', libelle='Licence 1')
    semestre = Semestre.objects.create(niveau=niveau, numero=1, libelle='S1')
    return annee, formation, niveau, semestre


def admission_admise(annee, formation, niveau, matricule='CAND2026001',
                     decision='ADMIS', avec_participant=False):
    from admissions.models import Admission, Candidat, Candidature
    from formations.models import Participant
    candidat = Candidat.objects.create(
        nom='Kouassi', prenom='Awa', email='awa.kouassi@example.ci',
        telephone='0700000001',
    )
    participant = None
    if avec_participant:
        participant = Participant.objects.create(
            matricule=matricule, nom='Kouassi', prenom='Awa',
            email='awa.kouassi@example.ci',
        )
        candidat.participant = participant
        candidat.save(update_fields=['participant'])
    candidature = Candidature.objects.create(
        candidat=candidat, annee_academique=annee, ref_formation=formation,
        niveau=niveau, statut=Candidature.Statut.ADMIS,
    )
    admission = Admission.objects.create(
        candidature=candidature,
        candidat=candidat, annee_academique=annee, ref_formation=formation,
        niveau=niveau, decision=decision,
        reference_decision=f'DEC-{matricule}',
    )
    return admission, candidat, participant


def inscription_validee(annee, formation, niveau, matricule='ETU2026001',
                        statut='VALIDEE', avec_user=False):
    from formations.models import Participant
    from scolarite.models import DossierEtudiant, InscriptionAdministrative
    participant = Participant.objects.create(
        matricule=matricule, nom='Traoré', prenom='Ibrahim',
        email='ib.traore@example.ci',
    )
    if avec_user:
        participant.user = User.objects.create_user(
            username=matricule.lower(), password='Mot#2026x',
            role='AUDITEUR', is_active=False,
        )
        participant.save(update_fields=['user'])
    dossier = DossierEtudiant.objects.create(participant=participant)
    ia = InscriptionAdministrative.objects.create(
        etudiant=dossier, annee_academique=annee, ref_formation=formation,
        niveau=niveau, statut=statut,
    )
    return ia, participant


def agent_actif(matricule='AG001', date_entree=None, date_sortie=None,
                avec_compte=False, role_code=None, cree_par=None):
    from ressources_humaines.models import Agent
    user = User.objects.create_user(
        username=matricule.lower(), password='Mot#2026x', role=ROLE_RBAC_DEFAUT,
    ) if avec_compte else None
    agent = Agent.objects.create(
        matricule=matricule, nom='Diallo', prenom='Mamadou',
        email=f'{matricule.lower()}@injs.ci', telephone='0700000002',
        statut='ACTIF', date_entree=date_entree or date(2026, 1, 5),
        date_sortie=date_sortie, user=user,
    )
    compte = None
    if avec_compte and user is not None:
        compte = CompteUtilisateur.objects.create(
            user=user, statut=CompteUtilisateur.Statut.ACTIF,
            canal=CanalAcces.WEB, cree_par=cree_par,
            date_activation=timezone.now(),
        )
        if role_code:
            role = RoleMetier.objects.get(code=role_code)
            AttributionRole.objects.create(
                compte=compte, role=role, niveau_effectif='N2',
                motif='Attribution de jeu de test U5.',
                statut=AttributionRole.Statut.ACTIVE,
                date_debut=timezone.localdate(),
            )
    return agent, user, compte


def membre_jury(annee, formation, niveau, user=None, fonction='MEMBRE',
                username='jury001', legacy_role='FORMATEUR',
                avec_compte=False, role_code=None, cree_par=None,
                type_session='NORMALE', version=1):
    """Session de jury (maquette verrouillée) + membre désigné (historisé).

    - ``user`` : utilisateur métier existant (sinon créé par le jeu) ;
    - ``avec_compte`` : un profil CURP ACTIF porte l'utilisateur.
    Retourne ``(membre, session, user)``.
    """
    from jurys.models import MembreJury, SessionJury
    from scolarite.models import Maquette
    maquette = Maquette.objects.create(
        annee_academique=annee, ref_formation=formation, niveau=niveau,
        version=version, statut=Maquette.Statut.VALIDEE,
        libelle='Maquette de jeu de test U5.',
    )
    session = SessionJury.objects.create(
        annee_academique=annee, ref_formation=formation, niveau=niveau,
        maquette=maquette, type_session=type_session,
        statut=SessionJury.Statut.DELIBERATION,
    )
    if user is None:
        user = User.objects.create_user(
            username=username, password='Mot#2026x', role=legacy_role,
            first_name='Aïcha', last_name='Koné',
            email=f'{username}@injs.ci',
        )
    if avec_compte:
        compte = CompteUtilisateur.objects.create(
            user=user, statut=CompteUtilisateur.Statut.ACTIF,
            canal=CanalAcces.WEB, cree_par=cree_par,
            date_activation=timezone.now(),
        )
        if role_code:
            role = RoleMetier.objects.get(code=role_code)
            AttributionRole.objects.create(
                compte=compte, role=role, niveau_effectif='N2',
                motif='Attribution de jeu de test U5.',
                statut=AttributionRole.Statut.ACTIVE,
                date_debut=timezone.localdate(),
            )
    membre = MembreJury.objects.create(session=session, user=user,
                                       fonction=fonction)
    return membre, session, user


def affectation_enseignant(annee, formation, niveau, semestre,
                           badge='ENS001', statut='VALIDEE'):
    from formations.models import Formateur
    from scolarite.models import AffectationPedagogique
    formateur = Formateur.objects.create(
        numerobadge=badge, nom='N’Guessan', prenom='Koffi',
        email=f'{badge.lower()}@injs.ci', telephone='0700000003',
    )
    affectation = AffectationPedagogique.objects.create(
        annee_academique=annee, ref_formation=formation, niveau=niveau,
        semestre=semestre, enseignant=formateur, statut=statut,
    )
    return affectation, formateur
