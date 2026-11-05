"""Complétion experte du référentiel des salles — commande ``completer_salles``.

Garanties vérifiées :
1. le dry-run (défaut) n'écrit rien ;
2. une valeur déjà renseignée n'est jamais écrasée ;
3. le nombre inscrit dans le nom prime (« Amphi 250 places ») ;
4. les règles par famille produisent capacité + équipements + CADRAGE ;
5. les espaces non sportifs ne reçoivent pas de type sportif inventé ;
6. la commande est idempotente.
"""

import io

from django.core.management import call_command
from django.test import TestCase

from formations.models import RefBatiment, RefSalle, RefSite
from referentiels.models import RefTypeEspaceSportif


class CompleterSallesTests(TestCase):
    def setUp(self):
        self.site = RefSite.objects.create(nom='INJS Test')
        self.batiment = RefBatiment.objects.create(site=self.site, nom='Bâtiment Test')
        self.bloc = RefBatiment.objects.create(site=self.site, nom='Bloc ENSEPS')

    def salle(self, nom, type_lieu='SALLE', batiment=None, **champs):
        return RefSalle.objects.create(
            site=self.site, batiment=batiment or self.batiment,
            nom=nom, type_lieu=type_lieu, **champs,
        )

    def lancer(self, *args):
        sortie = io.StringIO()
        call_command('completer_salles', *args, stdout=sortie)
        return sortie.getvalue()

    def test_dry_run_n_ecrit_rien(self):
        salle = self.salle('Salle informatique A', 'INFORMATIQUE')
        self.lancer()
        salle.refresh_from_db()
        self.assertIsNone(salle.capacite)
        self.assertEqual(salle.equipements, '')
        self.assertEqual(salle.fiabilite, 'A_RENSEIGNER')

    def test_valeurs_existantes_jamais_ecrasees(self):
        salle = self.salle('Salle informatique A', 'INFORMATIQUE',
                            capacite=99, equipements='Matériel attesté')
        self.lancer('--appliquer')
        salle.refresh_from_db()
        self.assertEqual(salle.capacite, 99)
        self.assertEqual(salle.equipements, 'Matériel attesté')

    def test_nombre_dans_le_nom_prime(self):
        salle = self.salle('Amphi 250 places', 'AMPHI')
        self.lancer('--appliquer')
        salle.refresh_from_db()
        self.assertEqual(salle.capacite, 250)

    def test_regles_par_famille_et_cadrage(self):
        info = self.salle('Salle informatique A', 'INFORMATIQUE')
        amphi = self.salle('Amphithéâtre ENSEP', 'AMPHI')
        self.lancer('--appliquer')
        info.refresh_from_db()
        amphi.refresh_from_db()
        self.assertEqual(info.capacite, 30)
        self.assertIn('Postes informatiques', info.equipements)
        self.assertEqual(amphi.capacite, 200)
        self.assertEqual(info.fiabilite, 'CADRAGE')
        self.assertEqual(amphi.fiabilite, 'CADRAGE')

    def test_salle_disciplinaire_bloc_enseignement(self):
        salle = self.salle('Salle de sociologie', 'SALLE', batiment=self.bloc)
        self.lancer('--appliquer')
        salle.refresh_from_db()
        self.assertEqual(salle.capacite, 35)

    def test_espace_sportif_type_et_non_sportif_sans_type(self):
        RefTypeEspaceSportif.objects.create(code='DOJO', libelle='Dojo')
        dojo = self.salle('Salle de judo', 'SPORT')
        parking = self.salle('Parking étudiants', 'SPORT')
        self.lancer('--appliquer')
        dojo.refresh_from_db()
        parking.refresh_from_db()
        self.assertEqual(dojo.type_espace.code, 'DOJO')
        self.assertEqual(dojo.capacite, 30)
        self.assertIsNone(parking.type_espace)
        self.assertEqual(parking.capacite, 150)
        self.assertIn('stationnement', parking.equipements)

    def test_idempotence(self):
        self.salle('Salle informatique A', 'INFORMATIQUE')
        self.lancer('--appliquer')
        rapport = self.lancer('--appliquer')
        self.assertIn('Capacités complétées : 0', rapport)
        self.assertIn('Équipements complétés : 0', rapport)
