"""Seed et réconciliation idempotente du Lot 1.1 pour l'INJS Marcory.

Exécute de bout en bout :
1. Réconciliation Formation -> RefFormation
2. Réconciliation Module -> RefModule
3. Initialisation de l'infrastructure physique INJS Marcory (Site, Bâtiments, Salles) et rattachement des modules
4. Initialisation des référentiels pédagogiques LMD (Niveaux, Semestres, Parcours, Règles de validation)
5. Création et activation de la maquette pédagogique de référence L3 STAPS (30 ECTS, 3 UEs, 6 ECUEs)

Usage :
    python manage.py seed_lot1_1_injs
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction

from formations.models import Formation, Module, RefFormation, RefModule, RefSite, RefBatiment, RefSalle
from referentiels.models import RefTypeEspaceSportif
from scolarite.models import (
    AnneeAcademique, TypeFormation, Niveau, Semestre, Parcours,
    RegleValidationLMD, Maquette, UE, ECUE
)


class Command(BaseCommand):
    help = "Initialise et réconcilie les données pédagogiques et spatiales du Lot 1.1 (LMD INJS Marcory)."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("--- 1. Réconciliation Formations / Cycles ---")
        call_command('reconcilier_formations_cycles', creer_cycles_manquants=True)

        self.stdout.write("--- 2. Réconciliation Modules / RefModules ---")
        call_command('rebuild_ref_modules')

        self.stdout.write("--- 3. Infrastructure physique INJS Marcory ---")
        self._seed_infrastructure()

        self.stdout.write("--- 4. Référentiels LMD & Maquette pédagogique ---")
        self._seed_lmd_maquette()

        self.stdout.write(self.style.SUCCESS("=== Lot 1.1 initialisé et réconcilié avec succès ==="))

    def _seed_infrastructure(self):
        types_espaces = [
            ("AMPHI", "Amphithéâtre", "Salle de cours magistraux à grande capacité"),
            ("SALLE_TD", "Salle de Travaux Dirigés", "Salle de cours théoriques"),
            ("SALLE_INFO", "Salle Informatique", "Salle équipée de postes informatiques"),
            ("TERRAIN_EXT", "Terrain Extérieur", "Terrain de sport de plein air (football, athlétisme, etc.)"),
            ("GYMNASE", "Gymnase Couvert", "Plateau sportif couvert omnisports"),
            ("SALLE_REUNION", "Salle de Réunion", "Salle de commission, jurys ou soutenance"),
        ]
        for code, libelle, desc in types_espaces:
            RefTypeEspaceSportif.objects.get_or_create(
                code=code, defaults={"libelle": libelle, "description": desc, "actif": True}
            )

        # Coordonnées **officielles** de l'INJS Marcory, validées par le
        # commanditaire le 26/09/2026 (arbitrage A-03 de l'audit
        # docs/audits/AUDIT-INJS-LMD-2026-09-26.md, § 23.1).
        #
        # ATTENTION — historique : ce seed posait 5.302500 / -3.978500 avec un
        # rayon de 300 m. Cette valeur n'a jamais été validée par l'INJS et se
        # situe à **782 m** des coordonnées officielles : avec un rayon de 200 m
        # elle placerait le campus hors de sa propre zone. Ne pas la restaurer.
        site, _ = RefSite.objects.get_or_create(
            nom="Campus INJS Marcory (Abidjan)",
            defaults={
                "geofence_latitude": Decimal("5.308300"),
                "geofence_longitude": Decimal("-3.982500"),
                "geofence_rayon_m": 200,
                "actif": True,
            }
        )

        bat_staps, _ = RefBatiment.objects.get_or_create(site=site, nom="Bâtiment Pédagogique STAPS", defaults={"actif": True})
        bat_sport, _ = RefBatiment.objects.get_or_create(site=site, nom="Complexe Sportif & Gymnase", defaults={"actif": True})
        bat_admin, _ = RefBatiment.objects.get_or_create(site=site, nom="Bâtiment Direction & Administration", defaults={"actif": True})

        type_amphi = RefTypeEspaceSportif.objects.filter(code="AMPHI").first()
        type_td = RefTypeEspaceSportif.objects.filter(code="SALLE_TD").first()
        type_gym = RefTypeEspaceSportif.objects.filter(code="GYMNASE").first()
        type_reunion = RefTypeEspaceSportif.objects.filter(code="SALLE_REUNION").first()

        salles_data = [
            (bat_staps, "Amphithéâtre A", RefSalle.TypeLieu.AMPHI, 250, type_amphi),
            (bat_staps, "Amphithéâtre B", RefSalle.TypeLieu.AMPHI, 180, type_amphi),
            (bat_staps, "Salle STAPS 101", RefSalle.TypeLieu.SALLE, 45, type_td),
            (bat_staps, "Salle STAPS 102", RefSalle.TypeLieu.SALLE, 45, type_td),
            (bat_sport, "Gymnase Omnisports Central", RefSalle.TypeLieu.GYMNASE, 500, type_gym),
            (bat_sport, "Salle Spécifique Gymnastique", RefSalle.TypeLieu.GYMNASE, 80, type_gym),
            (bat_admin, "Salle du Conseil et Jurys", RefSalle.TypeLieu.REUNION, 40, type_reunion),
        ]
        salles_creees = []
        for bat, nom, type_lieu, cap, te in salles_data:
            salle, _ = RefSalle.objects.get_or_create(
                site=site, batiment=bat, nom=nom,
                defaults={"type_lieu": type_lieu, "capacite": cap, "type_espace": te, "actif": True}
            )
            salles_creees.append(salle)

        # Lier tous les modules au site et à une salle par défaut
        modules = list(Module.objects.all())
        for idx, mod in enumerate(modules):
            salle_assignee = salles_creees[idx % len(salles_creees)]
            mod.site = site
            mod.batiment = salle_assignee.batiment.nom if salle_assignee.batiment else ""
            mod.salle = salle_assignee.nom
            mod.save(update_fields=["site", "batiment", "salle"])
        self.stdout.write(f"  {len(modules)} modules rattachés au campus {site.nom}")

    def _seed_lmd_maquette(self):
        ref_form = RefFormation.objects.first()
        if not ref_form:
            ref_form, _ = RefFormation.objects.get_or_create(
                code='L_STAPS',
                defaults={
                    'intitule': 'Licence STAPS - Sciences et Techniques des Activités Physiques et Sportives',
                    'actif': True,
                    'type_diplome': 'LICENCE',
                    'duree_annees': 3,
                    'nb_semestres': 6,
                    'nb_credites': 180,
                    'domaine': 'Sciences du Sport',
                    'mention': 'Entraînement et Professorat',
                }
            )
        Formation.objects.get_or_create(
            ref_formation=ref_form,
            defaults={'formation': ref_form.intitule}
        )

        call_command('init_referentiels_lmd', annee='2026-2027', courante=True, avec_parcours_injs=True)

        annee = AnneeAcademique.objects.get(libelle='2026-2027')
        ref_form = RefFormation.objects.first()
        l3 = Niveau.objects.get(code='L3')
        s5 = Semestre.objects.get(niveau=l3, numero=5)

        parcours, _ = Parcours.objects.get_or_create(
            ref_formation=ref_form, code='PROF_COLLEGE',
            defaults={'intitule': 'Professorat de Collège STAPS', 'actif': True}
        )

        RegleValidationLMD.objects.get_or_create(
            ref_formation=ref_form, niveau=l3,
            defaults={
                'seuil_admission': Decimal('10.00'),
                'compensation': RegleValidationLMD.Compensation.SEMESTRE,
                'seuil_elim': Decimal('7.00'),
                'credits_semestre': 30,
                'capitalisation_activee': True,
                'actif': True,
            }
        )

        maquette = Maquette.objects.filter(
            annee_academique=annee,
            ref_formation=ref_form,
            parcours=parcours,
            niveau=l3,
            version=1,
        ).first()

        if not maquette:
            maquette = Maquette.objects.create(
                annee_academique=annee,
                ref_formation=ref_form,
                parcours=parcours,
                niveau=l3,
                version=1,
                statut=Maquette.Statut.BROUILLON,
                libelle='Maquette L3 Professorat STAPS 2026-2027',
            )

        if maquette.unites_enseignement.count() == 0:
            ue1 = UE.objects.create(
                maquette=maquette, semestre=s5, code='UE51',
                intitule='Sciences et Didactique des APS', credits=12, caractere=UE.Caractere.OBLIGATOIRE, ordre=1
            )
            ue2 = UE.objects.create(
                maquette=maquette, semestre=s5, code='UE52',
                intitule='Sciences Fondamentales & Biomécanique', credits=10, caractere=UE.Caractere.OBLIGATOIRE, ordre=2
            )
            ue3 = UE.objects.create(
                maquette=maquette, semestre=s5, code='UE53',
                intitule='Management, Droit et Éthique du Sport', credits=8, caractere=UE.Caractere.OBLIGATOIRE, ordre=3
            )

            ref_mod_deonto = RefModule.objects.filter(intitule__icontains='DÉONTOLOGIE').first()
            ref_mod_manage = RefModule.objects.filter(intitule__icontains='LEADERSHIP').first()

            ECUE.objects.create(
                ue=ue1, code='ECUE511',
                intitule='Athlétisme & Pratiques Sportives', credits=6, coefficient=Decimal('2.0'),
                volume_cm=Decimal('20'), volume_td=Decimal('30'), volume_tp=Decimal('20'), ordre=1
            )
            ECUE.objects.create(
                ue=ue1, code='ECUE512',
                intitule='Didactique et Pédagogie STAPS', credits=6, coefficient=Decimal('2.0'),
                volume_cm=Decimal('25'), volume_td=Decimal('25'), volume_tp=Decimal('10'), ordre=2
            )

            ECUE.objects.create(
                ue=ue2, code='ECUE521',
                intitule='Biomécanique et Physiologie de l\'effort', credits=5, coefficient=Decimal('1.5'),
                volume_cm=Decimal('25'), volume_td=Decimal('20'), volume_tp=Decimal('15'), ordre=1
            )
            ECUE.objects.create(
                ue=ue2, code='ECUE522',
                intitule='Santé, Hygiène et Secourisme', credits=5, coefficient=Decimal('1.5'),
                volume_cm=Decimal('20'), volume_td=Decimal('20'), volume_tp=Decimal('10'), ordre=2
            )

            ECUE.objects.create(
                ue=ue3, code='ECUE531',
                intitule='Déontologie et Fonction Publique', credits=4, coefficient=Decimal('1.0'),
                volume_cm=Decimal('20'), volume_td=Decimal('15'), ref_module=ref_mod_deonto, ordre=1
            )
            ECUE.objects.create(
                ue=ue3, code='ECUE532',
                intitule='Leadership, Management et Droit Administratif', credits=4, coefficient=Decimal('1.0'),
                volume_cm=Decimal('20'), volume_td=Decimal('15'), ref_module=ref_mod_manage, ordre=2
            )

            problemes = maquette.verifier_coherence()
            if problemes:
                raise ValueError(f"Incohérences dans la maquette : {problemes}")
            maquette.statut = Maquette.Statut.ACTIVE
            maquette.save()

        self.stdout.write(f"  Maquette '{maquette.libelle}' : {maquette.credits_total} ECTS, {maquette.statut}")
