"""C1 — Jeux de données de référence pour les tests des évaluations.

Construction d'un périmètre LMD **réel** (année, formation, niveau,
semestre, maquette, UE, ECUE, affectation, inscription) en respectant
l'ordre imposé par les garde-fous de ``scolarite`` :

    maquette BROUILLON → UE → ECUE → validation → activation
    → affectation pédagogique → inscription pédagogique

Aucune donnée existante n'est modifiée : tout est créé en base de test.
"""
from datetime import date
import uuid

from django.contrib.auth import get_user_model
from django.utils import timezone

from formations.models import Formateur, Participant, RefFormation, RefSite
from scolarite.models import (
    AffectationPedagogique,
    AnneeAcademique,
    DossierEtudiant,
    ECUE,
    Groupe,
    InscriptionAdministrative,
    InscriptionPedagogique,
    Maquette,
    Niveau,
    Semestre,
    UE,
)

User = get_user_model()


def creer_annee(libelle='2026-2027', courante=True):
    return AnneeAcademique.objects.create(
        libelle=libelle,
        date_debut=date(2026, 10, 1),
        date_fin=date(2027, 9, 30),
        courante=courante,
    )


def creer_ref_formation(code='L1-LSF', intitule='Licence 1 — Lettres'):
    return RefFormation.objects.create(code=code, intitule=intitule)


def creer_niveau(code='L1', credits_requis=60):
    return Niveau.objects.create(
        code=code, libelle=f'Niveau {code}', cycle=Niveau.Cycle.LICENCE,
        ordre=1, credits_requis=credits_requis,
    )


def creer_semestre(niveau, numero=1, libelle='S1'):
    return Semestre.objects.create(niveau=niveau, numero=numero, libelle=libelle)


def creer_maquette(annee, ref_formation, niveau, version=1, libelle='Maquette test'):
    return Maquette.objects.create(
        annee_academique=annee, ref_formation=ref_formation, niveau=niveau,
        version=version, statut=Maquette.Statut.BROUILLON, libelle=libelle,
    )


def creer_ue(maquette, semestre, code='UE-ANA', credits=6):
    return UE.objects.create(
        maquette=maquette, semestre=semestre, code=code,
        intitule='UE Analyse', credits=credits,
    )


def creer_ecue(ue, code='ECUE-ANA-1', credits=3, coefficient=2):
    return ECUE.objects.create(
        ue=ue, code=code, intitule='ECUE Analyse 1', credits=credits,
        coefficient=coefficient, volume_cm=30,
    )


def activer_maquette(maquette):
    """BROUILLON → VALIDEE → ACTIVE (transitions autorisées R4)."""
    maquette.statut = Maquette.Statut.VALIDEE
    maquette.save()
    maquette.statut = Maquette.Statut.ACTIVE
    maquette.activee_le = timezone.now()
    maquette.save()
    return maquette


def creer_formateur(nom='KONE', prenom='Awa', user=None, badge=None):
    """Formateur au badge unique, éventuellement rattaché à un compte.

    Le badge est tiré au hasard car la colonne ``numerobadge`` est unique en
    base : deux constructeurs de jeu de données ne doivent pas se chevaucher.
    """
    if badge is None:
        badge = f'F-{uuid.uuid4().hex[:8].upper()}'
    formateur = Formateur.objects.create(numerobadge=badge, nom=nom, prenom=prenom)
    if user is not None:
        formateur.user = user
        formateur.save()
    return formateur


def creer_affectation(annee, ref_formation, niveau, semestre, ecue, formateur):
    return AffectationPedagogique.objects.create(
        annee_academique=annee, ref_formation=ref_formation, niveau=niveau,
        semestre=semestre, ecue=ecue, enseignant=formateur,
        type_enseignement=AffectationPedagogique.TypeEnseignement.CM,
        volume_horaire=30, statut=AffectationPedagogique.Statut.VALIDEE,
    )


def creer_etudiant(matricule='ETU-001', nom='KOUASSI', prenom='Adjoua'):
    participant = Participant.objects.create(matricule=matricule, nom=nom, prenom=prenom)
    return DossierEtudiant.objects.create(participant=participant)


def creer_inscription(etudiant, annee, ref_formation, niveau):
    return InscriptionAdministrative.objects.create(
        etudiant=etudiant, annee_academique=annee, ref_formation=ref_formation,
        niveau=niveau, statut=InscriptionAdministrative.Statut.VALIDEE,
    )


def creer_inscription_pedagogique(inscription, ecue, semestre, credits=3, groupe=None):
    return InscriptionPedagogique.objects.create(
        inscription=inscription, ecue=ecue, semestre=semestre, credits=credits,
        groupe=groupe, type_enseignement=InscriptionPedagogique.TypeEnseignement.CM,
        statut=InscriptionPedagogique.Statut.VALIDEE,
        origine=InscriptionPedagogique.Origine.AUTOMATIQUE,
    )


def creer_groupe(annee, ref_formation, niveau, nom='L1-G1'):
    return Groupe.objects.create(
        annee_academique=annee, ref_formation=ref_formation, niveau=niveau, nom=nom,
    )


def base_lmd_complete(formateur_user=None, suffixe='A'):
    """Construit un périmètre LMD activé et prêt pour les évaluations.

    ``formateur_user`` rattache le formateur de référence à un compte : c'est
    ce lien qui porte l'isolation de périmètre ENCADRANT.
    ``suffixe`` évite les collisions de libellés uniques (deux périmètres
    indépendants dans un même test).
    """
    # Une seule année « courante » est autorisée en base : seul le premier
    # périmètre en devient porteuse.
    annee = creer_annee(f'2026-2027 ({suffixe})', courante=(suffixe == 'A'))
    ref_formation = creer_ref_formation(
        code=f'L1-LSF-{suffixe}', intitule=f'Licence 1 {suffixe}',
    )
    niveau = creer_niveau(code=f'L1-{suffixe}')
    semestre = creer_semestre(niveau, libelle=f'S1 {suffixe}')
    maquette = creer_maquette(
        annee, ref_formation, niveau, libelle=f'Maquette {suffixe}',
    )
    ue = creer_ue(maquette, semestre, code=f'UE-ANA-{suffixe}')
    ecue = creer_ecue(ue, code=f'ECUE-ANA-{suffixe}-1')
    activer_maquette(maquette)
    formateur = creer_formateur(user=formateur_user)
    affectation = creer_affectation(
        annee, ref_formation, niveau, semestre, ecue, formateur,
    )
    etudiant = creer_etudiant(matricule=f'ETU-001-{suffixe}')
    inscription = creer_inscription(etudiant, annee, ref_formation, niveau)
    inscription_pedagogique = creer_inscription_pedagogique(
        inscription, ecue, semestre,
    )
    return {
        'annee': annee, 'ref_formation': ref_formation, 'niveau': niveau,
        'semestre': semestre, 'maquette': maquette, 'ue': ue, 'ecue': ecue,
        'formateur': formateur, 'affectation': affectation, 'etudiant': etudiant,
        'inscription': inscription, 'inscription_pedagogique': inscription_pedagogique,
    }


def creer_compte(role, username, formateur=None):
    return User.objects.create_user(
        username=username, password='motdepasse-test-2026',
        email=f'{username}@injs.test', role=role,
    )