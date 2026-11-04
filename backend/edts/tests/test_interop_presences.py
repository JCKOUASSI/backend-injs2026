"""Tests de préparation à l'interopérabilité Présences (extension GET INJS).

Critères couverts (extension §13) :
- unicité et stabilité de l'identifiant d'une séance (UUID conservé après
  modification ordinaire et après régénération du placement) ;
- rattachement de la séance à son contexte (groupe, salle géolocalisée) ;
- une simulation ou une séance non publiée ne peut pas ouvrir de session
  officielle de présence ; une séance publiée le peut ;
- traçabilité des modifications (historique + événement) ;
- annulation puis reprogrammation reliées, sans ressusciter l'annulée ;
- suppression physique impossible si des pointages existent ;
- étudiants théoriquement attendus depuis le groupe, et instantané figé
  insensible aux évolutions ultérieures des affectations ;
- permissions : lecture authentifiée, écritures réservées aux rôles de
  planification, publication réservée à la validation ;
- le service d'interopérabilité n'importe pas l'application ``presences``
  (aucune dépendance circulaire GET → Présences).
"""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from edts.models import AffectationCreneau, CreneauTemplate, EmploiDuTemps
from edts.models_interop import (
    SalleGeolocalisation,
    SeanceEvenement,
    SeanceHistorique,
    SeanceRegistre,
)
from edts.moteur import interop_presences as svc
from formations.models import Participant, RefFormation, RefSalle, RefSite
from presences.models import Pointage
from scolarite.models import (
    AffectationGroupe,
    AnneeAcademique,
    DossierEtudiant,
    Groupe,
    InscriptionAdministrative,
    Niveau,
    StatutEtudiant,
)

User = get_user_model()


class InteropPresencesBase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='interop_admin', password='x', role=User.Role.ADMIN,
        )
        self.enseignant = User.objects.create_user(
            username='interop_ens', password='x', role='AUDITEUR',
        )
        self.annee = AnneeAcademique.objects.create(
            libelle='2026-2027',
            date_debut=date(2026, 9, 1), date_fin=date(2027, 7, 31),
        )
        self.formation = RefFormation.objects.create(intitule='Éducation et Motricité')
        self.niveau = Niveau.objects.create(code='L1', libelle='Licence 1')
        self.groupe = Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, nom='L1-EM-G1',
        )
        self.creneau = CreneauTemplate.objects.create(
            jour='LUNDI', heure_debut=time(8, 0), heure_fin=time(10, 0),
        )
        self.emploi = EmploiDuTemps.objects.create(
            annee_academique=self.annee, population_type='GROUPE',
            population_id=self.groupe.id, statut='BROUILLON',
        )
        self.affectation = AffectationCreneau.objects.create(
            emploi_du_temps=self.emploi, creneau_template=self.creneau,
            semaine_debut=1, semaine_fin=12, groupe=self.groupe,
            nature='COURS', intitule='CM Anatomie',
        )

    def publier(self, registre):
        for etape in (
            SeanceRegistre.Statut.EN_ATTENTE_VALIDATION,
            SeanceRegistre.Statut.VALIDEE,
            SeanceRegistre.Statut.PUBLIEE,
        ):
            svc.transitionner(registre, etape, acteur=self.admin)
        return registre


class RegistreIdentiteTests(InteropPresencesBase):
    def test_uuid_unique_et_stable(self):
        registre, cree = svc.assurer_registre(self.affectation, acteur=self.admin)
        self.assertTrue(cree)
        self.assertEqual(registre.statut, SeanceRegistre.Statut.BROUILLON)
        uuid_initial = registre.uuid
        autre, cree2 = svc.assurer_registre(self.affectation, acteur=self.admin)
        self.assertFalse(cree2)
        self.assertEqual(autre.uuid, uuid_initial)
        self.assertEqual(SeanceRegistre.objects.count(), 1)

    def test_modification_ordinaire_conserve_identite_et_trace(self):
        registre, _ = svc.assurer_registre(self.affectation, acteur=self.admin)
        self.publier(registre)
        uuid_initial = registre.uuid
        svc.enregistrer_modification(
            registre, acteur=self.admin, motif='Changement de salle',
            champs_modifies=['salle_id'],
        )
        registre.refresh_from_db()
        self.assertEqual(registre.uuid, uuid_initial)
        self.assertEqual(registre.version, 2)
        self.assertEqual(registre.statut, SeanceRegistre.Statut.MODIFIEE)
        self.assertTrue(svc.peut_ouvrir_session_presence(registre))
        self.assertTrue(
            registre.historique.filter(action=SeanceHistorique.Action.MODIFICATION).exists()
        )
        self.assertTrue(
            registre.evenements.filter(type=SeanceEvenement.Type.SEANCE_MODIFIEE).exists()
        )

    def test_regeneration_rattache_le_meme_registre(self):
        registre, _ = svc.assurer_registre(self.affectation, acteur=self.admin)
        uuid_initial = registre.uuid
        affectation_id = self.affectation.id
        # Régénération : la ligne de placement disparaît, le registre survit.
        self.affectation.delete()
        registre.refresh_from_db()
        self.assertIsNone(registre.affectation_id)
        nouvelle = AffectationCreneau.objects.create(
            emploi_du_temps=self.emploi, creneau_template=self.creneau,
            semaine_debut=1, semaine_fin=12, groupe=self.groupe,
            nature='COURS', intitule='CM Anatomie',
        )
        self.assertNotEqual(nouvelle.id, affectation_id)
        rattache, cree = svc.assurer_registre(nouvelle, acteur=self.admin)
        self.assertFalse(cree)
        self.assertEqual(rattache.uuid, uuid_initial)
        self.assertEqual(rattache.affectation_id, nouvelle.id)
        self.assertTrue(
            rattache.historique.filter(action=SeanceHistorique.Action.RATTACHEMENT).exists()
        )


class CycleDeVieTests(InteropPresencesBase):
    def test_seule_une_seance_publiee_ouvre_une_session(self):
        registre, _ = svc.assurer_registre(self.affectation, acteur=self.admin)
        self.assertFalse(svc.peut_ouvrir_session_presence(registre))
        svc.transitionner(registre, SeanceRegistre.Statut.SIMULATION, acteur=self.admin)
        self.assertFalse(svc.peut_ouvrir_session_presence(registre))
        svc.transitionner(registre, SeanceRegistre.Statut.BROUILLON, acteur=self.admin)
        self.publier(registre)
        self.assertTrue(svc.peut_ouvrir_session_presence(registre))
        self.assertTrue(
            registre.evenements.filter(type=SeanceEvenement.Type.SEANCE_PUBLIEE).exists()
        )
        self.assertIsNotNone(registre.publie_le)

    def test_transition_illegale_refusee(self):
        registre, _ = svc.assurer_registre(self.affectation, acteur=self.admin)
        self.publier(registre)
        with self.assertRaises(ValueError):
            svc.transitionner(registre, SeanceRegistre.Statut.BROUILLON, acteur=self.admin)

    def test_annulation_puis_reprogrammation_reliee(self):
        registre, _ = svc.assurer_registre(self.affectation, acteur=self.admin)
        self.publier(registre)
        svc.transitionner(
            registre, SeanceRegistre.Statut.ANNULEE, acteur=self.admin,
            motif='Enseignant indisponible',
        )
        self.assertFalse(svc.peut_ouvrir_session_presence(registre))
        autre_creneau = CreneauTemplate.objects.create(
            jour='MARDI', heure_debut=time(10, 0), heure_fin=time(12, 0),
        )
        nouvelle_affectation = AffectationCreneau.objects.create(
            emploi_du_temps=self.emploi, creneau_template=autre_creneau,
            semaine_debut=1, semaine_fin=12, groupe=self.groupe,
            nature='COURS', intitule='CM Anatomie (reprogrammée)',
        )
        nouveau = svc.reprogrammer(
            registre, nouvelle_affectation, acteur=self.admin, motif='Report au mardi',
        )
        self.assertNotEqual(nouveau.uuid, registre.uuid)
        self.assertEqual(nouveau.seance_origine_id, registre.id)
        registre.refresh_from_db()
        self.assertEqual(registre.statut, SeanceRegistre.Statut.ANNULEE)
        self.assertEqual(registre.motif_annulation, 'Enseignant indisponible')
        evenement = nouveau.evenements.get(type=SeanceEvenement.Type.SEANCE_REPROGRAMMEE)
        self.assertEqual(evenement.charge_utile['seance_annulee_uuid'], str(registre.uuid))

    def test_suppression_interdite_si_pointages(self):
        from django.db import transaction

        Pointage.objects.create(
            seance_edt=self.affectation, timestamp_entree=timezone.now(),
        )
        # Savepoint : la ProtectedError doit pouvoir être absorbée sans
        # empoisonner la transaction du TestCase.
        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                self.affectation.delete()
        self.assertTrue(AffectationCreneau.objects.filter(pk=self.affectation.pk).exists())


class EtudiantsAttendusTests(InteropPresencesBase):
    def _inscrire(self, matricule, nom, dans_groupe=True):
        participant = Participant.objects.create(
            matricule=matricule, nom=nom, prenom='Test', sexe='FEMININ',
        )
        statut = StatutEtudiant.objects.get_or_create(
            code='ACTIF', defaults={'libelle': 'Actif'},
        )[0]
        dossier = DossierEtudiant.objects.create(participant=participant, statut=statut)
        inscription = InscriptionAdministrative.objects.create(
            etudiant=dossier, annee_academique=self.annee,
            ref_formation=self.formation, niveau=self.niveau,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )
        if dans_groupe:
            AffectationGroupe.objects.create(
                inscription=inscription, groupe=self.groupe, active=True,
            )
        return participant

    def test_attendus_depuis_le_groupe_et_instantane_fige(self):
        self._inscrire('INJS26-2001', 'Niamien')
        self._inscrire('INJS26-2002', 'Koffi')
        self._inscrire('INJS26-2003', 'Horsgroupe', dans_groupe=False)

        attendus = svc.etudiants_attendus(self.affectation)
        self.assertEqual(attendus['base'], 'AFFECTATION_GROUPE_ACTIVE')
        self.assertEqual(attendus['effectif'], 2)
        self.assertEqual(
            {e['matricule'] for e in attendus['etudiants']},
            {'INJS26-2001', 'INJS26-2002'},
        )

        registre, _ = svc.assurer_registre(self.affectation, acteur=self.admin)
        instantane = svc.creer_instantane(registre, acteur=self.admin)
        self.assertEqual(instantane.effectif, 2)
        # Les affectations évoluent ensuite : l'instantané reste figé.
        AffectationGroupe.objects.filter(groupe=self.groupe).first().delete()
        self.assertEqual(svc.etudiants_attendus(self.affectation)['effectif'], 1)
        instantane.refresh_from_db()
        self.assertEqual(instantane.effectif, 2)
        self.assertEqual(len(instantane.participants), 2)


class GeolocalisationTests(InteropPresencesBase):
    def test_salle_geolocalisee_dans_le_contexte(self):
        site = RefSite.objects.create(nom='INJS Marcory')
        salle = RefSalle.objects.create(site=site, nom='Amphithéâtre A', capacite=200)
        SalleGeolocalisation.objects.create(
            salle=salle, latitude='5.2959000', longitude='-3.9861000',
            rayon_tolerance_m=120, type_espace=SalleGeolocalisation.TypeEspace.AMPHITHEATRE,
            statut_configuration=SalleGeolocalisation.StatutConfiguration.CONFIGUREE,
        )
        self.affectation.salle = salle
        self.affectation.save(update_fields=['salle'])
        registre, _ = svc.assurer_registre(self.affectation, acteur=self.admin)
        contexte = svc.contexte_seance(registre)
        geo = contexte['placement']['salle']['geolocalisation']
        self.assertTrue(geo['coordonnees_disponibles'])
        self.assertEqual(geo['rayon_tolerance_m'], 120)
        self.assertEqual(geo['statut_configuration'], 'CONFIGUREE')


class ApiInteropTests(InteropPresencesBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.registre, _ = svc.assurer_registre(self.affectation, acteur=self.admin)

    def test_lecture_authentifiee_et_publication(self):
        self.client.force_authenticate(self.enseignant)
        res = self.client.get('/api/edts/interop/seances-publiees/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['count'], 0)

        self.publier(self.registre)
        res = self.client.get('/api/edts/interop/seances-publiees/')
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['seance_uuid'], str(self.registre.uuid))

        res = self.client.get(f'/api/edts/interop/seances/{self.registre.uuid}/')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['peut_ouvrir_session_presence'])
        self.assertEqual(res.data['placement']['annee_academique'], '2026-2027')

    def test_anonyme_refuse(self):
        res = self.client.get('/api/edts/interop/seances-publiees/')
        self.assertIn(res.status_code, (401, 403))

    def test_transition_reservee_aux_roles(self):
        url = f'/api/edts/interop/seances/{self.registre.uuid}/transition/'
        # AUDITEUR : ni planification ni validation.
        self.client.force_authenticate(self.enseignant)
        res = self.client.post(url, {'statut': 'EN_ATTENTE_VALIDATION'}, format='json')
        self.assertEqual(res.status_code, 403)
        # ADMIN peut planifier mais la publication suit le cycle complet.
        self.client.force_authenticate(self.admin)
        res = self.client.post(url, {'statut': 'PUBLIEE'}, format='json')
        self.assertEqual(res.status_code, 409)
        res = self.client.post(url, {'statut': 'EN_ATTENTE_VALIDATION'}, format='json')
        self.assertEqual(res.status_code, 200)

    def test_reconcilier_un_emploi_publie(self):
        self.emploi.statut = 'PUBLIE'
        self.emploi.save(update_fields=['statut'])
        self.client.force_authenticate(self.admin)
        res = self.client.post(f'/api/edts/interop/emplois/{self.emploi.id}/reconcilier/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['publiees'], 1)
        self.registre.refresh_from_db()
        self.assertEqual(self.registre.statut, SeanceRegistre.Statut.PUBLIEE)
        res = self.client.get('/api/edts/interop/evenements/?non_consommes=1')
        self.assertTrue(any(
            e['type'] == 'SEANCE_PUBLIEE' for e in res.data['results']
        ))

    def test_sans_dependance_circulaire_vers_presences(self):
        import edts.moteur.interop_presences as module
        import inspect
        source = inspect.getsource(module)
        self.assertNotIn('from presences', source)
        self.assertNotIn('import presences', source)
