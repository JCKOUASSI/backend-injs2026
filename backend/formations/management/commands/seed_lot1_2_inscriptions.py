"""Seed et initialisation idempotente du Lot 1.2 pour l'INJS Marcory.

Exécute de bout en bout le cycle d'admissions et d'inscriptions LMD :
1. Initialisation des référentiels d'admissions (Voies d'accès, Types de candidatures, Pièces justificatives)
2. Campagne de recrutement STAPS L3 2026-2027 (statut OUVERTE)
3. Épreuves de concours (Physique, Écrit, Oral) rattachées aux espaces du campus Marcory
4. Candidats et dépôts de dossiers complets avec validation des pièces
5. Convocations, notation aux épreuves, verrouillage et publication du classement officiel
6. Admission prononcée, conversion en Inscription Administrative (IA) validée
7. Génération des matricules normalisés INJS (INJS26-XXXX) et création des Dossiers Étudiants
8. Inscriptions Pédagogiques (IP) automatiques (6 ECUEs, 30 ECTS par étudiant)
9. Constitution des Groupes pédagogiques (Promotion, TD1, TD2) et affectation des étudiants

Usage :
    python manage.py seed_lot1_2_inscriptions
"""
from datetime import date, time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction

from authentication.models import User
from formations.models import RefFormation, RefCategorie, RefGrade, RefVague, RefSite, RefSalle
from scolarite.models import (
    AnneeAcademique, Niveau, Parcours, RegimeEtudes,
    InscriptionAdministrative, InscriptionPedagogique, DossierEtudiant, Groupe
)
from admissions.models import (
    TypeCandidature, VoieAcces, TypePiece, CampagneAdmission,
    Candidat, Candidature, PieceCandidature, Epreuve, NoteConcours, ClassementConcours, Admission
)
from admissions import services as cand_services, concours_services, admission_services, workflow
from scolarite import inscription_services, pedagogie_services, groupes_services


CANDIDATS_STAPS = [
    ("KOUASSI", "Yao Emmanuel", Candidat.Sexe.MASCULIN, date(2002, 4, 12), "Abidjan", "kouassi.yao@injs.ci", "0701020304", Decimal("16.5"), Decimal("14.0"), Decimal("15.5")),
    ("TRAORE", "Fatou Aïcha", Candidat.Sexe.FEMININ, date(2003, 8, 25), "Bouaké", "traore.fatou@injs.ci", "0705060708", Decimal("15.0"), Decimal("16.0"), Decimal("16.0")),
    ("KONE", "Bakary", Candidat.Sexe.MASCULIN, date(2001, 11, 3), "Korhogo", "kone.bakary@injs.ci", "0709101112", Decimal("17.0"), Decimal("13.5"), Decimal("14.0")),
    ("DIABATE", "Mariam", Candidat.Sexe.FEMININ, date(2002, 6, 19), "Yamoussoukro", "diabate.mariam@injs.ci", "0713141516", Decimal("14.5"), Decimal("15.5"), Decimal("15.0")),
    ("N'GUESSAN", "Koffi Serge", Candidat.Sexe.MASCULIN, date(2003, 1, 15), "Daloa", "nguessan.koffi@injs.ci", "0717181920", Decimal("16.0"), Decimal("14.5"), Decimal("14.5")),
    ("OUATTARA", "Aminata", Candidat.Sexe.FEMININ, date(2002, 9, 30), "San-Pédro", "ouattara.aminata@injs.ci", "0721222324", Decimal("15.5"), Decimal("15.0"), Decimal("16.5")),
]


class Command(BaseCommand):
    help = "Initialise et valide le cycle d'admissions, inscriptions administratives et pédagogiques LMD (Lot 1.2)."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("--- 1. Vérification des prérequis LMD (Lot 1.1) ---")
        call_command('seed_lot1_1_injs')

        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        annee = AnneeAcademique.objects.get(libelle='2026-2027')
        ref_form = RefFormation.objects.first()
        l3 = Niveau.objects.get(code='L3')
        parcours = Parcours.objects.get(code='PROF_COLLEGE')
        regime = RegimeEtudes.objects.get(code='INITIAL')
        cat_a, _ = RefCategorie.objects.get_or_create(libelle='A', defaults={'actif': True})
        grade_a3, _ = RefGrade.objects.get_or_create(categorie=cat_a, libelle='A3', defaults={'actif': True})
        vague1, _ = RefVague.objects.get_or_create(libelle='PREMIERE VAGUE', defaults={'actif': True})
        site = RefSite.objects.get(nom='Campus INJS Marcory (Abidjan)')
        salle_amphi = RefSalle.objects.filter(nom__icontains='Amphithéâtre A').first()
        salle_gym = RefSalle.objects.filter(nom__icontains='Gymnase').first()
        salle_td = RefSalle.objects.filter(nom__icontains='STAPS 101').first()

        self.stdout.write("--- 2. Référentiels d'admissions & Pièces ---")
        voie, _ = VoieAcces.objects.get_or_create(code='CONCOURS_DIRECT', defaults={'libelle': 'Concours Direct STAPS', 'actif': True})
        type_cand, _ = TypeCandidature.objects.get_or_create(code='INITIALE', defaults={'libelle': 'Candidature Initiale', 'actif': True})

        pieces_data = [
            ('DIPLOME', 'Copie certifiée du Diplôme (Bac ou Bac+2)', True, False),
            ('EXTRAIT_NAISSANCE', 'Extrait d’acte de naissance', True, False),
            ('CERTIFICAT_MEDICAL', 'Certificat médical d’aptitude sportive INJS', True, True),
            ('PHOTO_IDENTITE', 'Photos d’identité couleur récentes', True, False),
            ('CASIER_JUDICIAIRE', 'Extrait de casier judiciaire (moins de 3 mois)', True, False),
        ]
        for code, libelle, oblig, avec_exp in pieces_data:
            TypePiece.objects.get_or_create(
                code=code, defaults={'libelle': libelle, 'obligatoire_par_defaut': oblig, 'avec_date_expiration': avec_exp, 'actif': True}
            )

        self.stdout.write("--- 3. Campagne de recrutement et Épreuves ---")
        campagne, _ = CampagneAdmission.objects.get_or_create(
            annee_academique=annee,
            ref_formation=ref_form,
            parcours=parcours,
            defaults={
                'libelle': 'Concours d’Entrée STAPS Licence 3 2026-2027',
                'date_ouverture': date(2026, 9, 1),
                'date_fermeture': date(2026, 10, 31),
                'quota_admissibles': 50,
                'quota_admis': 30,
                'statut': CampagneAdmission.Statut.OUVERTE,
            }
        )
        if campagne.statut != CampagneAdmission.Statut.OUVERTE:
            campagne.statut = CampagneAdmission.Statut.OUVERTE
            campagne.save()

        ep1, _ = Epreuve.objects.get_or_create(
            campagne=campagne, intitule='Épreuve Physique et Sportive (Pratique)',
            defaults={'type': Epreuve.Type.PHYSIQUE, 'date': date(2026, 9, 20), 'heure_debut': time(8, 0), 'duree_minutes': 180, 'salle': salle_gym, 'coefficient': Decimal('3.0')}
        )
        ep2, _ = Epreuve.objects.get_or_create(
            campagne=campagne, intitule='Culture Générale et Sportive (Écrit)',
            defaults={'type': Epreuve.Type.ECRIT, 'date': date(2026, 9, 21), 'heure_debut': time(9, 0), 'duree_minutes': 120, 'salle': salle_amphi, 'coefficient': Decimal('2.0')}
        )
        ep3, _ = Epreuve.objects.get_or_create(
            campagne=campagne, intitule='Entretien de Motivation & Pédagogie (Oral)',
            defaults={'type': Epreuve.Type.ORAL, 'date': date(2026, 9, 22), 'heure_debut': time(14, 0), 'duree_minutes': 30, 'salle': salle_td, 'coefficient': Decimal('2.0')}
        )
        epreuves = [ep1, ep2, ep3]

        self.stdout.write("--- 4. Candidatures, Pièces & Notation du concours ---")
        for nom, prenom, sexe, ddn, ldn, email, tel, n1, n2, n3 in CANDIDATS_STAPS:
            candidat, _ = Candidat.objects.get_or_create(
                nom=nom, prenom=prenom,
                defaults={
                    'sexe': sexe, 'date_naissance': ddn, 'lieu_naissance': ldn,
                    'nationalite': 'Ivoirienne', 'email': email, 'telephone': tel,
                }
            )
            candidature, cree = Candidature.objects.get_or_create(
                candidat=candidat,
                annee_academique=annee,
                ref_formation=ref_form,
                niveau=l3,
                defaults={
                    'campagne': campagne,
                    'parcours': parcours,
                    'type_candidature': type_cand,
                    'voie_acces': voie,
                    'regime': regime,
                    'vague': vague1,
                }
            )
            cand_services.initialiser_pieces(candidature, acteur=admin_user)
            for piece in candidature.pieces_obligatoires:
                cand_services.verifier_piece(piece, PieceCandidature.Statut.VALIDEE, acteur=admin_user)

            for st in [
                Candidature.Statut.SOUMISE,
                Candidature.Statut.EN_ATTENTE_DE_VERIFICATION,
                Candidature.Statut.PIECES_VALIDEES,
                Candidature.Statut.EN_ETUDE,
            ]:
                if candidature.statut != st and st in workflow.transitions_possibles(candidature):
                    workflow.appliquer_transition(candidature, st, acteur=admin_user)

            if not ep1.verrouillee:
                concours_services.enregistrer_note(ep1, candidature, utilisateur=admin_user, note=n1)
            if not ep2.verrouillee:
                concours_services.enregistrer_note(ep2, candidature, utilisateur=admin_user, note=n2)
            if not ep3.verrouillee:
                concours_services.enregistrer_note(ep3, candidature, utilisateur=admin_user, note=n3)

        for ep in epreuves:
            if not ep.verrouillee:
                concours_services.verrouiller_epreuve(ep, utilisateur=admin_user)

        if not ClassementConcours.objects.filter(campagne=campagne, publie=True).exists():
            concours_services.calculer_classement(campagne, utilisateur=admin_user)
            concours_services.publier_classement(campagne, utilisateur=admin_user)

        self.stdout.write("--- 5. Groupes pédagogiques STAPS ---")
        grp_promo, _ = Groupe.objects.get_or_create(
            annee_academique=annee, ref_formation=ref_form, niveau=l3, parcours=parcours,
            nom='L3-STAPS-PROMO', defaults={'capacite_max': 150, 'actif': True}
        )
        grp_td1, _ = Groupe.objects.get_or_create(
            annee_academique=annee, ref_formation=ref_form, niveau=l3, parcours=parcours,
            nom='L3-STAPS-TD1', defaults={'capacite_max': 30, 'actif': True}
        )
        grp_td2, _ = Groupe.objects.get_or_create(
            annee_academique=annee, ref_formation=ref_form, niveau=l3, parcours=parcours,
            nom='L3-STAPS-TD2', defaults={'capacite_max': 30, 'actif': True}
        )

        self.stdout.write("--- 6. Admissions, Inscriptions Administratives & Pédagogiques ---")
        candidatures = list(campagne.candidatures.order_by('id'))
        for idx, candidature in enumerate(candidatures):
            if candidature.statut in (Candidature.Statut.EN_ETUDE, Candidature.Statut.PIECES_VALIDEES):
                workflow.appliquer_transition(candidature, Candidature.Statut.ADMISSIBLE, acteur=admin_user)

            admission = Admission.objects.filter(candidature=candidature).first()
            if not admission:
                admission = admission_services.creer_admission(
                    candidature, acteur=admin_user,
                    categorie_id=cat_a.id, grade_id=grade_a3.id, vague_id=vague1.id,
                )
            if admission.decision != Admission.Decision.ADMIS:
                admission_services.prononcer_decision(
                    admission, Admission.Decision.ADMIS, acteur=admin_user,
                    reference='ARRETE-INJS-2026-0042',
                )

            inscription = InscriptionAdministrative.objects.filter(admission=admission).first()
            if not inscription:
                inscription = inscription_services.convertir_admission_en_inscription(
                    admission, acteur=admin_user, valider=True,
                )

            # Inscriptions pédagogiques LMD (UE/ECUE/ECTS)
            if inscription.inscriptions_pedagogiques.count() == 0:
                pedagogie_services.generer_inscriptions_pedagogiques(inscription, acteur=admin_user)

            # Affectation groupe TD
            grp_td = grp_td1 if idx % 2 == 0 else grp_td2
            aff_active = inscription.affectations.filter(active=True).first()
            if not aff_active or aff_active.groupe_id != grp_td.id:
                groupes_services.affecter_groupe(inscription, grp_td, acteur=admin_user, motif='Affectation groupe TD LMD')

            self.stdout.write(
                f"  Etudiant: {inscription.etudiant.participant.nom} {inscription.etudiant.participant.prenom} | "
                f"Matricule: {inscription.etudiant.matricule} | Statut: {inscription.statut} | "
                f"IPs: {inscription.inscriptions_pedagogiques.count()} ECUEs | Groupe: {grp_td.nom}"
            )

        self.stdout.write(self.style.SUCCESS("=== Lot 1.2 initialisé et validé avec succès ==="))
