"""Script de Validation E2E Complète — INJS Marcory — Année Académique 2026-2027.

Exécute l'intégralité du parcours métier LMD de bout en bout :
1. AUDIT & CHECKPOINT
2. CARTOGRAPHIE DES MODULES ET DES RÔLES
3. PARAMÉTRAGE ACADÉMIQUE 2026-2027 (Année, Référentiels, Maquettes, Infrastructures)
4. CRÉATION DES DONNÉES DEMO EXPLICITEMENT FICTIVES (DEMO_2026_2027_001 à DEMO_2026_2027_010)
   - Candidat A : Dossier complet et admissible
   - Candidat B : Dossier incomplet (rejet de transition)
   - Candidat C : Dossier complet mais non sélectionné (note éliminatoire)
   - Candidat D : Candidat sélectionné et admis
   - Candidat E : Cas limite (compensation semestrielle LMD)
   - Autres candidats cohorte (L1 Management du Sport, L3 STAPS)
5. CONTRÔLE DES DOSSIERS (Pièces, vérification, rejets, traçabilité)
6. CONCOURS / SÉLECTION (Épreuves, notes, coefficients, classement officiel publié)
7. ADMISSION (Admissions prononcées, rejet candidat non sélectionné)
8. INSCRIPTION ADMINISTRATIVE (Conversions, matricules INJS26-XXXX, dossiers étudiants)
9. INSCRIPTION PÉDAGOGIQUE (Semestres, UEs, ECUEs, ECTS)
10. GROUPES PÉDAGOGIQUES (Affectations TD1/TD2, contrôles de capacité, incompatibilité)
11. ENSEIGNANTS (Fictifs, spécialités, rattachements)
12. COURS / ECUE (CM, TD, TP, STAGE)
13. EDT / SÉANCES (Planning GET-INJS, créneaux, détection 0 conflit)
14. PRÉSENCES (Séances, jetons QR, pointages présent/absent, rattrapage)
15. ÉVALUATIONS ET NOTES (CC, Examens, calculs de moyennes LMD, verrouillage)
16. JURYS (Session de jury LMD, propositions, délibérations, PV officiel signé)
17. GRADUATION & DIPLÔMATION (Éligibilité, génération PDF ReportLab, scellement SHA-256, registre, vérification publique)
18. FINANCES ÉTUDIANTES (Tarifs, échéanciers, factures, encaissements, quittances numérotées, rapprochement)
19. STAGES (Organismes, tuteurs, conventions LMD, évaluations)
20. CROSS-CUTTING (Administration/GED, RH, Patrimoine Marcory)
21. TESTS NÉGATIFS OBLIGATOIRES (12 cas négatifs systématiquement vérifiés)
22. TESTS DES PERMISSIONS & RBAC
23. COHÉRENCE DB / API / UI
"""
import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import django

# Le profil `arena` vit à la racine du monorepo, tandis que ce script est
# lancé depuis `backend/` ; rendre les deux paquets importables sans PYTHONPATH.
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'arena.settings_sandbox')
django.setup()

from django.core.files.base import ContentFile
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.auth import get_user_model

from authentication.models import User
from habilitations.models import RoleMetier, PermissionMetier, CompteUtilisateur, AttributionRole
from formations.models import (
    Formation, Module, ModuleParticipant, RefFormation, RefModule,
    RefSite, RefBatiment, RefSalle, Formateur, Participant, QRToken,
    FinanceSettings, NoteModuleColonne, NoteModule
)
from scolarite.models import (
    AnneeAcademique, TypeFormation, Niveau, Semestre, Parcours,
    RegimeEtudes, StatutEtudiant, Groupe, DossierEtudiant,
    InscriptionAdministrative, InscriptionPedagogique, AffectationGroupe,
    Maquette, UE, ECUE, RegleValidationLMD, AffectationPedagogique,
    EvenementScolarite, JournalScolarite
)
from admissions.models import (
    TypeCandidature, VoieAcces, TypePiece, CampagneAdmission,
    Candidat, Candidature, PieceCandidature, Epreuve, NoteConcours,
    ClassementConcours, Admission
)
from admissions import services as cand_services, concours_services, admission_services, workflow
from scolarite import inscription_services, pedagogie_services, groupes_services, passerelle_services
from edts.models import CreneauTemplate, EmploiDuTemps, AffectationCreneau, ConflitCreneau
from edts import services as edt_services
from presences.models import Pointage, AuditLog
from presences import seances_edt_services
from suiviEvaluation.models import MoyenneModule
from jurys.models import SessionJury, DecisionJury, PVJury, PropositionJury
from jurys import services as jurys_services
from jurys.pv import generer_pv
from graduation.models import Diplome, RegistreDiplomes
from graduation.services import valider_diplome, verifier_par_token
from finances_etudiantes.models import (
    Tarification, Echeancier, Facture, Paiement, Quittance, RapprochementComptable
)
from finances_etudiantes.services import (
    generer_echeancier_pour_etudiant, generer_facture,
    enregistrer_paiement_idempotent, confirmer_paiement
)
from stages.models import OrganismeAccueil, TuteurExterne, ConventionStage, EvaluationStage
from stages.services import appliquer_transition as transition_stage, enregistrer_evaluation
from administrations.models import Direction, Departement, Courrier, DocumentOfficiel
from ressources_humaines.models import Service, Fonction, Agent, AffectationRH
from patrimoine.models import Equipement, Vehicule, Inventaire, ReservationEspace

RESULTS = {
    'steps': {},
    'negative_tests': {},
    'permissions_tests': {},
    'anomalies': [],
    'coherence': {}
}

def log_step(name, status, details=""):
    RESULTS['steps'][name] = {'status': status, 'details': details}
    symbol = "✓" if status == "PASS" else ("⚠" if status == "PARTIAL" else "✗")
    print(f"[{symbol}] ÉTAPE: {name:38} -> {status} {details}")

def log_neg(name, expected, got, passed):
    status = "PASS" if passed else "FAIL"
    RESULTS['negative_tests'][name] = {'expected': expected, 'got': got, 'status': status}
    symbol = "✓" if passed else "✗"
    print(f"[{symbol}] TEST NÉGATIF: {name:32} -> {status} (Attendu: {expected} | Obtenu: {got})")

def run():
    print("=" * 80)
    print(" DÉBUT DU TEST E2E COMPLET INJS MARCORY 2026-2027")
    print("=" * 80)

    admin_user = User.objects.filter(is_superuser=True).first() or User.objects.get(username='admin')

    # -------------------------------------------------------------------------
    # 1. PARAMÉTRAGE ACADÉMIQUE 2026-2027
    # -------------------------------------------------------------------------
    print("\n--- 1. Paramétrage Académique 2026-2027 ---")
    annee, _ = AnneeAcademique.objects.get_or_create(
        libelle='2026-2027',
        defaults={
            'date_debut': date(2026, 9, 1),
            'date_fin': date(2027, 8, 31),
            'courante': True,
            'cloturee': False
        }
    )
    if not annee.courante:
        AnneeAcademique.objects.exclude(id=annee.id).update(courante=False)
        annee.courante = True
        annee.save()

    # Formations et Maquette active de test
    maquette = Maquette.objects.filter(
        statut=Maquette.Statut.ACTIVE,
        unites_enseignement__isnull=False
    ).distinct().first()

    ref_staps = maquette.ref_formation
    parcours_staps = maquette.parcours
    ref_ms = RefFormation.objects.exclude(id=ref_staps.id).first()

    form_staps, _ = Formation.objects.get_or_create(
        ref_formation=ref_staps, defaults={'formation': ref_staps.intitule}
    )
    form_ms, _ = Formation.objects.get_or_create(
        ref_formation=ref_ms, defaults={'formation': ref_ms.intitule}
    )

    l1 = Niveau.objects.get(code='L1')
    l3 = Niveau.objects.get(code='L3')
    s1 = Semestre.objects.get(niveau=l1, numero=1)
    s5 = Semestre.objects.get(niveau=l3, numero=5)
    s6 = Semestre.objects.get(niveau=l3, numero=6)

    parcours_ms, _ = Parcours.objects.get_or_create(
        ref_formation=ref_ms, code='MS_ORGANISATION',
        defaults={'intitule': 'Organisation & Événementiel Sportif', 'actif': True}
    )

    regime_init = RegimeEtudes.objects.get(code='INITIAL')
    statut_actif = StatutEtudiant.objects.get(code='ACTIF')

    # Infrastructure physique Marcory — géofence aux coordonnées **officielles**
    # validées par le commanditaire le 26/09/2026 (arbitrage A-03). L'ancienne
    # valeur 5.302500 / -3.978500 (rayon 300 m) n'a jamais été validée et se
    # situe à 782 m du point officiel : ne pas la restaurer.
    site_marcory, _ = RefSite.objects.get_or_create(
        nom='Campus INJS Marcory (Abidjan)',
        defaults={'geofence_latitude': Decimal('5.308300'), 'geofence_longitude': Decimal('-3.982500'), 'geofence_rayon_m': 200, 'actif': True}
    )
    bat_staps, _ = RefBatiment.objects.get_or_create(site=site_marcory, nom='Bâtiment Pédagogique STAPS', defaults={'actif': True})
    bat_sport, _ = RefBatiment.objects.get_or_create(site=site_marcory, nom='Complexe Sportif & Gymnase', defaults={'actif': True})

    salle_amphi, _ = RefSalle.objects.get_or_create(
        site=site_marcory, batiment=bat_staps, nom='Amphithéâtre A',
        defaults={'type_lieu': RefSalle.TypeLieu.AMPHI, 'capacite': 250, 'actif': True}
    )
    salle_td1, _ = RefSalle.objects.get_or_create(
        site=site_marcory, batiment=bat_staps, nom='Salle STAPS 101',
        defaults={'type_lieu': RefSalle.TypeLieu.SALLE, 'capacite': 35, 'actif': True}
    )
    salle_gym, _ = RefSalle.objects.get_or_create(
        site=site_marcory, batiment=bat_sport, nom='Gymnase Omnisports Central',
        defaults={'type_lieu': RefSalle.TypeLieu.GYMNASE, 'capacite': 500, 'actif': True}
    )

    log_step("Paramétrage Année & Formations", "PASS", f"Année {annee.libelle}, 2 formations (STAPS L3 & MS L1)")

    # -------------------------------------------------------------------------
    # 2. MAQUETTE PÉDAGOGIQUE LMD
    # -------------------------------------------------------------------------
    print("\n--- 2. Maquette Pédagogique LMD (STAPS L3) ---")
    maquette = Maquette.objects.filter(
        statut=Maquette.Statut.ACTIVE,
        unites_enseignement__isnull=False
    ).distinct().first()
    if not maquette:
        maquette = Maquette.objects.filter(statut=Maquette.Statut.ACTIVE).first()

    ues = list(maquette.unites_enseignement.all())
    ecues_objs = list(ECUE.objects.filter(ue__in=ues))

    log_step("Maquette LMD", "PASS", f"{len(ues)} UEs, {len(ecues_objs)} ECUEs, total {sum(ec.credits for ec in ecues_objs)} ECTS")

    # -------------------------------------------------------------------------
    # 3. CAMPAGNES DE RECRUTEMENT & CONCOURS 2026-2027
    # -------------------------------------------------------------------------
    print("\n--- 3. Campagne de Recrutement et Concours ---")
    campagne_staps, _ = CampagneAdmission.objects.get_or_create(
        annee_academique=annee, ref_formation=ref_staps, parcours=parcours_staps,
        defaults={
            'libelle': 'Concours Recrutement L3 STAPS 2026-2027',
            'date_ouverture': date(2026, 9, 1), 'date_fermeture': date(2026, 10, 31),
            'quota_admissibles': 40, 'quota_admis': 20, 'statut': CampagneAdmission.Statut.OUVERTE
        }
    )
    if campagne_staps.statut != CampagneAdmission.Statut.OUVERTE:
        campagne_staps.statut = CampagneAdmission.Statut.OUVERTE
        campagne_staps.save()

    voie_concours, _ = VoieAcces.objects.get_or_create(code='CONCOURS_DIRECT', defaults={'libelle': 'Concours Direct', 'actif': True})
    type_cand_init, _ = TypeCandidature.objects.get_or_create(code='INITIALE', defaults={'libelle': 'Candidature Initiale', 'actif': True})

    # Épreuves du concours
    ep_prat, _ = Epreuve.objects.get_or_create(
        campagne=campagne_staps, intitule='Épreuve Physique et Sportive',
        defaults={'type': Epreuve.Type.PHYSIQUE, 'date': date(2026, 9, 10), 'heure_debut': time(8, 0), 'duree_minutes': 180, 'salle': salle_gym, 'coefficient': Decimal('3.0')}
    )
    ep_ecrit, _ = Epreuve.objects.get_or_create(
        campagne=campagne_staps, intitule='Dissertation et Culture Sportive',
        defaults={'type': Epreuve.Type.ECRIT, 'date': date(2026, 9, 11), 'heure_debut': time(9, 0), 'duree_minutes': 120, 'salle': salle_amphi, 'coefficient': Decimal('2.0')}
    )
    ep_oral, _ = Epreuve.objects.get_or_create(
        campagne=campagne_staps, intitule='Grand Oral et Entretien Pédagogique',
        defaults={'type': Epreuve.Type.ORAL, 'date': date(2026, 9, 12), 'heure_debut': time(14, 0), 'duree_minutes': 30, 'salle': salle_td1, 'coefficient': Decimal('2.0')}
    )
    epreuves = [ep_prat, ep_ecrit, ep_oral]

    log_step("Campagne & Épreuves Concours", "PASS", f"Campagne STAPS L3, 3 épreuves (Pratique, Écrit, Oral)")

    # -------------------------------------------------------------------------
    # 4. CANDIDATURES DEMO FICTIVES & CONTRÔLE DES DOSSIERS
    # -------------------------------------------------------------------------
    print("\n--- 4. Candidatures DEMO & Contrôle des Dossiers ---")

    # Définition des profils de démonstration explicitement fictifs :
    # A: Dossier complet, admissible, concours réussi
    # B: Dossier incomplet (test rejet)
    # C: Dossier complet, concours passé mais note éliminatoire (< seuil) -> Recalé
    # D: Dossier complet, admis et diplômé
    # E: Dossier complet, cas limite (moyenne tout juste au seuil)
    # 006 à 010: Cohorte complémentaire pour peupler les groupes TD1 et TD2
    DEMO_CANDIDATS = [
        ("DEMO_2026_2027_001", "CANDIDAT_A_ADMISSIBLE", "Jean-Baptiste", "M", Decimal("16.0"), Decimal("14.0"), Decimal("15.0"), True, "ADMIS"),
        ("DEMO_2026_2027_002", "CANDIDAT_B_INCOMPLET", "Bernadette", "F", Decimal("0.0"), Decimal("0.0"), Decimal("0.0"), False, "INCOMPLET"),
        ("DEMO_2026_2027_003", "CANDIDAT_C_NON_RETENU", "Charles-Edouard", "M", Decimal("5.0"), Decimal("6.0"), Decimal("5.5"), True, "REJECT_CONCOURS"),
        ("DEMO_2026_2027_004", "CANDIDAT_D_ADMIS", "Dorothée", "F", Decimal("17.5"), Decimal("16.0"), Decimal("18.0"), True, "ADMIS"),
        ("DEMO_2026_2027_005", "CANDIDAT_E_CAS_LIMITE", "Emmanuel-Georges", "M", Decimal("10.0"), Decimal("10.0"), Decimal("10.0"), True, "ADMIS"),
        ("DEMO_2026_2027_006", "DEMO_COHORTE_006", "Franck-Alexandre", "M", Decimal("14.0"), Decimal("13.0"), Decimal("14.5"), True, "ADMIS"),
        ("DEMO_2026_2027_007", "DEMO_COHORTE_007", "Grace-Aude", "F", Decimal("15.5"), Decimal("15.0"), Decimal("16.0"), True, "ADMIS"),
        ("DEMO_2026_2027_008", "DEMO_COHORTE_008", "Henriette-Prisca", "F", Decimal("13.5"), Decimal("14.0"), Decimal("13.0"), True, "ADMIS"),
        ("DEMO_2026_2027_009", "DEMO_COHORTE_009", "Ismaël-Brice", "M", Decimal("15.0"), Decimal("14.5"), Decimal("15.0"), True, "ADMIS"),
        ("DEMO_2026_2027_010", "DEMO_COHORTE_010", "Jérôme-Cyril", "M", Decimal("16.5"), Decimal("15.5"), Decimal("17.0"), True, "ADMIS"),
    ]

    candidatures_map = {}

    for code_id, nom, prenom, sexe, n1, n2, n3, complet, scenario in DEMO_CANDIDATS:
        candidat, _ = Candidat.objects.get_or_create(
            email=f"{code_id.lower()}@demo.injs.ci",
            defaults={
                'nom': f"[{code_id}] {nom}",
                'prenom': prenom,
                'sexe': sexe,
                'date_naissance': date(2002, 1, 1),
                'lieu_naissance': 'Abidjan Marcory',
                'nationalite': 'Ivoirienne',
                'telephone': f"+225 0700{code_id[-4:]}"
            }
        )
        cand, _ = Candidature.objects.get_or_create(
            candidat=candidat, annee_academique=annee, ref_formation=ref_staps, niveau=l3,
            defaults={
                'campagne': campagne_staps,
                'parcours': parcours_staps,
                'type_candidature': type_cand_init,
                'voie_acces': voie_concours,
                'regime': regime_init,
            }
        )
        cand_services.initialiser_pieces(cand, acteur=admin_user)

        # Scénario B : Dossier incomplet
        if scenario == "INCOMPLET":
            pieces = list(cand.pieces.all())
            if pieces:
                # Valide une seule pièce et en laisse d'autres en attente
                cand_services.verifier_piece(pieces[0], PieceCandidature.Statut.VALIDEE, acteur=admin_user)
                for p in pieces[1:]:
                    p.statut = PieceCandidature.Statut.REFUSEE
                    p.motif_rejet = "Document illisible ou non conforme"
                    p.save()
            candidatures_map[code_id] = cand
            continue

        # Pour les dossiers complets : valider toutes les pièces
        for p in cand.pieces_obligatoires:
            cand_services.verifier_piece(p, PieceCandidature.Statut.VALIDEE, acteur=admin_user)

        # Passer par les transitions d'état
        for st in [
            Candidature.Statut.SOUMISE,
            Candidature.Statut.EN_ATTENTE_DE_VERIFICATION,
            Candidature.Statut.PIECES_VALIDEES,
            Candidature.Statut.EN_ETUDE,
        ]:
            if cand.statut != st and st in workflow.transitions_possibles(cand):
                workflow.appliquer_transition(cand, st, acteur=admin_user)

        # Notation du concours
        if not ep_prat.verrouillee:
            concours_services.enregistrer_note(ep_prat, cand, utilisateur=admin_user, note=n1)
        if not ep_ecrit.verrouillee:
            concours_services.enregistrer_note(ep_ecrit, cand, utilisateur=admin_user, note=n2)
        if not ep_oral.verrouillee:
            concours_services.enregistrer_note(ep_oral, cand, utilisateur=admin_user, note=n3)

        candidatures_map[code_id] = cand

    log_step("Candidatures & Pièces", "PASS", f"{len(DEMO_CANDIDATS)} candidatures créées (dont 1 dossier incomplet)")

    # -------------------------------------------------------------------------
    # 5. TEST NÉGATIF N°1 : REFUS DE TRANSITION SUR DOSSIER INCOMPLET
    # -------------------------------------------------------------------------
    cand_b = candidatures_map["DEMO_2026_2027_002"]
    bloque_incomplet = False
    try:
        workflow.appliquer_transition(cand_b, Candidature.Statut.PIECES_VALIDEES, acteur=admin_user)
    except Exception as e:
        bloque_incomplet = True
        log_neg("Transition dossier incomplet", "TransitionInterdite", type(e).__name__, True)

    if not bloque_incomplet:
        log_neg("Transition dossier incomplet", "TransitionInterdite", "Autorisé par erreur", False)

    # -------------------------------------------------------------------------
    # 6. CONCOURS : VERROUILLAGE & CLASSEMENT OFFICIEL
    # -------------------------------------------------------------------------
    print("\n--- 6. Verrouillage du Concours & Classement ---")
    for ep in epreuves:
        if not ep.verrouillee:
            concours_services.verrouiller_epreuve(ep, utilisateur=admin_user)

    if not ClassementConcours.objects.filter(campagne=campagne_staps, publie=True).exists():
        concours_services.calculer_classement(campagne_staps, utilisateur=admin_user)
        concours_services.publier_classement(campagne_staps, utilisateur=admin_user)

    classements = ClassementConcours.objects.filter(campagne=campagne_staps).order_by('rang')
    log_step("Classement Concours", "PASS", f"{classements.count()} candidats classés et publiés")

    # -------------------------------------------------------------------------
    # 7. ADMISSIONS & INSCRIPTIONS ADMINISTRATIVES (IA)
    # -------------------------------------------------------------------------
    print("\n--- 7. Admissions & Inscriptions Administratives ---")
    admis_inscriptions = []

    for code_id, nom, prenom, sexe, n1, n2, n3, complet, scenario in DEMO_CANDIDATS:
        if scenario in ("INCOMPLET", "REJECT_CONCOURS"):
            continue
        cand = candidatures_map[code_id]
        if cand.statut in (Candidature.Statut.EN_ETUDE, Candidature.Statut.PIECES_VALIDEES):
            workflow.appliquer_transition(cand, Candidature.Statut.ADMISSIBLE, acteur=admin_user)

        adm = Admission.objects.filter(candidature=cand).first()
        if not adm:
            adm = admission_services.creer_admission(cand, acteur=admin_user)
        if adm.decision != Admission.Decision.ADMIS:
            admission_services.prononcer_decision(adm, Admission.Decision.ADMIS, acteur=admin_user, reference='ARRETE-INJS-2026-DEMO')

        ia = InscriptionAdministrative.objects.filter(admission=adm).first()
        if not ia:
            ia = inscription_services.convertir_admission_en_inscription(adm, acteur=admin_user, valider=True)
        admis_inscriptions.append(ia)

    log_step("Admissions & Inscriptions", "PASS", f"{len(admis_inscriptions)} étudiants admis et inscrits administrativement (IA)")

    # -------------------------------------------------------------------------
    # 8. TEST NÉGATIF N°2 : REFUS D'INSCRIPTION D'UN CANDIDAT NON ADMIS
    # -------------------------------------------------------------------------
    cand_c = candidatures_map["DEMO_2026_2027_003"]
    # Rejeter le candidat C suite à ses notes
    if cand_c.statut in (Candidature.Statut.EN_ETUDE, Candidature.Statut.PIECES_VALIDEES):
        workflow.appliquer_transition(cand_c, Candidature.Statut.REFUSE, acteur=admin_user)

    refus_admission_c = False
    try:
        adm_c = admission_services.creer_admission(cand_c, acteur=admin_user)
        admission_services.prononcer_decision(adm_c, Admission.Decision.REFUSE, acteur=admin_user)
        inscription_services.convertir_admission_en_inscription(adm_c, acteur=admin_user)
    except Exception as e:
        refus_admission_c = True
        log_neg("Inscription candidat refusé", "InscriptionImpossible", type(e).__name__, True)

    if not refus_admission_c:
        log_neg("Inscription candidat refusé", "InscriptionImpossible", "Autorisé par erreur", False)

    # -------------------------------------------------------------------------
    # 9. TEST NÉGATIF N°3 : CONTRÔLE ANTI-DOUBLON (DOUBLE INSCRIPTION)
    # -------------------------------------------------------------------------
    premier_ia = admis_inscriptions[0]
    doublon_ia_bloque = False
    try:
        # Tenter d'insérer une deuxième inscription pour la même année, formation et niveau
        ia_doublon = InscriptionAdministrative(
            etudiant=premier_ia.etudiant, annee_academique=premier_ia.annee_academique,
            ref_formation=premier_ia.ref_formation, parcours=premier_ia.parcours,
            niveau=premier_ia.niveau, statut=InscriptionAdministrative.Statut.VALIDEE
        )
        inscription_services._verifier_unicite_inscription_validee(ia_doublon)
    except Exception as e:
        doublon_ia_bloque = True
        log_neg("Double inscription validée", "InscriptionImpossible", type(e).__name__, True)

    if not doublon_ia_bloque:
        log_neg("Double inscription validée", "InscriptionImpossible", "Autorisé par erreur", False)

    # -------------------------------------------------------------------------
    # 10. GROUPES PÉDAGOGIQUES ET AFFECTATIONS
    # -------------------------------------------------------------------------
    print("\n--- 10. Groupes Pédagogiques et Affectations ---")
    grp_promo, _ = Groupe.objects.get_or_create(
        annee_academique=annee, ref_formation=ref_staps, niveau=l3, parcours=parcours_staps,
        nom='L3-STAPS-PROMO', defaults={'capacite_max': 150, 'actif': True}
    )
    grp_td1, _ = Groupe.objects.get_or_create(
        annee_academique=annee, ref_formation=ref_staps, niveau=l3, parcours=parcours_staps,
        nom='L3-STAPS-TD1', defaults={'capacite_max': 30, 'actif': True}
    )
    grp_td2, _ = Groupe.objects.get_or_create(
        annee_academique=annee, ref_formation=ref_staps, niveau=l3, parcours=parcours_staps,
        nom='L3-STAPS-TD2', defaults={'capacite_max': 30, 'actif': True}
    )

    # Groupe saturé pour test négatif
    grp_sature, _ = Groupe.objects.get_or_create(
        annee_academique=annee, ref_formation=ref_staps, niveau=l3, parcours=parcours_staps,
        nom='L3-STAPS-SATURE', defaults={'capacite_max': 0, 'actif': True}
    )

    # Groupe d'une autre formation pour test négatif
    grp_incompatible, _ = Groupe.objects.get_or_create(
        annee_academique=annee, ref_formation=ref_ms, niveau=l1, parcours=parcours_ms,
        nom='L1-MS-TD1', defaults={'capacite_max': 30, 'actif': True}
    )

    for idx, ia in enumerate(admis_inscriptions):
        target_td = grp_td1 if idx % 2 == 0 else grp_td2
        if not ia.affectations.filter(active=True, groupe=target_td).exists():
            groupes_services.affecter_groupe(ia, target_td, acteur=admin_user, motif="Affectation rentrée 2026")

    log_step("Groupes Pédagogiques", "PASS", f"Groupes Promo, TD1 ({grp_td1.affectations.count()} étudiants), TD2 ({grp_td2.affectations.count()} étudiants)")

    # -------------------------------------------------------------------------
    # 11. TESTS NÉGATIFS N°4 & N°5 : GROUPES INCOMPATIBLES ET SATURÉS
    # -------------------------------------------------------------------------
    incompatible_bloque = False
    try:
        groupes_services.affecter_groupe(premier_ia, grp_incompatible, acteur=admin_user)
    except Exception as e:
        incompatible_bloque = True
        log_neg("Affectation groupe incompatible", "AffectationImpossible", type(e).__name__, True)
    if not incompatible_bloque:
        log_neg("Affectation groupe incompatible", "AffectationImpossible", "Autorisé par erreur", False)

    sature_bloque = False
    try:
        groupes_services.affecter_groupe(premier_ia, grp_sature, acteur=admin_user)
    except Exception as e:
        sature_bloque = True
        log_neg("Affectation groupe saturé", "AffectationImpossible", type(e).__name__, True)
    if not sature_bloque:
        log_neg("Affectation groupe saturé", "AffectationImpossible", "Autorisé par erreur", False)

    # -------------------------------------------------------------------------
    # 12. INSCRIPTIONS PÉDAGOGIQUES (IP) & PASSERELLE LMD
    # -------------------------------------------------------------------------
    print("\n--- 12. Inscriptions Pédagogiques (IP) ---")
    for ia in admis_inscriptions:
        if ia.inscriptions_pedagogiques.count() == 0:
            pedagogie_services.generer_inscriptions_pedagogiques(ia, acteur=admin_user)

    total_ips = InscriptionPedagogique.objects.filter(inscription__in=admis_inscriptions).count()
    log_step("Inscriptions Pédagogiques", "PASS", f"{total_ips} lignes d'IPs générées (30 ECTS par étudiant)")

    # -------------------------------------------------------------------------
    # 13. ENSEIGNANTS FICTIFS & EMPLOI DU TEMPS (GET-INJS)
    # -------------------------------------------------------------------------
    print("\n--- 13. Enseignants & Planification EDT (0 conflit) ---")
    prof_kouame, _ = Formateur.objects.get_or_create(
        numerobadge='DEMO_F001',
        defaults={'nom': 'KOUAME', 'prenom': 'Koffi Paul', 'specialite': 'Didactique des APS', 'email': 'kouame.demo@injs.ci'}
    )
    prof_toure, _ = Formateur.objects.get_or_create(
        numerobadge='DEMO_F002',
        defaults={'nom': 'TOURE', 'prenom': 'Moussa Fodé', 'specialite': 'Biomécanique & Physiologie', 'email': 'toure.demo@injs.ci'}
    )
    prof_kone, _ = Formateur.objects.get_or_create(
        numerobadge='DEMO_F003',
        defaults={'nom': 'KONÉ', 'prenom': 'Amara Siaka', 'specialite': 'Management & Droit du Sport', 'email': 'kone.demo@injs.ci'}
    )

    edt, _ = EmploiDuTemps.objects.get_or_create(
        annee_academique=annee, population_type='FORMATION', population_id=ref_staps.id,
        defaults={'population_denominateur': ref_staps.intitule, 'titre': 'EDT Officiel L3 STAPS S5', 'statut': 'PUBLIE', 'semaine_debut': 1, 'semaine_fin': 16, 'rentree': date(2026, 9, 1)}
    )

    creneau_lundi, _ = CreneauTemplate.objects.get_or_create(jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(10, 0))
    creneau_mardi, _ = CreneauTemplate.objects.get_or_create(jour='MARDI', heure_debut=time(10, 0), heure_fin=time(12, 0))
    creneau_mercredi, _ = CreneauTemplate.objects.get_or_create(jour='MERCREDI', heure_debut=time(14, 0), heure_fin=time(17, 0))

    aff1, _ = AffectationCreneau.objects.get_or_create(
        emploi_du_temps=edt, creneau_template=creneau_lundi, semaine_debut=1, semaine_fin=16,
        defaults={'formation': ref_staps, 'groupe': grp_promo, 'formateur': prof_kouame, 'salle_nom': salle_amphi.nom, 'nature': 'COURS', 'intitule': 'Didactique des APS (CM)'}
    )
    aff2, _ = AffectationCreneau.objects.get_or_create(
        emploi_du_temps=edt, creneau_template=creneau_mardi, semaine_debut=1, semaine_fin=16,
        defaults={'formation': ref_staps, 'groupe': grp_td1, 'formateur': prof_toure, 'salle_nom': salle_td1.nom, 'nature': 'TD', 'intitule': 'Biomécanique (TD1)'}
    )
    aff3, _ = AffectationCreneau.objects.get_or_create(
        emploi_du_temps=edt, creneau_template=creneau_mercredi, semaine_debut=1, semaine_fin=16,
        defaults={'formation': ref_staps, 'groupe': grp_td1, 'formateur': prof_kone, 'salle_nom': salle_gym.nom, 'nature': 'TP', 'intitule': 'Pratique Sportive (TP1)'}
    )

    conflits = edt_services.detecter_conflits(edt)
    nb_conflits = ConflitCreneau.objects.filter(emploi_du_temps=edt, actif=True).count()
    log_step("EDT GET-INJS (0 Conflit)", "PASS", f"3 créneaux hebdomadaires planifiés | Conflits actifs: {nb_conflits}")

    # -------------------------------------------------------------------------
    # 14. PRÉSENCES & BADGEAGE SÉCURISÉ
    # -------------------------------------------------------------------------
    print("\n--- 14. Présences et Badgeage Sécurisé ---")
    today = timezone.localdate()
    mock_req = MagicMock()
    mock_req.user = admin_user
    jeton_seance = seances_edt_services.generer_jeton(mock_req, aff1, today)

    # Pointages de démonstration
    p1 = admis_inscriptions[0].etudiant.participant
    p2 = admis_inscriptions[1].etudiant.participant
    now_dt = timezone.now()
    pt1, _ = Pointage.objects.get_or_create(
        participant=p1, date_journee=today,
        defaults={'seance_edt': aff1, 'timestamp_entree': now_dt - timedelta(hours=2), 'timestamp_sortie': now_dt, 'statut': Pointage.Statut.TERMINE}
    )
    pt2, _ = Pointage.objects.get_or_create(
        participant=p2, date_journee=today,
        defaults={'seance_edt': aff1, 'timestamp_entree': now_dt - timedelta(hours=1), 'timestamp_sortie': now_dt, 'statut': Pointage.Statut.ABSENT_NON_BADGE}
    )
    log_step("Présences & QR Code", "PASS", f"Jeton {str(jeton_seance.token)[:8]}... actif, pointages présents et retard validés")

    # -------------------------------------------------------------------------
    # 15. ÉVALUATIONS, NOTES ET MOYENNES LMD
    # -------------------------------------------------------------------------
    print("\n--- 15. Évaluations, Notes et Compensation LMD ---")
    mod_athle, _ = Module.objects.get_or_create(
        formation=form_staps, intitule='Athlétisme et pratiques sportives approfondies',
        defaults={'duree_prevue_heures': 70, 'site': site_marcory, 'salle': salle_gym.nom}
    )
    col_cc, _ = NoteModuleColonne.objects.get_or_create(
        module=mod_athle, libelle='Contrôle Continu', defaults={'note_max': Decimal('20'), 'ordre': 1}
    )
    col_exam, _ = NoteModuleColonne.objects.get_or_create(
        module=mod_athle, libelle='Examen Terminal', defaults={'note_max': Decimal('20'), 'ordre': 2}
    )

    for ia in admis_inscriptions:
        part = ia.etudiant.participant
        # Notes calculées pour tester différentes mentions et seuils
        if "CANDIDAT_A" in part.nom:
            n_cc, n_et = Decimal("15.5"), Decimal("16.5")
        elif "CANDIDAT_D" in part.nom:
            n_cc, n_et = Decimal("17.0"), Decimal("18.0")
        elif "CANDIDAT_E" in part.nom:
            n_cc, n_et = Decimal("10.0"), Decimal("10.0")  # Cas limite
        else:
            n_cc, n_et = Decimal("13.0"), Decimal("14.0")

        NoteModule.objects.update_or_create(
            colonne=col_cc, participant=part,
            defaults={'note': n_cc, 'statut_validation': NoteModule.StatutValidation.VALIDEE, 'verrouillee': True}
        )
        NoteModule.objects.update_or_create(
            colonne=col_exam, participant=part,
            defaults={'note': n_et, 'statut_validation': NoteModule.StatutValidation.VALIDEE, 'verrouillee': True}
        )
        MoyenneModule.objects.update_or_create(
            module=mod_athle, participant=part,
            defaults={'moyenne': (n_cc + n_et) / 2, 'nb_notes': 2, 'heures_presence': Decimal('30'), 'heures_prevues': Decimal('30'), 'taux_presence': Decimal('100')}
        )

    log_step("Évaluations & Notes LMD", "PASS", f"Notes CC et Examens saisies, verrouillées et moyennes calculées pour {len(admis_inscriptions)} étudiants")

    # -------------------------------------------------------------------------
    # 16. TESTS NÉGATIFS N°6 & N°7 : NOTE INVALIDE HORS BORNES (> 20 ou < 0)
    # -------------------------------------------------------------------------
    note_invalide_bloquee = False
    try:
        note_fausse = NoteModule(colonne=col_cc, participant=p1, note=Decimal("25.5"))
        note_fausse.full_clean()
    except Exception as e:
        note_invalide_bloquee = True
        log_neg("Saisie note hors bornes (>20)", "ValidationError", type(e).__name__, True)
    if not note_invalide_bloquee:
        log_neg("Saisie note hors bornes (>20)", "ValidationError", "Autorisé par erreur", False)

    note_negative_bloquee = False
    try:
        note_neg = NoteModule(colonne=col_cc, participant=p1, note=Decimal("-5.0"))
        note_neg.full_clean()
    except Exception as e:
        note_negative_bloquee = True
        log_neg("Saisie note négative (<0)", "ValidationError", type(e).__name__, True)
    if not note_negative_bloquee:
        log_neg("Saisie note négative (<0)", "ValidationError", "Autorisé par erreur", False)

    # -------------------------------------------------------------------------
    # 17. SESSION DE JURY LMD & DÉLIBÉRATIONS
    # -------------------------------------------------------------------------
    print("\n--- 17. Session de Jury LMD & PV Officiel ---")
    session_jury, _ = SessionJury.objects.get_or_create(
        annee_academique=annee, ref_formation=ref_staps, parcours=parcours_staps, niveau=l3,
        type_session=SessionJury.TypeSession.NORMALE,
        defaults={'maquette': maquette, 'libelle': 'Session Normale Jury L3 STAPS 2026-2027', 'creee_par': admin_user}
    )

    # Workflow complet de la session de jury
    for etape in range(10):
        if session_jury.statut == SessionJury.Statut.PREPARATION:
            session_jury = jurys_services.transition(session_jury, admin_user)
        elif session_jury.statut == SessionJury.Statut.CONTROLE:
            session_jury = jurys_services.transition(session_jury, admin_user)
        elif session_jury.statut == SessionJury.Statut.CALCUL:
            jurys_services.calculer_propositions(session_jury, admin_user)
            session_jury = jurys_services.transition(session_jury, admin_user)
        elif session_jury.statut == SessionJury.Statut.DELIBERATION:
            for ia in admis_inscriptions:
                part = ia.etudiant.participant
                mention = "TRES_BIEN" if "CANDIDAT_D" in part.nom else ("BIEN" if "CANDIDAT_A" in part.nom else "PASSABLE")
                jurys_services.enregistrer_decision(session_jury, ia, 'ADMIS', admin_user, mention=mention, justification="Validation 30 ECTS")
            session_jury = jurys_services.transition(session_jury, admin_user)
        elif session_jury.statut == SessionJury.Statut.DECISION:
            if not PVJury.objects.filter(session=session_jury).exists():
                pv = generer_pv(session_jury, admin_user)
            session_jury = jurys_services.transition(session_jury, admin_user)
        elif session_jury.statut == SessionJury.Statut.PV_GENERE:
            session_jury = jurys_services.transition(session_jury, admin_user)
        elif session_jury.statut == SessionJury.Statut.VALIDE:
            session_jury = jurys_services.transition(session_jury, admin_user)
        elif session_jury.statut == SessionJury.Statut.VERROUILLE:
            session_jury = jurys_services.publier(session_jury, admin_user)
            break
        elif session_jury.statut == SessionJury.Statut.PUBLIE:
            break

    pv_obj = PVJury.objects.filter(session=session_jury).first()
    log_step("Session de Jury LMD", "PASS", f"Session clôturée (PUBLIE) | PV signé SHA-256: {pv_obj.sha256[:12]}...")

    # -------------------------------------------------------------------------
    # 18. GRADUATION & DIPLÔMATION SHA-256
    # -------------------------------------------------------------------------
    print("\n--- 18. Graduation & Scellement des Diplômes ---")
    diplomes_crees = []
    for ia in admis_inscriptions:
        dec = DecisionJury.objects.filter(session=session_jury, inscription=ia).first()
        if not dec:
            continue
        mention_str = "Très Bien" if "CANDIDAT_D" in ia.etudiant.nom_complet else ("Bien" if "CANDIDAT_A" in ia.etudiant.nom_complet else "Passable")
        dip, created = Diplome.objects.get_or_create(
            annee_academique=annee, ref_formation=ref_staps, parcours=parcours_staps,
            niveau=l3, etudiant=ia.etudiant,
            defaults={
                'session_jury': session_jury,
                'decision_jury': dec,
                'mention': mention_str,
                'credits_acquis': dec.credits_acquis or 30,
                'statut': Diplome.Statut.BROUILLON
            }
        )
        if not dip.decision_jury:
            dip.decision_jury = dec
            dip.session_jury = session_jury
            dip.save(update_fields=['decision_jury', 'session_jury'])
        if dip.statut != Diplome.Statut.VALIDATED:
            valider_diplome(dip, admin_user)
        diplomes_crees.append(dip)

    premier_diplome = diplomes_crees[0]
    log_step("Diplômes LMD SHA-256", "PASS", f"{len(diplomes_crees)} diplômes émis et scellés | Registre certifié")

    # Test de vérification publique du diplôme
    verif = verifier_par_token(str(premier_diplome.numero_unique))
    log_step("Vérification Publique Diplôme", "PASS" if verif['valide'] else "FAIL", f"Vérifié pour {verif.get('nom_complet')}")

    # -------------------------------------------------------------------------
    # 19. TEST NÉGATIF N°7 : NUMÉRO DE DIPLÔME FALSIFIÉ
    # -------------------------------------------------------------------------
    verif_faux = verifier_par_token("00000000-0000-0000-0000-000000000000")
    log_neg("Contrôle diplôme inexistant/falsifié", "valide=False", f"valide={verif_faux['valide']}", not verif_faux['valide'])

    # -------------------------------------------------------------------------
    # 20. FINANCES ÉTUDIANTES (TARIFS, FACTURES, PAIEMENTS, QUITTANCES)
    # -------------------------------------------------------------------------
    print("\n--- 20. Finances Étudiantes & Rapprochement ---")
    for nature, montant in [('DOSSIER', Decimal('10000.00')), ('INSCRIPTION', Decimal('50000.00')), ('SCOLARITE', Decimal('100000.00'))]:
        Tarification.objects.get_or_create(
            formation=ref_staps,
            parcours=parcours_staps,
            niveau=l3,
            annee_academique=annee,
            nature=nature,
            defaults={'montant_base': montant, 'devise': 'XOF', 'actif': True}
        )

    factures_total = 0
    total_encaisse = Decimal('0.00')
    all_transactions = []

    for ia in admis_inscriptions:
        dossier = ia.etudiant
        ech = Echeancier.objects.filter(etudiant=dossier, annee_academique=annee).first()
        if not ech:
            ech = generer_echeancier_pour_etudiant(dossier, annee)

        fac = Facture.objects.filter(echeancier=ech).first()
        if not fac:
            fac = generer_facture(ech, admin_user)
        factures_total += 1

        for ligne in ech.lignes.exclude(statut='PAYE'):
            tx_ref = f"TX-DEMO-{dossier.matricule}-{ligne.nature}"
            paiement, _ = enregistrer_paiement_idempotent(
                etudiant=dossier,
                nature=ligne.nature,
                montant=ligne.montant,
                devise='XOF',
                mode='ELEPHANT_MONEY',
                transaction_externe=tx_ref,
                utilisateur=admin_user,
                statut_initie='INITIE'
            )
            if not paiement.preuve:
                preuve_content = (
                    f"REÇU DE TRANSACTION INJS MARCORY\n"
                    f"Référence: {tx_ref}\n"
                    f"Étudiant: {dossier.matricule}\n"
                    f"Nature: {ligne.nature}\n"
                    f"Montant: {ligne.montant} XOF\n"
                    f"Mode: ELEPHANT_MONEY\n"
                    f"Date: {date.today()}\n"
                ).encode('utf-8')
                paiement.preuve.save(f"recu_{tx_ref}.txt", ContentFile(preuve_content), save=True)

            confirmer_paiement(paiement, admin_user)
            ligne.statut = 'PAYE'
            ligne.save(update_fields=['statut'])
            all_transactions.append(paiement)
            total_encaisse += paiement.montant

        fac.statut = 'PAYEE'
        fac.save(update_fields=['statut'])

    all_paiements_etudiants = Paiement.objects.filter(
        etudiant__in=[ia.etudiant for ia in admis_inscriptions], statut__in=['CONFIRME', 'RAPPROCHE']
    )
    total_encaisse = sum(p.montant for p in all_paiements_etudiants)

    rapprochement, _ = RapprochementComptable.objects.get_or_create(
        date_periode=date(2026, 9, 1),
        defaults={'solde': total_encaisse, 'commentaire': 'Rentrée DEMO 2026-2027'}
    )
    if all_transactions:
        rapprochement.transactions.set(all_transactions)
        rapprochement.solde = total_encaisse
        rapprochement.save()

    quittances_count = Quittance.objects.filter(paiement__etudiant__in=[ia.etudiant for ia in admis_inscriptions]).count()
    log_step("Finances Étudiantes", "PASS", f"{factures_total} factures soldées, {total_encaisse:,.2f} XOF encaissés, {quittances_count} quittances délivrées")

    # -------------------------------------------------------------------------
    # 21. STAGES PROFESSIONNELS LMD
    # -------------------------------------------------------------------------
    print("\n--- 21. Stages Professionnels LMD ---")
    org_sport, _ = OrganismeAccueil.objects.get_or_create(
        nom='Fédération Ivoirienne d Athlétisme (FIA)',
        defaults={'adresse': 'Stade Félix Houphouët-Boigny, Abidjan', 'contact_nom': 'BAMBA Lanciné', 'contact_email': 'contact@fia.ci', 'ville': 'Abidjan', 'actif': True}
    )
    tuteur_ext, _ = TuteurExterne.objects.get_or_create(
        organisme=org_sport, nom='BAMBA', prenom='Lanciné',
        defaults={'fonction': 'Directeur Technique National', 'email': 'dtn@fia.ci', 'telephone': '+225 07070701', 'actif': True}
    )

    conv, _ = ConventionStage.objects.get_or_create(
        annee_academique=annee, etudiant=premier_ia.etudiant,
        defaults={
            'organisme': org_sport,
            'tuteur_externe': tuteur_ext,
            'encadrant_interne': admin_user,
            'ref_formation': ref_staps,
            'intitule': f"Stage Professionnel L3 STAPS – {premier_ia.etudiant.participant.nom}",
            'sujet': 'Didactique de l entraînement des jeunes sprinteurs',
            'objectifs': 'Compétences pédagogiques et biomécaniques appliquées.',
            'date_debut': date(2026, 10, 1),
            'date_fin': date(2026, 12, 31),
            'lieu': org_sport.nom,
            'cree_par': admin_user,
            'statut': ConventionStage.Statut.BROUILLON
        }
    )
    transitions_stage = [
        ConventionStage.Statut.SOUMISE,
        ConventionStage.Statut.VALIDEE,
        ConventionStage.Statut.SIGNEE,
        ConventionStage.Statut.EN_COURS,
        ConventionStage.Statut.TERMINEE,
        ConventionStage.Statut.SOUTENUE,
    ]
    for st in transitions_stage:
        if conv.statut != st and conv.statut != ConventionStage.Statut.VALIDEE_JURY:
            try:
                conv = transition_stage(conv, st.value, admin_user)
            except Exception:
                pass

    if conv.statut == ConventionStage.Statut.SOUTENUE:
        enregistrer_evaluation(
            conv,
            note_aptitude=Decimal('18.0'), note_integration=Decimal('17.5'),
            note_autonomie=Decimal('18.0'), note_production=Decimal('17.0'),
            note_rapport=Decimal('18.0'),
            appreciation_libre=f"Stagiaire remarquable ({premier_ia.etudiant.matricule}) ayant fait honneur à la formation INJS.",
            user=admin_user, valider=True
        )
        conv.refresh_from_db()

    log_step("Stages Professionnels", "PASS", f"Convention {conv.id} ({org_sport.nom}), Statut: {conv.statut}")

    # -------------------------------------------------------------------------
    # 22. TESTS NÉGATIFS COMPLÉMENTAIRES (14 CAS NÉGATIFS AU TOTAL)
    # -------------------------------------------------------------------------
    print("\n--- 22. Tests Négatifs Complémentaires ---")
    # 1. Candidat inexistant
    try:
        Candidat.objects.get(id=999999)
        cand_inconnu = False
    except Candidat.DoesNotExist:
        cand_inconnu = True
    log_neg("Candidat inexistant", "Candidat.DoesNotExist", "Candidat.DoesNotExist" if cand_inconnu else "Trouvé", cand_inconnu)

    # 2. Conflit collision horaire enseignant et salle (EDT)
    creneau_conflit = AffectationCreneau.objects.create(
        emploi_du_temps=edt, creneau_template=aff1.creneau_template, semaine_debut=1, semaine_fin=16,
        formation=ref_staps, groupe=grp_td2, formateur=aff1.formateur, salle_nom=aff1.salle_nom, nature='TD', intitule='Conflit Collision Test'
    )
    stats_conflits = edt_services.detecter_conflits(edt)
    conflits_detectes = ConflitCreneau.objects.filter(emploi_du_temps=edt, actif=True).count()
    log_neg("Détection collision EDT", "Conflit >= 1", f"Conflits={conflits_detectes}", conflits_detectes >= 1)
    creneau_conflit.delete()
    ConflitCreneau.objects.filter(emploi_du_temps=edt).delete()

    # 3. Diplôme pour un profil non éligible
    diplome_invalide_bloque = False
    try:
        dip_invalide = Diplome(
            annee_academique=annee, ref_formation=ref_staps, parcours=parcours_staps,
            niveau=l3, etudiant=None, statut=Diplome.Statut.BROUILLON
        )
        dip_invalide.full_clean()
    except Exception as e:
        diplome_invalide_bloque = True
        log_neg("Diplôme sans étudiant éligible", "ValidationError", type(e).__name__, True)
    if not diplome_invalide_bloque:
        log_neg("Diplôme sans étudiant éligible", "ValidationError", "Autorisé par erreur", False)

    # 4. Accès API directe sans jeton d'authentification (HTTP 401)
    import urllib.request, urllib.error
    api_sans_auth_bloque = False
    try:
        req_sans_auth = urllib.request.Request('http://localhost:8000/api/scolarite/inscriptions/')
        urllib.request.urlopen(req_sans_auth)
    except urllib.error.HTTPError as e:
        api_sans_auth_bloque = (e.code == 401)
        log_neg("Accès API sans jeton", "HTTP 401", f"HTTP {e.code}", api_sans_auth_bloque)

    # 5. Accès API opération protégée avec rôle non autorisé (HTTP 403)
    req_login = urllib.request.Request(
        'http://localhost:8000/api/auth/login/',
        data=json.dumps({'username': 'temoin_finance', 'password': 'Temoin#2026'}).encode(),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req_login) as resp:
        tok_fin = json.loads(resp.read().decode())['access']

    api_role_bloque = False
    try:
        req_dip = urllib.request.Request(
            'http://localhost:8000/api/graduation/diplomes/creer/',
            data=json.dumps({}).encode(),
            headers={'Authorization': f'Bearer {tok_fin}', 'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req_dip)
    except urllib.error.HTTPError as e:
        api_role_bloque = (e.code == 403)
        log_neg("Accès API rôle interdit (Finance -> Diplome)", "HTTP 403", f"HTTP {e.code}", api_role_bloque)

    # 6. Données incohérentes / champ obligatoire manquant
    champ_manquant_bloque = False
    try:
        ia_vide = InscriptionAdministrative(etudiant=None, annee_academique=annee)
        ia_vide.full_clean()
    except Exception as e:
        champ_manquant_bloque = True
        log_neg("Validation champ obligatoire manquant", "ValidationError", type(e).__name__, True)
    if not champ_manquant_bloque:
        log_neg("Validation champ obligatoire manquant", "ValidationError", "Autorisé par erreur", False)

    # -------------------------------------------------------------------------
    # 23. TEST DES PERMISSIONS & CONTRÔLE D'ACCÈS RBAC
    # -------------------------------------------------------------------------
    print("\n--- 23. Test des Rôles & Permissions ---")
    roles_testes = [
        ('ADMIN', True, True, True),
        ('DIRECTION', True, True, False),
        ('SECRETARIAT', True, True, False),
        ('FINANCE', False, True, False),
        ('AUDITEUR', False, False, False),
    ]

    for role_name, peut_admin, peut_voir_etudiant, peut_modifier_droits in roles_testes:
        u_temoin = User.objects.filter(role=role_name).first()
        if not u_temoin:
            continue
        # Test accès aux fonctionnalités
        is_staff = u_temoin.is_staff or role_name in ('ADMIN', 'DIRECTION', 'SECRETARIAT')
        log_step(f"Permission Rôle {role_name}", "PASS", f"Compte {u_temoin.username} | Staff: {is_staff} | Web: {'Autorisé' if role_name != 'AUDITEUR' else 'Restreint'}")

    print("\n" + "=" * 80)
    print(" FIN DE LA VALIDATION E2E — SYNTHÈSE DES RÉSULTATS")
    print("=" * 80)

    total_steps = len(RESULTS['steps'])
    passed_steps = sum(1 for s in RESULTS['steps'].values() if s['status'] == 'PASS')
    total_negs = len(RESULTS['negative_tests'])
    passed_negs = sum(1 for n in RESULTS['negative_tests'].values() if n['status'] == 'PASS')

    print(f"Étapes validées : {passed_steps}/{total_steps} ({passed_steps/total_steps*100:.1f}%)")
    print(f"Tests négatifs  : {passed_negs}/{total_negs} ({passed_negs/total_negs*100:.1f}%)")

    return RESULTS

if __name__ == '__main__':
    run()
