"""GET-INJS — données de référence (écran « Référentiels » du hub).

``GET /api/edts/lmd/referentiels/`` expose les référentiels réels qui
alimentent le moteur de génération : mentions et écoles, filières métier
(parcours) avec état de maquette, maquettes et leurs modules, bâtiments
et salles, enseignants, groupes (avec effectif réel) et vagues. Aucun
compteur n'est inventé : chacun est recalculé depuis sa source.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from edts.models import InscriptionImportee
from edts.tests.test_lot2_moteur import FabriqueLMD
from formations.models import Formateur, RefBatiment, RefSalle, RefSite
from referentiels.models import RefEcole, RefFiliere, RefMention
from scolarite.models import Maquette


def _utilisateur(nom, role):
    from django.contrib.auth import get_user_model

    U = get_user_model()
    user = U.objects.create_user(username=nom, password='x')
    user.role = role
    user.save()
    return user


class ReferentielsTests(TestCase):
    def setUp(self):
        self.f = FabriqueLMD(self).creer_base(perimetre='INJS', filiere='F01')
        self.annee = self.f.annee
        self.client = APIClient()
        self.client.force_authenticate(user=_utilisateur('lecteur-ref', 'ADMIN'))

        self.ecole = RefEcole.objects.create(code='ENSEPS', libelle='ENSEPS')
        self.mention = RefMention.objects.create(
            code='STAPS', libelle='STAPS',
            nom_complet='Sciences et Techniques des APS', ecole=self.ecole,
        )
        self.filiere = RefFiliere.objects.create(
            code='EM', libelle='Éducation et Motricité', ecole=self.ecole,
            mention=self.mention, code_dossier='F01',
        )
        # Le cycle de la fabrique devient un cycle de la filière EM.
        self.f.cycle.filiere = self.filiere
        self.f.cycle.save()

    def referentiels(self, **params):
        params.setdefault('annee', self.annee.pk)
        return self.client.get('/api/edts/lmd/referentiels/', params)

    def test_mentions_et_ecoles(self):
        data = self.referentiels().json()
        self.assertEqual(data['mentions'], [{
            'code': 'STAPS',
            'nom': 'Sciences et Techniques des APS',
            'ecole': 'ENSEPS',
        }])
        self.assertEqual(data['compteurs']['filieres'], 1)

    def test_parcours_maquette_parametrable_puis_publiee(self):
        maquette, _ue, _ecue = self.f.creer_maquette()
        self.f.creer_groupe()

        data = self.referentiels().json()
        self.assertEqual(data['compteurs']['formations'], 1)
        [parcours] = data['parcours']
        self.assertEqual(parcours['code'], 'EM')
        self.assertEqual(parcours['mention'], 'STAPS')
        # Maquette encore en brouillon : rien n'est publié pour le moteur.
        self.assertEqual(parcours['maquette'], 'paramétrable')
        self.assertEqual(parcours['groupes'], 1)
        self.assertEqual(data['compteurs']['modules'], 0)

        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save()
        data = self.referentiels().json()
        self.assertEqual(data['parcours'][0]['maquette'], 'publiée')
        # Le module de la maquette active devient visible du moteur.
        self.assertEqual(data['compteurs']['modules'], 1)
        [ligne] = data['maquettes']
        self.assertEqual(ligne['statut_libelle'], 'Publiée')
        self.assertEqual(ligne['ues'], 1)
        self.assertEqual(ligne['modules'], 1)
        self.assertEqual(ligne['credits'], 10)

    def test_salles_enseignants_groupes_vagues(self):
        site = RefSite.objects.create(nom='INJS Marcory')
        batiment = RefBatiment.objects.create(site=site, nom='Bâtiment A')
        RefSalle.objects.create(
            site=site, batiment=batiment, code='SAL-1', nom='Salle 1',
            capacite=40,
        )
        Formateur.objects.create(
            nom='Kouadio', prenom='Adjoua', specialite='Sport',
        )
        groupe = self.f.creer_groupe()
        InscriptionImportee.objects.create(
            annee_academique=self.annee, matricule='EXT-1', nom='YAO',
            ref_formation=self.f.cycle, niveau=self.f.niveau, groupe=groupe,
        )

        data = self.referentiels().json()
        self.assertEqual(data['compteurs']['salles'], 1)
        # La fabrique a déjà créé un formateur : le compteur les totalise.
        self.assertEqual(data['compteurs']['enseignants'], 2)
        self.assertEqual(data['compteurs']['groupes'], 1)
        # Idem pour le site et le bâtiment créés par la fabrique.
        self.assertEqual(data['infrastructure']['sites'], 2)
        self.assertEqual(data['infrastructure']['batiments'], 2)
        [salle] = data['infrastructure']['salles']
        self.assertEqual(salle['batiment'], 'Bâtiment A')
        self.assertEqual(salle['capacite'], 40)
        enseignant = next(
            e for e in data['enseignants'] if e['nom'] == 'Kouadio')
        self.assertEqual(enseignant['specialite'], 'Sport')
        [ligne_groupe] = data['groupes']
        # Effectif réel : l'inscription importée rattachée au groupe.
        self.assertEqual(ligne_groupe['effectif'], 1)
        self.assertEqual(ligne_groupe['capacite'], 30)

    def test_annee_requise(self):
        reponse = self.client.get('/api/edts/lmd/referentiels/')
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(reponse.json()['motif_echec'], 'ANNEE_ACADEMIQUE_REQUISE')

    def test_anonyme_refuse(self):
        reponse = APIClient().get(
            '/api/edts/lmd/referentiels/', {'annee': self.annee.pk},
        )
        self.assertIn(reponse.status_code, (401, 403))
