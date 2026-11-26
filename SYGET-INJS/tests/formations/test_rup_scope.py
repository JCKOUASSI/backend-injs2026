"""Tests du rôle RUP — périmètre par module référentiel (matière plateforme)."""

import datetime

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.urls import reverse

from apps.formations.models import AffectationFormateurGroupe, Formateur, FormationModule, ResponsableUnitePedagogique
from apps.groupes.models import Groupe
from apps.referentiels.models import Module, Specialite
from apps.seances.models import Seance


@pytest.fixture
def roles(db):
    call_command("seed_roles")


@pytest.fixture
def specialite_ref(db):
    return Specialite.objects.create(code="GEN", libelle="Général")


@pytest.fixture
def module_up(db, specialite_ref):
    return Module.objects.create(titre="Culture Civique", specialite=specialite_ref)


@pytest.fixture
def module_autre(db, specialite_ref):
    return Module.objects.create(titre="Droit", specialite=specialite_ref)


@pytest.fixture
def module_hors_perimetre(db):
    spec = Specialite.objects.create(code="INFO", libelle="Informatique")
    return Module.objects.create(titre="Programmation", specialite=spec)


@pytest.fixture
def rup_user(roles, module_up):
    user = User.objects.create_user("rup_user", "rup@test.ci", "pass")
    user.groups.add(Group.objects.get(name="RUP_EDT"))
    ResponsableUnitePedagogique.objects.create(user=user, module=module_up)
    return user


@pytest.fixture
def formation_avec_modules(type_formation, module_up, module_autre, module_hors_perimetre):
    from apps.formations.repositories import FormationModuleRepository, FormationRepository
    from apps.formations.services import FormationService

    formation = FormationService(FormationRepository(), FormationModuleRepository()).creer(
        type_formation_id=type_formation.pk,
        intitule="Formation RUP",
        vague="V1",
        date_debut=datetime.date(2025, 1, 6),
        date_fin=datetime.date(2025, 3, 28),
    )
    periode = formation.periodes.first()
    for module in (module_up, module_autre, module_hors_perimetre):
        FormationModule.objects.create(
            formation=formation,
            periode=periode,
            module=module,
            volume_horaire=8,
        )
    return formation


@pytest.fixture
def groupe(formation_avec_modules):
    return Groupe.objects.create(formation=formation_avec_modules, nom="A4_GROUPE1", max_auditeurs=25)


@pytest.fixture
def formateur(db, specialite_ref):
    f = Formateur.objects.create(numero="+2250101010101", nom="RUP", prenom="Formateur")
    f.specialites.add(specialite_ref)
    return f


@pytest.mark.django_db
class TestRupScope:
    def test_rup_voit_formation_si_son_module_au_programme(self, rup_user, formation_avec_modules):
        from django.test import Client

        client = Client()
        client.force_login(rup_user)
        resp = client.get(reverse("formations:list"))
        assert resp.status_code == 200
        ids = {f.pk for f in resp.context["formations"]}
        assert formation_avec_modules.pk in ids

    def test_rup_ne_voit_pas_formation_sans_son_module(self, rup_user, type_formation, module_hors_perimetre):
        from apps.formations.repositories import FormationModuleRepository, FormationRepository
        from apps.formations.services import FormationService
        from django.test import Client

        formation = FormationService(FormationRepository(), FormationModuleRepository()).creer(
            type_formation_id=type_formation.pk,
            intitule="Sans module RUP",
            vague="V2",
            date_debut=datetime.date(2025, 4, 1),
            date_fin=datetime.date(2025, 6, 30),
        )
        periode = formation.periodes.first()
        FormationModule.objects.create(
            formation=formation,
            periode=periode,
            module=module_hors_perimetre,
            volume_horaire=4,
        )

        client = Client()
        client.force_login(rup_user)
        resp = client.get(reverse("formations:list"))
        ids = {f.pk for f in resp.context["formations"]}
        assert formation.pk not in ids

    def test_preview_filtre_seances_par_module_rup(
        self, rup_user, formation_avec_modules, groupe, module_up, module_autre, module_hors_perimetre
    ):
        from django.test import Client

        for module in (module_up, module_autre, module_hors_perimetre):
            Seance.objects.create(
                groupe=groupe,
                module=module,
                date=datetime.date(2025, 1, 6),
                heure_debut=datetime.time(8, 0),
                heure_fin=datetime.time(12, 0),
                duree_minutes=240,
            )

        client = Client()
        client.force_login(rup_user)
        resp = client.get(reverse("seances:preview", kwargs={"groupe_pk": groupe.pk}))
        assert resp.status_code == 200
        assert len(resp.context["seances"]) == 1
        assert resp.context["seances"][0].module_id == module_up.pk
        assert resp.context["perimetre_partiel"] is True

    def test_un_seul_rup_par_utilisateur(self, rup_user, module_autre):
        with pytest.raises(Exception):
            ResponsableUnitePedagogique.objects.create(user=rup_user, module=module_autre)


@pytest.mark.django_db
class TestRupAffectations:
    def test_rup_peut_affecter_formateur_par_groupe(
        self, rup_user, formation_avec_modules, groupe, module_up, formateur
    ):
        from django.test import Client

        client = Client()
        client.force_login(rup_user)
        url = reverse(
            "formations:rup_affectation",
            kwargs={"formation_pk": formation_avec_modules.pk, "groupe_pk": groupe.pk, "module_pk": module_up.pk},
        )
        resp = client.post(url, {"formateur_id": formateur.pk})
        assert resp.status_code == 302
        aff = AffectationFormateurGroupe.objects.get(groupe=groupe, module=module_up)
        assert aff.formateur_id == formateur.pk

    def test_rup_peut_modifier_formateur_existant(
        self, rup_user, formation_avec_modules, groupe, module_up, specialite_ref
    ):
        from django.test import Client

        f1 = Formateur.objects.create(numero="+225401", nom="Ancien", prenom="Form")
        f1.specialites.add(specialite_ref)
        f2 = Formateur.objects.create(numero="+225402", nom="Nouveau", prenom="Form")
        f2.specialites.add(specialite_ref)
        AffectationFormateurGroupe.objects.create(groupe=groupe, module=module_up, formateur=f1)

        client = Client()
        client.force_login(rup_user)
        url = reverse(
            "formations:rup_affectation",
            kwargs={"formation_pk": formation_avec_modules.pk, "groupe_pk": groupe.pk, "module_pk": module_up.pk},
        )
        resp = client.post(url, {"formateur_id": f2.pk})
        assert resp.status_code == 302
        aff = AffectationFormateurGroupe.objects.get(groupe=groupe, module=module_up)
        assert aff.formateur_id == f2.pk

    def test_rup_modification_formateur_maj_seances(
        self, rup_user, formation_avec_modules, groupe, module_up, specialite_ref
    ):
        import datetime

        from django.test import Client

        from apps.seances.models import Seance

        f1 = Formateur.objects.create(numero="+225501", nom="Seance", prenom="Old")
        f1.specialites.add(specialite_ref)
        f2 = Formateur.objects.create(numero="+225502", nom="Seance", prenom="New")
        f2.specialites.add(specialite_ref)
        AffectationFormateurGroupe.objects.create(groupe=groupe, module=module_up, formateur=f1)
        Seance.objects.create(
            groupe=groupe,
            module=module_up,
            date=datetime.date(2025, 2, 10),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            formateur_nom=f1.nom,
            formateur_prenom=f1.prenom,
            formateur_numero=f1.numero,
            formateur_referentiel=f1,
        )

        client = Client()
        client.force_login(rup_user)
        url = reverse(
            "formations:rup_affectation",
            kwargs={"formation_pk": formation_avec_modules.pk, "groupe_pk": groupe.pk, "module_pk": module_up.pk},
        )
        client.post(url, {"formateur_id": f2.pk})

        seance = Seance.objects.get(groupe=groupe, module=module_up)
        assert seance.formateur_prenom == "New"
        assert seance.formateur_referentiel_id == f2.pk

    def test_rup_refuse_autre_module(
        self, rup_user, formation_avec_modules, groupe, module_autre, formateur
    ):
        from django.test import Client

        client = Client()
        client.force_login(rup_user)
        url = reverse(
            "formations:rup_affectation",
            kwargs={
                "formation_pk": formation_avec_modules.pk,
                "groupe_pk": groupe.pk,
                "module_pk": module_autre.pk,
            },
        )
        resp = client.post(url, {"formateur_id": formateur.pk})
        assert resp.status_code == 403
        assert not AffectationFormateurGroupe.objects.filter(groupe=groupe, module=module_autre).exists()

    def test_rup_ne_voit_que_formateurs_de_sa_specialite(
        self, rup_user, formation_avec_modules, module_up, specialite_ref, module_hors_perimetre
    ):
        from django.test import Client

        spec_info = module_hors_perimetre.specialite
        formateur_ok = Formateur.objects.create(numero="+225111", nom="OK", prenom="Gen")
        formateur_ok.specialites.add(specialite_ref)
        formateur_ko = Formateur.objects.create(numero="+225222", nom="KO", prenom="Info")
        formateur_ko.specialites.add(spec_info)

        client = Client()
        client.force_login(rup_user)
        resp = client.get(reverse("formations:formateurs_list"))
        numeros = {f.numero for f in resp.context["formateurs"]}
        assert "+225111" in numeros
        assert "+225222" not in numeros
        assert resp.context["filtre_specialite_rup"] is True

    def test_rup_refuse_affectation_formateur_mauvaise_specialite(
        self, rup_user, formation_avec_modules, groupe, module_up, module_hors_perimetre
    ):
        from django.test import Client

        formateur_ko = Formateur.objects.create(numero="+225333", nom="KO", prenom="Affect")
        formateur_ko.specialites.add(module_hors_perimetre.specialite)

        client = Client()
        client.force_login(rup_user)
        url = reverse(
            "formations:rup_affectation",
            kwargs={"formation_pk": formation_avec_modules.pk, "groupe_pk": groupe.pk, "module_pk": module_up.pk},
        )
        resp = client.post(url, {"formateur_id": formateur_ko.pk})
        assert resp.status_code == 302
        assert not AffectationFormateurGroupe.objects.filter(groupe=groupe, module=module_up).exists()

    def test_page_rup_un_seul_module(
        self, rup_user, formation_avec_modules, groupe, module_up
    ):
        from django.test import Client

        client = Client()
        client.force_login(rup_user)
        resp = client.get(reverse("formations:rup_unite", kwargs={"pk": formation_avec_modules.pk}))
        assert resp.status_code == 200
        assert len(resp.context["sections"]) == 1
        assert resp.context["sections"][0]["formation_module"].module.titre == "Culture Civique"
        assert resp.context["module_rup"].titre == "Culture Civique"
