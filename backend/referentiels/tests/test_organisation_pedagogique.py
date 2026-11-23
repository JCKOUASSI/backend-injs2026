"""Organisation pédagogique : vagues, site géorepéré, espaces sportifs typés.

L'import canonique complète les cinq référentiels de la catégorie sans
jamais inventer : les vagues reçoivent code et provenance (leurs
rattachements de campagne restent vides), le site reçoit le géorepérage
validé (le PDF ne donne qu'un exemple divergent), et chaque espace
sportif nommé par l'inventaire est rattaché à son type — les parkings
et esplanades, non sportifs, restent sans type.
"""
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from formations.models import RefBatiment, RefSalle, RefSite, RefVague
from referentiels.models import RefStatutVague, RefTypeEspaceSportif


class ImportOrganisationPedagogiqueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command(
            'importer_referentiels_injs', '--sans-cycles', stdout=StringIO(),
        )

    def test_vagues_codees_et_tracees_sans_rattachement_invente(self):
        vagues = list(RefVague.objects.order_by('ordre'))
        self.assertEqual(
            [v.libelle for v in vagues],
            ['PREMIERE VAGUE', 'DEUXIEME VAGUE', 'TROISIEME VAGUE'],
        )
        for i, vague in enumerate(vagues, 1):
            with self.subTest(libelle=vague.libelle):
                self.assertEqual(vague.code, f'VAGUE_{i}')
                self.assertEqual(vague.ordre, i)
                self.assertTrue(vague.actif)
                self.assertTrue(vague.source_document.strip())
                self.assertEqual(vague.fiabilite, 'OFFICIEL')
                # Campagne par campagne : aucun rattachement anticipé.
                self.assertIsNone(vague.formation_id)
                self.assertIsNone(vague.statut_id)
                self.assertIsNone(vague.periode_debut)
                self.assertIsNone(vague.effectif_prevu)

    def test_statuts_de_vague_cinq_etats_du_cycle(self):
        codes = set(RefStatutVague.objects.values_list('code', flat=True))
        self.assertEqual(
            codes,
            {'PREVISIONNELLE', 'OUVERTE', 'EN_COURS', 'TERMINEE', 'CLOTUREE'},
        )
        ouverte = RefStatutVague.objects.get(code='OUVERTE')
        self.assertTrue(ouverte.est_ouvert)
        # L'état d'usage (actif/inactif/archivé du PDF §2) n'est pas un
        # statut de cycle de vie : il ne doit pas polluer la nomenclature.
        self.assertFalse(codes & {'ACTIF', 'INACTIF', 'ARCHIVE', 'NON_DETERMINE'})

    def test_site_georepere_aux_coordonnees_validees(self):
        site = RefSite.objects.get(nom='INJS Marcory')
        self.assertEqual(site.geofence_latitude, Decimal('5.308300'))
        self.assertEqual(site.geofence_longitude, Decimal('-3.982500'))
        self.assertEqual(site.geofence_rayon_m, 200)
        self.assertTrue(site.source_document.strip())

    def test_batiments_et_salles_complets_hors_inventaire_diem(self):
        self.assertEqual(RefBatiment.objects.count(), 16)
        self.assertEqual(RefSalle.objects.count(), 166)
        for salle in RefSalle.objects.all():
            self.assertTrue(salle.code)
            self.assertTrue(salle.nom)
            self.assertIsNotNone(salle.site_id)
            self.assertIsNotNone(salle.batiment_id)
            self.assertTrue(salle.type_lieu)
            self.assertTrue(salle.source_document.strip())

    def test_espaces_sportifs_nommes_rattaches_a_leur_type(self):
        types = RefSalle.objects.filter(type_espace__isnull=False)
        self.assertEqual(types.count(), 25)
        par_nom = {
            s.nom: s.type_espace.code
            for s in types.select_related('type_espace')
        }
        self.assertEqual(par_nom['Piscine olympique'], 'PISCINE')
        self.assertEqual(par_nom["Bassin d'apprentissage"], 'BASSIN_APPRENTISSAGE')
        self.assertEqual(par_nom['Gymnase 1'], 'GYMNASE')
        self.assertEqual(par_nom['Piste 400 m'], 'PISTE_ATHLETISME')
        self.assertEqual(par_nom['Dojo'], 'DOJO')
        self.assertEqual(par_nom['Salle haltérophilie'], 'SALLE_HALTEROPHILIE')
        # Non sportifs malgré l'étiquette d'inventaire : aucun type déduit.
        for nom in ('Parking enseignants', 'Parking étudiants', 'Esplanade',
                    "Place d'armes", 'Jardin pédagogique'):
            salle = RefSalle.objects.get(nom=nom)
            self.assertIsNone(salle.type_espace_id, nom)
        # Les quatre types du PDF §8 existent même sans salle rattachée.
        self.assertTrue(
            {'SALLE_EXPRESSION', 'SALLE_APA', 'STADE', 'TERRAIN_SABLE'}
            <= set(RefTypeEspaceSportif.objects.values_list('code', flat=True))
        )

    def test_deuxieme_execution_ne_cree_rien(self):
        avant = (
            RefVague.objects.count(), RefSite.objects.count(),
            RefBatiment.objects.count(), RefSalle.objects.count(),
            RefSalle.objects.filter(type_espace__isnull=False).count(),
        )
        call_command(
            'importer_referentiels_injs', '--sans-cycles', stdout=StringIO(),
        )
        self.assertEqual(
            avant,
            (RefVague.objects.count(), RefSite.objects.count(),
             RefBatiment.objects.count(), RefSalle.objects.count(),
             RefSalle.objects.filter(type_espace__isnull=False).count()),
        )
