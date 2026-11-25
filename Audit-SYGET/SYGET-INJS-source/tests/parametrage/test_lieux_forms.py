"""
Tests des formulaires de lieux (site / bâtiment / salle).
"""

import pytest
from django.core.exceptions import ValidationError

from apps.parametrage.forms import BatimentForm, SalleForm
from apps.parametrage.models import Batiment, Salle, Site


@pytest.mark.django_db
class TestLieuxForms:
    """Vérifie les règles d'intégrité sur les formulaires des lieux."""

    def test_batiment_refuse_site_inactif(self):
        site = Site.objects.create(nom="Site X", actif=False)
        form = BatimentForm(data={"site": site.pk, "nom": "Bat A"})
        assert not form.is_valid()
        assert "site" in form.errors

    def test_batiment_accepte_site_actif(self):
        site = Site.objects.create(nom="Site Y", actif=True)
        form = BatimentForm(data={"site": site.pk, "nom": "Bat B"})
        assert form.is_valid()

    def test_salle_refuse_batiment_inactif(self):
        site = Site.objects.create(nom="Site Z", actif=True)
        bat = Batiment.objects.create(site=site, nom="Bat C", actif=False)
        form = SalleForm(data={"batiment": bat.pk, "nom": "Salle 1"})
        assert not form.is_valid()
        assert "batiment" in form.errors

    def test_salle_refuse_batiment_sur_site_inactif(self):
        site = Site.objects.create(nom="Site W", actif=False)
        bat = Batiment.objects.create(site=site, nom="Bat D", actif=True)
        form = SalleForm(data={"batiment": bat.pk, "nom": "Salle 2"})
        assert not form.is_valid()
        assert "batiment" in form.errors

    def test_salle_accepte_batiment_et_site_actifs(self):
        site = Site.objects.create(nom="Site V", actif=True)
        bat = Batiment.objects.create(site=site, nom="Bat E", actif=True)
        form = SalleForm(data={"batiment": bat.pk, "nom": "Salle 3"})
        assert form.is_valid()
        salle = form.save()
        assert isinstance(salle, Salle)


@pytest.mark.django_db
class TestLieuxActivationContraintes:
    """Vérifie les contraintes de désactivation hiérarchiques."""

    def test_site_ne_peut_pas_etre_desactive_si_batiments_actifs(self):
        site = Site.objects.create(nom="Site Parent", actif=True)
        Batiment.objects.create(site=site, nom="Bat Parent", actif=True)
        site.actif = False
        with pytest.raises(ValidationError):
            site.save()

    def test_batiment_ne_peut_pas_etre_desactive_si_salles_actives(self):
        site = Site.objects.create(nom="Site Parent 2", actif=True)
        batiment = Batiment.objects.create(site=site, nom="Bat Parent 2", actif=True)
        Salle.objects.create(batiment=batiment, nom="Salle Parent", actif=True)
        batiment.actif = False
        with pytest.raises(ValidationError):
            batiment.save()
