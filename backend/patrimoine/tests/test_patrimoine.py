"""Tests smoke du lot L7 — Patrimoine.

Couverture : équipement + mouvement tracé, maintenance, réservation avec
validation obligatoire, garde de dates inversées.
"""
import datetime as dt

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from formations.models import RefSite

from patrimoine import services
from patrimoine.models import Equipement, Maintenance, MouvementPatrimonial, ReservationEspace, Vehicule


def make_salle(nom='Salle 101'):
    site = RefSite.objects.create(nom=f'Site {nom}')
    return site.salles.create(nom=nom)


class TestEquipement(TestCase):
    def test_creation_equipement_avec_mouvement(self):
        salle = make_salle()
        e = Equipement.objects.create(
            espace=salle, nom='Projecteur', num_serie='PRJ-001',
        )
        services.tracer_mouvement(
            MouvementPatrimonial.TypeMouvement.ACQUISITION,
            equipement=e, detail='Achat projecteur',
        )
        self.assertEqual(MouvementPatrimonial.objects.count(), 1)
        self.assertEqual(MouvementPatrimonial.objects.first().equipement, e)

    def test_mouvement_sans_cible_refuse(self):
        with self.assertRaises(ValueError):
            services.tracer_mouvement(MouvementPatrimonial.TypeMouvement.ACQUISITION)


class TestVehicule(TestCase):
    def test_creation_vehicule(self):
        v = Vehicule.objects.create(immatriculation='AB-123-CD')
        self.assertEqual(str(v), 'AB-123-CD')

    def test_immatriculation_unique(self):
        Vehicule.objects.create(immatriculation='AB-999-CD')
        with self.assertRaises(Exception):
            Vehicule.objects.create(immatriculation='AB-999-CD')


class TestMaintenance(TestCase):
    def test_creation_maintenance(self):
        m = Maintenance.objects.create(
            description='Changement climatiseur', date_debut=dt.date(2026, 9, 10),
        )
        self.assertEqual(m.statut, Maintenance.Statut.PLANIFIEE)

    def test_transition_vers_terminee(self):
        m = Maintenance.objects.create(
            description='Réparation', date_debut=dt.date(2026, 9, 10),
        )
        services.transitionner_maintenance(m, Maintenance.Statut.EN_COURS)
        services.transitionner_maintenance(m, Maintenance.Statut.TERMINEE)
        m.refresh_from_db()
        self.assertEqual(m.statut, Maintenance.Statut.TERMINEE)

    def test_dates_inverses_refuse(self):
        m = Maintenance(
            description='X', date_debut=dt.date(2026, 12, 31),
            date_fin=dt.date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError):
            m.full_clean()


class TestReservation(TestCase):
    def test_reservation_validation_obligatoire(self):
        salle = make_salle('Amphi A')
        r = ReservationEspace.objects.create(
            salle=salle, motif='Soutenance',
            date_debut=timezone.make_aware(dt.datetime(2026, 10, 1, 9, 0)),
            date_fin=timezone.make_aware(dt.datetime(2026, 10, 1, 12, 0)),
        )
        self.assertEqual(r.statut, ReservationEspace.Statut.PROVISOIRE)
        services.valider_reservation(r, valide_par=None)
        r.refresh_from_db()
        self.assertEqual(r.statut, ReservationEspace.Statut.VALIDEE)

    def test_reservation_dates_inverses_refuse(self):
        salle = make_salle('Salle B')
        r = ReservationEspace(
            salle=salle, motif='X',
            date_debut=timezone.make_aware(dt.datetime(2026, 10, 1, 12, 0)),
            date_fin=timezone.make_aware(dt.datetime(2026, 10, 1, 9, 0)),
        )
        with self.assertRaises(ValidationError):
            r.full_clean()