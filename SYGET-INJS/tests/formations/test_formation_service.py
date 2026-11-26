import pytest

from apps.formations.repositories import FormationModuleRepository, FormationRepository
from apps.formations.services import FormationService


def _service():
    return FormationService(FormationRepository(), FormationModuleRepository())


def _fixer_dates_periode(formation, date_debut, date_fin):
    """Aligne la première période (et les modules déjà rattachés) sur un intervalle de test."""
    p = formation.periodes.order_by("ordre", "date_debut").first()
    return _service().modifier_periode(
        p.pk,
        formation.pk,
        p.libelle,
        date_debut,
        date_fin,
        rythme_mensuel=p.rythme_mensuel,
    )


@pytest.mark.django_db
class TestFormationService:
    """Tests du service de gestion des formations."""

    def test_creer_formation(self, type_formation):
        """Une formation est correctement créée."""
        import datetime

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation test",
            vague="Vague 1",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        assert formation.pk is not None
        assert formation.intitule == "Formation test"
        assert formation.type_formation == type_formation
        assert formation.rythme_mensuel == "4"
        assert formation.periodes.count() == 1
        assert formation.periodes.first().date_debut == datetime.date(2025, 1, 6)

    def test_creer_formation_avec_rythme_mensuel(self, type_formation):
        """La contrainte de rythme mensuel est persistée."""
        import datetime

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation rythme mensuel",
            vague="Vague 1",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
            rythme_mensuel="2",
        )
        assert formation.rythme_mensuel == "2"

    def test_supprimer_formation_avec_modules_et_periodes(self, type_formation, module_referentiel):
        """La suppression d'une formation retire modules puis périodes (PROTECT sur periode)."""
        import datetime

        from apps.formations.models import Formation
        from apps.parametrage.models import ModuleTypeFormation

        service = _service()
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation à supprimer",
            vague="V1",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            volume_horaire_defaut=8,
        )
        service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            site_noms=["Site A"],
            batiment_noms=["Bat A"],
            salle_noms=["Salle 101"],
        )
        assert formation.modules.exists()
        assert formation.periodes.exists()

        service.supprimer(formation.pk)

        assert not Formation.objects.filter(pk=formation.pk).exists()

    def test_date_fin_avant_debut_leve_erreur(self, type_formation):
        """Une date de fin antérieure à la date de début lève ValueError."""
        import datetime

        service = FormationService(FormationRepository(), FormationModuleRepository())
        with pytest.raises(ValueError, match="date de fin"):
            service.creer(
                type_formation_id=type_formation.pk,
                intitule="Formation invalide",
                vague="",
                date_debut=datetime.date(2025, 3, 28),
                date_fin=datetime.date(2025, 1, 6),
            )

    def test_ajouter_module(self, type_formation, module_referentiel):
        """Un module est ajouté à une formation."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation avec module",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            volume_horaire_defaut=20,
        )
        fm = service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            site_noms=["Site A"],
            batiment_noms=["Bat A"],
            salle_noms=["Salle 101"],
        )
        assert fm.volume_horaire == 20
        assert fm.module == module_referentiel
        assert fm.creneau_mode == "matin_et_soir"

    def test_ajouter_module_avec_creneau_mode(self, type_formation, module_referentiel):
        """Le mode de créneau est porté par le module de formation."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation creneau module",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            volume_horaire_defaut=20,
        )

        fm = service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            creneau_mode="soir",
            site_noms=["Site A"],
            batiment_noms=["Bat A"],
            salle_noms=["Salle 101"],
        )
        assert fm.creneau_mode == "soir"

    def test_ajouter_module_meme_salle_matin_et_soir_sans_conflit(self, type_formation, module_referentiel):
        """Même salle et dates : matin + soir sur deux modules distincts ne doit pas bloquer."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation
        from apps.referentiels.models import Module

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation matin soir",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        module_soir = Module.objects.create(titre="Module soir", specialite=module_referentiel.specialite)
        for module in (module_referentiel, module_soir):
            ModuleTypeFormation.objects.create(
                module=module,
                type_formation=type_formation,
                volume_horaire_defaut=20,
            )

        _fixer_dates_periode(formation, datetime.date(2025, 2, 3), datetime.date(2025, 2, 7))
        lieu = {
            "site_noms": ["Site A"],
            "batiment_noms": ["Bat A"],
            "salle_noms": ["Salle 101"],
        }

        service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            creneau_mode="matin",
            **lieu,
        )
        fm_soir = service.ajouter_module(
            formation.pk,
            module_soir.pk,
            creneau_mode="soir",
            **lieu,
        )

        assert fm_soir.creneau_mode == "soir"

    def test_ajouter_module_meme_salle_meme_creneau_leve_conflit(self, type_formation, module_referentiel):
        """Même salle, dates et créneau : le second module doit être refusé."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation
        from apps.referentiels.models import Module

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation conflit matin",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        module_b = Module.objects.create(titre="Module B", specialite=module_referentiel.specialite)
        for module in (module_referentiel, module_b):
            ModuleTypeFormation.objects.create(
                module=module,
                type_formation=type_formation,
                volume_horaire_defaut=20,
            )

        _fixer_dates_periode(formation, datetime.date(2025, 2, 3), datetime.date(2025, 2, 7))
        lieu = {
            "site_noms": ["Site A"],
            "batiment_noms": ["Bat A"],
            "salle_noms": ["Salle 101"],
        }

        service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            creneau_mode="matin",
            **lieu,
        )

        with pytest.raises(ValueError, match="Conflit de salle"):
            service.ajouter_module(
                formation.pk,
                module_b.pk,
                creneau_mode="matin",
                **lieu,
            )

    def test_ajouter_module_site_obligatoire_mais_batiment_salle_optionnels(self, type_formation, module_referentiel):
        """Le site est requis, mais le bâtiment/salle peuvent être laissés vides."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation site obligatoire",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            volume_horaire_defaut=20,
        )

        fm = service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            grade_cible=["__ALL__"],
            site_noms=["Site A"],
            batiment_noms=[],
            salle_noms=[],
        )

        assert fm.site_nom == "Site A"
        assert fm.batiment_nom == ""
        assert fm.salle_nom == ""

    def test_ajouter_module_applique_volume_par_grade_cible(self, type_formation, module_referentiel):
        """Le volume horaire par défaut tient compte du grade ciblé quand il est paramétré."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation avec volume par grade",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            grade_cible="A3",
            volume_horaire_defaut=18,
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            grade_cible="A4",
            volume_horaire_defaut=26,
        )

        fm = service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            grade_cible="A4",
            site_noms=["Site A"],
            batiment_noms=["Bat A"],
            salle_noms=["Salle 101"],
        )

        assert fm.grade_cible == "A4"
        assert fm.volume_horaire == 26

    def test_ajouter_module_grade_cible_utilise_volume_generique_si_absent(self, type_formation, module_referentiel):
        """Si aucun volume spécifique au grade n'existe, le volume générique est utilisé."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation volume générique",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            volume_horaire_defaut=20,
        )

        fm = service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            grade_cible="B",
            site_noms=["Site A"],
            batiment_noms=["Bat A"],
            salle_noms=["Salle 101"],
        )

        assert fm.grade_cible == "B"
        assert fm.volume_horaire == 20

    def test_ajouter_module_utilise_volume_grade_parent(self, type_formation, module_referentiel):
        """Un paramétrage volume sur B doit couvrir un module ciblé B3."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation volume parent",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            grade_cible="B",
            volume_horaire_defaut=24,
        )

        fm = service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            grade_cible="B3",
            site_noms=["Site A"],
            batiment_noms=["Bat A"],
            salle_noms=["Salle 101"],
        )

        assert fm.grade_cible == "B3"
        assert fm.volume_horaire == 24

    def test_ajouter_module_accepte_plusieurs_grades(self, type_formation, module_referentiel):
        """Un module peut cibler plusieurs grades dans le programme pédagogique."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation multi-grades",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            grade_cible="A3",
            volume_horaire_defaut=20,
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            grade_cible="A4",
            volume_horaire_defaut=20,
        )

        fm = service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            grade_cible=["A3", "A4"],
            site_noms=["Site A"],
            batiment_noms=["Bat A"],
            salle_noms=["Salle 101"],
        )

        assert fm.grade_cible == "A3, A4"
        assert fm.volume_horaire == 20

    def test_ajouter_module_plusieurs_grades_volumes_distincts_stocke_null(self, type_formation, module_referentiel):
        """Volumes paramétrage différents par grade : pas de valeur unique stockée sur la ligne."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation volumes distincts",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            grade_cible="A",
            volume_horaire_defaut=20,
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            grade_cible="B",
            volume_horaire_defaut=16,
        )

        fm = service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            grade_cible=["A", "B"],
            site_noms=["Site A"],
            batiment_noms=["Bat A"],
            salle_noms=["Salle 101"],
        )

        assert fm.grade_cible == "A, B"
        assert fm.volume_horaire is None

    def test_ajouter_module_tous_grades(self, type_formation, module_referentiel):
        """Le mode tous grades est stocké en vide et utilise la règle générique."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation tous grades",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            volume_horaire_defaut=22,
        )

        fm = service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            grade_cible=["__ALL__"],
            site_noms=["Site A"],
            batiment_noms=["Bat A"],
            salle_noms=["Salle 101"],
        )

        assert fm.grade_cible == ""
        assert fm.volume_horaire == 22

    def test_ajouter_module_tous_grades_volumes_specifiques_distincts_sans_generique_stocke_null(
        self, type_formation, module_referentiel
    ):
        """Tous grades : seules des règles par grade avec volumes différents → pas de volume unique en base."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation tous grades volumes mixtes",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            grade_cible="A3",
            volume_horaire_defaut=20,
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            grade_cible="A4",
            volume_horaire_defaut=26,
        )

        fm = service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            grade_cible=["__ALL__"],
            site_noms=["Site A"],
            batiment_noms=["Bat A"],
            salle_noms=["Salle 101"],
        )

        assert fm.grade_cible == ""
        assert fm.volume_horaire is None

    def test_ajouter_module_leve_erreur_si_liste_salles_trop_longue(self, type_formation, module_referentiel):
        """Un message métier clair est renvoyé avant erreur SQL si le CSV dépasse la limite."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation limite CSV",
            vague="",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 3, 28),
        )
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            volume_horaire_defaut=20,
        )
        salle_noms = [f"SALLE_{i:03d}" for i in range(90)]

        with pytest.raises(ValueError, match="liste des salles est trop longue"):
            service.ajouter_module(
                formation.pk,
                module_referentiel.pk,
                grade_cible=["__ALL__"],
                site_noms=["SITE A"],
                batiment_noms=["BAT A"],
                salle_noms=salle_noms,
            )

    def test_ajouter_et_modifier_periode(self, type_formation, module_referentiel):
        """Les périodes portent dates et rythme ; les modules héritent des dates."""
        import datetime

        from apps.parametrage.models import ModuleTypeFormation

        service = _service()
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation multi-périodes",
            vague="",
            date_debut=datetime.date(2025, 1, 1),
            date_fin=datetime.date(2025, 12, 31),
            rythme_mensuel="4",
        )
        p2 = service.ajouter_periode(
            formation.pk,
            "Trimestre 2",
            datetime.date(2025, 4, 1),
            datetime.date(2025, 6, 30),
            rythme_mensuel="2",
        )
        assert p2.rythme_mensuel == "2"
        assert formation.periodes.count() == 2

        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=type_formation,
            volume_horaire_defaut=8,
        )
        fm = service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            periode_id=p2.pk,
            site_noms=["Site A"],
        )
        assert fm.date_debut == p2.date_debut
        assert fm.date_fin == p2.date_fin
        assert fm.periode_id == p2.pk

        service.modifier_periode(
            p2.pk,
            formation.pk,
            "T2 modifié",
            datetime.date(2025, 5, 1),
            datetime.date(2025, 5, 31),
            rythme_mensuel="3",
        )
        fm.refresh_from_db()
        assert fm.date_debut == datetime.date(2025, 5, 1)
        assert fm.periode.rythme_mensuel == "3"

    def test_supprimer_periode_vide(self, type_formation):
        import datetime

        service = _service()
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation période vide",
            vague="",
            date_debut=datetime.date(2025, 1, 1),
            date_fin=datetime.date(2025, 12, 31),
        )
        extra = service.ajouter_periode(
            formation.pk,
            "Période 2",
            datetime.date(2025, 6, 1),
            datetime.date(2025, 6, 30),
        )
        service.supprimer_periode(formation.pk, extra.pk)
        assert formation.periodes.count() == 1

    def test_modifier_formation(self, formation):
        """Les champs généraux d'une formation peuvent être mis à jour."""
        import datetime

        from apps.referentiels.models import TypeFormation

        tf2 = TypeFormation.objects.create(code="XYZ", libelle="Type test")
        service = FormationService(FormationRepository(), FormationModuleRepository())
        updated = service.modifier(
            formation_id=formation.pk,
            type_formation_id=tf2.pk,
            intitule="Intitulé modifié",
            vague="",
            date_debut=datetime.date(2025, 2, 1),
            date_fin=datetime.date(2025, 4, 30),
            rythme_mensuel="3",
        )
        assert updated.intitule == "Intitulé modifié"
        assert updated.type_formation_id == tf2.pk
        assert updated.date_debut == datetime.date(2025, 2, 1)
        assert updated.date_fin == datetime.date(2025, 4, 30)
        assert updated.rythme_mensuel == "3"

    def test_import_formateurs_detecte_la_feuille_avec_entetes(self):
        """Les en-têtes peuvent se trouver sur une feuille autre que la première (souvent la couverture)."""
        from io import BytesIO

        import openpyxl

        from apps.formations.models import Formateur

        wb = openpyxl.Workbook()
        ws_cover = wb.active
        ws_cover.title = "Couverture"
        for i in range(30):
            ws_cover.append([f"Texte hors tableau {i}"])
        ws_data = wb.create_sheet("Formateurs")
        ws_data.append(["numero", "nom", "prenom", "email", "telephone", "organisation", "specialites"])
        ws_data.append(
            [
                "+2250102099911",
                "DIALLO",
                "Ibrahim",
                "ib@example.com",
                "+2250102099922",
                "ORG-Z",
                "GENERAL",
            ]
        )
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        service = FormationService(FormationRepository(), FormationModuleRepository())
        report = service.importer_formateurs_depuis_excel(buf)
        assert report.nb_erreurs == 0
        assert report.nb_formateurs_importes >= 1
        f = Formateur.objects.get(numero="+2250102099911")
        assert f.nom == "DIALLO"

    def test_import_formateurs_entetes_apres_plus_de_20_lignes(self):
        """La ligne d'en-têtes peut être au-delà de l'ancienne limite de 20 lignes."""
        from io import BytesIO

        import openpyxl

        from apps.formations.models import Formateur

        wb = openpyxl.Workbook()
        ws = wb.active
        for i in range(35):
            ws.append([f"preambule {i}"])
        ws.append(["numero", "nom", "prenom", "email", "telephone", "organisation", "specialites"])
        ws.append(["+2250102099933", "BA", "Ka", "ba@ex.com", "010203", "O", "GENERAL"])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        service = FormationService(FormationRepository(), FormationModuleRepository())
        report = service.importer_formateurs_depuis_excel(buf)
        assert report.nb_erreurs == 0
        assert Formateur.objects.filter(numero="+2250102099933").exists()

    def test_import_formateurs_colonne_module_titre_sans_specialites(self, specialite_generale):
        """Fichier avec module_titre (sans colonne specialites) : spécialité déduite du référentiel Module."""
        from io import BytesIO

        import openpyxl

        from apps.formations.models import Formateur
        from apps.referentiels.models import Module

        Module.objects.create(
            titre="Module titre import formateurs XYZ",
            specialite=specialite_generale,
        )

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["numero", "nom", "prenom", "email", "telephone", "organisation", "module_titre"])
        ws.append(
            [
                "+2250102099944",
                "TRAORE",
                "Awa",
                "awa.t@example.com",
                "0700000001",
                "ORG",
                "Module titre import formateurs XYZ",
            ]
        )
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        service = FormationService(FormationRepository(), FormationModuleRepository())
        report = service.importer_formateurs_depuis_excel(buf)
        assert report.nb_erreurs == 0
        f = Formateur.objects.get(numero="+2250102099944")
        assert f.specialites.filter(code="GENERAL").exists()

    def test_import_formateurs_module_titre_prefixe_tronque(self, specialite_generale):
        """Titre de module tronqué dans l'Excel : correspondance par préfixe sur le référentiel."""
        from io import BytesIO

        import openpyxl

        from apps.formations.models import Formateur
        from apps.referentiels.models import Module

        Module.objects.create(
            titre="Ethique Publique Et Lutte Contre La Corruption",
            specialite=specialite_generale,
        )

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["numero", "nom", "prenom", "email", "telephone", "organisation", "module_titre"])
        ws.append(
            [
                "+2250102099955",
                "ZORO",
                "Zoe",
                "zoe.z@example.com",
                "0700000002",
                "ORG",
                "Ethique Publique Et Lutte Contre La Corr",
            ]
        )
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        service = FormationService(FormationRepository(), FormationModuleRepository())
        report = service.importer_formateurs_depuis_excel(buf)
        assert report.nb_erreurs == 0
        assert not any(e.startswith("Note :") for e in report.erreurs)
        f = Formateur.objects.get(numero="+2250102099955")
        assert f.specialites.filter(code="GENERAL").exists()

    def test_import_formateurs_module_titre_sans_affectation_groupe(
        self, formation, module_referentiel, parametres
    ):
        """module_titre sert à la spécialité uniquement, sans créer d'affectation groupe."""
        from io import BytesIO

        import openpyxl

        from apps.formations.models import AffectationFormateurGroupe, Formateur, FormationModule
        from apps.groupes.repositories import ConfigGroupeRepository, GroupeRepository, JourCoursRepository
        from apps.groupes.services import GroupeService

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=10,
            site_nom="SITE-T",
        )
        gsvc = GroupeService(
            GroupeRepository(),
            ConfigGroupeRepository(),
            JourCoursRepository(),
        )
        g = gsvc.creer(formation_id=formation.pk, nom="Groupe import formateur", max_auditeurs=25)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["numero", "nom", "prenom", "email", "telephone", "organisation", "module_titre"])
        ws.append(
            [
                "+2250102099977",
                "IMPORT",
                "Attach",
                "attach.import@example.com",
                "0700000003",
                "ORG",
                module_referentiel.titre,
            ]
        )
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        service = FormationService(FormationRepository(), FormationModuleRepository())
        report = service.importer_formateurs_depuis_excel(buf)
        assert report.nb_erreurs == 0
        f = Formateur.objects.get(numero="+2250102099977")
        assert not AffectationFormateurGroupe.objects.filter(
            groupe_id=g.pk,
            module_id=module_referentiel.pk,
            formateur_id=f.pk,
        ).exists()

    def test_import_formateurs_numero_nom_prenom_seuls(self, specialite_generale):
        """Seules les colonnes numero, nom, prenom sont obligatoires ; GENERAL si pas de spécialité."""
        from io import BytesIO

        import openpyxl

        from apps.formations.models import Formateur

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["numero", "nom", "prenom"])
        ws.append(["+2250102099988", "MIN", "TroisColonnes"])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        service = FormationService(FormationRepository(), FormationModuleRepository())
        report = service.importer_formateurs_depuis_excel(buf)
        assert report.nb_erreurs == 0
        f = Formateur.objects.get(numero="+2250102099988")
        assert f.nom == "MIN"
        assert f.prenom == "TroisColonnes"
        assert f.specialites.filter(code="GENERAL").exists()
