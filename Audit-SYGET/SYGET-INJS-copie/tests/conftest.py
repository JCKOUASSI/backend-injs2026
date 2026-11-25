import pytest


@pytest.fixture(autouse=True)
def _referentiel_formateur_general_pour_planning(db):
    """
    Au moins un formateur avec la spécialité GENERAL est requis pour générer un planning
    lorsque les modules référentiels ont cette spécialité.
    """
    from apps.formations.models import Formateur
    from apps.referentiels.models import Specialite

    spec = Specialite.objects.get(code="GENERAL")
    f, _ = Formateur.objects.get_or_create(
        numero="+2250999999001",
        defaults={
            "nom": "POOL",
            "prenom": "GENERAL",
            "email": "pool.gen@test.ci",
            "telephone": "01",
            "organisation": "TST",
        },
    )
    if not f.specialites.filter(pk=spec.pk).exists():
        f.specialites.add(spec)


@pytest.fixture
def type_formation(db):
    """Crée ou récupère un TypeFormation FAC (peut exister via seed)."""
    from apps.referentiels.models import TypeFormation

    tf, _ = TypeFormation.objects.get_or_create(
        code="FAC",
        defaults={"libelle": "Formation d'Adaptation à la Carrière"},
    )
    return tf


@pytest.fixture
def type_formation_fab(db):
    """Crée ou récupère un TypeFormation FAB."""
    from apps.referentiels.models import TypeFormation

    tf, _ = TypeFormation.objects.get_or_create(
        code="FAB",
        defaults={"libelle": "Formation d'Adaptation au Budget"},
    )
    return tf


@pytest.fixture
def specialite_generale(db):
    """Spécialité par défaut du référentiel (créée par migration)."""
    from apps.referentiels.models import Specialite

    return Specialite.objects.get(code="GENERAL")


@pytest.fixture
def formateur_general_planning(db):
    """Formateur de pool GENERAL (créé par le fixture autouse)."""
    from apps.formations.models import Formateur

    return Formateur.objects.get(numero="+2250999999001")


@pytest.fixture
def module_referentiel(db, specialite_generale):
    """Crée un Module de référence pour les tests."""
    from apps.referentiels.models import Module

    return Module.objects.create(titre="Culture Civique", specialite=specialite_generale)


@pytest.fixture
def grade(db):
    """Crée un Grade A3 pour les tests."""
    from apps.parametrage.models import Grade

    return Grade.objects.create(libelle="A3", ordre=1)


@pytest.fixture
def vague(db):
    """Crée une Vague pour les tests."""
    from apps.parametrage.models import Vague

    return Vague.objects.create(libelle="Vague 1")


@pytest.fixture
def parametres(db, request):
    """Retourne les paramètres de planification utilisables dans les tests.

    Si la fixture ``formation`` est aussi demandée, retourne ``ParametreFormation``
    (paramètres propres à la formation). Sinon retourne ``ParametreGeneral``.
    """
    from apps.parametrage.models import ParametreFormation, ParametreGeneral, copier_parametres_planification

    generaux = ParametreGeneral.get()
    if "formation" in request.fixturenames:
        formation = request.getfixturevalue("formation")
        params = ParametreFormation.get_for_formation(formation.pk)
        copier_parametres_planification(generaux, params)
        params.save()
        return params
    return generaux


@pytest.fixture
def formation(db, type_formation):
    """Crée une Formation de test."""
    import datetime

    from apps.formations.repositories import FormationModuleRepository, FormationRepository
    from apps.formations.services import FormationService

    service = FormationService(FormationRepository(), FormationModuleRepository())
    return service.creer(
        type_formation_id=type_formation.pk,
        intitule="Formation test",
        vague="Vague 1",
        date_debut=datetime.date(2025, 1, 6),
        date_fin=datetime.date(2025, 3, 28),
    )


def configurer_periode_principale(formation, *, date_debut=None, date_fin=None, rythme_mensuel=None):
    """Met à jour la première période d'une formation (tests planning / modules)."""
    p = formation.periodes.order_by("ordre", "date_debut").first()
    if p is None:
        return None
    fields = []
    if date_debut is not None:
        p.date_debut = date_debut
        fields.append("date_debut")
    if date_fin is not None:
        p.date_fin = date_fin
        fields.append("date_fin")
    if rythme_mensuel is not None:
        p.rythme_mensuel = rythme_mensuel
        fields.append("rythme_mensuel")
    if fields:
        p.save(update_fields=fields)
        from apps.formations.models import FormationModule

        FormationModule.objects.filter(periode_id=p.pk).update(
            date_debut=p.date_debut,
            date_fin=p.date_fin,
        )
    return p


@pytest.fixture
def auditeur(db):
    """Crée un Auditeur de test avec matricule unique."""
    from apps.auditeurs.matricule import generer_matricule
    from apps.auditeurs.models import Auditeur

    return Auditeur.objects.create(
        nom="MARTIN",
        prenom="Jean",
        matricule=generer_matricule("MARTIN", "Jean") + "01",
        genre="M",
        grade="A3",
        categorie="A",
        type_concours="Direct",
        libelle_concours="Concours Direct Catégorie A",
    )


@pytest.fixture
def auditeur2(db):
    """Crée un second Auditeur de test avec matricule unique."""
    from apps.auditeurs.matricule import generer_matricule
    from apps.auditeurs.models import Auditeur

    return Auditeur.objects.create(
        nom="DUPONT",
        prenom="Alice",
        matricule=generer_matricule("DUPONT", "Alice") + "02",
        genre="F",
        grade="A2",
        categorie="A",
    )
