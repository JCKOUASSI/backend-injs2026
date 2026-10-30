"""L'outil de mesure de charge doit être rejouable sur la base réelle.

Constat. `benchmark_getinjs` a été écrit pour une base **vierge** : il créait
ses créneaux avec `create()`. Sur la base de développement — qui contient les
24 créneaux du canevas officiel — il s'arrêtait sur une erreur d'unicité. Un
outil de mesure qu'on ne peut pas relancer là où l'on veut mesurer ne mesure
rien : il faut soit une base jetable, soit une correction. C'est la correction
qui est testée ici.

Ce qui est vérifié :

1. la commande s'exécute sur une base qui contient déjà des créneaux et
   **réutilise** ceux qui existent (compte publié, aucun créneau inventé) ;
2. l'option `--souples actif` mesure le régime activé **sans laisser de trace**
   dans la base : le réglage est écrit dans la transaction annulée ;
3. le rapport publié contient le régime, la politique appliquée et le bilan des
   règles souples — sans quoi la mesure ne serait pas interprétable ;
4. les données synthétiques ne sont pas conservées (aucun étudiant réel touché).
"""

import io

from django.core.management import call_command
from django.test import TestCase

from edts.models import CreneauTemplate, PolitiqueContraintesSouples


class BenchmarkRejouableTests(TestCase):
    """La commande s'exécute sur une base déjà pourvue en créneaux."""

    def setUp(self):
        # Base « réaliste » : des créneaux existent déjà (comme en production).
        for jour in ('LUNDI', 'MARDI'):
            for debut, fin in ((8, 10), (10, 12), (14, 16), (16, 18)):
                CreneauTemplate.objects.create(
                    jour=jour, heure_debut=f'{debut:02d}:00',
                    heure_fin=f'{fin:02d}:00',
                )
        self.avant = CreneauTemplate.objects.count()

    def _lancer(self, *options):
        sortie = io.StringIO()
        call_command('benchmark_getinjs', '--etudiants', '100',
                     *options, stdout=sortie, stderr=io.StringIO())
        return sortie.getvalue()

    def test_reutilise_les_creneaux_existants_sans_erreur(self):
        self._lancer()
        # Aucun créneau supprimé ni dupliqué : la commande s'adapte.
        self.assertEqual(CreneauTemplate.objects.count(), self.avant)

    def test_regime_actif_mesure_sans_modifier_la_base(self):
        PolitiqueContraintesSouples.objects.update_or_create(
            pk=1, defaults={'actives': False, 'motif': 'État initial.'})
        sortie = self._lancer('--souples', 'actif')
        self.assertIn('contraintes souples : actives', sortie)
        # Le réglage réel n'a pas bougé : la mesure s'annule avec sa transaction.
        self.assertFalse(PolitiqueContraintesSouples.charger().actives)
        self.assertEqual(PolitiqueContraintesSouples.charger().motif,
                         'État initial.')

    def test_rapport_sans_donnees_synthetiques_conservees(self):
        from scolarite.models import AnneeAcademique

        self._lancer()
        self.assertFalse(
            AnneeAcademique.objects.filter(libelle__startswith='BENCHMARK-').exists(),
            'Le benchmark ne doit rien laisser derrière lui.',
        )
