"""Politique des contraintes souples réglable depuis l'admin Django.

Pourquoi ces tests. Le chantier 2 a livré des règles souples **inactives par
défaut**, activables par un réglage Django — c'est-à-dire par un développeur
qui modifie un fichier et redémarre le service. L'INJS ne peut pas gouverner
ses emplois du temps dans ces conditions. Ces tests vérifient la chaîne
complète : ligne unique en base, validation, écran d'admin réellement ouvert,
priorité des couches, exposition par l'API et effet réel sur le solveur.

Ce qui est explicitement couvert :

1. **Ligne unique** : deux enregistrements ne peuvent pas coexister ;
2. **Validation stricte** : pause incomplète ou inversée, borne nulle, poids
   nul sont refusés avec un message utilisable ;
3. **Priorité** : défauts < réglage Django < ligne de l'admin < paramètre de
   génération — la décision opérationnelle la plus récente gagne, l'appel
   explicite garde le dernier mot ;
4. **Admin accessible** : l'écran s'ouvre, l'auteur est renseigné
   automatiquement, ni ajout d'une seconde ligne ni suppression ne sont
   possibles ;
5. **Effet réel** : une fois activée en base, la génération signale les règles
   souples sans qu'aucun paramètre ne soit passé — et reste non bloquante.
"""

from datetime import time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from edts.moteur import contraintes as C
from edts.models import PolitiqueContraintesSouples


def _politique(**valeurs):
    """Politique valide par défaut, surchargeable champ par champ."""
    base = {'actives': True}
    base.update(valeurs)
    return PolitiqueContraintesSouples(**base)


class ModelePolitiqueTests(TestCase):
    """La ligne elle-même : défauts, unicité, validation, conversion."""

    def test_defauts_inactifs(self):
        ligne = PolitiqueContraintesSouples()
        self.assertFalse(ligne.actives)
        self.assertEqual(ligne.max_heures_consecutives, 4.0)
        self.assertEqual(ligne.max_heures_par_jour, 8.0)
        self.assertEqual(ligne.tolerance_minutes, 15)
        self.assertIsNone(ligne.pause_debut)
        self.assertIsNone(ligne.pause_fin)

    def test_une_seule_ligne_possible(self):
        _politique(motif='Première décision.').save()
        _politique(motif='Deuxième décision.', max_heures_par_jour=9).save()
        self.assertEqual(PolitiqueContraintesSouples.objects.count(), 1)
        self.assertEqual(PolitiqueContraintesSouples.charger().motif,
                         'Deuxième décision.')

    def test_charger_sans_ligne(self):
        self.assertIsNone(PolitiqueContraintesSouples.charger())

    def test_pause_incomplete_refusee(self):
        with self.assertRaises(ValidationError) as ctx:
            _politique(pause_debut=time(12, 15)).full_clean()
        self.assertIn('pause_debut', ctx.exception.message_dict)

    def test_pause_inversee_refusee(self):
        with self.assertRaises(ValidationError) as ctx:
            _politique(pause_debut=time(13, 30),
                       pause_fin=time(12, 15)).full_clean()
        self.assertIn('pause_fin', ctx.exception.message_dict)

    def test_borne_nulle_refusee(self):
        for champ in ('max_heures_consecutives', 'max_heures_par_jour'):
            with self.subTest(champ=champ), self.assertRaises(ValidationError):
                _politique(**{champ: 0}).full_clean()

    def test_poids_nul_refuse(self):
        with self.assertRaises(ValidationError) as ctx:
            _politique(poids_trou=0).full_clean()
        self.assertIn('poids_trou', ctx.exception.message_dict)

    def test_pause_convertie_en_heures_et_minutes(self):
        ligne = _politique(pause_debut=time(12, 15), pause_fin=time(13, 30))
        # Forme interne : minutes depuis minuit (comparaisons du moteur).
        self.assertEqual(ligne.en_politique()['pause_dejeuner'], (735, 810))
        # Forme lisible : ce que l'API et les écrans affichent.
        self.assertEqual(C.pause_lisible((735, 810)), ['12:15', '13:30'])

    def test_pause_absente_reste_none(self):
        self.assertIsNone(_politique().en_politique()['pause_dejeuner'])

    def test_resume_trace_l_auteur(self):
        # « DIRECTION » : le rôle qui décide d'une politique pédagogique.
        auteur = get_user_model().objects.create_user(
            username='direction', password='x', role='DIRECTION')
        ligne = _politique(motif='Journée ramadanesque.')
        ligne.modifie_par = auteur
        ligne.save()
        resume = ligne.resume()
        self.assertEqual(resume['modifie_par'], 'direction')
        self.assertEqual(resume['motif'], 'Journée ramadanesque.')
        self.assertIsNotNone(resume['modifie_le'])


class ResolutionPolitiqueTests(TestCase):
    """Priorité des couches : ce que le moteur applique réellement."""

    def test_sans_ligne_ni_reglage_origine_defaut(self):
        effectif = C.politique_effective()
        self.assertEqual(effectif['origine'], 'defaut')
        self.assertFalse(effectif['politique']['actives'])
        self.assertIsNone(effectif['reglage'])

    def test_reglage_django_seul(self):
        with override_settings(EDTS_CONTRAINTES_SOUPLES={'actives': True}):
            effectif = C.politique_effective()
        self.assertEqual(effectif['origine'], 'reglage_django')
        self.assertTrue(effectif['politique']['actives'])

    def test_ligne_admin_l_emporte_sur_le_reglage_django(self):
        _politique(max_heures_par_jour=6, motif='Décision INJS.').save()
        with override_settings(EDTS_CONTRAINTES_SOUPLES={
                'actives': True, 'max_heures_par_jour': 10}):
            effectif = C.politique_effective()
        self.assertEqual(effectif['origine'], 'base')
        self.assertEqual(effectif['politique']['max_heures_par_jour'], 6)
        self.assertEqual(effectif['reglage']['motif'], 'Décision INJS.')

    def test_parametre_de_generation_garde_le_dernier_mot(self):
        _politique(max_heures_par_jour=6).save()
        effectif = C.politique_effective({'max_heures_par_jour': 3})
        self.assertEqual(effectif['origine'], 'parametre')
        self.assertEqual(effectif['politique']['max_heures_par_jour'], 3)

    def test_valeur_corrompue_en_base_est_refusee(self):
        """Une valeur impossible contournée en SQL ne passe pas en silence."""
        _politique().save()
        PolitiqueContraintesSouples.objects.filter(pk=1).update(
            max_heures_par_jour=-2)
        with self.assertRaises(ValueError):
            C.politique_souples()


class AdminPolitiqueTests(TestCase):
    """L'écran réel : il s'ouvre, il enregistre, il ne se duplique pas."""

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            'admin_politique', 'politique@example.com', 'MotDePasse#2026')
        self.client.force_login(self.admin)

    def _url(self, suffixe=''):
        return f'/admin/edts/politiquecontraintessouples/{suffixe}'

    def test_liste_ouvrable(self):
        self.assertEqual(self.client.get(self._url()).status_code, 200)

    def test_formulaire_d_ajout_ouvrable(self):
        self.assertEqual(self.client.get(self._url('add/')).status_code, 200)

    def test_enregistrement_renseigne_l_auteur_et_force_la_ligne_unique(self):
        reponse = self.client.post(self._url('add/'), {
            'actives': 'on',
            'max_heures_consecutives': '4',
            'max_heures_par_jour': '8',
            'tolerance_minutes': '15',
            'penaliser_trous': 'on',
            'poids_trou': '1',
            'poids_consecutif': '2',
            'poids_surcharge': '3',
            'motif': 'Activation décidée par la direction.',
        })
        self.assertEqual(reponse.status_code, 302, reponse.content[:500])
        ligne = PolitiqueContraintesSouples.charger()
        self.assertEqual(ligne.pk, 1)
        self.assertTrue(ligne.actives)
        self.assertEqual(ligne.modifie_par, self.admin)

    def test_pas_de_seconde_ligne_ni_de_suppression(self):
        _politique().save()
        # L'admin elle-même refuse l'ajout d'une seconde ligne…
        self.assertEqual(self.client.get(self._url('add/')).status_code, 403)
        # …et la suppression (qui effacerait la trace de la décision).
        from django.contrib import admin as django_admin

        from edts.admin import PolitiqueContraintesSouplesAdmin

        instance = PolitiqueContraintesSouplesAdmin(
            PolitiqueContraintesSouples, django_admin.site)
        requete = type('R', (), {'user': self.admin})()
        self.assertFalse(instance.has_add_permission(requete))
        self.assertFalse(instance.has_delete_permission(requete))
        # La fiche existante reste modifiable : c'est tout l'intérêt.
        self.assertTrue(instance.has_change_permission(requete))

    def test_validation_affichee_dans_le_formulaire(self):
        reponse = self.client.post(self._url('add/'), {
            'max_heures_consecutives': '4',
            'max_heures_par_jour': '0',
            'tolerance_minutes': '15',
            'poids_trou': '1',
            'poids_consecutif': '2',
            'poids_surcharge': '3',
        })
        self.assertEqual(reponse.status_code, 200, 'Le formulaire doit rester affiché.')
        self.assertIsNone(PolitiqueContraintesSouples.objects.first())
        self.assertContains(reponse, 'La borne doit être supérieure à 0')


class ApiPolitiqueTests(TestCase):
    """Ce que l'écran d'audit reçoit : la politique ET son origine."""

    def setUp(self):
        from edts.tests.test_lot3_api_lmd import creer_utilisateur
        from rest_framework.test import APIClient

        self.utilisateur = creer_utilisateur('lecteur-politique', 'SECRETARIAT')
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.utilisateur)

    def _souples(self):
        reponse = self.client_api.get('/api/edts/lmd/constraints/')
        self.assertEqual(reponse.status_code, 200)
        return reponse.json()['souples']

    def test_origine_defaut_sans_reglage(self):
        souples = self._souples()
        self.assertEqual(souples['origine'], 'defaut')
        self.assertIsNone(souples['reglage'])
        self.assertFalse(souples['politique']['actives'])
        self.assertIn('Admin Django', souples['activation'])

    def test_ligne_enregistree_exposee_avec_sa_trace(self):
        auteur = get_user_model().objects.create_user(
            username='chef_sec', password='x', role='CHEF_SECRETARIAT')
        ligne = _politique(
            max_heures_par_jour=9, pause_debut=time(12, 15),
            pause_fin=time(13, 30), motif='Pause déjeuner officialisée.')
        ligne.modifie_par = auteur
        ligne.save()

        souples = self._souples()
        self.assertEqual(souples['origine'], 'base')
        self.assertTrue(souples['politique']['actives'])
        self.assertEqual(souples['politique']['max_heures_par_jour'], 9)
        # L'API parle en heures et minutes, jamais en minutes depuis minuit.
        self.assertEqual(souples['politique']['pause_dejeuner'],
                         ['12:15', '13:30'])
        self.assertEqual(souples['reglage']['motif'],
                         'Pause déjeuner officialisée.')
        self.assertEqual(souples['reglage']['modifie_par'], 'chef_sec')


class EffetReelSurLeMoteurTests(TestCase):
    """Activer depuis l'admin doit changer le moteur, sans redéploiement."""

    def setUp(self):
        from edts.tests.test_lot2_moteur import FabriqueLMD
        from scolarite.models import AffectationPedagogique, ECUE

        self.f = FabriqueLMD(self).creer_base()
        self.f.creer_maquette()
        self.groupe = self.f.creer_groupe()
        self.f.creer_salle('Salle A', 'SALLE', 30)
        self.f.creer_creneaux(jours=('LUNDI',), heures=((8, 10), (10, 12)))
        ecue2 = ECUE.objects.create(
            ue=self.f.ue, code='ECUE2', intitule='ECUE test 2', credits=4)
        self.f.creer_affectation(volume=2, groupe=self.groupe)
        AffectationPedagogique.objects.create(
            annee_academique=self.f.annee, ref_formation=self.f.cycle,
            parcours=self.f.parcours, niveau=self.f.niveau,
            semestre=self.f.semestre, ue=self.f.ue, ecue=ecue2,
            groupe=self.groupe, enseignant=self.f.formateur,
            type_enseignement='TD', volume_horaire=2, statut='VALIDEE',
        )

    def _generer(self):
        from edts.moteur import generation as G

        return G.generate_schedule(
            annee_academique_id=self.f.annee.pk,
            ref_formation_id=self.f.cycle.pk,
            parcours_id=self.f.parcours.pk,
            niveau_id=self.f.niveau.pk,
            semestre_id=self.f.semestre.pk,
            groupe_ids=str(self.groupe.pk),
        )

    def test_ligne_inactivee_ne_change_rien(self):
        _politique(actives=False).save()
        resultat = self._generer()
        bilan = resultat.metrics['contraintes_souples']
        self.assertFalse(bilan['active'])

    def test_ligne_activee_pilote_le_moteur_sans_parametre(self):
        _politique(actives=True, max_heures_par_jour=3,
                   max_heures_consecutives=2).save()
        resultat = self._generer()
        bilan = resultat.metrics['contraintes_souples']
        self.assertTrue(bilan['active'])
        self.assertGreaterEqual(
            bilan['trous'] + bilan['series_trop_longues']
            + bilan['journees_surchargees'], 1)
        # Toujours non bloquant : les deux séances sont planifiées.
        self.assertEqual(resultat.status, 'GENERATION_OK')
        self.assertEqual(resultat.non_places, [])
        self.assertEqual(resultat.metrics['seances_placees'], 2)
