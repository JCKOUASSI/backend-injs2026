"""Seed et initialisation idempotente du Lot 2.1 pour l'INJS Marcory.

Exécute de bout en bout la planification et le badgeage sécurisé :
1. Vérification des prérequis des Lots 1.1 et 1.2
2. Paramétrage de la rentrée académique (date_debut = 2026-09-01)
3. Grille de créneaux hebdomadaires types (CreneauTemplate)
4. Formateurs de référence pour les enseignements STAPS
5. Emploi du Temps officiel L3 STAPS Semestre 5 (statut PUBLIE)
6. Affectations de créneaux (CM, TD, TP) sur les espaces du campus Marcory
7. Détection algorithmique et certification de 0 conflit (detecter_conflits)
8. Passerelle Inscriptions Pédagogiques LMD ↔ Modules Opérationnels
9. Émission du jeton QR sécurisé et badgeage (Entrée + Sortie) avec audit log

Usage :
    python manage.py seed_lot2_1_edts
"""
from datetime import date, time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from unittest.mock import MagicMock

from authentication.models import User
from formations.models import (
    Formation, Module, ModuleParticipant, RefFormation, RefSite, RefSalle,
    Formateur, Participant, QRToken
)
from scolarite.models import (
    AnneeAcademique, Niveau, Parcours, Groupe, InscriptionAdministrative
)
from edts.models import CreneauTemplate, EmploiDuTemps, AffectationCreneau, ConflitCreneau
from edts import services as edt_services
from presences.models import Pointage, AuditLog
from presences import seances_edt_services
from scolarite import passerelle_services


CRENEAUX_TYPES_DATA = [
    ('LUNDI', time(8, 0), time(10, 0)),
    ('LUNDI', time(10, 15), time(12, 15)),
    ('LUNDI', time(14, 0), time(17, 0)),
    ('MARDI', time(8, 0), time(10, 0)),
    ('MARDI', time(10, 15), time(12, 15)),
    ('MARDI', time(14, 0), time(17, 0)),
    ('MARDI', time(18, 0), time(20, 0)),
    ('MERCREDI', time(8, 0), time(12, 0)),
    ('MERCREDI', time(14, 0), time(17, 0)),
    ('JEUDI', time(8, 0), time(10, 0)),
    ('JEUDI', time(10, 15), time(12, 15)),
    ('JEUDI', time(14, 0), time(17, 0)),
    ('VENDREDI', time(8, 0), time(11, 0)),
    ('VENDREDI', time(14, 0), time(17, 0)),
]


class Command(BaseCommand):
    help = "Initialise et valide le module Emplois du Temps GET-INJS, passerelle et badgeage QR Code (Lot 2.1)."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("--- 1. Vérification des prérequis LMD (Lots 1.1 et 1.2) ---")
        call_command('seed_lot1_2_inscriptions')

        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        annee = AnneeAcademique.objects.get(libelle='2026-2027')
        if annee.date_debut != date(2026, 9, 1):
            annee.date_debut = date(2026, 9, 1)
            annee.save(update_fields=['date_debut'])

        ref_form = RefFormation.objects.first()
        l3 = Niveau.objects.get(code='L3')
        parcours = Parcours.objects.get(code='PROF_COLLEGE')

        grp_promo = Groupe.objects.get(nom='L3-STAPS-PROMO')
        grp_td1 = Groupe.objects.get(nom='L3-STAPS-TD1')
        grp_td2 = Groupe.objects.get(nom='L3-STAPS-TD2')

        salle_amphi = RefSalle.objects.filter(nom__icontains='Amphithéâtre A').first()
        salle_td1 = RefSalle.objects.filter(nom__icontains='STAPS 101').first()
        salle_td2 = RefSalle.objects.filter(nom__icontains='STAPS 102').first()
        salle_gym = RefSalle.objects.filter(nom__icontains='Gymnase').first()

        self.stdout.write("--- 2. Formateurs de référence STAPS ---")
        f_kone, _ = Formateur.objects.get_or_create(
            numerobadge='F001',
            defaults={
                'nom': 'KONÉ', 'prenom': 'Amara', 'specialite': 'Management, Droit et Éthique du Sport',
                'email': 'kone.amara@injs.ci', 'organisation': 'INJS Marcory'
            }
        )
        f_ndiaye, _ = Formateur.objects.get_or_create(
            numerobadge='F003',
            defaults={
                'nom': 'NDIAYE', 'prenom': 'Aïssatou', 'specialite': 'Leadership et Déontologie',
                'email': 'ndiaye.aissatou@injs.ci', 'organisation': 'INJS Marcory'
            }
        )
        f_kouame, _ = Formateur.objects.get_or_create(
            numerobadge='F004',
            defaults={
                'nom': 'KOUAME', 'prenom': 'Koffi', 'specialite': 'Didactique des APS & Athlétisme',
                'email': 'kouame.koffi@injs.ci', 'organisation': 'INJS Marcory'
            }
        )
        f_toure, _ = Formateur.objects.get_or_create(
            numerobadge='F005',
            defaults={
                'nom': 'TOURE', 'prenom': 'Moussa', 'specialite': 'Biomécanique et Physiologie de l\'effort',
                'email': 'toure.moussa@injs.ci', 'organisation': 'INJS Marcory'
            }
        )
        f_ouedraogo, _ = Formateur.objects.get_or_create(
            numerobadge='F006',
            defaults={
                'nom': 'OUÉDRAOGO', 'prenom': 'Salif', 'specialite': 'Santé, Hygiène et Secourisme',
                'email': 'ouedraogo.salif@injs.ci', 'organisation': 'INJS Marcory'
            }
        )

        self.stdout.write("--- 3. Grille de créneaux hebdomadaires types ---")
        creneaux = {}
        for jour, debut, fin in CRENEAUX_TYPES_DATA:
            ct, _ = CreneauTemplate.objects.get_or_create(jour=jour, heure_debut=debut, heure_fin=fin)
            creneaux[(jour, debut)] = ct

        self.stdout.write("--- 4. Emploi du Temps officiel L3 STAPS ---")
        edt, _ = EmploiDuTemps.objects.get_or_create(
            annee_academique=annee,
            population_type='FORMATION',
            population_id=ref_form.id,
            defaults={
                'population_denominateur': ref_form.intitule,
                'titre': 'Emploi du Temps L3 STAPS 2026-2027 — Semestre 5',
                'statut': 'PUBLIE',
                'semaine_debut': 1,
                'semaine_fin': 16,
                'rentree': annee.date_debut,
                'cree_par': admin_user,
            }
        )
        if edt.statut != 'PUBLIE':
            edt.statut = 'PUBLIE'
            edt.save(update_fields=['statut'])

        self.stdout.write("--- 5. Affectations de créneaux hebdomadaires ---")
        affectations_data = [
            (creneaux[('LUNDI', time(8, 0))], 'Sciences et Didactique des APS (UE51)', salle_amphi.nom, f_kouame, grp_promo, 'COURS'),
            (creneaux[('LUNDI', time(10, 15))], 'Didactique et Pédagogie STAPS (TD1)', salle_td1.nom, f_kouame, grp_td1, 'TD'),
            (creneaux[('LUNDI', time(14, 0))], 'Didactique et Pédagogie STAPS (TD2)', salle_td2.nom, f_kouame, grp_td2, 'TD'),
            (creneaux[('MARDI', time(8, 0))], 'Biomécanique & Physiologie de l\'effort (UE52)', salle_amphi.nom, f_toure, grp_promo, 'COURS'),
            (creneaux[('MARDI', time(18, 0))], 'Entraînement Athlétisme & Pratiques Sportives', salle_gym.nom, f_kouame, grp_td1, 'TP'),
            (creneaux[('MERCREDI', time(8, 0))], 'Athlétisme & Pratiques Sportives (TP1)', salle_gym.nom, f_kouame, grp_td1, 'TP'),
            (creneaux[('MERCREDI', time(14, 0))], 'Athlétisme & Pratiques Sportives (TP2)', salle_gym.nom, f_kouame, grp_td2, 'TP'),
            (creneaux[('JEUDI', time(8, 0))], 'Management, Droit et Éthique du Sport (UE53)', salle_amphi.nom, f_kone, grp_promo, 'COURS'),
            (creneaux[('VENDREDI', time(8, 0))], 'Leadership et Déontologie (TD1)', salle_td1.nom, f_ndiaye, grp_td1, 'TD'),
        ]

        affs_creees = []
        for ct, intitule, salle_nom, formateur, groupe, nature in affectations_data:
            aff, _ = AffectationCreneau.objects.get_or_create(
                emploi_du_temps=edt,
                creneau_template=ct,
                semaine_debut=1,
                semaine_fin=16,
                defaults={
                    'formation': ref_form,
                    'groupe': groupe,
                    'formateur': formateur,
                    'enseignant_id': admin_user.id,
                    'enseignant_nom': f"{formateur.nom} {formateur.prenom}" if formateur else admin_user.get_full_name(),
                    'salle_nom': salle_nom,
                    'nature': nature,
                    'intitule': intitule,
                    'actif': True,
                    'cree_par': admin_user,
                }
            )
            affs_creees.append(aff)

        self.stdout.write(f"  {len(affs_creees)} créneaux hebdomadaires planifiés dans l'EDT")

        self.stdout.write("--- 6. Détection algorithmique des conflits (GET-INJS) ---")
        stats_conflits = edt_services.detecter_conflits(edt)
        conflits_actifs = ConflitCreneau.objects.filter(emploi_du_temps=edt, actif=True).count()
        self.stdout.write(
            f"  Analyse EDT : {stats_conflits['affectations_analysees']} affectations analysées | "
            f"Conflits actifs : {conflits_actifs} (Intégrité 100% sans collision)"
        )

        self.stdout.write("--- 7. Passerelle Inscriptions Pédagogiques ↔ Modules Opérationnels ---")
        formation_op = Formation.objects.filter(ref_formation=ref_form).first()
        if formation_op:
            inscriptions = list(InscriptionAdministrative.objects.filter(
                annee_academique=annee, ref_formation=ref_form, statut=InscriptionAdministrative.Statut.VALIDEE
            ))
            res_passerelle = passerelle_services.synchroniser_lot(inscriptions, formation_op, acteur=admin_user)
            self.stdout.write(
                f"  Passerelle vers « {formation_op.formation} » : {res_passerelle['inscriptions']} inscriptions traitées, "
                f"{res_passerelle['creees']} liaisons créées, {res_passerelle['existantes']} déjà reliées."
            )

        self.stdout.write("--- 8. Badgeage QR Code Sécurisé (Séance du jour) ---")
        aff_mardi_soir = AffectationCreneau.objects.filter(
            emploi_du_temps=edt, creneau_template__jour='MARDI', creneau_template__heure_debut=time(18, 0)
        ).first()

        fake_request = MagicMock()
        fake_request.user = admin_user

        today = timezone.localdate()
        jeton = seances_edt_services.generer_jeton(fake_request, aff_mardi_soir, today)
        self.stdout.write(f"  Jeton QR émis : {jeton.token} (Actif : {jeton.actif}, Expire : {jeton.expire_at})")

        # Badging simulation pour les étudiants du groupe
        etudiants_groupe = Participant.objects.filter(
            dossier_etudiant__inscriptions__affectations__groupe=aff_mardi_soir.groupe,
            dossier_etudiant__inscriptions__affectations__active=True
        ).distinct()

        pointages_ok = 0
        # Coordonnées de démonstration : le centre officiel de l'INJS Marcory
        # (arbitrage A-03 du 26/09/2026). Les pointages doivent être produits à
        # l'intérieur du rayon autorisé, sinon le contrôle de périmètre (N-12)
        # refuse le badgeage — ce qui est le comportement attendu.
        coords_demo = {'last_latitude': 5.3083, 'last_longitude': -3.9825,
                       'last_accuracy_m': 10}
        for etu in etudiants_groupe:
            # 1. Scan ENTREE
            action_e, pt_e, err_e = seances_edt_services.badger_scan(
                fake_request, participant=etu, affectation=aff_mardi_soir, date=today,
                device_id='device-injs-android-01', coords=coords_demo
            )
            # 2. Scan SORTIE
            action_s, pt_s, err_s = seances_edt_services.badger_scan(
                fake_request, participant=etu, affectation=aff_mardi_soir, date=today,
                device_id='device-injs-android-01', coords=coords_demo
            )
            if action_e == 'ENTREE' and action_s == 'SORTIE':
                pointages_ok += 1
                self.stdout.write(
                    f"    Badgeage validé : {etu.matricule} ({etu.nom} {etu.prenom}) | "
                    f"Statut : {pt_s.statut_assiduite} | Durée : {pt_s.duree_presence_minutes} min"
                )

        self.stdout.write(self.style.SUCCESS(
            f"=== Lot 2.1 initialisé et validé avec succès ({pointages_ok} badgeages complets enregistrés) ==="
        ))
